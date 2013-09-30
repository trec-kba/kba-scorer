'''
This script generates scores for TREC KBA 2013 SSF, described here:

   http://trec-kba.org/trec-kba-2013.shtml

Direction questions & comments to the TREC KBA forums:
http://groups.google.com/group/trec-kba

'''
## use float division instead of integer division
from __future__ import division

__usage__ = '''
python -m kba.score.ssf submissions trec-kba-ssf-2013-expanded-judgments.json
'''

import os
import sys
import csv
import gzip
import json
import argparse
import traceback
try:
    import matplotlib.pyplot as plt
except ImportError:
    plt = None

from operator import itemgetter
from collections import defaultdict

from kba.scorer._metrics import getMedian, performance_metrics, full_run_metrics, find_max_scores
from kba.scorer._outputs import write_team_summary, write_graph, write_performance_metrics, log

## most basic level: identify documents that substantiate a particular
## slot_type that emerged during the corpus time range (ETR+TTR)
DOCS = 'DOCS'  

## on top of DOCS, also find the substring in that fills the slot
OVERLAPS = 'OVERLAPS' 

## on top of OVERLAPS: correctly coref the different slot fills by
## assigning consistent equiv_ids
FILLS = 'FILLS'  

## on top of FILLS, find earliest date_hour that contains a document
## that substantiates the slot fill, date_hours between the earliest
## known and the earliest found by an algorithm are false negatives.
DATE_HOURS = 'DATE_HOURS'  

MODES = [DOCS, OVERLAPS, FILLS, DATE_HOURS]

def load_annotation(path_to_annotation_file, reject, slot_type_filter=None):
    '''
    Loads the SSF truth data from its JSON format on disk
    
    path_to_annotation_file: string file system path to the JSON annotation file
    
    reject:  callable that returns boolean given a target_id
    '''
    try:
        native_annotation = json.load(open(path_to_annotation_file))
    except Exception, exc:
        sys.exit( 'failed to open %r:\n%s' % (path_to_annotation_file, traceback.format_exc(exc)) )

    for target_id in native_annotation.keys():
        if reject(target_id):
            log('excluding truth data for %s' % target_id)
            native_annotation.pop(target_id)

    ## invert the annotation file to have a stream_id index pointing
    ## to target_ids point to slot_types pointing to slot fills,
    ## instead of the reverse
    annotation = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))

    for target_id, slots in native_annotation.items():
        for slot_type, fills in slots.items():
            if slot_type_filter and slot_type != slot_type_filter:
                log('excluding truth data for %s' % slot_type)
                continue
            elif slot_type in ['SignificantOther', 'Children']:
                log('excluding truth data for %s because not part of official slot inventory.  To score this, use --slot-type' % slot_type)
                continue
            for equiv_id, equiv_class in fills.items():
                for stream_id in equiv_class['stream_ids'].keys():
                    ## one document can give multiple fills for the
                    ## same slot type on the same entity
                    annotation[stream_id][target_id][slot_type][equiv_id] = equiv_class

    ## count number of true things in the annotation set -- for each MODE
    positives = defaultdict(lambda: defaultdict(int))
    for target_id, slots in native_annotation.items():
        for slot_type, fills in slots.items():
            for equiv_id, equiv_class in fills.items():
                ## number of known fills per target_id
                positives[FILLS][target_id] += 1

                ## number of known substantiating documents per target_id
                positives[DOCS][target_id] += len(list(set(equiv_class['stream_ids'].keys())))

                ## number of date_hours with known substantiating docs per target_id
                positives[DATE_HOURS][target_id] += len(list(set(map(itemgetter(0), equiv_class['stream_ids'].values()))))
                ## we only consider one byte range per document, so these are equal:
                positives[OVERLAPS][target_id] = positives[DOCS][target_id]

    return annotation, positives


def score_confusion_matrix_DOCS(run_file_handle, annotation, positives,
                           cutoff_step_size=50, unannotated_is_TN=False, debug=False):
    '''
    read a run submission and generate a confusion matrix (number of
    true/false positives and true/false negatives) for DOCS mode
    evaluation.  Generate a confusion matrix for each cutoff step and
    each mode.
    
    run_file_handle: str, a filesystem link to the run submission 
    annotation: dict, containing the annotation data
    cutoff_step_size: int, increment between cutoffs
    unannotated_is_TN: boolean, true to count unannotated as negatives
    
    returns a confusion matrix dictionary for each target_id 
    '''
    ## Create a dictionary containing the confusion matrix (CM)
    cutoffs = range(0, 999, cutoff_step_size)

    def init_confusion_matrix():
        return dict(TP=0, FP=0, FN=0, TN=0)

    ## confusion matrix is mode-->target_id-->cutoff-->2-by-2 matrix
    CM = {mode: defaultdict(lambda: defaultdict(init_confusion_matrix))
          for mode in MODES}

    ## count the total number of assertions per entity
    num_assertions = {}

    ## keep assertions that are in the annotation set, because this is
    ## much smaller than the entire run submission.  We will pass this
    ## to the four evaluation steps beyond DOCS.
    DOCS_TPs = list()

    ## Iterate through every row of the run
    for onerow in run_file_handle:
        ## Skip Comments         
        if onerow.startswith('#') or len(onerow.strip()) == 0:
            continue

        row = onerow.split()
        assert len(row) == 11, row
        try:
            stream_id = row[2]
            timestamp = int(stream_id.split('-')[0])
            target_id = row[3]
            conf = int(float(row[4]))

            rating = int(row[5])
            contains_mention = int(row[6])
            date_hour = row[7]
            slot_type = row[8]
            equiv_id = row[9]
            start_byte, end_byte = row[10].split('-')
            start_byte = int(start_byte)
            end_byte = int(end_byte)

        except Exception, exc:
            print repr(row)
            sys.exit(traceback.format_exc(exc))

        if target_id not in num_assertions:
            num_assertions[target_id] = {'total': 0,
                                         'is_annotated_TP': 0}

        ## keep track of total number of assertions per entity
        num_assertions[target_id]['total'] += 1
        
        ## all modes start with DOCS, so is_annotated_TP means that
        ## the system has a DOCS-TP above some conf threshold
        is_annotated_TP = False
        if stream_id in annotation:
            if target_id in annotation[stream_id]:
                if slot_type in annotation[stream_id][target_id]:
                    is_annotated_TP = True
                    rec = (stream_id, target_id, conf, rating, contains_mention, date_hour, slot_type, equiv_id, start_byte, end_byte)
                    DOCS_TPs.append( rec )
                    log('TP: %r' % (rec,))

        if is_annotated_TP:
            num_assertions[target_id]['is_annotated_TP'] += 1

        increment_CM(is_annotated_TP, conf, cutoffs, CM, DOCS, target_id, unannotated_is_TN)

    correct_FN(CM, DOCS, positives)

    if debug:
        print 'showing assertion counts:'
        print json.dumps(num_assertions, indent=4, sort_keys=True)

    ## sort by date_hour
    DOCS_TPs.sort(key=itemgetter(5))

    return CM, DOCS_TPs

def increment_CM(is_annotated_TP, conf, cutoffs, CM, mode, target_id, unannotated_is_TN=False):
    '''
    for a given TP with some conf score, update the CM for the given mode
    '''
    ## count T/F N/P for each mode
    if is_annotated_TP:
        for cutoff in cutoffs:                
            if conf > cutoff:
                ## If above the cutoff: DOCS-mode true-positive
                CM[DOCS][target_id][cutoff]['TP'] += 1

    ## In the annotation set and non-useful                       
    elif not is_annotated_TP:
        for cutoff in cutoffs:
            if conf > cutoff:
                ## Above the cutoff: false-positive
                CM[DOCS][target_id][cutoff]['FP'] += 1
            else:
                ## Below the cutoff: true-negative
                CM[DOCS][target_id][cutoff]['TN'] += 1

    ## Not in the annotation set so its a negative (if flag is true)
    elif unannotated_is_TN:
        for cutoff in cutoffs:
            if conf > cutoff:
                ## Above the cutoff: false-positive
                CM[DOCS][target_id][cutoff]['FP'] += 1
            else:
                ## Below the cutoff: true-negative
                CM[DOCS][target_id][cutoff]['TN'] += 1    
    
    return CM

def correct_FN(CM, mode, positives):
    '''
    Correct FN for things in the annotation set that are NOT in the run
    '''
    for target_id in CM[mode]:
        for cutoff in CM[mode][target_id]:
            ## Then subtract the number of TP at each cutoffs 
            ## (since FN+TP==True things in annotation set)
            CM[mode][target_id][cutoff]['FN'] = \
                positives[mode][target_id] - CM[mode][target_id][cutoff]['TP']

    return CM


def score_confusion_matrix_OVERLAP(CM, DOCS_TPs, annotation, positives,
                                cutoff_step_size=50, unannotated_is_TN=False,
                                debug=False):
    '''
    construct OVERLAP_TPs by excluding from DOCS_TPs those assertions
    that do not overlap any string identified by an assessor
    '''
    cutoffs = range(0, 999, cutoff_step_size)

    OVERLAP_TPs = list()

    for rec in DOCS_TPs:
        (stream_id, target_id, conf, rating, contains_mention, 
         date_hour, slot_type, runs_equiv_id, start_byte, end_byte) = rec

        start_byte = int(start_byte)
        end_byte = int(end_byte)

        for true_equiv_id, equiv_class in annotation[stream_id][target_id][slot_type].items():
            offsets = equiv_class['stream_ids'][stream_id][1]
            overlaps = False
            for offset in offsets:
                assert isinstance(offset[0], int)
                assert isinstance(offset[1], int)
                if start_byte <= offset[1] and end_byte >= offset[0]:
                    overlaps = True
                    break
            log('(%d, %d) compared to offsets %r\n' % (start_byte, end_byte, offsets))

            if not overlaps:
                increment_CM(False, conf, cutoffs, CM, OVERLAPS, unannotated_is_TN)
                
            #log('found one!!  system equiv_id (%r) --> assessors equiv_id (%r)'
            #    % (runs_equiv_id, true_equiv_id))
            rec = list(rec)
            rec[7] = (runs_equiv_id, true_equiv_id)
            rec = tuple(rec)
            OVERLAP_TPs.append(rec)

            increment_CM(True, conf, cutoffs, CM, OVERLAPS, unannotated_is_TN)

    correct_FN(CM, OVERLAPS, positives)

    return CM, OVERLAP_TPs


def score_confusion_matrix_FILLS(CM, OVERLAPS_TPs, annotation, positives,
                           unannotated_is_TN=False,
                           cutoff_step_size=50, debug=False):
    '''
    construct FILLS_TPs by excluding from OVERLAPS_TPs those assertions
    that either:

       1) re-use an earlier (run)equiv_id that was not associated with
       the same (truth)equiv_id from the truth set

       1) fail to re-use an earlier (run)equiv_id that _was_
       associated with a (truth)equiv_id from the truth set

    '''
    cutoffs = range(0, 999, cutoff_step_size)

    FILLS_TPs = list()

    runs_to_true = dict()
    true_to_runs = dict()

    for rec in OVERLAPS_TPs:
        (stream_id, target_id, conf, rating, contains_mention, date_hour, 
         slot_type, (runs_equiv_id, true_equiv_id), start_byte, end_byte) = rec

        ## this is a tri-state variable
        FILLS_correct = None

        if runs_equiv_id not in runs_to_true and true_equiv_id not in true_to_runs:
            runs_to_true[runs_equiv_id] = true_equiv_id
            true_to_runs[true_equiv_id] = runs_equiv_id

        else:

            ## check failure mode #1 in __doc__ string
            if runs_equiv_id in runs_to_true:
                ## run has previously asserted this equiv_id
                if true_equiv_id == runs_to_true[runs_equiv_id]:
                    FILLS_correct = True
                else:
                    FILLS_correct = False

            ## check failure mode #2 in __doc__ string
            if true_equiv_id in true_to_runs:
                if runs_equiv_id == true_to_runs[true_equiv_id]:
                    if FILLS_correct is not False:
                        FILLS_correct = True
                else:
                    FILLS_correct = False

        if FILLS_correct in [True, None]:
            FILLS_TPs.append( rec )

        if FILLS_correct is True:
            increment_CM(True, conf, cutoffs, CM, FILLS, target_id, unannotated_is_TN)
        elif FILLS_correct is False:
            increment_CM(False, conf, cutoffs, CM, FILLS, target_id, unannotated_is_TN)

    correct_FN(CM, FILLS, positives)

    return CM, FILLS_TPs


def score_confusion_matrix_DATE_HOURS(CM, FILLS_TPs, annotation, positives,
                                cutoff_step_size=50, unannotated_is_TN=False,
                                debug=False):
    '''
    construct DATE_HOURS_TPs by excluding from FILLS_TPs those
    assertions that happen after the first one
    '''
    cutoffs = range(0, 999, cutoff_step_size)

    ## FILLS_TPs are already in date_hour order, so we only have to
    ## count the first one for each equiv_id
    seen = set()
    DATE_HOURS_TPs = list()

    for rec in FILLS_TPs:
        (stream_id, target_id, conf, rating, contains_mention, 
         date_hour, slot_type, equiv_id, start_byte, end_byte) = rec

        if equiv_id in seen:
            increment_CM(False, conf, cutoffs, CM, DATE_HOURS, target_id, unannotated_is_TN)
            continue

        ## this way of filtering is inadequate -- should be giving
        ## partial credit for finding slot fill late
        seen.add(equiv_id)
        DATE_HOURS_TPs.append(rec)

        increment_CM(True, conf, cutoffs, CM, FILLS, unannotated_is_TN)

        for cutoff in CM[DATE_HOURS][target_id]:
            ## Then subtract the number of TP at each cutoffs 
            ## (since FN+TP==True things in annotation set)
            CM[DATE_HOURS][target_id][cutoff]['FN'] = \
                positives[DATE_HOURS][target_id] - CM[DATE_HOURS][target_id][cutoff]['TP']

    return CM, DATE_HOURS_TPs


def make_description(args, mode):
    ## Output the key performance statistics
    if args.reject_wikipedia and not args.reject_twitter:
        entities = '-twitter-only'
    elif args.reject_twitter and not args.reject_wikipedia:
        entities = '-wikipedia-only'
    else:
        assert not (args.reject_wikipedia and args.reject_twitter), \
            'cannot score with no entities'
        entities = '-all-entities'

    if args.use_micro_averaging:
        avg = '-microavg'
    else:
        avg = '-macroavg'

    if args.slot_type:
        slot_type = '-' + args.slot_type

    else:
        slot_type = '-all'

    description = 'ssf' \
            + '-' + mode \
            + entities \
            + slot_type \
            + avg \
            + '-cutoff-step-size-' \
            + str(args.cutoff_step)

    return description

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, usage=__usage__)
    parser.add_argument(
        'run_dir', 
        help='path to the directory containing run files')
    parser.add_argument('annotation', help='path to the annotation file')
    parser.add_argument(
        '--cutoff-step-size', type=int, default=50, dest = 'cutoff_step_size',
        help='step size used in computing scores tables and plots')
    parser.add_argument(
        '--unannotated-is-true-negative', default=False, action='store_true', dest='unan_is_true',
        help='compute scores using assumption that all unjudged documents are true negatives, i.e. that the system used to feed tasks to assessors in June 2012 had perfect recall.  Default is to not assume this and only consider (stream_id, target_id) pairs that were judged.')
    parser.add_argument(
        '--use-micro-averaging', default=False, action='store_true', dest='use_micro_averaging',
        help='compute scores for each mention and then average regardless of entity.  Default is macro averaging')
    parser.add_argument(
        '--slot-type', default=None,
        help='limit scoring to truth data of only one slot type')
    parser.add_argument(
        '--reject-twitter', default=False, action='store_true', 
        help='exclude twitter entities from the truth data')
    parser.add_argument(
        '--reject-wikipedia', default=False, action='store_true', 
        help='exclude twitter entities from the truth data')
    parser.add_argument(
        '--debug', default=False, action='store_true', dest='debug',
        help='print out debugging diagnostics')
    args = parser.parse_args()

    ## construct reject callable
    def reject(target_id):
        if args.reject_twitter and 'twitter.com' in target_id:
            return True
        if args.reject_wikipedia and 'wikipedia.org' in target_id:
            return True
        return False

    ## Load in the annotation data
    annotation, positives = load_annotation(args.annotation, reject, slot_type_filter=args.slot_type)
    print 'This assumes that all run file names end in .gz'

    ## mode --> team_id --> system_id --> score type
    team_scores = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(dict))))

    for run_file_name in os.listdir(args.run_dir):
        if not run_file_name.endswith('.gz'):
            print 'ignoring: %s' % run_file_name
            continue

        ## Open the run file    
        run_file_path = os.path.join(args.run_dir, run_file_name)
        if run_file_path.endswith('.gz'):
            run_file_handle = gzip.open(run_file_path, 'r')
        else:
            run_file_handle =      open(run_file_path, 'r')

        first_line = run_file_handle.readline()
        assert first_line.startswith('#')
        try:
            filter_run = json.loads(first_line[1:])
        except:
            sys.exit('failed to get JSON out of: %r' % first_line[1:])
        
        ### many CCR runs, including some from organizers have task_id
        ### set to SSF :-(, so we must detect this.
        ## read to first non-comment line
        second_line = None
        while not second_line:
            second_line = run_file_handle.readline()
            if second_line.strip().startswith('#'):
                second_line = None

        if 'NULL' in second_line or filter_run['task_id'] != 'kba-ssf-2013':
            print 'ignoring non-SSF run: %s' % run_file_name
            continue

        ## Open run file again now that we verified it is SSF
        run_file_path = os.path.join(args.run_dir, run_file_name)
        if run_file_path.endswith('.gz'):
            run_file_handle = gzip.open(run_file_path, 'r')
        else:
            run_file_handle =      open(run_file_path, 'r')

        print 'processing: %s' % run_file_name
        print json.dumps(filter_run, indent=4, sort_keys=True)

        ## Generate the confusion matrices for a run
        CM, DOCS_TPs = score_confusion_matrix_DOCS(
            run_file_handle,
            annotation, 
            positives,
            args.cutoff_step_size, args.unan_is_true,
            debug=args.debug)

        CM, OVERLAP_TPs, = score_confusion_matrix_OVERLAP(
            CM, DOCS_TPs, annotation, positives,
            cutoff_step_size=50, debug=args.debug)

        CM, FILLS_TPs, = score_confusion_matrix_FILLS(
            CM, OVERLAP_TPs, annotation, positives,
            cutoff_step_size=50, debug=args.debug)

        CM, DATE_HOURS_TPs, = score_confusion_matrix_DATE_HOURS(
            CM, FILLS_TPs, annotation, positives,
            cutoff_step_size=50, debug=args.debug)

        ## split into team name and create stats file
        team_id, system_id = run_file_name[:-3].split('-')

        log(json.dumps(CM, indent=4, sort_keys=True))

        for mode in MODES:
            
            description = make_description(args, mode)

            ## Generate performance metrics for a run
            Scores = performance_metrics(CM[mode])

            (CM[mode]['average'], Scores['average']) = \
                full_run_metrics(CM[mode], Scores, args.micro_is_true)

            max_scores = find_max_scores(Scores)
            team_scores[mode][team_id][system_id] = max_scores

            ## Print the top F-Score
            log( '   %s: max(avg(F_1)): %.3f' % (mode, max_scores['average']['F'] ))
            log( '   %s: max(F_1(avg(P), avg(R))): %.3f' % (mode, max_scores['average']['F_recomputed'] ))
            log( '   %s: max(avg(SU)):  %.3f' % (mode, max_scores['average']['SU'] ))

            ## Output the key performance statistics
            base_output_filepath = os.path.join(
                args.run_dir, 
                run_file_name + '-' + description)

            output_filepath = base_output_filepath + '.csv'

            write_performance_metrics(output_filepath, CM[mode], Scores)
            print ' wrote metrics table to %s' % output_filepath

            if not plt:
                print ' not generating plot, because could not import matplotlib'
            else:
                ## Output a graph of the key performance statistics
                graph_filepath = base_output_filepath + '.png'
                write_graph(graph_filepath, Scores['average'])
                print ' wrote plot image to %s' % graph_filepath
    
    for mode in MODES:
        description = make_description(args, mode)

        ## When folder is finished running output a high level summary of the scores to overview.csv
        write_team_summary(description, team_scores[mode])

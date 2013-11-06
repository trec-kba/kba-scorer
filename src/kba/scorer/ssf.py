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
import time
import argparse
import traceback
from datetime import datetime
from operator import itemgetter
from collections import defaultdict

from kba.scorer._metrics import compile_and_average_performance_metrics, find_max_scores
from kba.scorer._outputs import write_team_summary, write_graph, write_performance_metrics, log

## most basic level: identify documents that substantiate a particular
## slot_type that emerged during the corpus time range (ETR+TTR)
DOCS = 'DOCS'  

## on top of DOCS, also find the substring in that fills the slot
OVERLAP = 'OVERLAP' 

## on top of OVERLAP: correctly coref the different slot fills by
## assigning consistent equiv_ids
FILL = 'FILL'  

## on top of FILL, find earliest date_hour that contains a document
## that substantiates the slot fill, date_hours between the earliest
## known and the earliest found by an algorithm are false negatives.
DATE_HOUR = 'DATE_HOUR'  

MODES = [DOCS, OVERLAP, FILL, DATE_HOUR]

def load_annotation(path_to_annotation_file, reject, slot_type_filter=None,
                    pooled_only=False,
                    pooled_assertion_keys=None):
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
    # stream_id --> target_id --> slot_types
    annotation = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))

    unofficial_slots = ['SignificantOther', 'Children']

    for target_id, slots in native_annotation.items():
        for slot_type, fills in slots.items():
            if slot_type_filter and slot_type != slot_type_filter:
                log('excluding truth data for %s' % slot_type)
                continue
            elif (slot_type_filter not in unofficial_slots) and slot_type in unofficial_slots:
                log('excluding truth data for %s because not part of official slot inventory.  To score this, use --slot-type' % slot_type)
                continue
            for equiv_id, equiv_class in fills.items():
                for stream_id in equiv_class['stream_ids'].keys():
                    assertion_key = (stream_id, target_id, slot_type) 
                    if pooled_only and assertion_key not in pooled_assertion_keys:
                        log('excluding truth data for %s because not in any run submission' 
                            % (assertion_key, ))
                        continue

                    ## one document can give multiple fills for the
                    ## same slot type on the same entity
                    annotation[stream_id][target_id][slot_type][equiv_id] = equiv_class

    ## count number of true things in the annotation set -- for each MODE
    positives = defaultdict(lambda: defaultdict(int))
    for target_id, slots in native_annotation.items():
        for slot_type, fills in slots.items():
            for equiv_id, equiv_class in fills.items():
                ## number of known substantiating documents per target_id
                positives[DOCS][target_id] += len(list(set(equiv_class['stream_ids'].keys())))

                ## we only consider one byte range per document, so these are equal:
                positives[OVERLAP][target_id] = positives[DOCS][target_id]

                ## these are also equal
                positives[FILL][target_id] = positives[DOCS][target_id]

                ## number of date_hours with known substantiating docs per target_id
                #positives[DATE_HOUR][target_id] += len(list(set(map(itemgetter(0), equiv_class['stream_ids'].values()))))

                ## super strict version of date_hours is that there is
                ## only the first date_hour and only one document for
                ## it
                positives[DATE_HOUR][target_id] += 1


    return annotation, positives

def assertions(run_file_handle):
    '''
    iterate over run_file_handle yielding assertion keys and rows
    
    assertion key = (stream_id, target_id, slot_type)
    '''
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
            assert 0 < conf <= 1000
            row[4] = conf

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

        assertion_key = (stream_id, target_id, slot_type)
        yield assertion_key, row


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

    for stream_id in annotation:
        for target_id in annotation[stream_id]:
            for mode in MODES:
                ## make sure that the confusion matrix has entries for all entities
                if target_id not in CM[mode]:
                    CM[mode][target_id] = dict()
                    for cutoff in cutoffs:
                        CM[mode][target_id][cutoff] = dict(TP=0, FP=0, FN=0, TN=0)

    ## count the total number of assertions per entity
    num_assertions = {}

    ## keep assertions that are in the annotation set, because this is
    ## much smaller than the entire run submission.  We will pass this
    ## to the four evaluation steps beyond DOCS.
    DOCS_TPs = list()

    ## Iterate through every row of the run and construct a
    ## de-duplicated run summary
    run_set = dict()
    for assertion_key, row in assertions(run_file_handle):
        conf = row[4]

        stream_id, target_id, slot_type = assertion_key
        if positives[DOCS].get(target_id, 0) == 0:
            #log('ignoring assertion on entity for which no DOCS positives are known: %s' % target_id)
            continue

        if assertion_key in run_set:
            other_row = run_set[assertion_key]
            if other_row[4] > conf:
                log('ignoring a duplicate row with lower conf: %d > %d'
                    % (other_row[4], conf))
                continue

        #log('got a row: %r' % (row,))
        run_set[assertion_key] = row

    log('considering %d unique DOCS assertions' % len(run_set))
    for row in run_set.values():

        stream_id = row[2]
        timestamp = int(stream_id.split('-')[0])
        target_id = row[3]
        conf = row[4]
        rating = row[5]

        contains_mention = int(row[6])
        date_hour = row[7]
        slot_type = row[8]
        equiv_id = row[9]
        start_byte, end_byte = row[10].split('-')
        start_byte = int(start_byte)
        end_byte = int(end_byte)


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
                    #log('TP: %r' % (rec,))

        if is_annotated_TP:
            num_assertions[target_id]['is_annotated_TP'] += 1

        increment_CM(is_annotated_TP, conf=conf, cutoffs=cutoffs, CM=CM, 
                     mode=DOCS, 
                     target_id=target_id, unannotated_is_TN=unannotated_is_TN)

    correct_FN(CM, DOCS, positives)

    if debug:
        print 'showing assertion counts:'
        print json.dumps(num_assertions, indent=4, sort_keys=True)

    ## sort by date_hour
    DOCS_TPs.sort(key=itemgetter(5))

    return CM, DOCS_TPs

def increment_CM(is_annotated_TP, conf=0, cutoffs=None, CM=None, mode=None, target_id=None, unannotated_is_TN=False):
    '''
    for a given TP with some conf score, update the CM for the given mode
    '''
    assert target_id and isinstance(target_id, str) and target_id.startswith('http'), target_id

    ## count T/F N/P for each mode
    if is_annotated_TP:
        for cutoff in cutoffs:                
            if conf > cutoff:
                CM[mode][target_id][cutoff]['TP'] += 1

    ## In the annotation set and non-useful                       
    elif not is_annotated_TP:
        for cutoff in cutoffs:
            if conf > cutoff:
                ## Above the cutoff: false-positive
                CM[mode][target_id][cutoff]['FP'] += 1
            else:
                ## Below the cutoff: true-negative
                CM[mode][target_id][cutoff]['TN'] += 1

    ## Not in the annotation set so its a negative (if flag is true)
    elif unannotated_is_TN:
        for cutoff in cutoffs:
            if conf > cutoff:
                ## Above the cutoff: false-positive
                CM[mode][target_id][cutoff]['FP'] += 1
            else:
                ## Below the cutoff: true-negative
                CM[mode][target_id][cutoff]['TN'] += 1    
    
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
            assert positives[mode][target_id] >= CM[mode][target_id][cutoff]['TP'], \
                "how did we get more TPs than available positives[mode=%s][target_id=%s] = %d >= %d = CM[mode][target_id][cutoff=%f]['TP']" \
                % (mode, target_id, positives[mode][target_id], CM[mode][target_id][cutoff]['TP'], cutoff)

    return CM


def score_confusion_matrix_OVERLAP(CM, DOCS_TPs, annotation, positives,
                                cutoff_step_size=50, unannotated_is_TN=False,
                                debug=False):
    '''
    construct OVERLAP_TPs by excluding from DOCS_TPs those assertions
    that do not overlap any string identified by an assessor
    '''
    cutoffs = range(0, 999, cutoff_step_size)

    OVERLAP_TPs = dict()

    log('considering %d unique OVERLAP assertions' % len(DOCS_TPs))
    for rec in DOCS_TPs:
        (stream_id, target_id, conf, rating, contains_mention, 
         date_hour, slot_type, runs_equiv_id, start_byte, end_byte) = rec

        if positives[OVERLAP].get(target_id, 0) == 0:
            log('ignoring assertion on entity for which no OVERLAP positives are known: %s' % target_id)
            continue

        start_byte = int(start_byte)
        end_byte = int(end_byte)

        for true_equiv_id, equiv_class in annotation[stream_id][target_id][slot_type].items():
            offsets = equiv_class['stream_ids'][stream_id][1]
            overlaps = False
            for offset in offsets:
                assert isinstance(offset[0], int)
                assert isinstance(offset[1], int)

                ## we could/should be much stricter here, 10x is a big window
                true_len = offset[1] - offset[0]
                runs_len = end_byte - start_byte
                if start_byte <= offset[1] and end_byte >= offset[0] and runs_len < 10 * true_len:
                    overlaps = True
                    break

            #log('(%d, %d) compared to offsets %r\n' % (start_byte, end_byte, offsets))

            if not overlaps:
                increment_CM(False, conf=conf, cutoffs=cutoffs, CM=CM, 
                             mode=OVERLAP, 
                             target_id=target_id, unannotated_is_TN=unannotated_is_TN)

            #log('found one!!  system equiv_id (%r) --> assessors equiv_id (%r)'
            #    % (runs_equiv_id, true_equiv_id))
            rec = list(rec)
            rec[7] = (runs_equiv_id, true_equiv_id)
            rec = tuple(rec)

            assertion_key = (stream_id, target_id, slot_type, start_byte, end_byte)
            if assertion_key in OVERLAP_TPs:
                other_row = OVERLAP_TPs[assertion_key]
                if other_row[4] > conf:
                    log('ignoring a duplicate row with lower conf: %d > %d'
                        % (other_row[4], conf))
                    continue

            OVERLAP_TPs[assertion_key] = rec

            increment_CM(True, conf=conf, cutoffs=cutoffs, CM=CM, 
                         mode=OVERLAP, 
                         target_id=target_id, unannotated_is_TN=unannotated_is_TN)

    correct_FN(CM, OVERLAP, positives)

    if OVERLAP_TPs:
        assert CM[OVERLAP]

    OVERLAP_TPs = OVERLAP_TPs.values()

    return CM, OVERLAP_TPs


def score_confusion_matrix_FILL(CM, OVERLAP_TPs, annotation, positives,
                           unannotated_is_TN=False,
                           cutoff_step_size=50, debug=False):
    '''
    construct FILL_TPs by excluding from OVERLAP_TPs those assertions
    that either:

       1) re-use an earlier (run)equiv_id that was not associated with
       the same (truth)equiv_id from the truth set

       1) fail to re-use an earlier (run)equiv_id that _was_
       associated with a (truth)equiv_id from the truth set

    '''
    cutoffs = range(0, 999, cutoff_step_size)

    FILL_TPs = dict()

    runs_to_true = dict()
    true_to_runs = dict()

    log('considering %d unique FILL assertions' % len(OVERLAP_TPs))
    for rec in OVERLAP_TPs:
        (stream_id, target_id, conf, rating, contains_mention, date_hour, 
         slot_type, (runs_equiv_id, true_equiv_id), start_byte, end_byte) = rec

        if positives[FILL].get(target_id, 0) == 0:
            log('ignoring assertion on entity for which no FILL positives are known: %s' % target_id)
            continue

        ## this is a tri-state variable
        FILL_correct = None

        if runs_equiv_id not in runs_to_true and true_equiv_id not in true_to_runs:
            runs_to_true[runs_equiv_id] = true_equiv_id
            true_to_runs[true_equiv_id] = runs_equiv_id

        else:

            ## check failure mode #1 in __doc__ string
            if runs_equiv_id in runs_to_true:
                ## run has previously asserted this equiv_id
                if true_equiv_id == runs_to_true[runs_equiv_id]:
                    FILL_correct = True
                else:
                    FILL_correct = False

            ## check failure mode #2 in __doc__ string
            if true_equiv_id in true_to_runs:
                if runs_equiv_id == true_to_runs[true_equiv_id]:
                    if FILL_correct is not False:
                        FILL_correct = True
                else:
                    FILL_correct = False

        if FILL_correct in [True, None]:

            assertion_key = (stream_id, target_id, slot_type, true_equiv_id)
            if assertion_key in FILL_TPs:
                other_row = FILL_TPs[assertion_key]
                if other_row[4] > conf:
                    log('ignoring a duplicate row with lower conf: %d > %d'
                        % (other_row[4], conf))
                    continue

            FILL_TPs[assertion_key] = rec

        increment_CM(FILL_correct, conf=conf, cutoffs=cutoffs, CM=CM, mode=FILL, 
                     target_id=target_id, 
                     unannotated_is_TN=unannotated_is_TN)

    correct_FN(CM, FILL, positives)

    FILL_TPs = FILL_TPs.values()

    return CM, FILL_TPs


def score_confusion_matrix_DATE_HOUR(CM, FILL_TPs, annotation, positives,
                                cutoff_step_size=50, unannotated_is_TN=False,
                                debug=False):
    '''
    construct DATE_HOUR_TPs by excluding from FILL_TPs those
    assertions that happen after the first one
    '''
    cutoffs = range(0, 999, cutoff_step_size)

    ## FILL_TPs are already in date_hour order, so we only have to
    ## count the first one for each equiv_id
    seen = set()
    DATE_HOUR_TPs = list()

    log('considering %d unique DATE_HOUR assertions' % len(FILL_TPs))
    for rec in FILL_TPs:
        (stream_id, target_id, conf, rating, contains_mention, 
         date_hour, slot_type, equiv_id, start_byte, end_byte) = rec

        if positives[DATE_HOUR].get(target_id, 0) == 0:
            log('ignoring assertion on entity for which no DATE_HOUR positives are known: %s' % target_id)
            continue

        if equiv_id in seen:
            increment_CM(False, conf=conf, cutoffs=cutoffs, CM=CM, mode=DATE_HOUR, 
                         target_id=target_id, 
                         unannotated_is_TN=unannotated_is_TN)
            continue

        ## this way of filtering is inadequate -- should be giving
        ## partial credit for finding slot fill late
        seen.add(equiv_id)
        DATE_HOUR_TPs.append(rec)

        increment_CM(True, conf=conf, cutoffs=cutoffs, CM=CM, mode=DATE_HOUR, 
                     target_id=target_id, 
                     unannotated_is_TN=unannotated_is_TN)

        for cutoff in CM[DATE_HOUR][target_id]:
            ## Then subtract the number of TP at each cutoffs 
            ## (since FN+TP==True things in annotation set)
            CM[DATE_HOUR][target_id][cutoff]['FN'] = \
                positives[DATE_HOUR][target_id] - CM[DATE_HOUR][target_id][cutoff]['TP']

    log('considering %d DATE_HOUR_TPs' % len(DATE_HOUR_TPs))
    return CM, DATE_HOUR_TPs


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

    if args.slot_type:
        slot_type = '-' + args.slot_type

    else:
        slot_type = '-all-slots'

    if args.pooled_only:
        pooled_only = '-pooled-only'
    else:
        pooled_only = ''

    description = 'ssf' \
            + '-' + mode \
            + pooled_only \
            + entities \
            + slot_type \
            + '-cutoff-step-size-' \
            + str(args.cutoff_step_size)

    return description

def ssf_runs(args):
    '''
    yield file handles for all of the SSF runs
    '''

    log( 'This assumes that all run file names end in .gz' )
    run_count = 0
    for run_file_name in os.listdir(args.run_dir):
        if not run_file_name.endswith('.gz'):
            log( 'ignoring: %s' % run_file_name )
            continue

        if args.run_name_filter and not run_file_name.startswith(args.run_name_filter):
            log( 'ignoring: %s' % run_file_name)
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
            log( 'ignoring non-SSF run: %s' % run_file_name )
            continue

        ## Open run file again now that we verified it is SSF
        run_file_path = os.path.join(args.run_dir, run_file_name)
        if run_file_path.endswith('.gz'):
            run_file_handle = gzip.open(run_file_path, 'r')
        else:
            run_file_handle =      open(run_file_path, 'r')

        log( 'processing: %s' % run_file_name )
        log( json.dumps(filter_run, indent=4, sort_keys=True) )

        yield run_file_name, run_file_handle

        #run_count += 1
        #if run_count > 2:
        #    break

if __name__ == '__main__':
    start_time = time.time()
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
        '--slot-type', default=None,
        help='limit scoring to truth data of only one slot type')
    parser.add_argument(
        '--pooled-only', default=False, action='store_true',
        help='limit scoring to truth data that at least one run found')
    parser.add_argument(
        '--reject-twitter', default=False, action='store_true', 
        help='exclude twitter entities from the truth data')
    parser.add_argument(
        '--reject-wikipedia', default=False, action='store_true', 
        help='exclude twitter entities from the truth data')
    parser.add_argument(
        '--debug', default=False, action='store_true', dest='debug',
        help='print out debugging diagnostics')
    parser.add_argument(
        '--run-name-filter', default=None,
        help='beginning of string of filename to filter runs that get considered')
    args = parser.parse_args()

    ## construct reject callable
    def reject(target_id):
        if args.reject_twitter and 'twitter.com' in target_id:
            return True
        if args.reject_wikipedia and 'wikipedia.org' in target_id:
            return True
        return False

    ## stream_id --> target_id --> slot_type observed in at least one run
    pooled_assertion_keys = set()
    if args.pooled_only:
        for run_file_name, run_file_handle in ssf_runs(args):
            for assertion_key, row in assertions(run_file_handle):
                pooled_assertion_keys.add(assertion_key)

    ## Load in the annotation data
    annotation, positives = load_annotation(
        args.annotation, reject, 
        slot_type_filter=args.slot_type,
        pooled_only = args.pooled_only,
        pooled_assertion_keys = pooled_assertion_keys,
        )

    log('considering the following positives:\n%s' % json.dumps(positives, indent=4, sort_keys=True))
    for mode in MODES:
        log('considering the %d positives for %s' % (sum(positives[mode].values()), mode))
    

    ## mode --> team_id --> system_id --> score type
    team_scores = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(dict))))

    for run_file_name, run_file_handle in ssf_runs(args):

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

        CM, FILL_TPs, = score_confusion_matrix_FILL(
            CM, OVERLAP_TPs, annotation, positives,
            cutoff_step_size=50, debug=args.debug)

        CM, DATE_HOUR_TPs, = score_confusion_matrix_DATE_HOUR(
            CM, FILL_TPs, annotation, positives,
            cutoff_step_size=50, debug=args.debug)

        ## split into team name and create stats file
        team_id, system_id = run_file_name[:-3].split('-')

        ## now we switch from calling it a confusion matrix to calling
        ## it the general statistics matrix:
        stats = CM

        for mode in MODES:
            
            description = make_description(args, mode)

            ## Generate performance metrics for a run
            compile_and_average_performance_metrics(stats[mode])

            max_scores = find_max_scores(stats[mode])

            team_scores[mode][team_id][system_id] = max_scores

            ## Output the key performance statistics
            base_output_filepath = os.path.join(
                args.run_dir, 
                run_file_name + '-' + description)

            output_filepath = base_output_filepath + '.csv'

            write_performance_metrics(output_filepath, stats[mode])

            ## Output a graph of the key performance statistics
            graph_filepath = base_output_filepath + '.png'
            write_graph(graph_filepath, stats[mode])

        log(json.dumps(stats, indent=4, sort_keys=True))

    for mode in MODES:
        description = make_description(args, mode)

        ## When folder is finished running output a high level summary of the scores to overview.csv
        write_team_summary(description, team_scores[mode])

    elapsed = time.time() - start_time
    log('finished after %d seconds at at %r'
        % (elapsed, datetime.utcnow()))

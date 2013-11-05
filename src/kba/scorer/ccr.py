'''
This script generates scores for TREC KBA 2013 CCR, described here:

   http://trec-kba.org/trec-kba-2013.shtml

Direction questions & comments to the TREC KBA forums:
http://groups.google.com/group/trec-kba

'''
## use float division instead of integer division
from __future__ import division

__usage__ = '''
python -m kba.score.ccr submissions trec-kba-ccr-judgments-2013-07-08.before-and-after-cutoff.filter-run.txt
'''

END_OF_FEB_2012 = 1330559999

import os
import sys
import csv
import gzip
import json
import time
import argparse
from datetime import datetime
from collections import defaultdict

from kba.scorer._metrics import compile_and_average_performance_metrics, find_max_scores
from kba.scorer._outputs import write_team_summary, write_graph, write_performance_metrics, log

def build_confusion_matrix(path_to_run_file, annotation, cutoff_step, unannotated_is_TN, include_training, debug, thresh=2, require_positives=False):
    '''
    This function generates the confusion matrix (number of true/false positives
    and true/false negatives.  
    
    path_to_run_file: str, a filesystem link to the run submission 
    annotation: dict, containing the annotation data
    cutoff_step: int, increment between cutoffs
    unannotated_is_TN: boolean, true to count unannotated as negatives
    include_training: boolean, true to include training documents
    
    returns a confusion matrix dictionary for each target_id 
    '''
    
    ## Open the run file    
    if path_to_run_file.endswith('.gz'):
        run_file = gzip.open(path_to_run_file, 'r')
    else:
        run_file = open(path_to_run_file, 'r')
        
    ## Create a dictionary containing the confusion matrix (CM)
    cutoffs = range(0, 999, cutoff_step)
    CM = dict()

    ## count the total number of assertions per entity
    num_assertions = {}

    num_positives = defaultdict(int)
    for (stream_id, target_id), is_positive in annotation.items():
        if is_positive:
            num_positives[target_id] += 1

    ## Iterate through every row of the run and construct a
    ## de-duplicated run summary
    run_set = dict()
    for onerow in run_file:
        ## Skip Comments         
        if onerow.startswith('#') or len(onerow.strip()) == 0:
            continue

        row = onerow.split()
        stream_id = row[2]
        timestamp = int(stream_id.split('-')[0])
        target_id = row[3]
        conf = int(float(row[4]))
        assert 0 < conf <= 1000
        row[4] = conf

        rating = int(row[5])
        assert -1 <= rating <= 2
        row[5] = rating

        #log('ratings:  %r <?> %r' % (rating, thresh))
        if rating < thresh:
            log('ignoring assertion below the rating threshold: %r < %r' % (rating, thresh))
            continue

        if require_positives and num_positives.get(target_id, 0) == 0:
            log('ignoring assertion on entity for which no CCR positives are known: %s' % target_id)
            continue

        assertion_key = (stream_id, target_id)
        if assertion_key in run_set:
            other_row = run_set[assertion_key]
            if other_row[4] > conf:
                log('ignoring a duplicate row with lower conf: %d > %d'
                    % (other_row[4], conf))
                continue

            if other_row[4] == conf:
                ## compare rating level
                if other_row[5] != rating:
                    log('same conf, different rating:\n%r\n%r\ntaking higher rating' % (row, other_row))
                    ## accept higher rating
                    if other_row[5] > rating:
                        continue

        #log('got a row: %r' % (row,))
        run_set[assertion_key] = row

    log('considering %d assertions' % len(run_set))
    run_set = run_set.values()
    while run_set:
        row = run_set.pop()

        stream_id = row[2]
        timestamp = int(stream_id.split('-')[0])
        target_id = row[3]
        conf = row[4]
        rating = row[5]

        if target_id not in num_assertions:
            num_assertions[target_id] = {'total': 0,
                                       'in_TTR': 0,
                                       'in_ETR': 0,
                                       'in_annotation_set': 0}

        ## keep track of total number of assertions per entity
        num_assertions[target_id]['total'] += 1
        if timestamp <= END_OF_FEB_2012:
            num_assertions[target_id]['in_TTR'] += 1
        else:
            num_assertions[target_id]['in_ETR'] += 1

        ## If the entity has not been seen yet create a confusion matrix for it
        if not target_id in CM:
            CM[target_id] = dict()
            for cutoff in cutoffs:
                CM[target_id][cutoff] = dict(TP=0, FP=0, FN=0, TN=0)     

        if (not include_training) and (timestamp <= END_OF_FEB_2012):
            continue   
        
        in_annotation_set = (stream_id, target_id) in annotation

        if in_annotation_set:
            num_assertions[target_id]['in_annotation_set'] += 1

        
        ## In the annotation set and useful
        if in_annotation_set and annotation[(stream_id, target_id)]:            
            for cutoff in cutoffs:                
                if conf > cutoff:
                    ## If above the cutoff: true-positive
                    CM[target_id][cutoff]['TP'] += 1                    
                   
        ## In the annotation set and non-useful                       
        elif in_annotation_set and not annotation[(stream_id, target_id)]:
            for cutoff in cutoffs:
                if conf > cutoff:
                    ## Above the cutoff: false-positive
                    CM[target_id][cutoff]['FP'] += 1
                else:
                    ## Below the cutoff: true-negative
                    CM[target_id][cutoff]['TN'] += 1            
        ## Not in the annotation set so its a negative (if flag is true)
        elif unannotated_is_TN:
            for cutoff in cutoffs:
                if conf > cutoff:
                    ## Above the cutoff: false-positive
                    CM[target_id][cutoff]['FP'] += 1
                else:
                    ## Below the cutoff: true-negative
                    CM[target_id][cutoff]['TN'] += 1    
    
    ## Correct FN for things in the annotation set that are NOT in the run
    ## First, calculate number of true things in the annotation set
    annotation_positives = defaultdict(int)
    for stream_id, target_id in annotation:
        timestamp = int(stream_id.split('-')[0])

        if (not include_training) and (timestamp <= END_OF_FEB_2012):
            continue 

        annotation_positives[target_id] += int(annotation[(stream_id,target_id)])
        
    for target_id in CM:
        for cutoff in CM[target_id]:
            ## Then subtract the number of TP at each cutoffs 
            ## (since FN+TP==True things in annotation set)
            #log('annotation_positives[%s] = %d' % (target_id, annotation_positives[target_id]))
            #log('CN[%s][cutoff=%d] = %r' % (target_id, cutoff, CM[target_id][cutoff]))

            CM[target_id][cutoff]['FN'] = annotation_positives[target_id] - CM[target_id][cutoff]['TP']

            #log('CN[%s][cutoff=%d] = %r' % (target_id, cutoff, CM[target_id][cutoff]))
            assert annotation_positives[target_id] >= CM[target_id][cutoff]['TP'], \
                "how did we get more TPs than available annotation_positives[target_id=%s] = %d >= %d = CM[target_id][cutoff=%f]['TP']" \
                % (target_id, annotation_positives[target_id], CM[target_id][cutoff]['TP'], cutoff)

    log( 'showing assertion counts:' )
    log( json.dumps(num_assertions, indent=4, sort_keys=True) )

    return CM
    
def load_annotation(path_to_annotation_file, thresh, min_len_clean_visible, reject, require_positives=False, any_up=False):
    '''
    Loads the annotation file into a dict
    
    path_to_annotation_file: string filesystem path to the annotation file
    include_useful: true to include docs marked useful and vital

    :param min_len_clean_visible: minimum length of the clean_visible,
    which is in the 12 column of the expanded truth data file

    :param reject:  callable that returns boolean given a target_id

    :param require_positives: if set to True, reject any target entity
    for which no true positives exist.
    '''
    assert -1 <= thresh <= 2, thresh

    annotation_file = csv.reader(open(path_to_annotation_file, 'r'), delimiter='\t')

    annotation = dict()
    for row in annotation_file:
       ## Skip comments
       if row[0][0] == "#":
           continue 
       
       stream_id = row[2]
       target_id = row[3]
       rating = int(row[5])
       assert -1 <= rating <=2, rating

       if len(row) == 12:
           ## only the later versions of the truth data carried this
           ## twelve column for excluding documents with insufficient
           ## clean_visible to be judged.  We use a default cutoff of
           ## 100 bytes which means removing these counts below:
           #              (stream_id, target_id) pairs:  34921 above, and 15767 below 100 bytes of clean_visible
           # (assessor_id, stream_id, target_id) pairs:  47446 above, and 19948 below 100 bytes of clean_visible
           len_clean_visible = int(row[11])
           if len_clean_visible < min_len_clean_visible:
               log('excluding stream_id=%s for len(clean_visible)=%d' % (stream_id, len_clean_visible))
               continue

       if reject(target_id):
           log('excluding truth data for %s' % target_id)
           continue

       ## Add the stream_id and target_id to a hashed dictionary
       ## 0 means that its not vital 1 means that it is vital
              
       if (stream_id, target_id) in annotation:
           ## if rating is below threshold, then some assessor viewed
           ## it as not good enough, so be conservative and downgrade
           if not any_up and rating < thresh:
               ## default any_up=False means that if *any* assessor
               ## voted *against* the assertion, then *exclude* it
               annotation[(stream_id, target_id)] = False

           elif any_up and rating >= thresh:
               ## any_up means that if *any* assessor voted *for* the
               ## assertion, then *include* it
               annotation[(stream_id, target_id)] = True
       else:
           ## store bool values in the annotation index
           annotation[(stream_id, target_id)] = rating >= thresh 

    has_true = set()
    for (stream_id, target_id), is_true in annotation.items():
        if is_true:
            has_true.add(target_id)

    if require_positives:
        for stream_id, target_id in annotation.keys():
            if target_id not in has_true:
                log('rejecting %s for lack of any true positives -- because require_positives=True' % target_id)
                annotation.pop( (stream_id, target_id) )

    log('%d target_ids have at least one true positive' % len(has_true))

    num_true = sum(map(int, annotation.values()))
    log('loaded annotation to create a dict of %d (stream_id, target_id) pairs with %d True' % (len(annotation), num_true))
    if num_true == 0:
        sys.exit('found no true positives given the filters')
    return annotation

def make_description(args):
    ## Output the key performance statistics
    if args.reject_wikipedia and not args.reject_twitter:
        entities = '-twitter-only'
    elif args.reject_twitter and not args.reject_wikipedia:
        entities = '-wikipedia-only'
    elif args.group:
        entities = '-' + args.group + '-only'
    else:
        assert not (args.reject_wikipedia and args.reject_twitter), \
            'cannot score with no entities'
        entities = '-all-entities'

    rating_types = '-vital'
    if args.include_useful:
        rating_types += '+useful'
    elif args.include_neutral:
        rating_types += '+neutral'

    if args.require_positives:
        req_pos = '-require-positives'
    else:
        req_pos = ''

    if args.any_up:
        any_up = '-any-up'
    else:
        any_up = ''

    description = 'ccr' \
            + entities \
            + rating_types \
            + req_pos \
            + any_up \
            + '-cutoff-step-size-' \
            + str(args.cutoff_step)

    return description

def process_run(args, run_file_name, annotation, description, thresh):
    '''
    compute scores and generate output files for a single run
    
    :returns dict: max_scores for this one run
    '''
    ## Generate confusion matrices from a run for each target_id
    ## and for each step of the confidence cutoff
    stats = build_confusion_matrix(
        os.path.join(args.run_dir, run_file_name) + '.gz',
        annotation, args.cutoff_step, args.unan_is_true, args.include_training,
        thresh=thresh,
        require_positives=args.require_positives,
        debug=args.debug)

    compile_and_average_performance_metrics(stats)

    max_scores = find_max_scores(stats)

    log(json.dumps(stats, indent=4, sort_keys=True))

    base_output_filepath = os.path.join(
        args.run_dir, 
        run_file_name + '-' + description)

    output_filepath = base_output_filepath + '.csv'
    write_performance_metrics(output_filepath, stats)

    ## Output a graph of the key performance statistics
    graph_filepath = base_output_filepath + '.png'
    write_graph(graph_filepath, stats)

    return max_scores


def score_all_runs(args, description, reject):
    '''
    score all the runs in the specified runs dir using the various
    filters and configuration settings

    :param description: string used for file names
    :param reject: callable to rejects truth data
    '''
    if args.include_neutral:
        thresh = 0
    elif args.include_useful:
        thresh = 1
    else:
        thresh = 2

    ## Load in the annotation data
    annotation = load_annotation(args.annotation, thresh,
                                 args.min_len_clean_visible, reject,
                                 require_positives=args.require_positives
                                 )
    log( 'This assumes that all run file names end in .gz' )

    #import gc
    #from guppy import hpy
    #hp = hpy()
    
    run_count = 0
    team_scores = defaultdict(lambda: defaultdict(dict))
    for run_file in os.listdir(args.run_dir):
        if not run_file.endswith('.gz'):
            continue
        
        if args.run_name_filter and not run_file.startswith(args.run_name_filter):
            continue

        ## take the name without the .gz
        run_file_name = '.'.join(run_file.split('.')[:-1])
        log( 'processing: %s.gz' % run_file_name )
        
        max_scores = process_run(args, run_file_name, annotation, description, thresh)

        ## split into team name and create stats file
        team_id, system_id = run_file_name.split('-')
        team_scores[team_id][system_id] = max_scores

        #gc.collect()
        #log(str(hp.heap()))

        run_count += 1
        #if run_count > 2:
        #    break

    ## When folder is finished running output a high level summary of the scores to overview.csv
    write_team_summary(description, team_scores)

if __name__ == '__main__':
    start_time = time.time()
    parser = argparse.ArgumentParser(description=__doc__, usage=__usage__)
    parser.add_argument(
        'run_dir', 
        help='path to the directory containing run files')
    parser.add_argument('annotation', help='path to the annotation file')
    parser.add_argument(
        '--min-len-clean-visible', type=int, default=100, 
        help='minimum length of clean_visible content for a stream_id to be included in truth data')
    parser.add_argument(
        '--require-positives', default=False, action='store_true',
        help='reject any target_id that has no true positive examples in the truth data')
    parser.add_argument(
        '--cutoff-step', type=int, default=50, dest = 'cutoff_step',
        help='step size used in computing scores tables and plots')
    parser.add_argument(
        '--unannotated-is-true-negative', default=False, action='store_true', dest='unan_is_true',
        help='compute scores using assumption that all unjudged documents are true negatives, i.e. that the system used to feed tasks to assessors in June 2012 had perfect recall.  Default is to not assume this and only consider (stream_id, target_id) pairs that were judged.')
    parser.add_argument(
        '--include-useful', default=False, action='store_true', dest='include_useful',
        help='in addition to documents rated vital, also include those rated useful')
    parser.add_argument(
        '--include-neutral', default=False, action='store_true', dest='include_neutral',
        help='in addition to documents rated vital, and useful also include those rated neutral')
    parser.add_argument(
        '--include-training', default=False, action='store_true', dest='include_training',
        help='includes documents from before the ETR period')
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
        '--any-up', default=False, action='store_true', 
        help='When identifying positive assertions in the training data, if *any* assessor voted *against* a (stream_id, target_id), then it is *removed* from the truth set by default.  If this flag is set, then the behavior is reversed:  if *any* assessor voted *for* an assertion, then it is *included*.')
    parser.add_argument(
        '--group', default=None,
        help='limit entities to this group')
    parser.add_argument(
        '--entity-type', default=None,
        help='limit entities to this entity-type')
    parser.add_argument(
        '--topics-path', default=None,
        help='path to file containing JSON structure of query topics')
    parser.add_argument(
        '--run-name-filter', default=None,
        help='beginning of string of filename to filter runs that get considered')
    args = parser.parse_args()

    accepted_target_ids = set()
    if args.group or args.entity_type:
        if not args.topics_path:
            sys.exit('must specify --topics-path to use --group')
        targets = json.load(open(args.topics_path))['targets']
        for targ in targets:
            if targ['group'] == args.group or targ['entity_type'] == args.entity_type:
                accepted_target_ids.add(targ['target_id'])
    
    description = make_description(args)

    ## construct reject callable
    def reject(target_id):
        if args.reject_twitter and 'twitter.com' in target_id:
            return True
        if args.reject_wikipedia and 'wikipedia.org' in target_id:
            return True
        if args.group or args.entity_type:
            if target_id not in accepted_target_ids:
                return True  ## i.e. reject it
        return False

    score_all_runs(args, description, reject)

    elapsed = time.time() - start_time
    log('finished after %d seconds at at %r'
        % (elapsed, datetime.utcnow()))

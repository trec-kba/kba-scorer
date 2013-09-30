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
import argparse
try:
    import matplotlib.pyplot as plt
except ImportError:
    plt = None

from collections import defaultdict

from kba.scorer._metrics import getMedian, performance_metrics, full_run_metrics, find_max_scores
from kba.scorer._outputs import write_team_summary, write_graph, write_performance_metrics, log

def score_confusion_matrix(path_to_run_file, annotation, cutoff_step, unannotated_is_TN, include_training, debug):
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

    ## Iterate through every row of the run
    for onerow in run_file:
        ## Skip Comments         
        if onerow.startswith('#') or len(onerow.strip()) == 0:
            continue

        row = onerow.split()
        stream_id = row[2]
        timestamp = int(stream_id.split('-')[0])
        target_id = row[3]
        score = int(float(row[4]))

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

        ## If the entity has been seen yet create a confusion matrix for it
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
                if score > cutoff:
                    ## If above the cutoff: true-positive
                    CM[target_id][cutoff]['TP'] += 1                    
                   
        ## In the annotation set and non-useful                       
        elif in_annotation_set and not annotation[(stream_id, target_id)]:
            for cutoff in cutoffs:
                if score > cutoff:
                    ## Above the cutoff: false-positive
                    CM[target_id][cutoff]['FP'] += 1
                else:
                    ## Below the cutoff: true-negative
                    CM[target_id][cutoff]['TN'] += 1            
        ## Not in the annotation set so its a negative (if flag is true)
        elif unannotated_is_TN:
            for cutoff in cutoffs:
                if score > cutoff:
                    ## Above the cutoff: false-positive
                    CM[target_id][cutoff]['FP'] += 1
                else:
                    ## Below the cutoff: true-negative
                    CM[target_id][cutoff]['TN'] += 1    
    
    ## Correct FN for things in the annotation set that are NOT in the run
    ## First, calculate number of true things in the annotation set
    annotation_positives = defaultdict(int)
    for key in annotation:
        stream_id = key[0]
        timestamp = int(stream_id.split('-')[0])

        if (not include_training) and (timestamp <= 1325375999):
            continue 

        target_id = key[1]
        annotation_positives[target_id] += annotation[(stream_id,target_id)]
        
    for target_id in CM:
        for cutoff in CM[target_id]:
            ## Then subtract the number of TP at each cutoffs 
            ## (since FN+TP==True things in annotation set)
            CM[target_id][cutoff]['FN'] = annotation_positives[target_id] - CM[target_id][cutoff]['TP']

    if debug:
        log( 'showing assertion counts:' )
        log( json.dumps(num_assertions, indent=4, sort_keys=True) )

    return CM
    
def load_annotation(path_to_annotation_file, include_useful, include_neutral, min_len_clean_visible, reject):
    '''
    Loads the annotation file into a dict
    
    path_to_annotation_file: string filesystem path to the annotation file
    include_useful: true to include docs marked useful and vital

    reject:  callable that returns boolean given a target_id
    '''
    annotation_file = csv.reader(open(path_to_annotation_file, 'r'), delimiter='\t')

    annotation = dict()
    for row in annotation_file:
       ## Skip comments
       if row[0][0] == "#":
           continue 
       
       stream_id = row[2]
       target_id = row[3]
       rating = int(row[5])

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

       if include_neutral:
           thresh = 0
       elif include_useful:
           thresh = 1
       else:
           thresh = 2
       
       ## Add the stream_id and target_id to a hashed dictionary
       ## 0 means that its not vital 1 means that it is vital
              
       if (stream_id, target_id) in annotation:
           ## 2 means the annotators gave it a yes for vitality
           if rating < thresh:
                annotation[(stream_id, target_id)] = False
       else:
           ## store bool values in the annotation index
           annotation[(stream_id, target_id)] = rating >= thresh 

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

    if args.use_micro_averaging:
        avg = '-microavg'
    else:
        avg = '-macroavg'

    rating_types = '-vital'
    if args.include_useful:
        rating_types += '+useful'
    elif args.include_neutral:
        rating_types += '+neutral'

    description = 'ccr' \
            + entities \
            + rating_types \
            + avg \
            + '-cutoff-step-size-' \
            + str(args.cutoff_step)

    return description

def score_all_runs(args, description, reject):
    '''
    score all the runs in the specified runs dir using the various
    filters and configuration settings

    :param description: string used for file names
    :param reject: callable to rejects truth data
    '''
    ## Load in the annotation data
    annotation = load_annotation(args.annotation, args.include_useful, args.include_neutral, 
                                 args.min_len_clean_visible, reject)
    log( 'This assumes that all run file names end in .gz' )

    team_scores = defaultdict(lambda: defaultdict(dict))
    for run_file in os.listdir(args.run_dir):
        if not run_file.endswith('.gz'):
            continue
        
        ## take the name without the .gz
        run_file_name = '.'.join(run_file.split('.')[:-1])
        log( 'processing: %s.gz' % run_file_name )
        
        ## Generate the confusion matrix for a run
        CM = score_confusion_matrix(
            os.path.join(args.run_dir, run_file), 
            annotation, args.cutoff_step, args.unan_is_true, args.include_training,
            debug=args.debug)

        ## Generate performance metrics for a run
        Scores = performance_metrics(CM)
        
        ## Generate the average metrics
        (CM['average'], Scores['average']) = full_run_metrics(CM, Scores, args.use_micro_averaging)

        max_scores = find_max_scores(Scores)

        ## split into team name and create stats file
        team_id, system_id = run_file_name.split('-')
        team_scores[team_id][system_id] = max_scores

        ## Print the top F-Score
        log( '   max(avg(F_1)): %.3f' % max_scores['average']['F'] )
        log( '   max(F_1(avg(P), avg(R))): %.3f' % max_scores['average']['F_recomputed'] )
        log( '   max(avg(SU)):  %.3f' % max_scores['average']['SU'] )
        
        base_output_filepath = os.path.join(
            args.run_dir, 
            run_file_name + '-' + description)

        output_filepath = base_output_filepath + '.csv'
        write_performance_metrics(output_filepath, CM, Scores)
        log( ' wrote metrics table to %s' % output_filepath )
        
        if not plt:
            log( ' not generating plot, because could not import matplotlib' )
        else:
            ## Output a graph of the key performance statistics
            graph_filepath = base_output_filepath + '.png'
            write_graph(graph_filepath, Scores['average'])
            log( ' wrote plot image to %s' % graph_filepath )

    ## When folder is finished running output a high level summary of the scores to overview.csv
    write_team_summary(description, team_scores)
            
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, usage=__usage__)
    parser.add_argument(
        'run_dir', 
        help='path to the directory containing run files')
    parser.add_argument('annotation', help='path to the annotation file')
    parser.add_argument(
        '--min-len-clean-visible', type=int, default=100, 
        help='minimum length of clean_visible content for a stream_id to be included in truth data')
    parser.add_argument(
        '--cutoff-step', type=int, default=50, dest = 'cutoff_step',
        help='step size used in computing scores tables and plots')
    parser.add_argument(
        '--unannotated-is-true-negative', default=False, action='store_true', dest='unan_is_true',
        help='compute scores using assumption that all unjudged documents are true negatives, i.e. that the system used to feed tasks to assessors in June 2012 had perfect recall.  Default is to not assume this and only consider (stream_id, target_id) pairs that were judged.')
    parser.add_argument(
        '--use-micro-averaging', default=False, action='store_true', dest='use_micro_averaging',
        help='compute scores for each mention and then average regardless of entity.  Default is macro averaging')
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
        '--group', default=None,
        help='limit entities to this group')
    parser.add_argument(
        '--entity-type', default=None,
        help='limit entities to this entity-type')
    parser.add_argument(
        '--topics-path', default=None,
        help='path to file containing JSON structure of query topics')
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

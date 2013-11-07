'''
common functions for scoring systems

'''
## use float division instead of integer division
from __future__ import division
from collections import defaultdict
import sys
import json

def getMedian(numericValues):
    '''
    Returns the median from a list
    
    numericValues: list of numbers
    '''    
    theValues = sorted(numericValues)
    if len(theValues) % 2 == 1:
        return theValues[(len(theValues)+1)//2-1]
    else:
        lower = theValues[len(theValues)//2-1]
        upper = theValues[len(theValues)//2]
        return (float(lower + upper)) / 2

    
def precision(TP, FP):
    '''
    Calculates the precision given the number of true positives (TP) and
    false-positives (FP)
    '''      
    if (TP+FP) > 0:
        precision = float(TP) / (TP + FP)
        if not (0.0 <= precision <= 1.0):
            sys.exit('invalid precision = %f = float(TP=%d) / (TP=%d + FP=%d)' 
                     % (precision, TP, TP, FP))
        return precision
    else:
        return 0.0  ## can get either 1.0 or 0.0, and 0 is more conservative

def recall(TP, FN):
    '''
    Calculates the recall given the number of true positives (TP) and
    false-negatives (FN)
    '''    
    if (TP+FN) > 0:
        recall = float(TP) / (TP + FN)
        if not (0.0 <= recall <= 1.0):
            sys.exit('invalid recall = %f = float(TP=%d) / (TP=%d + FN=%d)' 
                     % (recall, TP, TP, FN))
        return recall
    else:
        return 0.0  ## can get either 1.0 or 0.0, and 0 is more conservative

def fscore(precision=None, recall=None):
    '''
    Calculates the F-score given the precision and recall
    '''
    if precision + recall > 0:
        return float(2 * precision * recall) / (precision + recall)
    else:
        return 0.0
    
def scaled_utility(TP, FP, FN, MinNU = -0.5):
    '''
    Scaled Utility from http://trec.nist.gov/pubs/trec11/papers/OVER.FILTERING.pdf
    
    MinNU is an optional tunable parameter
    '''
    if (TP + FN) > 0:
        T11U = float(2 * TP - FP)
        MaxU = float(2 * (TP + FN))
        T11NU = float(T11U) / MaxU 
        return (max(T11NU, MinNU) - MinNU) / (1 - MinNU)
    else:
        return 0.0

def is_valid_target_id(str_that_might_be_target_id):
    '''
    check that the input string starts with http, and is therefore
    probably a valid TREC KBA target_id and not one of the other
    strings that can appear in stats, such as "micro_average"
    '''
    return str_that_might_be_target_id.startswith('http')

def is_valid_confusion_matrix(CM):
    return all(0 <= CM[key] for key in ['TP', 'FP', 'TN', 'FN'])

def compile_and_average_performance_metrics(stats):
    '''
    construct P/R/F/SU for every entity and also for three methods of
    averaging over the entities:

      * micro -- weights each assertion equally

      * macro -- weights each entity equally (same as the B-cubed _extraction_ measure)

      * weighted -- weights each entity by the number of possible positives in the truth set
    '''
    compile_performance_metrics(stats)
    micro_average(stats)
    macro_average(stats)
    weighted_average(stats)


def compile_performance_metrics(stats):
    '''
    Extend stats by adding the performance metrics at each cutoff.
    New keys added to each stats[target_id][cutoff] matrix:
 
      * P = precision
      * R = recall
      * F = F_beta=1
      * SU = scaled utility
    
    stats: dict containing the confusion matrix of counts of type-II
    errors (True/False Positives/Negatives)
    '''    
    for target_id in stats:
        for cutoff in stats[target_id]:
            _stats = stats[target_id][cutoff]

            assert is_valid_confusion_matrix(_stats), _stats

            _stats['P'] = precision(_stats['TP'], _stats['FP'])
            
            _stats['R'] =    recall(_stats['TP'], _stats['FN'])
            
            ## F-Score --> NB: this uses the two values just computed above
            _stats['F'] =    fscore(_stats['P'],  _stats['R'])
            
            ## Scaled Utility from http://trec.nist.gov/pubs/trec11/papers/OVER.FILTERING.pdf
            _stats['SU'] = scaled_utility(_stats['TP'], _stats['FP'], _stats['FN'])


def micro_average(stats):
    '''
    create stats['micro_average'] containing the micro averaged values
    of all the metrics

    Computes "F" as F_1(micro_average(P), micro_average(R))
    '''
    ## We could just average P and R, but to get SU averaged
    ## correctly, we need to go back to the confusion matrix, so
    ## construct a dict structured like stats with all of the counts
    ## on a single target_id=="micro_average"
    stats_summed = dict(micro_average=defaultdict(lambda: defaultdict(int)))

    for target_id in stats:
        for cutoff in stats[target_id]:
            for metric in ['TP', 'FP', 'TN', 'FN']:
                stats_summed['micro_average'][cutoff][metric] += stats[target_id][cutoff][metric]


    compile_performance_metrics(stats_summed)

    stats['micro_average'] = stats_summed.pop('micro_average')


def macro_average(stats):
    '''
    create stats['macro_average'] containing the macro averaged values
    of all the metrics

    Computes "F" as F_1(macro_average(P), macro_average(R))
    '''
    _average(stats)

def weighted_average(stats):
    '''
    create stats['weighted_average'] containing the macro averaged values
    of all the metrics

    Computes "F" as F_1(weighted_average(P), weighted_average(R))
    '''
    num_possible_positives = defaultdict(int)
    for target_id in stats:
        num_possible_positives[target_id] += \
            stats[target_id][0]['TP'] + stats[target_id][0]['FN']    
    total_possible_positives = sum(num_possible_positives.values())

    ## rescale back to one
    for target_id in num_possible_positives:
        if total_possible_positives > 0:
            num_possible_positives[target_id] /= total_possible_positives
        else:
            num_possible_positives[target_id] = 0

    _average(stats, weight=num_possible_positives.get, name='weighted_average')

def _average(stats, metrics=['P', 'R', 'SU'], weight=lambda target_id: 1, name='macro_average'):
    '''
    computes stats[name] = a weighted average of the 'metrics' in
    'stats' using the weighting function.

    Default is to average P, R, SU using weight=1 for each entity

    If 'P' and 'R' are in metrics, then computes 
       stats["F"] = F_1(_average(P), _average(R))
    '''
    num_entities = sum(is_valid_target_id(key) for key in stats)
    _average = defaultdict(lambda: defaultdict(float))
    for target_id in stats:
        if not is_valid_target_id(target_id): 
            ## ignore non-query keys, e.g. "micro_average"
            continue
        for cutoff in stats[target_id]:
            for metric in ['P', 'R', 'SU']:
                #print 'including in average: %r --> %r' % (target_id, stats[target_id][cutoff])
                _average[cutoff][metric] += stats[target_id][cutoff][metric] * weight(target_id) / num_entities

    if 'P' in metrics and 'R' in metrics:
        for cutoff in _average:
            _average[cutoff]['F'] = fscore(precision=_average[cutoff]['P'], 
                                           recall   =_average[cutoff]['R'])

    print 'computed %s using num_entities=%d' % (name, num_entities)
    stats[name] = _average

def find_max_scores(stats):
    '''
    find max 'F' and max 'SU' and store P_at_best_F and R_at_best_F

    :returns dict: max_scores[target_id][metric] = float
    '''
    max_scores = defaultdict(dict)

    ## Store top F, SU for each target_id, which includes the special
    ## values of "{micro,macro,weighted}_average" thereby appling the
    ## same cutoff for all entities.
    #for avg in ['micro_average', 'macro_average', 'weighted_average']:
    for target_id in stats:
        ## find the maximum F, and capture its underlying P and R
        best_SU = 0
        best_F = 0
        P_at_best_F = 0
        R_at_best_F = 0
        for cutoff in stats[target_id]:
            if stats[target_id][cutoff]['SU'] > best_SU:
                best_SU = stats[target_id][cutoff]['SU']
            if stats[target_id][cutoff]['F'] > best_F:
                best_F = stats[target_id][cutoff]['F']
                P_at_best_F = stats[target_id][cutoff]['P']
                R_at_best_F = stats[target_id][cutoff]['R']

        max_scores[target_id]['SU'] = best_SU
        max_scores[target_id]['F'] = best_F
        max_scores[target_id]['P'] = P_at_best_F
        max_scores[target_id]['R'] = R_at_best_F

    return max_scores

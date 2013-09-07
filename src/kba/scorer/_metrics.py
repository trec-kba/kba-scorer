'''
common functions for scoring systems

'''
## use float division instead of integer division
from __future__ import division
from collections import defaultdict

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
        return float(TP) / (TP + FP)
    else:
        return 0.0

def recall(TP, FN):
    '''
    Calculates the recall given the number of true positives (TP) and
    false-negatives (FN)
    '''    
    if (TP+FN) > 0:
        return float(TP) / (TP + FN)
    else:
        return 0.0

def fscore(precision, recall):
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

def performance_metrics(CM, debug=False):
    '''
    Computes the performance metrics (precision, recall, F-score, scaled utility)
    
    CM: dict containing the confusion matrix calculated from score_confusion_matrix()
    '''
    ## Compute the performance statistics                
    Scores = dict()
    
    for target_id in CM:
        Scores[target_id] = dict()
        for cutoff in CM[target_id]:
            Scores[target_id][cutoff] = dict()

            ## Precision
            Scores[target_id][cutoff]['P'] = precision(CM[target_id][cutoff]['TP'],
                                                       CM[target_id][cutoff]['FP'])

            ## Recall
            Scores[target_id][cutoff]['R'] = recall(CM[target_id][cutoff]['TP'],
                                                    CM[target_id][cutoff]['FN'])

            ## F-Score
            Scores[target_id][cutoff]['F'] = fscore(Scores[target_id][cutoff]['P'],
                                                    Scores[target_id][cutoff]['R'])

            ## Scaled Utility from http://trec.nist.gov/pubs/trec11/papers/OVER.FILTERING.pdf
            Scores[target_id][cutoff]['SU'] = scaled_utility(CM[target_id][cutoff]['TP'], 
                                                  CM[target_id][cutoff]['FP'], 
                                                  CM[target_id][cutoff]['FN'])
    return Scores


def full_run_metrics(CM, Scores, use_micro_averaging=False):
    '''
    Computes the metrics for the whole run over all the entities
    
    CM: dict, the confusion matrix for each target_id defined below
    Scores: dict, the scores for each target_id

    :param use_micro_averaging: false --> average over mentions, true --> average over entities (target_ids)
    :type use_micro_averaging: bool
    
    returns (CM_total, Scores_average) the average of the scores and the summed
    confusion matrix     
    '''
    
    flipped_CM = defaultdict(dict)
    for key, val in CM.items():
        for subkey, subval in val.items():
            flipped_CM[subkey][key] = subval

    CM_total = dict()
    
    for cutoff in flipped_CM:
        CM_total[cutoff] = dict(TP=0, FP=0, FN=0, TN=0)     
        for target_id in flipped_CM[cutoff]:
            for key in CM[target_id][cutoff]:
                CM_total[cutoff][key] += CM[target_id][cutoff][key]
            
    flipped_Scores = defaultdict(dict)
    for key, val in Scores.items():
        for subkey, subval in val.items():
            flipped_Scores[subkey][key] = subval
        
    Scores_average = dict()
    ## Do macro averaging
    if not use_micro_averaging:
        for cutoff in flipped_Scores:
            Scores_average[cutoff] = dict(P=0.0, R=0.0, F=0.0, SU=0.0)
            ## Sum over target_ids for each cutoff
            for target_id in flipped_Scores[cutoff]:
                for metric in flipped_Scores[cutoff][target_id]:
                    Scores_average[cutoff][metric] += Scores[target_id][cutoff][metric]
        ## Divide by the number of target_ids to get the average metrics
        for cutoff in Scores_average:
            for metric in Scores_average[cutoff]:
                Scores_average[cutoff][metric] = Scores_average[cutoff][metric] / len(Scores)

        print 'macro averaged'

    ## Do micro averaging
    else:
        tempCM = dict(average=CM_total)
        tempScores = performance_metrics(tempCM)
        Scores_average = tempScores['average']
        print 'micro averaged'

    return CM_total, Scores_average


def find_max_scores(Scores):
    '''
    find the maximum of each type of metric across all cutoffs
    '''
    max_scores = defaultdict(dict)
    
    ## Store top F, SU for each target_id, which takes special value
    ## of "average" thereby appling the same cutoff for all entities.
    for target_id in Scores:
        for metric in ['P', 'R', 'F', 'SU']:
            max_scores[target_id][metric] =  \
                max([Scores[target_id][cutoff][metric]
                     for cutoff in Scores[target_id]])

    max_scores['average']['F_recomputed'] = \
        max([fscore(Scores['average'][cutoff]['P'], 
                    Scores['average'][cutoff]['R'])
             for cutoff in Scores['average']])

    return max_scores

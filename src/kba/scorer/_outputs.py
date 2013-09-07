'''
tools for generating output plots and CSV files

'''
import csv
import sys
import math
from collections import defaultdict
from kba.scorer._metrics import getMedian
try:
    import matplotlib.pyplot as plt
except ImportError:
    plt = None

def write_graph(path_to_write_graph, Scores):
    '''
    Writes a graph showing the 4 metrics computed
    
    path_to_write_graph: string with graph output destination
    Scores: dict containing the score metrics computed using performance_metrics()
    '''
    plt.figure()
    Precision = list()
    Recall = list()
    Fscore = list()
    Xaxis = list()
    ScaledUtil = list()
    for cutoff in sorted(Scores,reverse=True):
        Xaxis.append(cutoff)
        Recall.append(Scores[cutoff]['R'])
        Precision.append(Scores[cutoff]['P'])
        Fscore.append(Scores[cutoff]['F'])
        ScaledUtil.append(Scores[cutoff]['SU'])

    plt.plot(Xaxis, Precision, label='Precision')
    plt.plot(Xaxis, Recall, label='Recall')
    plt.plot(Xaxis, Fscore, label='F-Score')
    plt.plot(Xaxis, ScaledUtil, label='Scaled Utility')
    plt.xlabel('Cutoff')
    plt.ylim(-0.01, 1.3)
    plt.xlim(1000,0)
    plt.legend(loc='upper right')        
    plt.savefig(path_to_write_graph)
    plt.close()

def write_performance_metrics(path_to_write_csv, CM, Scores):
    '''
    Writes a CSV file with the performance metrics at each cutoff
    
    path_to_write_csv: string with CSV file destination
    CM: dict, Confusion matrix generated from score_confusion_matrix()
    Scores: dict containing the score metrics computed using performance_metrics()
    '''
    writer = csv.writer(open(path_to_write_csv, 'wb'), delimiter=',')
    ## Write a header
    writer.writerow(['target_id','cutoff', 'TP', 'FP', 'FN', 'TN', 'P', 'R', 'F', 'SU'])
    
    ## Write the metrics for each cutoff and target_id to a new line,
    ## where target_id also takes special value of "average"
    for target_id in sorted(CM):
        for cutoff in sorted(CM[target_id], reverse=True):
            writer.writerow([target_id, cutoff,
                             CM[target_id][cutoff]['TP'], CM[target_id][cutoff]['FP'], 
                             CM[target_id][cutoff]['FN'], CM[target_id][cutoff]['TN'],
                             Scores[target_id][cutoff]['P'], Scores[target_id][cutoff]['R'], 
                             Scores[target_id][cutoff]['F'], Scores[target_id][cutoff]['SU']])


def write_team_summary(team_scores):
    '''
    Writes a CSV file with the max, average, median and min F and SU for each teams run
    
    path_to_write_csv: string with CSV file destination
    team_scores: dict, contains the F and SU for each run of each team
    '''

    run_writer = csv.writer(open('run-overview.csv', 'wb'), delimiter=',')
    ## Write a header
    run_writer.writerow(['team_id', 'system_id','maxF', 'maxF_recomputed', 'maxSU'])

    ## write averaged metrics
    for team_id in team_scores:
        for system_id in team_scores[team_id]:
            run_writer.writerow([team_id, system_id,
                                 team_scores[team_id][system_id]['average']['F'],
                                 team_scores[team_id][system_id]['average']['F_recomputed'],
                                 team_scores[team_id][system_id]['average']['SU']])

    flipped_ts = defaultdict(dict)
    
    for team_id in team_scores:
        for system_id, val in team_scores[team_id].items():
            for target_id, subval in val.items():
                flipped_ts[target_id][team_id + '-' + system_id] = subval

    url_writer = csv.writer(open('target_id-overview.csv', 'wb'), delimiter=',')
    ## Write a header
    url_writer.writerow(['target_id',
                     'maxF', 'medianF', 'meanF', 'minF',
                     'maxSU', 'medianSU', 'meanSU', 'minSU'])
                         
    ## Write the metrics for each target_id (including "average") to a new line
    for target_id in flipped_ts: 
        url_writer.writerow([target_id,
                            max([flipped_ts[target_id][team_system_id]['F'] 
                                 for team_system_id in flipped_ts[target_id]]),
                            getMedian([flipped_ts[target_id][team_system_id]['F'] 
                                 for team_system_id in flipped_ts[target_id]]),
                            float(sum([flipped_ts[target_id][team_system_id]['F'] 
                                 for team_system_id in flipped_ts[target_id]])) / len(team_scores),
                            min([flipped_ts[target_id][team_system_id]['F'] 
                                 for team_system_id in flipped_ts[target_id]]),          
                            max([flipped_ts[target_id][team_system_id]['SU'] 
                                 for team_system_id in flipped_ts[target_id]]),
                            getMedian([flipped_ts[target_id][team_system_id]['SU'] 
                                 for team_system_id in flipped_ts[target_id]]),
                            float(sum([flipped_ts[target_id][team_system_id]['SU'] 
                                 for team_system_id in flipped_ts[target_id]])) / len(team_scores),
                            min([flipped_ts[target_id][team_system_id]['SU'] 
                                 for team_system_id in flipped_ts[target_id]])
             ])


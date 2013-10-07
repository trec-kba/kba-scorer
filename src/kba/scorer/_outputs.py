'''
tools for generating output plots and CSV files

'''
import csv
import sys
import math
from collections import defaultdict
from kba.scorer._metrics import getMedian
try:
    import matplotlib as mpl
    mpl.use('Agg')
    import matplotlib.pyplot as plt
except ImportError:
    plt = None

def log(m):
    print m
    sys.stdout.flush()

def write_graph(path_to_write_graph, stats):
    '''
    Writes a graph showing the 4 metrics computed
    
    path_to_write_graph: string with graph output destination
    
    :param stats: dict containing confusion matrix elements and
    aggregate scores
    '''
    if not plt:
        log( ' matplotlib not available, so not plots generated' )
        return 

    stats = stats['macro_average']

    plt.figure()
    Precision = list()
    Recall = list()
    Fscore = list()
    ScaledUtil = list()
    Xaxis = list()
    for cutoff in sorted(stats,reverse=True):
        Xaxis.append(cutoff)
        Recall.append(stats[cutoff]['R'])
        Precision.append(stats[cutoff]['P'])
        Fscore.append(stats[cutoff]['F'])
        ScaledUtil.append(stats[cutoff]['SU'])

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

    log( ' wrote plot image to %s' % path_to_write_graph )


def write_performance_metrics(path_to_write_csv, stats):
    '''
    Write a CSV file with the performance metrics at each cutoff
    
    :param path_to_write_csv: string with CSV file destination

    :param stats: dict containing confusion matrix elements and
    aggregate scores
    '''
    writer = csv.writer(open(path_to_write_csv, 'wb'), delimiter=',')
    ## Write a header
    writer.writerow(['target_id','cutoff', 'TP', 'FP', 'FN', 'TN', 'P', 'R', 'F', 'SU'])
    
    ## Write the metrics for each cutoff and target_id to a new line,
    ## where target_id also takes special value of "average"
    for target_id in sorted(stats):
        for cutoff in sorted(stats[target_id], reverse=True):
            writer.writerow([target_id, cutoff,
                             stats[target_id][cutoff]['TP'], stats[target_id][cutoff]['FP'], 
                             stats[target_id][cutoff]['FN'], stats[target_id][cutoff]['TN'],
                             stats[target_id][cutoff]['P'], stats[target_id][cutoff]['R'], 
                             stats[target_id][cutoff]['F'], stats[target_id][cutoff]['SU']])


def write_team_summary(mode, team_scores):
    '''
    Writes a CSV file with the max, average, median and min F and SU for each teams run
    
    path_to_write_csv: string with CSV file destination
    team_scores: dict, contains the F and SU for each run of each team
    '''
    path = 'overviews/%s-run-overview.csv' % mode
    run_writer = csv.writer(open(path, 'wb'), delimiter=',')
    ## Write a header
    columns = ['team_id', 'system_id']
    for avg in ['micro_average', 'macro_average', 'weighted_average']:
        columns += [avg + '_P', avg + '_R', avg + '_F', avg + '_SU']
    run_writer.writerow(columns)

    ## write averaged metrics
    for team_id in team_scores:
        for system_id in team_scores[team_id]:
            row = [team_id, system_id]
            log('  %s-%s' % (team_id, system_id))
            for avg in ['micro_average', 'macro_average', 'weighted_average']:
                ## Print the top F-Score
                log( '    %s: max(F_1(avg(P), avg(R))): %.3f' % (avg, team_scores[team_id][system_id][avg]['F']))
                log( '    %s: max(avg(SU)):  %.3f'            % (avg, team_scores[team_id][system_id][avg]['SU'] ))

                row += [team_scores[team_id][system_id][avg][metric]
                        for metric in ['P', 'R', 'F', 'SU']]
            run_writer.writerow(row)
    log('wrote ' + path)

    flipped_ts = defaultdict(dict)
    
    for team_id in team_scores:
        for system_id, val in team_scores[team_id].items():
            for target_id, subval in val.items():
                flipped_ts[target_id][team_id + '-' + system_id] = subval

    path = 'overviews/%s-target_id-overview.csv' % mode
    url_writer = csv.writer(open(path, 'wb'), delimiter=',')
    ## Write a header
    url_writer.writerow(['target_id',
                     'maxF', 'medianF', 'meanF', 'minF',
                     'maxSU', 'medianSU', 'meanSU', 'minSU'])
                         
    ## Write metrics for each target_id (including the three averages)
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

    log('wrote ' + path)

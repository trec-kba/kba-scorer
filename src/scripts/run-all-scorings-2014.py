'''
run the CCR scorer on all the groups, including no restriction to a single group
'''
import os
import sys
import json
import subprocess
import multiprocessing
from collections import defaultdict
targets = json.load(open('../../KBA/2014/judgments/trec-kba-2014-10-15-ccr-and-ssf-query-topics.json'))['targets']

step_size = 1
primary_commands = []
commands = []
ccr_template = "(python -m  kba.scorer.ccr %s --cutoff-step %d --any-up --require-positives=4 --restrict ../../KBA/2014/judgments/ttr-possessing-entities.txt /data/trec-kba/2014/trec-kba-2014-run-submissions/ ../../KBA/2014/judgments/trec-kba-2014-10-15-ccr-and-ssf.after-cutoff.tsv | gzip ) >& logs/2014-runs-ccr-%s.log.gz"

## without restrictions and before-and-after-cutoff
#ccr_template = "(python -m  kba.scorer.ccr %s --cutoff-step %d --any-up --require-positives=4 /data/trec-kba/2014/trec-kba-2014-run-submissions/ ../../KBA/2014/judgments/trec-kba-2014-10-15-ccr-and-ssf.before-and-after-cutoff.tsv | gzip ) >& logs/2014-runs-ccr-%s.log.gz"

#ssf_template = "(python -m  kba.scorer2.ssf %s --cutoff-step %d ../../2013-kba-runs/ ../../trec-kba-ssf-target-events-2013-07-16-expanded-stream-ids.json | gzip ) &> logs/2013-kba-runs-ssf-%s.log.gz"

avg_flag = ''

for entity_type in ['PER', 'ORG', 'FAC']:
    ent_flags = avg_flag + ' --entity-type %s --topics-path ../../KBA/2014/judgments/trec-kba-2014-10-15-ccr-and-ssf-query-topics.json ' % entity_type
    log_name = avg_flag + '-' + entity_type
    cmd = ccr_template % (ent_flags, step_size, log_name)
    commands.append(cmd)
    #print cmd

    for rating_flag in ['', '--include-useful']:
        flags = ' '.join([avg_flag, rating_flag, ent_flags])
        log_name = '-'.join([avg_flag, rating_flag, entity_type])
        cmd = ccr_template % (flags, step_size, log_name)
        if flags.strip():
            ## only do cmds with at least one flag
            commands.append(cmd)
            #print cmd

cmd = ccr_template % ('', step_size, 'primary')
commands.insert(0, cmd)
cmd = ccr_template % (' --require-positives=4 ', step_size, 'primary-req-pos')
commands.insert(0, cmd)

cmd = ccr_template % (' --include-useful ', step_size, 'primary')
commands.insert(0, cmd)
cmd = ccr_template % (' --include-useful --require-positives=4 ', step_size, 'primary-req-pos')
commands.insert(0, cmd)

#cmd = ssf_template % ('', step_size, 'primary')
#commands.insert(0, cmd)
#cmd = ssf_template % (' --pooled-only ', step_size, 'primary-pooled-only')
#commands.insert(0, cmd)

print len(commands), 'tasks to do'

sys.stdout.flush()

def run(cmd):
    print cmd
    sys.stdout.flush()
    p = subprocess.Popen(cmd, shell=True, executable="/bin/bash")
    p.wait()

#sys.exit()

#pool = multiprocessing.Pool(3, maxtasksperchild=1)
#pool.map(run, primary_commands)
#pool.close()
#pool.join()

pool = multiprocessing.Pool(8, maxtasksperchild=1)
pool.map(run, commands)
pool.close()
pool.join()

'''
ips = open('good-ips').read().splitlines()

base_cmd = "cd /data/trec-kba/users/jrf/KBA/2013/entities/score/src && ("

assignments = defaultdict(set)
i = 0
while commands:
    i += 1
    assignments[ips[i % len(ips)]].add(commands.pop())

counts = defaultdict(int)
for ip in ips:
    counts[len(assignments[ip])] += 1

print counts

remote_cmds = dict()
for ip in ips:
    remote_cmds[ip] = base_cmd + ') && ('.join(list(assignments[ip])) + ')'

#print '\n'.join(map(str, remote_cmds.items()))

for ip, remote_cmd in remote_cmds.items():
    cmd = 'ssh %s "echo \\"%s\\" > jobs.sh; chmod a+x jobs.sh" &' % (ip, remote_cmd)
    print cmd
    os.system(cmd)
'''

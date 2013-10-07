'''
run the CCR scorer on all the groups, including no restriction to a single group
'''
import os
import sys
import json
import subprocess
import multiprocessing
targets = json.load(open('../../trec-kba-ccr-and-ssf-query-topics-2013-07-16.json'))['targets']
groups = set()
for targ in targets:
    groups.add(targ['group'])
groups.remove('kba2012')
groups = list(groups)
groups.sort()

slot_types = ['Affiliate', 'TopMembers', 'FoundedBy', 'Contact_Meet_Entity', 'AssociateOf', 'Contact_Meet_PlaceTime', 'AwardsWon', 'DateOfDeath', 'CauseOfDeath', 'Titles', 'FounderOf', 'EmployeeOf', 'SignificantOther', 'Children']

primary_commands = []
commands = []
ccr_template = "python -m  kba.scorer.ccr %s --cutoff-step %d ../../2013-kba-runs/ ../../trec-kba-ccr-judgments-2013-09-26-expanded-with-ssf-inferred-vitals-plus-len-clean_visible.before-and-after-cutoff.filter-run.txt >& logs/2013-kba-runs-ccr-%s.log"

ssf_template = "python -m  kba.scorer.ssf %s --cutoff-step %d ../../2013-kba-runs/ ../../trec-kba-ssf-target-events-2013-07-16-expanded-stream-ids.json &> logs/2013-kba-runs-ssf-%s.log"
avg_flag = ''
step_size = 100
for group in groups:
    flags = avg_flag + ' --group %s --topics-path ../../trec-kba-ccr-and-ssf-query-topics-2013-07-16.json ' % group
    log_name = avg_flag + '-' + group
    cmd = ccr_template % (flags, step_size, log_name)
    commands.append(cmd)
    print cmd

for entity_type in ['PER', 'ORG', 'FAC']:
    flags = avg_flag + ' --entity-type %s --topics-path ../../trec-kba-ccr-and-ssf-query-topics-2013-07-16.json ' % entity_type
    log_name = avg_flag + '-' + entity_type
    cmd = ccr_template % (flags, step_size, log_name)
    commands.append(cmd)
    print cmd

for slot_type in slot_types:
    flags = avg_flag + ' --slot-type ' + slot_type + ' '
    log_name = avg_flag + '-' + slot_type
    cmd = ssf_template % (flags, step_size, log_name)
    commands.append(cmd)
    print cmd

for reject_flag in ['', '--reject-wikipedia', '--reject-twitter']:
    flags = ' '.join([avg_flag, reject_flag])
    log_name = '-'.join([avg_flag, reject_flag])
    cmd = ssf_template % (flags, step_size, log_name)
    if flags.strip():
        ## only do cmds with at least one flag
        commands.append(cmd)
        print cmd

    for rating_flag in ['', '--include-useful']:
        flags = ' '.join([avg_flag, rating_flag, reject_flag])
        log_name = '-'.join([avg_flag, rating_flag, reject_flag])
        cmd = ccr_template % (flags, step_size, log_name)
        if flags.strip():
            ## only do cmds with at least one flag
            commands.append(cmd)
            print cmd

step_size = 10
cmd = ccr_template % ('', step_size, 'primary')
primary_commands.insert(0, cmd)
cmd = ssf_template % ('', step_size, 'primary')
primary_commands.insert(0, cmd)
cmd = ssf_template % (' --pooled-only ', step_size, 'primary-pooled-only')
primary_commands.insert(0, cmd)

sys.stdout.flush()

def run(cmd):
    print cmd
    sys.stdout.flush()
    p = subprocess.Popen(cmd, shell=True, executable="/bin/bash")
    p.wait()

#sys.exit()

pool = multiprocessing.Pool(3, maxtasksperchild=1)
pool.map(run, primary_commands)
pool.close()
pool.join()

pool = multiprocessing.Pool(3, maxtasksperchild=1)
pool.map(run, commands)
pool.close()
pool.join()

'''This script generates scores for TREC KBA 2014 SSF, described here:

   http://trec-kba.org/trec-kba-2014/

Direction questions & comments to the TREC KBA forums:
http://groups.google.com/group/trec-kba

.. This software is released under an MIT/X11 open source license.
   Copyright 2014 Diffeo, Inc.

'''
from __future__ import absolute_import

from collections import Counter as StringCounter
from collections import defaultdict
import csv
import gzip
import json
import math
import os
import re
from operator import itemgetter
import pickle
import sys
import yaml

from streamcorpus import Chunk
from kba.scorer2.metrics import get_metric_by_name, available_metrics

def log(m):
    sys.stderr.write(m)
    sys.stderr.write('\n')
    sys.stderr.flush()

class ComparableProfile(object):
    '''
    A profile has a dict of slots -- a mapping from slot_name to a Counter of slot values. ComparableProfiles are
    profiles you can score in similarity with a compare function. Two profiles are  similar if they contain
    many of the same slot_names and for each slot_name similar values.
    '''
    
    def __init__(self, profile_name, truncate_counts = False):
        self._profile_name = profile_name

        #slot_name -> StringCounter
        self._slots = defaultdict(StringCounter)

        self._truncate_counts = truncate_counts

    def add_value_for_slot(self, slot_name, slot_value):
        '''
        Increment the slot_value in slot_name's StringCounter by 1.
        '''
        if self._truncate_counts:
            if not slot_value in self._slots[slot_name]:
                self._slots[slot_name][slot_value] += 1
            else:
                #probably paranoid, but
                #only increment if count is 0
                if self._slots[slot_name][slot_value] == 0:
                    self._slots[slot_name][slot_value] += 1
        else:
            self._slots[slot_name][slot_value] += 1

    def compare(self, other, scores):
        '''
        Return the comparison function applied between this profile and the other
        ComparableProfile.
        '''
        for metric_name in scores:
            metric = get_metric_by_name(metric_name)

            for slot_name, slot_value in self._slots.iteritems():
                other_slot_value = other._slots[slot_name] #defaults to empty StringCounter
                scores[metric_name] += metric(slot_value, other_slot_value)


def profiles_from_truthfile(truthfile_path):
    '''
    Returns dictionary mapping entity-name to ComparableProfile, where
    the ComparableProfiles are built from truth data.
    '''
    truth_file = open(truthfile_path, 'r')

    if truthfile_path.endswith('.json'):
        truth_parsed = json.load(truth_file)
    elif truthfile_path.endswith('.yaml'):
        truth_parsed = yaml.load(truth_file)
    else:
        raise ProgrammingError('Invalide file extension for truthfile_path. Only have support for .json or .yaml files')

    truth_profiles = dict()
    for ent_name,ent_data in truth_parsed['entities'].iteritems():
        profile = ComparableProfile(ent_name)
        for slot_name,slot_values in ent_data['slots'].iteritems():
            if isinstance(slot_values, (list,dict)):
                #somtimes slot_values is a list/dict
                for slot_value in slot_values:
                    #add tokens in slot_value
                    for value in slot_value['value'].lower().strip().split():
                        profile.add_value_for_slot(slot_name, value)
            else:
                #somtimes slot_values is a singleton
                for value in slot_values.lower().strip().split():
                    profile.add_value_for_slot(slot_name, value)

        truth_profiles[ent_name] = profile

    return truth_profiles

def profiles_from_runfile(runfile_path, offset_c_prepended = False, 
                          offset_inclusive = True,
                          decode_utf = False,
                          streamitems_dir = None,
                          max_lines = None,
                          ):

    '''
    Returns a dictionary mappping from entity-name to ComparableProfile, where the
    ComparableProfiles are constructed from a runfile.
    '''
    runfile = gzip.open(runfile_path, 'r')
    filter_run = runfile.readline()
    assert filter_run.startswith('#')
    filter_run = json.loads(filter_run[1:])
    if filter_run['task_id'] != 'kba-ssf-2014':
        # do nothing
        return

    runfile_profiles = dict()
    runfile_csv = csv.reader(runfile, delimiter='\t')

    count = 1
    for row in runfile_csv:

        #skip comments
        if row[0].startswith('#'):
            continue

        if max_lines is not None and count > max_lines:
            break

        count += 1
        #parse the row
        stream_item = row[2]
        profile_name = row[3]
        slot_name = row[8]
        slot_value = row[9]
        offset_str = row[10]

        #initialize profile
        if profile_name not in runfile_profiles:
            runfile_profiles[profile_name] = ComparableProfile(profile_name, truncate_counts = True)

        #do all the offsets have a 'c' prepended?
        if offset_c_prepended:
            #remove the 'c's
            offsets = [offset[1:] for offset in offset_str.split(',')]
        else:
            #if there is no 'c' prepended, we also know that there is one offset.
            offsets = [offset_str]

        log( '{}: fetching stream item: {}'.format(runfile_path, stream_item) )

        ## The chunk files are located two levels deep in a directory
        ## hierarchy, where each level is 2 character prefix of the
        ## stream-id.  We are going to extract the first 4 characters
        ## of the stream-id in chunks of 2, so we can find the
        ## corresponding StreamItem on the filesystem.  For example,
        ## the StreamItem with id
        ## 1234567890-abcdef0123456789abcdef0123456789 would be stored
        ## in a single-item chunk file called
        ## ./ab/cd/1234567890-abcdef0123456789abcdef0123456789.sc and
        ## the further file extensions of .xz or .xz.gpg are optional,
        ## because the streamcorpus python package handles that for
        ## us.
        match = re.match('.*-(..)(..).*', stream_item)

        if match is None:
            raise Exception("Cannot read StreamItem for {}".format(stream_item))

        stream_item_path = '{}/{}/{}.sc.xz.gpg'.format(
            match.group(1),
            match.group(2),
            stream_item)

        stream_item_file_path = os.path.join(streamitems_dir, stream_item_path)

        if not os.path.isfile(stream_item_file_path):
            log('Could not find stream item {}'.format(stream_item))
            continue

        c = Chunk(stream_item_file_path)

        si = [si for si in c][0] #collect the single si in this chunk

        #are the offsets indexes in the decoded string or the undecoded string?
        if decode_utf:
            clean_visible = si.body.clean_visible.decode('utf-8')
        else:
            clean_visible = si.body.clean_visible

        #parse each offset in offsets
        if len(offsets) > 1:
            begin = int(offsets[0].split('-')[0])
            end = int(offsets[-1].split('-')[1])
        else:
            offset = offsets[0]
            begin,end = [int(loc) for loc in offset.split('-')]

        #account for inclusive offsets.
        if offset_inclusive:
            end += 1

        #build the slot value from clean_visible.
        slot_value_processed = clean_visible[int(begin):int(end)].lower().replace('_', ' ').strip()
        
        if not decode_utf:
            #we now must decode, because clean_visible wasn't decoded from the start.
            try:
                slot_value_processed = slot_value_processed.decode('utf-8')
            except UnicodeDecodeError:
                log( 'Warning: Could not decode slot_value: {}. Will skip slot-fill.'.format(slot_value_processed))
                continue

        log('## %s %s: %s' % (profile_name, slot_name, slot_value_processed.encode('utf-8')))

        #we want the bag-of-words associated with this slot_value
        for value in slot_value_processed.split():
            runfile_profiles[profile_name].add_value_for_slot(slot_name, value)

    return runfile_profiles


def score_run(runfile_profiles, truth_profiles, scores):
    '''
    Score a runfile by going through all its discovered entity profiles and
    comparing them to the corresponding truth profiles.

    `scores` must be a dictionary with keys that are `metric_names`
    '''
    #score the runfile-profiles against the truth-profiles.
    for entity in runfile_profiles.keys():
        #get profiles to compare
        runfile_profile = runfile_profiles[entity]
        truth_profile = truth_profiles[entity]
        truth_profile.compare(runfile_profile, scores)


'''
configs deal with options that handle the idiosyncrasies of the
different runfiles.
'''
configs = {
    'BUPT_PRIS-ssf1.gz': dict(
        offset_inclusive=False,
        decode_utf=True
    ),
    'BUPT_PRIS-ssf2.gz': dict(
        offset_inclusive=False,
        decode_utf=True,
    ),
    'ecnu-ssf_run.gz': dict(
        offset_inclusive=False,
        decode_utf=True,
        offset_c_prepended=True,
    ),
    'baseline-ssf.gz': dict(
        offset_inclusive=False,
        decode_utf=True,
        offset_c_prepended=True,
    ),
    'baseline-ssf_oracle.gz': dict(
        offset_inclusive=False,
        decode_utf=True,
        offset_c_prepended=True,
    ),
}

def get_config_by_name(name):
    '''
    Return the proper config dictionary provided a runfile name.
    '''
    if name in configs:
        return configs[name]
    else:
        return dict()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('truth_data_path', default='~/KBA/2014/judgments/trec-kba-2014-07-11-ccr-and-ssf.profiles.json')
    parser.add_argument('runfile_dir', default='~/trec-kba-2014-run-submissions')
    parser.add_argument('streamitems_dir', default='~/trec-kba-2014-ssf-stream-items')
    parser.add_argument('--metric', default='all')
    parser.add_argument('--max-lines', default=None, type=int)
    args = parser.parse_args()

    #load truth-data
    truth_profiles = profiles_from_truthfile(args.truth_data_path)

    if args.metric == 'all':
        metrics = available_metrics
    else:
        if args.metric not in available_metrics:
            sys.exit('{} not in available_metrics={!r}'.format(args.metric, available_metrics))
        metrics = [args.metric]

    
    #mapping from metric name to a mapping from runfile name to score
    metric_to_scores = defaultdict(dict)
    for runfile in os.listdir(args.runfile_dir):
        if not runfile.endswith('.gz'): continue

        runfile_config = get_config_by_name(runfile)

        runfile_profiles = profiles_from_runfile(os.path.join(args.runfile_dir, runfile), 
                                                 streamitems_dir=args.streamitems_dir,
                                                 max_lines = args.max_lines,
                                                 **runfile_config)

        if not runfile_profiles:
            continue

        #collect scores for each metric
        scores = {metric: 0.0 for metric in metrics}
        score_run(runfile_profiles,
                  truth_profiles, 
                  scores)

        for metric_name, score in scores.items():
            metric_to_scores[metric_name][runfile] = score

    #print out results
    for metric, scores in metric_to_scores.items():
        print '\n\nusing the {} metric:'.format(metric)
        print '\t{}'.format(metric)
        scores = sorted(scores.items(), key=itemgetter(1), reverse=True)
        for runfile, score in scores:
            print '{}\t{}'.format(runfile.split('.')[0], score)

from __future__ import absolute_import

from collections import Counter as StringCounter
from collections import defaultdict
import csv
import math
import os
import json
import yaml

from streamcorpus import Chunk
from metrics import get_metric_by_name

#Where to locate the truth data.
truth_data_path = '/home/josh/git/KBA/2014/judgments/trec-kba-2014-07-11-ccr-and-ssf.profiles.json'

#Paths to runfile and streamitems directories.
runfile_dir = '/home/josh/kba-scorer/src/kba/scorer_2/data'
streamitems_dir = '/data/trec-kba/2014/trec-2014-run-submissions/ssf-stream-items'

class ComparableProfile(object):
    '''
    A profile has a dict of slots -- a mapping from slot_name to a Counter of slot values. ComparableProfiles are
    profiles you can score in similarity with a compare function. Two profiles are  similar if they contain
    many of the same slot_names and for each slot_name similar values.
    '''
    
    def __init__(self, profile_name, truncate_counts = True):
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

    def compare(self, other, metric_name='cosine'):
        '''
        Return the comparison function applied between this profile and the other
        ComparableProfile.
        '''
        metric = get_metric_by_name(metric_name)

        score_sum = 0.0
        for slot_name, slot_value in self._slots.iteritems():
            other_slot_value = other._slots[slot_name] #defaults to empty StringCounter
            score_sum += metric(slot_value, other_slot_value)

        return score_sum

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
                          decode_utf = False):
    '''
    Returns a dictionary mappping from entity-name to ComparableProfile, where the
    ComparableProfiles are constructed from a runfile.
    '''
    runfile = open(runfile_path, 'r')

    runfile_profiles = dict()
    runfile_csv = csv.reader(runfile, delimiter='\t')

    count = 1
    for row in runfile_csv:

        #skip comments
        if row[0].startswith('#'):
            continue

        if count > 1000:
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

        print '{}: fetching stream item: {}'.format(runfile_path, stream_item)

        #The chunk files are located two levels deep in a directory hierarchy, where each
        #level is 2 character prefix of the stream-id.
        #We are going to extract the first 4 characters of the stream-id in chunks of 2,
        #so we can find the corresponding StreamItem on the filesystem.
        import re
        match = re.match('.*-(..)(..).*', stream_item)

        if match is None:
            raise Exception("Cannot read StreamItem for {}".format(stream_item))

        stream_item_file = streamitems_dir+'/{}/{}/{}.sc.xz.gpg'.format(
            match.group(1),
            match.group(2),
            stream_item)

        c = Chunk(stream_item_file)

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
                print 'Warning: Could not decode slot_value: {}. Will skip decoding process.'.format(slot_value_processed)

        print slot_value_processed

        #we want the bag-of-words associated with this slot_value
        for value in slot_value_processed.split():
            runfile_profiles[profile_name].add_value_for_slot(slot_name, value)

    return runfile_profiles

def runfiles():
    '''
    Yields runfiles located within the runfile_dir
    '''
    for root, dirs, files in os.walk(runfile_dir):
        for runfile in files:
            yield runfile

        #do not want to recurse down the path.
        break

def score_run(runfile_path, truth_profiles, config, metric_name='cosine'):
    '''
    Score a runfile by going through all its discovered entity profiles and
    comparing them to the corresponding truth profiles.
    '''
    #load profiles from the corresponding runfile
    runfile_profiles = profiles_from_runfile(runfile_path, **config)

    #score the runfile-profiles against the truth-profiles.
    score_sum = 0.0
    for entity in runfile_profiles.keys():
        #get profiles to compare
        runfile_profile = runfile_profiles[entity]
        truth_profile = truth_profiles[entity]
        
        score_sum += truth_profile.compare(runfile_profile, metric_name=metric_name)

    return score_sum

'''
configs deal with options that handle the idiosyncrasies of the
different runfiles.
'''
configs = {
    'BUPT_PRIS-ssf1': dict(
        offset_inclusive=False,
        decode_utf=True
    ),
    'BUPT_PRIS-ssf2': dict(
        offset_inclusive=False,
        decode_utf=True,
    ),
    'ecnu-ssf_run': dict(
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

    #load truth-data
    truth_profiles = profiles_from_truthfile(truth_data_path)

    #calculate scores of runfiles
    scores = dict()
    for runfile in runfiles():
        score = score_run(runfile_dir+'/'+runfile, 
                          truth_profiles, 
                          get_config_by_name(runfile), 
                          metric_name='cosine')
        scores[runfile] = score

    print scores

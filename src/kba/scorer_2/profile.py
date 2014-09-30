from __future__ import absolute_import

from collections import defaultdict

from dossier.fc import StringCounter
from treelab.metrics.pairwise import vector

class ScorableProfile(object):

    @staticmethod
    def profiles_from_profilefile(profile_path):
        '''
        Returns dictionary mapping entity-name to ScorableProfile.
        '''
        profile_file = open(profile_path, 'r')
        
        import yaml
        profiles_yaml = yaml.load(profile_file)

        entities = profiles_yaml['entities']
        profiles = dict()
        for ent_name,ent_data in entities.iteritems():
            profile = ScorableProfile(ent_name)
            for slot_name,slot_values in ent_data['slots'].iteritems():
                if isinstance(slot_values, dict):
                    #we are a dict
                    for slot_value in slot_values:
                        profile.add_value_for_slot(slot_name, slot_value['value'])
                elif isinstance(slot_values, list):
                    for slot_value in slot_values:
                        profile.add_value_for_slot(slot_name, slot_value['value'])
                else:
                    profile.add_value_for_slot(slot_name, slot_values.lower())

            profiles[ent_name] = profile

        return profiles
        

    @staticmethod
    def profiles_from_runfile(runfile_path):
        '''
        Go through the runfile and build profiles by collapsing the
        temporal data into single profiles.
        '''
        runfile = open(runfile_path, 'r')
        
        #skip comment at beginning of file
        next(runfile)

        import csv
        profiles = dict()
        csv_reader = csv.reader(runfile, delimiter='\t')
        for row in csv_reader:
            if row[0].startswith('#'):
                continue
            profile_name = row[3]
            slot_name = row[8]
            slot_value = row[9]

            if profile_name not in profiles:
                profiles[profile_name] = ScorableProfile(profile_name, truncate_counts = True)

            profiles[profile_name].add_value_for_slot(slot_name, slot_value.lower().replace('_',' '))

        return profiles
        
        
    
    def __init__(self, profile_name, truncate_counts = False):
        #slot_name -> StringCounter
        self._profile_name = profile_name
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

    def compare(self, other, method='cosine'):
        '''
        Return the comparison function applied between this profile and the other
        ScorableProfile. Right now does basic cosine comparison.
        '''
        score_sum = 0.0
        for slot_name, slot_value in self._slots.iteritems():
            other_slot_value = other._slots[slot_name] #defaults to empty StringCounter
            if method == 'sokalsneath':
                score_sum += sokalsneath(slot_value, other_slot_value)
            else:
                score_sum += vector.dot(slot_value, other_slot_value)

        return score_sum/len(self._slots.keys())

def sokalsneath(sc1, sc2):
    '''
    Runs sokalsneath kernel on two StringCounters
    '''
    both = 0
    anotb = 0
    bnota = 0
    for key in sc1:
        if key in sc2:
            both += 1
        else:
            anotb += 1

    for key in sc2:
        if key in sc2:
            #skip
            pass
        else:
            bnota += 1

    R = 2 * (anotb + bnota)
    if both + R == 0:
        #this means that both s1 and s2 were empty counters
        return 0

    return float(both) / (both + R)

def score_run(runfile_path, profiles, method='cosine'):
    from_runfile = ScorableProfile.profiles_from_runfile(runfile_path)

    score_sum = 0.0
    for entity in from_runfile.keys():
        runfile = from_runfile[entity]
        profile = profiles[entity]
        
        score_sum += runfile.compare(profile, method=method)

    return score_sum / len(from_runfile.keys())
        
if __name__ == '__main__':
    scores = []
    profiles = ScorableProfile.profiles_from_profilefile('/home/josh/git/KBA/2014/judgments/trec-kba-2014-07-11-ccr-and-ssf.profiles.yaml')
    for suffix in xrange(1,15):
        score = score_run('data/SCU-ssf_{}'.format(suffix), profiles, method='sokalsneath')
        scores.append(score)
    print scores

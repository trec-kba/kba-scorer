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
        profiles = yaml.load(profile_file)

        entities = profiles['entities']
        profiles = defaultdict(ScorableProfile)
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
                    profile.add_value_for_slot(slot_name, slot_values)

            profiles[ent_name] = profile

        return profiles
        

    @staticmethod
    def profiles_from_runfile(runfile_path):
        '''
        Go through the runfile and build profiles by collapsing the
        temporal data into single profiles.
        '''
        pass
    
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
            score_sum += vector.dot(slot_value, other_slot_value)

        return score_sum/len(self._slots.keys())
        
if __name__ == '__main__':
    test = ScorableProfile.profiles_from_profilefile('/home/josh/git/KBA/2014/judgments/trec-kba-2014-07-11-ccr-and-ssf.profiles.yaml')
    first,second = test.keys()[0],test.keys()[1]
    test[first].compare(test[first])

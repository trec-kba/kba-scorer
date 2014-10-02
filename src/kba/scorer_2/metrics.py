import math

def get_metric_by_name(name):
    if name == 'sokalsneath':
        return sokalsneath
    elif name == 'cosine':
        return cosine
    elif name == 'dot':
        return dot
    else:
        raise ProgrammingError('No such metric \'{}\''.format(name))

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
        return 0.0

    return float(both) / (both + R)

def cosine(sc1, sc2):
    '''
    Runs cosine kernel on two StringCounters
    '''
    product = dot(sc1,sc2)
    normsc1 = dot(sc1,sc1)
    normsc2 = dot(sc2,sc2)

    #either norm 0 means one of the vectors was a 0 vector.
    if normsc1 == 0 or normsc2 == 0:
        return 0.0

    norm = math.sqrt(normsc1 * normsc2)
    return product / norm

def dot(sc1, sc2):
    dot_sum = 0.0

    #only need to loop through keys in sc1.
    for key in sc1:
        dot_sum += sc1[key] * sc2[key]
            
    return dot_sum

pairs = '''ccr-all-entities-vital-require-positives=4-any-up-cutoff-step-size-1-run-overview.csv,ccr-all-entities-vital+useful-require-positives=4-any-up-cutoff-step-size-1-run-overview.csv
'''

import os, sys

overview_path = 'overviews'

for filenames in pairs.splitlines():
    f1, f2 = filenames.split(',')
    f1 = '.'.join(f1.split('.')[:-1])
    f2 = '.'.join(f2.split('.')[:-1])
    fout = os.path.join(overview_path, f1 + '-' + f2)
    f1 = os.path.join(overview_path, f1)
    f2 = os.path.join(overview_path, f2)
    cmd = './kba/scorer/_runplotter-compare-vital+useful.R %s.csv %s.csv %s.pdf' % (f1, f2, fout)
    os.system(cmd)
    print cmd



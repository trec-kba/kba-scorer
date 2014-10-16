


import os
import sys
import gzip
import json
import zipfile
import argparse
from collections import defaultdict

parser = argparse.ArgumentParser()
parser.add_argument('runs')
parser.add_argument('--path', default='', help='path to use inside zip archive')
args = parser.parse_args()

teams = defaultdict(set)

#BIT-ECQ-ccr-all-entities-vital-microavg-cutoff-step-size-1.csv

POC = defaultdict(set)

for fname in os.listdir(args.runs):
    if not fname.endswith(('.gz', 'png', 'csv')):
        continue

    parts = fname.split('-')
    if not len(parts) >= 2:
        sys.exit('died: ' + fname)
    team_name = parts[0]
    run_name = parts[1]

    if fname.endswith('.gz'):
        run = gzip.open(os.path.join(args.runs, fname))
        run = run.readline()
        run = json.loads(run[1:])
        POC[team_name].add(run['poc_email'])
        print run['poc_email']

    if fname.endswith('png') or fname.endswith('csv'):
        teams[team_name].add(fname)


for team_name, fnames in teams.items():
    zip_fpath = os.path.join(args.runs, '%s.zip' % team_name)
    if os.path.exists(zip_fpath):
        os.remove(zip_fpath)
    fh = zipfile.ZipFile(zip_fpath, 'w', zipfile.ZIP_DEFLATED)

    for fname in fnames:
        fpath = os.path.join(args.runs, fname)
        print fpath
        sys.stdout.flush()
        fh.write(fpath)

    fh.close()

for team_name, poc_emails in POC.items():
    print team_name, poc_emails




import os
import sys
import zipfile
import argparse
from collections import defaultdict

parser = argparse.ArgumentParser()
parser.add_argument('runs')
args = parser.parse_args()

teams = defaultdict(set)


for fname in os.listdir(args.runs):
    if not (fname.endswith('png') or fname.endswith('csv')):
        continue
    parts = fname.split('-')
    if not len(parts) > 2:
        sys.exit(fname)
    team_name = parts[0]
    run_name = parts[1]

    teams[team_name].add(fname)

for team_name, fnames in teams.items():
    fh = zipfile.ZipFile(os.path.join(args.runs, '%s.zip' % team_name), 'w', zipfile.ZIP_DEFLATED)

    for fname in fnames:
        fpath = os.path.join(args.runs, fname)
        print fpath
        sys.stdout.flush()
        fh.write(fpath)

    fh.close()

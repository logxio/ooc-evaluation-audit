#!/usr/bin/env python3
"""Replay the corrected three-way frozen certificate on the rectal source.

The earlier two-way replay is preserved in repository history. This entry point
now uses the same public calibration/deployment pipeline as calibration_replay.py.
"""
import argparse
import json
import tempfile
from pathlib import Path
from blind2_predict import RECTAL
from blind2_score import RECTAL_CLINICAL
from calibration_replay import run_source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    rows = [{'patient': 'Patient' + str(p), 'x': list(v[:2]),
             'y': int(RECTAL_CLINICAL[p][1].lower() in ('0','1','ccr','pcr'))}
            for p,v in RECTAL.items() if 'radiation' in RECTAL_CLINICAL[p][0].lower()]
    with tempfile.TemporaryDirectory() as tmp:
        result = run_source('rectal_2025', rows, Path(tmp))
    text = json.dumps(result, indent=2) + '\n'
    if args.out: args.out.write_text(text)
    print(text)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Certify on a pilot, then apply to new patients: the release certificate on the rectal cohort.

A lab with outcomes for its first patients calibrates a certificate and applies it, frozen, to
the patients who follow. Here the pilot is rectal patients 1-42 and the new patients are 43-128
(patient 109, who received no radiation, is left out of the irradiation pair). The two readouts
are the organoid size ratios after irradiation and after 5-FU; a good response is tumour
regression grade 0-1 or a clinical complete response. The script runs the public command-line
tool exactly as a lab would (`chip_release.py --certify`, then `--certificate`) and only then
reads the new patients' outcomes to count released wrong calls. The rectal outcomes were read
for the second blind test before this script was written, so this is a replay of a frozen
procedure on a fixed split, not a blind test.
"""

import argparse
import csv
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from blind2_predict import RECTAL, RECTAL_BLIND, RECTAL_SEEN
from blind2_score import RECTAL_CLINICAL

ALPHAS = (0.10, 0.15, 0.20)
GOOD = {'0', '1', 'ccr', 'pcr'}


def table(numbers, path, with_outcome):
    with open(path, 'w', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(['patient', 'irradiation', 'fu5'] + (['response'] if with_outcome else []))
        for n in numbers:
            row = [f'Patient{n}', RECTAL[n][0], RECTAL[n][1]]
            writer.writerow(row + ([int(RECTAL_CLINICAL[n][1].lower() in GOOD)] if with_outcome else []))


def tool(*args):
    run = subprocess.run([sys.executable, 'chip_release.py', *args], check=True, text=True, capture_output=True)
    return json.loads(run.stdout)['summary']


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    irradiated = lambda n: 'radiation' in RECTAL_CLINICAL[n][0].lower()
    pilot = [n for n in RECTAL_SEEN if irradiated(n)]
    new = [n for n in RECTAL_BLIND if irradiated(n)]
    truth = {n: RECTAL_CLINICAL[n][1].lower() in GOOD for n in new}
    result = {'schema': 'blind2.certificate.replay.v1', 'pilot_patients': len(pilot), 'new_patients': len(new),
              'new_good_responders': sum(truth.values()), 'levels': []}
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        table(pilot, tmp / 'pilot.csv', True)
        table(new, tmp / 'new.csv', False)
        for alpha in ALPHAS:
            cert = tmp / f'cert_{alpha}.json'
            pilot_summary = tool(str(tmp / 'pilot.csv'), '--a', 'irradiation', '--b', 'fu5', '--outcome', 'response',
                                 '--certify', str(alpha), '--save-certificate', str(cert))
            actions = tmp / f'actions_{alpha}.csv'
            tool(str(tmp / 'new.csv'), '--a', 'irradiation', '--b', 'fu5', '--certificate', str(cert), '--out', str(actions))
            with open(actions, newline='') as handle:
                rows = list(csv.DictReader(handle))
            released = [r for r in rows if r['action'].startswith('release')]
            wrong = [r for r in released if (r['action'] == 'release: sensitive') != truth[int(r['patient'][7:])]]
            result['levels'].append({
                'alpha': alpha, 'pilot': pilot_summary['certificate'],
                'pilot_plain_agreement': {k: pilot_summary[k] for k in ('released', 'released_correct', 'retests')},
                'new_released': len(released), 'new_released_wrong': len(wrong),
                'new_wrong_release_share': round(len(wrong) / len(new), 4),
                'new_released_accuracy': round(1 - len(wrong) / len(released), 4) if released else None,
                'held': len(wrong) / len(new) <= alpha})
    if args.out:
        args.out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()

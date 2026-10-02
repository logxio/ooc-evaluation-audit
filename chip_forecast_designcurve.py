#!/usr/bin/env python3
"""Design-coverage curve: does held-out error fall as each training chemical contributes more of its sparse designs?

Arms at three measured concentrations, folds 1-4: N seeded random designs per training chemical (per-chemical CSVs of
chip_forecast_replay.py --train-designs N), the five published designs (five_designs in chip_forecast_ablations.csv) and
every design (chip_forecast_result.csv). Each arm is compared, paired by chemical, with the every-design model and with
the published neural process (protocol: chip_forecast_designcurve_protocol.json).
Run: python chip_forecast_designcurve.py chip_forecast_runs/curve_n*_fold*.csv
"""
import argparse
import csv
import json
import re
from pathlib import Path

import numpy as np

import chip_forecast as cf

ROOT = Path(__file__).resolve().parent
FOLDS = ('1', '2', '3', '4')


def errors(path, column, value):
    with open(path, newline='') as f:
        return {r['chemical']: float(r['curve_mae']) for r in csv.DictReader(f)
                if r[column] == value and r['k'] == '3' and r['fold'] in FOLDS}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('curves', type=Path, nargs='+')
    p.add_argument('--cache', type=Path, default=ROOT / '.cache' / 'neurochip_twin')
    p.add_argument('--out', type=Path, default=ROOT / 'chip_forecast_designcurve.json')
    a = p.parse_args()
    arms = {}
    for path in a.curves:
        n = re.fullmatch(r'curve_n(\d+)_fold\d\.csv', path.name).group(1)
        arms.setdefault(f'N{n}', {}).update(errors(path, 'method', 'designreplay'))
    arms = dict(sorted(arms.items(), key=lambda kv: int(kv[0][1:])))
    arms['published5'] = errors(ROOT / 'chip_forecast_ablations.csv', 'ablation', 'five_designs')
    arms['all'] = errors(ROOT / 'chip_forecast_result.csv', 'method', 'anchorboost')
    neural = cf.published(cf.fetch(a.cache)['results/trajectory_cv_per_chemical.csv'])[(3, 'neurotrajectory')]
    res = {}
    for name, e in arms.items():
        assert len(e) == 194, (name, len(e))
        res[name] = dict(mean=round(float(np.mean(list(e.values()))), 4))
        if name != 'all':
            res[name]['minus_all'] = cf.paired(e, arms['all'])
        res[name]['minus_neural_process'] = cf.paired(e, neural)
    text = json.dumps(res, indent=1) + '\n'
    a.out.write_text(text)
    print(text, end='')


if __name__ == '__main__':
    main()

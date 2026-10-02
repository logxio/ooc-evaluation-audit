#!/usr/bin/env python3
"""Action list for a chip screen: one row per held-out chemical design, from the registered decision-chain forecasts.

For every held-out (chemical, design) of folds 1-4 this applies the decision chain of chip_forecast_decision.py, whose
release rule is the function behind the patient report list (matched_regimen.py), and writes what the laboratory does
next: report the full-series activity call from the three measured concentrations, or measure the full series. Each row
keeps the measured concentrations, the forecast and measured-only scores, the call, its margin and the release margin,
and, for review, the call the full series gives.
Run: python chip_forecast_actions.py --analyze chip_forecast_runs/decision_fold*.npz --out chip_forecast_actions.csv
"""
import argparse
import csv
import json
from pathlib import Path

import chip_forecast as cf
import chip_forecast_decision as dc

CALL = {0: 'active', 1: 'inactive'}  # chip_forecast_decision labels a chemical 1 when its full-series response stays below 3


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--cache', type=Path, default=dc.ROOT / '.cache' / 'neurochip_twin')
    p.add_argument('--analyze', type=Path, nargs='+', required=True)
    p.add_argument('--test', type=int, nargs='+', default=[1, 2, 3, 4])
    p.add_argument('--out', type=Path, default=dc.ROOT / 'chip_forecast_actions.csv')
    a = p.parse_args()
    tasks = cf.load_tasks(cf.fetch(a.cache)['data_bundle/nfa_tasks.npz'])
    by_chem = {t.chem: t for t in tasks}
    table = dc.rows(tasks, dc.load(a.analyze))
    rules = {f: dc.decide(table, f, 'anchorboost') for f in a.test}
    out = []
    for r in (r for r in table if r['fold'] in a.test):
        design = int(r['patient'].rsplit('|', 1)[1])
        measured = cf.designs(by_chem[r['chem']], dc.K)[design]
        release = bool(r['anchorboost_release'])
        out.append(dict(chemical=r['chem'], fold=r['fold'], design=design,
                        measured_log10_uM=';'.join(f'{v:g}' for v in measured),
                        action='report call' if release else 'measure full series',
                        call=CALL[r['anchorboost_call']], margin=round(r['anchorboost_margin'], 4),
                        release_margin=rules[r['fold']]['margin'], forecast_score=round(r['anchorboost'], 4),
                        measured_only_score=round(r['measured_only'], 4), full_series_call=CALL[r['y']],
                        released_call_wrong=int(r['anchorboost_call'] != r['y']) if release else '',
                        wells_measured=r['wells_measured'], wells_full=r['wells_full']))
    with open(a.out, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    reported = [r for r in out if r['action'] == 'report call']
    used = sum(r['wells_measured'] if r['action'] == 'report call' else r['wells_full'] for r in out)
    print(json.dumps(dict(designs=len(out), chemicals=len({r['chemical'] for r in out}), report_call=len(reported),
                          measure_full_series=len(out) - len(reported),
                          wrong_reported_calls=sum(r['released_call_wrong'] for r in reported),
                          wells_saved_fraction=round(1 - used / sum(r['wells_full'] for r in out), 4)), indent=1))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Recompute frozen k=3 opponent comparisons from saved per-compound errors."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
BASE = ROOT / 'results/final/opponents'


def read_json(path):
    return json.loads(path.read_text())


def verify_hashes():
    manifest = read_json(BASE / 'manifest.json')
    for item in manifest['files']:
        path = ROOT / item['path']
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != item['sha256']:
            raise ValueError('Hash mismatch: ' + item['path'])
    return len(manifest['files'])


def csv_rows(path):
    with path.open(newline='') as handle:
        return list(csv.DictReader(handle))


def interval(delta, groups, replicates, seed):
    names = sorted(set(groups))
    position = {name: i for i, name in enumerate(names)}
    totals = np.zeros(len(names))
    counts = np.zeros(len(names))
    for value, group in zip(delta, groups):
        totals[position[group]] += value
        counts[position[group]] += 1
    indices = np.random.default_rng(seed).integers(0, len(names), (replicates, len(names)))
    values = totals[indices].sum(1) / counts[indices].sum(1)
    return np.percentile(values, [2.5, 97.5], method='linear').tolist(), len(names)


def summarize():
    verified = verify_hashes()
    protocol = read_json(BASE / 'protocol.json')
    reference = [row for row in csv_rows(ROOT / protocol['reference_per_chemical'])
                 if int(row['k']) == protocol['k'] and int(row['fold']) in protocol['folds']]
    anchor = {row['chemical']: row for row in reference if row['method'] == 'anchorboost'}
    if len(anchor) != protocol['primary_cohort']:
        raise ValueError('Unexpected baseline cohort')
    results = []
    for config in protocol['configurations']:
        cohort = set(anchor)
        if config['cohort'] == 'common_193':
            cohort.remove(protocol['common_cohort_exclusion'])
        if 'reference_method' in config:
            rows = [row for row in reference if row['method'] == config['reference_method']]
        else:
            rows = [row for row in csv_rows(ROOT / config['per_chemical']) if int(row['k']) == protocol['k']]
        candidates = {row['chemical']: row for row in rows if row['chemical'] in cohort}
        if len(candidates) != len([row for row in rows if row['chemical'] in cohort]):
            raise ValueError('Duplicate compound: ' + config['key'])
        if set(candidates) != cohort:
            raise ValueError('Incomplete frozen cohort: ' + config['key'])
        names = sorted(cohort)
        if any(candidates[name]['identity_group'] != anchor[name]['identity_group'] for name in names):
            raise ValueError('Identity mapping mismatch: ' + config['key'])
        ours = np.array([float(anchor[name]['mae']) for name in names])
        theirs = np.array([float(candidates[name]['mae']) for name in names])
        if not np.isfinite(ours).all() or not np.isfinite(theirs).all():
            raise ValueError('Non-finite error: ' + config['key'])
        delta = ours - theirs
        ci, groups = interval(delta, [anchor[name]['identity_group'] for name in names],
                              protocol['bootstrap']['replicates'], protocol['bootstrap']['seed'])
        row = dict(key=config['key'], label=config['label'], family=config['family'],
                   cohort=config['cohort'], n_compounds=len(names), n_identity_groups=groups,
                   anchorboost_mae=float(ours.mean()), opponent_mae=float(theirs.mean()),
                   paired_difference=float(delta.mean()), ci95=ci,
                   relative_difference_pct=float(100 * delta.mean() / theirs.mean()),
                   compounds_anchorboost_better=int((delta < 0).sum()),
                   outcome='win' if ci[1] < 0 else 'loss' if ci[0] > 0 else 'tie')
        if 'saved_summary' in config:
            saved = read_json(ROOT / config['saved_summary'])['summary']['k3'][config['cohort']]
            if not np.isclose(row['opponent_mae'], saved['mae'], rtol=0, atol=1e-12):
                raise ValueError('Saved mean mismatch: ' + config['key'])
            comparison = saved.get('versus', {}).get('anchorboost')
            if comparison is not None:
                expected_ci = [-comparison['ci95_identity'][1], -comparison['ci95_identity'][0]]
                if not np.allclose(ci, expected_ci, rtol=0, atol=1e-12):
                    raise ValueError('Saved paired interval mismatch: ' + config['key'])
                if not np.isclose(row['paired_difference'], -comparison['mean_diff'], rtol=0, atol=1e-12):
                    raise ValueError('Saved paired difference mismatch: ' + config['key'])
        results.append(row)
    counts = {outcome: sum(row['outcome'] == outcome for row in results) for outcome in ['win', 'tie', 'loss']}
    families = {}
    for row in results:
        families.setdefault(row['family'], []).append(row['outcome'])
    family_outcomes = {name: 'loss' if 'loss' in outcomes else 'win' if set(outcomes) == {'win'} else 'tie'
                       for name, outcomes in sorted(families.items())}
    return dict(schema='final.opponents.summary.v1', k=3, baseline_mae=float(np.mean([float(row['mae']) for row in anchor.values()])),
                baseline_n_compounds=len(anchor), configuration_counts=counts,
                family_counts={outcome: list(family_outcomes.values()).count(outcome) for outcome in counts},
                family_outcomes=family_outcomes, comparisons=results)


def numbers(summary):
    command = 'python paper_final_opponents.py summarize'
    entries = []
    def add(key, value, unit, field, ci=None):
        row = dict(key='opponents.'+key, value=value, unit=unit, group='opponents',
                   source_file='results/final/opponents/summary.json', field=field, command=command)
        if ci is not None:
            row['ci95'] = ci
        entries.append(row)
    add('anchorboost_mae', summary['baseline_mae'], 'MAE', 'baseline_mae')
    add('baseline_compounds', summary['baseline_n_compounds'], 'compounds', 'baseline_n_compounds')
    for label in ['configuration_counts', 'family_counts']:
        for outcome, count in summary[label].items():
            add(label+'.'+outcome, count, 'configurations' if label.startswith('configuration') else 'families', label+'.'+outcome)
    for i, row in enumerate(summary['comparisons']):
        for name, unit in [('n_compounds','compounds'),('n_identity_groups','groups'),('anchorboost_mae','MAE'),
                           ('opponent_mae','MAE'),('paired_difference','MAE'),('relative_difference_pct','percent'),
                           ('compounds_anchorboost_better','compounds')]:
            add(row['key']+'.'+name, row[name], unit, f'comparisons[{i}].{name}', row['ci95'] if name == 'paired_difference' else None)
    return entries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['summarize', 'verify'])
    parser.add_argument('--write', action='store_true', help='Update derived summary and numbers from the frozen inputs')
    args = parser.parse_args()
    result = summarize()
    generated_numbers = numbers(result)
    if args.write:
        if args.action != 'summarize':
            parser.error('--write requires summarize')
        (BASE / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
        (BASE / 'numbers.json').write_text(json.dumps(generated_numbers, indent=2) + '\n')
    elif read_json(BASE / 'summary.json') != result or read_json(BASE / 'numbers.json') != generated_numbers:
        raise ValueError('Saved derived output differs from recomputation')
    print(json.dumps(result if args.action == 'summarize' else {'verified': True, 'configurations': len(result['comparisons']),
          'configuration_counts': result['configuration_counts'], 'family_counts': result['family_counts']}, indent=2))


if __name__ == '__main__':
    main()

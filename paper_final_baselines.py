#!/usr/bin/env python3
"""Recompute the baseline scoreboard from compact per-chemical errors.

Run: python paper_final_baselines.py
Requires NumPy. No model weights, network access, or training are used.
Negative paired differences favor the named AnchorBoost reference.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np

DEFAULT = Path(__file__).resolve().parent / 'results' / 'final' / 'baselines'


def read_inputs(root):
    meta = json.loads((root / 'methods.json').read_text())
    data, identities = {}, {}
    for method in meta['methods']:
        mid = method['id']
        for k in method['available_k']:
            path = root / f'{mid}_k{k}.csv'
            rows = {}
            for r in csv.DictReader(path.open(newline='')):
                c = r['chemical']
                assert r['method'] == mid and int(r['k']) == k, path
                assert int(r['fold']) in meta['cohort']['folds'], path
                assert c not in rows, (path, c)
                value = float(r['mae'])
                assert np.isfinite(value) and value >= 0, (path, c)
                identity = r['identity_group']
                assert c not in identities or identities[c] == identity, c
                identities[c] = identity
                rows[c] = (identity, int(r['fold']), value)
            assert rows, path
            expected = method.get('csv_sha256', {}).get(str(k))
            if expected:
                assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, path
            data[mid, k] = rows
    for reference in meta['references']:
        for k in range(1, 5):
            rows = data[reference, k]
            assert len(rows) == meta['cohort']['chemicals']
            assert len({r[0] for r in rows.values()}) == meta['cohort']['identity_groups']
            first = data[meta['references'][0], k]
            assert {c: r[:2] for c, r in rows.items()} == {c: r[:2] for c, r in first.items()}
    return meta, data


def paired(reference_rows, other, replicates, seed, cache):
    keys = sorted(reference_rows.keys() & other.keys())
    assert keys
    assert all(reference_rows[c][:2] == other[c][:2] for c in keys)
    groups = tuple(reference_rows[c][0] for c in keys)
    names = sorted(set(groups))
    index = {g: i for i, g in enumerate(names)}
    delta = np.array([reference_rows[c][2] - other[c][2] for c in keys])
    total = np.bincount([index[g] for g in groups], weights=delta, minlength=len(names))
    count = np.bincount([index[g] for g in groups], minlength=len(names))
    cache_key = (groups, replicates, seed)
    if cache_key not in cache:
        draws = np.random.default_rng(seed).integers(0, len(names), (replicates, len(names)))
        cache[cache_key] = (draws, count[draws].sum(axis=1))
    draws, denominator = cache[cache_key]
    boot = total[draws].sum(axis=1) / denominator
    lo, hi = np.percentile(boot, [2.5, 97.5])
    return dict(paired_n=len(keys), paired_groups=len(names),
                reference_mae=float(np.mean([reference_rows[c][2] for c in keys])),
                opponent_mae=float(np.mean([other[c][2] for c in keys])),
                difference=float(delta.mean()), ci_low=float(lo), ci_high=float(hi),
                outcome='win' if hi < 0 else 'loss' if lo > 0 else 'tie',
                chemical_wins=int((delta < -1e-12).sum()),
                chemical_ties=int((np.abs(delta) <= 1e-12).sum()),
                chemical_losses=int((delta > 1e-12).sum()))


def compute(root):
    meta, data = read_inputs(root)
    rows, cache = [], {}
    comparisons = ['paired_n', 'paired_groups', 'reference_mae', 'opponent_mae',
                   'difference', 'ci_low', 'ci_high', 'outcome',
                   'chemical_wins', 'chemical_ties', 'chemical_losses']
    for method in meta['methods']:
        mid = method['id']
        for k in range(1, 5):
            values = data.get((mid, k), {})
            comparable = method.get('comparable', True)
            row = dict(method=mid, name=method['name'], k=k, role=method['role'],
                       family=method['family'], answer_seen=method['answer_seen'],
                       commercial_use=method['commercial_use'],
                       code_license=method['code_license'], weights_license=method['weights_license'],
                       status=('available' if comparable else 'different_protocol') if values else 'missing',
                       protocol=method.get('protocol', 'standard_194'),
                       n_chemicals=len(values), n_identity_groups=len({v[0] for v in values.values()}),
                       mae=float(np.mean([v[2] for v in values.values()])) if values else None,
                       bootstrap_replicates=method['bootstrap_replicates'],
                       bootstrap_seed=method['bootstrap_seed'])
            for reference in meta['references']:
                result = paired(data[reference, k], values, method['bootstrap_replicates'],
                                method['bootstrap_seed'], cache) if values and comparable else {}
                row.update({reference + '_' + key: result.get(key) for key in comparisons})
            rows.append(row)
    counts = []
    for reference in meta['references']:
        for k in range(1, 5):
            eligible = [r for r in rows if r['k'] == k and r['role'] == 'opponent'
                        and not r['answer_seen'] and r['status'] == 'available']
            counts.append(dict(reference=reference, k=k, opponents=len(eligible),
                               **{outcome: sum(r[reference + '_outcome'] == outcome for r in eligible)
                                  for outcome in ['win', 'tie', 'loss']}))
    summary = dict(schema='baseline_scoreboard.v1',
                   command='python paper_final_baselines.py',
                   metric='Mean of per-chemical MAE; five equally weighted designs per chemical.',
                   paired_difference='reference minus opponent; negative favors the reference',
                   interval='95% percentile paired identity-cluster bootstrap; chemicals in each sampled identity stay together; chemical-weighted mean within each resample.',
                   outcome='win: upper limit < 0; loss: lower limit > 0; tie: otherwise',
                   counts_scope='Available comparable opponent method rows with answer_seen=false; own versions, controls and research committee excluded. Variants are counted separately, not as independent model families. Intervals are unadjusted for multiple comparisons.',
                   cohort=meta['cohort'], references=meta['references'], counts=counts, rows=rows)
    for filename, content in [('scoreboard.json', json.dumps(summary, indent=2, ensure_ascii=True) + '\n')]:
        temporary = root / (filename + '.tmp')
        temporary.write_text(content)
        temporary.replace(root / filename)
    temporary = root / 'scoreboard.csv.tmp'
    with temporary.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(root / 'scoreboard.csv')
    print(json.dumps(dict(methods=len(meta['methods']), available_cells=sum(r['status'] == 'available' for r in rows),
                          missing_cells=sum(r['status'] == 'missing' for r in rows), counts=counts), indent=2))
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=DEFAULT)
    compute(parser.parse_args().data_dir)

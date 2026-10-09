#!/usr/bin/env python3
"""Recompute held-out decisions and paired intervals from public frozen rows."""
import os
for _name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS'):
    os.environ[_name] = '1'
import sys
sys.dont_write_bytecode = True
import argparse
import csv
import gzip
import hashlib
import importlib.util
import json
import math
from collections import defaultdict
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parent

def load(path):
    path = Path(path)
    return json.loads(gzip.decompress(path.read_bytes()) if path.suffix == '.gz' else path.read_bytes())

def csv_rows(path):
    with Path(path).open(newline='') as stream:
        return list(csv.DictReader(stream))

def module(path):
    spec = importlib.util.spec_from_file_location('frozen_statistics_' + path.parent.name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

def frozen_sha(path, redactions):
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    relative = path.relative_to(ROOT).as_posix()
    for record in redactions['files']:
        if record['path'] == relative:
            if actual != record['redacted_sha256']:
                raise AssertionError('Public hash mismatch: ' + relative)
            return record['original_sha256']
    return actual

def verify(group):
    base = ROOT / 'results/final' / group
    manifest = load(base / 'manifest.json')
    redactions = load(ROOT / 'results/REDACTIONS.json')
    for rel, expected in manifest['sha256'].items():
        path = ROOT / rel
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, rel
    for record in redactions['files']:
        if not record['path'].startswith('results/final/' + group + '/'):
            continue
        assert frozen_sha(ROOT / record['path'], redactions) == record['original_sha256']
    return base, manifest

def compare(actual, expected, where='root'):
    """Compare all recomputed fields, with tolerance only for floating arithmetic."""
    if isinstance(actual, dict):
        for key, value in actual.items():
            if key == 'defined_resamples' and key not in expected:
                continue
            compare(value, expected[key if key in expected else str(key)], where + '/' + str(key))
    elif isinstance(actual, (list, tuple)):
        assert len(actual) == len(expected), where
        for index, value in enumerate(actual):
            compare(value, expected[index], where + '/' + str(index))
    elif isinstance(actual, (int, float, np.number)) and not isinstance(actual, bool):
        assert math.isclose(float(actual), float(expected), abs_tol=1e-9, rel_tol=1e-9), (where, actual, expected)
    else:
        assert actual == expected, (where, actual, expected)

def typed(rows):
    for row in rows:
        for key, value in list(row.items()):
            if key.endswith('_release') or key == 'lane':
                row[key] = value in ('True', '1')
            elif key.endswith('_call') or key in ('truth', 'wells_measured', 'wells_full', 'outer_fold', 'design'):
                row[key] = int(value)
    return rows

def numbers_for(group):
    entries = load(ROOT / 'results/final' / group / 'numbers.json')
    cache = {}
    for entry in entries:
        source = entry['source_file']
        if source not in cache:
            cache[source] = load(ROOT / source)
        value = cache[source]
        for part in entry['field'].strip('/').split('/'):
            key = part.replace('~1', '/').replace('~0', '~')
            value = value[int(key)] if isinstance(value, list) else value[key]
        expected = value.get('estimate', value.get('point')) if isinstance(value, dict) else value
        compare(entry['value'], expected, entry['key'])
        if 'ci95' in entry:
            compare(entry['ci95'], value['ci95'], entry['key'] + '/ci95')
    return entries

def digest(v):
    return hashlib.sha256(json.dumps(v, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

def getmeta(ids):
    g = defaultdict(lambda: {'chemicals': [], 'plates': set(), 'dates': set(), 'pairs': set()})
    for name, row in ids.items():
        q = g[row['drug_group']]
        q['chemicals'].append(name)
        for batch in row['batches']:
            plate, date = batch.rsplit('|', 1)
            q['plates'].add(plate)
            q['dates'].add(date)
            q['pairs'].add(batch)
    return g

def components(g, strict):
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]

    def join(a, b):
        parent[find(a)] = find(b)
    for group, v in g.items():
        node = 'identity:' + group
        find(node)
        for kind in ['plates', 'dates'] if strict else ['pairs']:
            for key in v[kind]:
                join(node, kind + ':' + key)
    blocks = defaultdict(list)
    for group in g:
        blocks[find('identity:' + group)].append(group)
    out = []
    for groups in blocks.values():
        out.append({'groups': sorted(groups), 'n_groups': len(groups), 'n_substances': sum((len(g[x]['chemicals']) for x in groups)), **{'n_' + k: len(set().union(*(g[x][k] for x in groups))) for k in ['plates', 'dates', 'pairs']}})
    return sorted(out, key=lambda x: (-x['n_groups'], digest(x['groups'])))

def count(names, ids, g):
    groups = {ids[x]['drug_group'] for x in names}
    return {'substances': len(names), 'identities': len(groups), **{k: len(set().union(*(g[x][k] for x in groups))) for k in ['plates', 'dates', 'pairs']}}

def metadata_counts(base):
    ids = load(base / 'common/identities.json')
    groups = getmeta(ids)
    feasibility = load(base / 'common/feasibility.json')
    strict = components(groups, True)
    compare(strict, feasibility['strict_graph']['components'], 'strict_graph')
    compare(len(groups), feasibility['total']['identities'], 'identity_count')
    compare(len(strict), feasibility['strict_graph']['n_components'], 'component_count')
    splits = load(base / 'common/strict_splits.json')
    for fold, split in splits.items():
        for role in ['train', 'calibration', 'test']:
            value = count(split[role], ids, groups)
            compare(value['identities'], split['group_counts'][role], 'split/' + fold + '/' + role)
            compare(value, feasibility['folds'][fold]['retained'][role], 'retained/' + fold + '/' + role)
    return dict(identities=len(groups), substances=len(ids), strict_components=len(strict),
                fold0_groups=splits['0']['group_counts'])


def summarize():
    base, manifest = verify('heldout')
    metadata = metadata_counts(base)
    stats = module(base / 'statistics.py')
    source = load(base / 'r2/summary.json')
    rows = typed(csv_rows(base / 'r2/design_decisions.csv'))
    reconstructed = {}
    for arm in ('B', 'A'):
        for variant in ('lane', 'no_lane'):
            for population in ('pooled', 'fold0', 'fold1_to_4'):
                selected = [r for r in rows if r['arm'] == arm and r['variant'] == variant and (population == 'pooled' or (r['outer_fold'] == 0) == (population == 'fold0'))]
                actual = stats.aggregate(selected)
                compare(actual, source['arms'][arm]['variants'][variant][population], arm + '/' + variant + '/' + population)
                reconstructed[arm + '/' + variant + '/' + population] = actual
    rec = csv_rows(base / 'common/reconstruction_designs.csv')
    for arm in ('B', 'A'):
        for population in ('pooled', 'fold0', 'fold1_to_4'):
            selected = [r for r in rec if r['arm'] == arm and r['regime'] == 'R2' and r['primary_population'] == '1' and (population == 'pooled' or (r['outer_fold'] == '0') == (population == 'fold0'))]
            groups = sorted({r['drug_group'] for r in selected})
            values = {method: np.array([np.mean([float(r[method + '_mae']) for r in selected if r['drug_group'] == g]) for g in groups]) for method in ('anchorboost', 'loglinear')}
            W = stats.weights(len(groups))
            a, b = values['anchorboost'], values['loglinear']
            actual = {'anchorboost': stats.ci(a.mean(), W @ a / len(groups)), 'interpolation': stats.ci(b.mean(), W @ b / len(groups)), 'relative_reduction': stats.ci(1 - a.mean() / b.mean(), 1 - (W @ a) / (W @ b)), 'anchorboost_minus_interpolation': stats.ci((a-b).mean(), W @ (a-b) / len(groups)), 'identities_anchorboost_better': int((a < b).sum())}
            compare(actual, source['arms'][arm]['reconstruction_cited'][population], 'reconstruction/' + arm + '/' + population)
    temporal = load(base / 'temporal/summary.json')
    temporal_rows = typed(csv_rows(base / 'temporal/design_decisions.csv'))
    temporal_results = {}
    for year in ('2016', '2017'):
        reference = temporal['units']['B/H/' + year]
        selected = [r for r in temporal_rows if r['arm'] == 'B' and r['split'] == 'H' and int(r['origin']) == reference['origin']]
        for row in selected:
            row['observed_active_fallback_call'] = row['measured_only_call']
        actual = stats.aggregate(selected)
        for method, key in [('anchorboost','full'), ('measured_only','measured_only'), ('loglinear','interpolation')]:
            for metric in ('reports','wrong_reports','wells_used','wells_full','full_coverage_errors'):
                compare(actual['methods'][method][metric], reference['decisions']['methods'][key][metric], year + '/' + method + '/' + metric)
        compare(actual['paired']['measured_only']['cost_savings'], reference['decisions']['paired']['full_minus_measured_only']['well_saving'], year + '/well_saving')
        temporal_results[year] = actual['paired']['measured_only']['cost_savings']
    entries = numbers_for('heldout')
    return {'group': 'heldout', 'metadata': metadata, 'input_files_verified': len(manifest['sha256']), 'number_entries_verified': len(entries), 'bootstrap_replicates': 4000, 'decision_tables_recomputed': 12, 'reconstruction_tables_recomputed': 6, 'large_archive_B': reconstructed['B/lane/fold1_to_4'], 'small_archive_B': reconstructed['B/lane/fold0'], 'temporal_B_well_saving': temporal_results}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['summarize', 'verify'])
    parser.add_argument('--numbers', action='store_true')
    args = parser.parse_args()
    result = summarize()
    print(json.dumps(numbers_for('heldout') if args.numbers else result, indent=2, allow_nan=False))
if __name__ == '__main__':
    main()

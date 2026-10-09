#!/usr/bin/env python3
"""Recompute saved EPA label agreement and paired intervals without fitting.

The stratified group bootstrap follows the frozen external-label analysis.
Only the three requested primary readouts are recomputed. Other saved tables
are retained as historical outputs and covered by the input hash manifest.
"""
import os
for _name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS'):
    os.environ[_name] = '1'
import csv
import hashlib
import json
import resource
import sys
import time
from collections import defaultdict
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent
BASE = ROOT / 'results/final/labels'
READOUTS = ('full_series', 'chain_anchorboost', 'chain_measured_only')
METRICS = ('sensitivity', 'specificity', 'balanced_accuracy', 'agreement', 'kappa')


def read_json(path):
    return json.loads(path.read_text())


def verify_hashes():
    manifest = read_json(BASE / 'manifest.json')
    for name, digest in manifest['files'].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
    return len(manifest['files'])


def frozen_sha(path):
    """Validate public bytes and return the original pre-redaction digest."""
    relative = str(path.relative_to(ROOT))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    matches = [r for r in read_json(ROOT / 'results/REDACTIONS.json')['files'] if r['path'] == relative]
    if matches:
        assert len(matches) == 1 and digest == matches[0]['redacted_sha256']
        return matches[0]['original_sha256']
    return digest


def weights_matrix(rows, replicates, seed):
    groups = defaultdict(list)
    for i, row in enumerate(rows):
        groups[row['drug_group']].append(i)
    strata = {'Positive': [], 'Negative': [], 'mixed': []}
    for group in sorted(groups):
        labels = {rows[i]['appendix_a'] for i in groups[group]}
        strata[next(iter(labels)) if len(labels) == 1 else 'mixed'].append(group)
    rng = np.random.default_rng(seed)
    weights = np.zeros((replicates + 1, len(rows)))
    weights[0] = 1
    for b in range(1, replicates + 1):
        for name in ('Positive', 'Negative', 'mixed'):
            gs = strata[name]
            if gs:
                for j in rng.integers(0, len(gs), len(gs)):
                    for i in groups[gs[j]]:
                        weights[b, i] += 1
    return weights, {k: len(v) for k, v in strata.items()}


def stats(weights, negative, inactive, count):
    a = weights @ ((1 - negative) * (count - inactive))
    b = weights @ ((1 - negative) * inactive)
    c = weights @ (negative * (count - inactive))
    d = weights @ (negative * inactive)
    n = a + b + c + d
    sensitivity, specificity = a / (a + b), d / (c + d)
    agreement = (a + d) / n
    chance = ((a + b) * (a + c) + (c + d) * (b + d)) / n ** 2
    return dict(sensitivity=sensitivity, specificity=specificity,
                balanced_accuracy=(sensitivity + specificity) / 2,
                agreement=agreement, kappa=(agreement - chance) / (1 - chance)), [float(x[0]) for x in (a, b, c, d)]


def ci(values):
    return [float(values[0]), *map(float, np.quantile(values[1:], [.025, .975]))]


def check(actual, expected):
    assert np.allclose(actual, expected, atol=1e-10, rtol=1e-10), (actual, expected)


def calculate():
    assert frozen_sha(BASE / 'protocol.json') == read_json(BASE / 'lane_B_R1/results.json')['protocol_sha256']
    outputs = {}
    for version in ('lane_B_R1', 'common_scale_B_R1'):
        folder = BASE / version
        saved = read_json(folder / 'results.json')
        primary = saved['sets']['primary']
        with (folder / 'supplementary_table_external_labels.csv').open(newline='') as f:
            rows = sorted((r for r in csv.DictReader(f)
                           if r['appendix_a'] in ('Positive', 'Negative')
                           and int(r['outer_fold']) in (1, 2, 3, 4)), key=lambda r: r['substance'])
        with (folder / 'design_decisions.csv').open(newline='') as f:
            designs = defaultdict(list)
            for row in csv.DictReader(f):
                if row['arm'] == 'B' and row['regime'] == 'R1' and row['primary_population'] == '1':
                    designs[row['chemical']].append(row)
        negative = np.array([r['appendix_a'] == 'Negative' for r in rows], int)
        assert len(rows) == primary['substances'] == 74
        assert int(negative.sum()) == primary['negative'] == 19
        weights, strata = weights_matrix(rows, **saved['bootstrap'])
        assert strata == primary['bootstrap_strata_groups']
        samples, majority, cells = {}, {}, {}
        for readout in READOUTS:
            counts = []
            for row in rows:
                dd = designs[row['substance']]
                assert len(dd) == 5
                if readout == 'full_series':
                    value = sum(int(d['truth']) for d in dd)
                    assert value == 5 * (row['full_series_call'] == 'inactive')
                else:
                    method = readout.removeprefix('chain_')
                    value = sum(int(d[method + '_call']) if d[method + '_release'] == 'True' else int(d['truth']) for d in dd)
                    assert value == int(row[readout + '_inactive_of_5'])
                counts.append(value)
            inactive = np.array(counts, float)
            samples[readout], table = stats(weights, negative, inactive, 5)
            majority[readout], _ = stats(weights, negative, (inactive >= 3).astype(float), 1)
            cell = {metric: ci(samples[readout][metric]) for metric in METRICS}
            cell['design_table_pos_active_pos_inactive_neg_active_neg_inactive'] = table
            cell['majority'] = {m: ci(majority[readout][m]) for m in METRICS if m != 'agreement'}
            expected = primary['readouts'][readout]
            for metric in METRICS:
                check(cell[metric], expected[metric])
            check(table, expected['design_table_pos_active_pos_inactive_neg_active_neg_inactive'])
            for metric in cell['majority']:
                check(cell['majority'][metric], expected['majority'][metric])
            cells[readout] = cell
        for readout in READOUTS[1:]:
            cells[readout]['minus_full_series'] = {}
            for metric in ('balanced_accuracy', 'kappa', 'sensitivity', 'specificity'):
                value = ci(samples[readout][metric] - samples['full_series'][metric])
                check(value, primary['readouts'][readout]['minus_full_series'][metric])
                cells[readout]['minus_full_series'][metric] = value
        release_results = {}
        for readout, expected in saved['table2_release'].items():
            method = readout.removeprefix('chain_')
            released, errors, reference_errors = [], [], []
            for row, label in zip(rows, negative):
                dd = [d for d in designs[row['substance']] if d[method + '_release'] == 'True']
                released.append(len(dd))
                errors.append(sum(int(int(d[method + '_call']) != label) for d in dd))
                reference_errors.append(sum(int(int(d['truth']) != label) for d in dd))
            denominator = weights @ np.array(released, float)
            rate = (weights @ np.array(errors, float)) / denominator
            reference_rate = (weights @ np.array(reference_errors, float)) / denominator
            cell = dict(released_designs=sum(released), designs=5 * len(rows),
                        released_disagree_expert=sum(errors),
                        full_series_disagree_expert_same_designs=sum(reference_errors),
                        rate=ci(rate), full_series_rate_same_designs=ci(reference_rate),
                        difference=ci(rate - reference_rate))
            for key, value in cell.items():
                check(value, expected[key])
            release_results[readout] = cell
        outputs[version] = dict(substances=len(rows), positive=int((1 - negative).sum()),
                                negative=int(negative.sum()), drug_groups=sum(strata.values()),
                                bootstrap=saved['bootstrap'], readouts=cells, release_table=release_results)
    return outputs


def main():
    assert len(sys.argv) == 2 and sys.argv[1] in ('summarize', 'verify'), 'Use: python paper_final_labels.py summarize'
    start = time.monotonic()
    hashes = verify_hashes()
    result = calculate()
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == 'darwin' else 1024)
    assert rss < 1_000_000_000
    print(json.dumps(dict(status='verified', input_hashes=hashes, new_fits=0,
                          seconds=time.monotonic() - start, peak_rss_bytes=rss,
                          tables=result), indent=2, allow_nan=False))


if __name__ == '__main__':
    main()

"""Shared readers and frozen-file verification for the final saved-results tables."""
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
os.environ.setdefault('OMP_NUM_THREADS', '1')
os.environ.setdefault('VECLIB_MAXIMUM_THREADS', '1')
import csv
import gzip
import hashlib
import json
import math
from fractions import Fraction
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent
FINAL = ROOT / 'results/final'

def load(path):
    path = Path(path)
    text = gzip.open(path, 'rt') if path.suffix == '.gz' else path.open()
    with text as f:
        return json.load(f)

def rcsv(path):
    path = Path(path)
    text = gzip.open(path, 'rt', newline='') if path.suffix == '.gz' else path.open(newline='')
    with text as f:
        return list(csv.DictReader(f))

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def frozen_sha(path):
    path = Path(path).resolve()
    actual = sha(path)
    for r in load(ROOT / 'results/REDACTIONS.json')['files']:
        if r['path'] == str(path.relative_to(ROOT)):
            if actual != r['redacted_sha256']:
                raise ValueError('Published hash mismatch: ' + r['path'])
            return r['original_sha256']
    return actual

def verify(group):
    manifest = load(FINAL / group / 'manifest.json')
    for r in manifest['files']:
        p = ROOT / r['path']
        if sha(p) != r['sha256']:
            raise ValueError('Input hash mismatch: ' + r['path'])
        if frozen_sha(p) != r['original_sha256']:
            raise ValueError('Frozen hash mismatch: ' + r['path'])
    return len(manifest['files'])

def same(actual, expected, path='', tol=1e-8):
    """Compare every field in a recomputed subset, including interval endpoints."""
    if isinstance(actual, dict):
        for k, v in actual.items():
            same(v, expected[k], path + '/' + str(k), tol)
    elif isinstance(actual, (list, tuple, np.ndarray)):
        if len(actual) != len(expected):
            raise AssertionError((path, len(actual), len(expected)))
        for i, (a, b) in enumerate(zip(actual, expected)):
            same(a, b, path + '/' + str(i), tol)
    elif isinstance(actual, (int, float, np.number)) and not isinstance(actual, bool):
        if not math.isclose(float(actual), float(expected), abs_tol=tol, rel_tol=1e-10):
            raise AssertionError((path, actual, expected))
    elif actual != expected:
        raise AssertionError((path, actual, expected))

def interval(point, samples):
    samples = np.asarray(samples, float)
    samples = samples[np.isfinite(samples)]
    return {'estimate': float(point), 'ci95': np.quantile(samples, [.025, .975]).tolist()}

def bootstrap():
    z = np.load(FINAL / 'reporting/bootstrap_identity_counts_seed0.npz', allow_pickle=False)
    names, W = z['groups'].tolist(), z['counts'].astype(float)
    generated = np.array([np.bincount(r, minlength=len(names)) for r in
        np.random.default_rng(0).integers(0, len(names), (4000, len(names)))])
    if not np.array_equal(W, generated):
        raise AssertionError('Bootstrap draw does not match its frozen seed')
    return names, W

def exact_rule(rule, x):
    ref = np.asarray(rule['reference'])
    dens = [int(round(1 / w)) for w in rule['weights']]
    if any(1 / d != w for d, w in zip(dens, rule['weights'])):
        raise ValueError('Rank weights must be reciprocal integers')
    scale = math.lcm(*dens)
    counts = np.array([scale // d for d in dens], dtype=np.int64)
    def rank2(v):
        return 2 * int(counts[ref < v].sum()) + int(counts[ref == v].sum())
    margin = Fraction(abs(rank2(x) - rank2(rule['cutoff'])), 2 * int(counts.sum()))
    return int(x <= rule['cutoff']), margin

def decision_rows(arm, lane=True):
    folder = FINAL / 'reporting'
    lambdas = load(folder / 'three_point_lambdas.json')[arm]
    rows = []
    for fold in range(1, 5):
        sub = folder / arm / f'fold{fold}'
        rules = load(sub / 'training_rules.json')['methods']
        cal = load(sub / 'calibration.json')
        for original in load(sub / 'design_decisions.json'):
            r = dict(original)
            is_lane = lane and r['measured_only'] >= 3
            if is_lane and r['truth'] != 0:
                raise AssertionError('Observed-active rule disagrees with the reference')
            for m in ['anchorboost', 'measured_only', 'loglinear']:
                call, margin = exact_rule(rules[m], r[m])
                same(call, r[m + '_call'])
                same(float(margin), r[m + '_margin'])
                lam = lambdas[str(fold)][m]['lambda'] if lane else cal[m]['margin']
                r[m + '_exact'] = (margin.numerator, margin.denominator)
                r[m + '_call'] = 0 if is_lane else call
                r[m + '_release'] = bool(is_lane or margin > Fraction(repr(lam)))
            rows.append(r)
    return rows

def numeric_entries(obj, prefix, group, source, command, pointer=''):
    """Export source-addressable numeric leaves; an estimate and its CI form one row."""
    entries = []
    def add(key, value, ptr, ci=None):
        leaf = key.lower()
        unit = 'count'
        if any(s in leaf for s in ['rate', 'loss', 'error', 'saving', 'fraction', 'accuracy', 'sensitivity', 'specificity', 'kappa']):
            unit = 'fraction'
        if 'wells' in leaf and not any(s in leaf for s in ['fraction', 'saving']):
            unit = 'wells'
        if 'threshold' in leaf or 'lambda' in leaf or 'margin' in leaf:
            unit = 'rank margin'
        metric = leaf.rsplit('.', 1)[-1]
        if metric in ['full_coverage_errors', 'wrong_reports', 'reports', 'designs', 'identity_groups', 'substances'] or metric.endswith('_count_difference'):
            unit = 'count'
        if metric.startswith('wells_') and metric.endswith('_count_difference'):
            unit = 'wells'
        if metric.endswith('_identity_mean_difference'):
            base = metric.removesuffix('_identity_mean_difference')
            if base in ['reports', 'wrong_reports']:
                unit = 'reports per identity group'
            elif base == 'wells_used':
                unit = 'wells per identity group'
        if 'reduction_pp' in leaf:
            unit = 'percentage points'
        row = dict(key=key, value=value, unit=unit, group=group,
                   source_file=source, field=ptr or '/', command=command)
        if ci is not None:
            row['ci95'] = ci
        entries.append(row)
    def walk(v, key, ptr):
        if isinstance(v, dict):
            if 'estimate' in v and isinstance(v['estimate'], (int, float)):
                add(key, v['estimate'], ptr + '/estimate', v.get('ci95'))
            else:
                for k, x in v.items():
                    walk(x, key + '.' + str(k), ptr + '/' + str(k).replace('~', '~0').replace('/', '~1'))
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            add(key, v, ptr)
    walk(obj, prefix, pointer)
    return entries

def write_json(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2, ensure_ascii=True, allow_nan=False) + '\n')

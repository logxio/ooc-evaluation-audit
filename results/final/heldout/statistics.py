"""Frozen identity-group aggregation functions."""
import numpy as np
from collections import defaultdict
METHODS = ["anchorboost", "measured_only", "loglinear", "observed_active_fallback"]
SOURCE_SHA256 = "5b61bd8d4eee15915386202daeee0607b79ef4bb2d6c2c77b2f6906f80f43abd"

def ci(estimate, samples):
    s = np.asarray(samples, float)
    s = s[np.isfinite(s)]
    return {'estimate': float(estimate), 'ci95': np.quantile(s, [.025, .975]).tolist(), 'defined_resamples': int(len(s))}

def weights(n):
    return np.array([np.bincount(row, minlength=n) for row in np.random.default_rng(0).integers(0, n, (4000, n))], float)

def aggregate(rows):
    groups = sorted({r['drug_group'] for r in rows})
    W = weights(len(groups))
    by = defaultdict(list)
    for r in rows:
        by[r['drug_group']].append(r)
    arr = {}
    for m in METHODS:
        rec = []
        for g in groups:
            part = by[g]
            rel = [r[m + '_release'] for r in part]
            wrong = [r[m + '_call'] != r['truth'] for r in part]
            rec.append(dict(designs=len(part), reports=sum(rel), wrong_reports=sum(a and b for a, b in zip(rel, wrong)), full_coverage_errors=sum(wrong),
                            wells_used=sum(r['wells_measured'] if a else r['wells_full'] for a, r in zip(rel, part)), wells_full=sum(r['wells_full'] for r in part)))
        v = {k: np.array([x[k] for x in rec], float) for k in rec[0]}
        v['release_rate'], v['drug_loss'], v['full_error_rate'] = v['reports'] / v['designs'], v['wrong_reports'] / v['designs'], v['full_coverage_errors'] / v['designs']
        arr[m] = v
    n = len(groups)
    methods = {}
    for m, v in arr.items():
        cell = {k: ci(v[k].sum(), W @ v[k]) for k in ['reports', 'wrong_reports', 'wells_used', 'wells_full', 'full_coverage_errors']}
        for k in ['release_rate', 'drug_loss', 'full_error_rate']:
            cell[k] = ci(v[k].mean(), W @ v[k] / n)
        cell['savings_vs_full'] = ci(1 - v['wells_used'].sum() / v['wells_full'].sum(), 1 - (W @ v['wells_used']) / (W @ v['wells_full']))
        methods[m] = cell
    paired = {}
    a = arr['anchorboost']
    for m in METHODS[1:]:
        c = arr[m]
        cell = {k: ci((a[k] - c[k]).mean(), W @ (a[k] - c[k]) / n) for k in ['release_rate', 'drug_loss', 'full_error_rate']}
        for k in ['reports', 'wrong_reports', 'wells_used']:
            cell[k + '_count_difference'] = ci((a[k] - c[k]).sum(), W @ (a[k] - c[k]))
        cell['cost_savings'] = ci(1 - a['wells_used'].sum() / c['wells_used'].sum(), 1 - (W @ a['wells_used']) / (W @ c['wells_used']))
        paired[m] = cell
    return {'identities': n, 'designs': len(rows), 'methods': methods, 'paired': paired}

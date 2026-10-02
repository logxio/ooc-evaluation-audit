#!/usr/bin/env python3
"""Learned-width intervals: each forecast's 90% interval is as wide as that forecast tends to be wrong.

The point forecasts are the frozen AnchorBoost errors saved by chip_forecast_selfcheck.py (per-chemical errors equal
the registered three-concentration run). A quantile gradient-boosted width model learns the 90th percentile of the
absolute well error from what the laboratory measured: output, distance to the measured concentrations, measured level
means and replicate spread at those concentrations, the interpolated value and the chemical's measured activity.
Cross-conformal calibration on the other folds' chemicals scales it to the nominal level. Width models are cross-fitted:
the errors of each calibration fold are scored by a width model trained on the remaining calibration folds, and the
test fold uses the mean of these models, so no error is scored by a width model that saw it.
Run: python chip_forecast_intervals.py selfcheck_fold0.npz selfcheck_fold1.npz ... selfcheck_fold4.npz --test 1 2 3 4
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor

import chip_forecast as cf
import chip_forecast_selfcheck as sc

ROOT = Path(__file__).resolve().parent
K = 3
ROWS = 300_000
WIDTH = dict(loss='quantile', quantile=0.9, max_iter=300, learning_rate=0.05, max_leaf_nodes=31,
             min_samples_leaf=200, random_state=0)
FLOOR = 0.05
# Published comparator, results/conformal_r7.json at the pinned commit: k=3, alpha 0.1, conformal, all five folds.
COMPARATOR = dict(source='results/conformal_r7.json', coverage=0.8989, coverage_ci95=[0.8914, 0.906],
                  full_width=7.413, half_width=7.413 / 2)


def covariates(task, ctx):
    """One row per held-out (well, output) entry, in the entry order of chip_forecast_selfcheck.py; context only."""
    ic = np.isin(task.logc, ctx)
    lvc, M, _ = cf.level_means(task, ic)
    L = len(lvc)
    M = M.reshape(L, cf.D)
    sd = np.zeros((L, cf.D), np.float32)
    for i, v in enumerate(lvc):
        idx = ic & (task.logc == v)
        y, m = task.y[idx].reshape(-1, cf.D), task.m[idx].reshape(-1, cf.D)
        n = m.sum(0)
        mu = (y * m).sum(0) / np.maximum(n, 1)
        sd[i] = np.sqrt(((y - mu) ** 2 * m).sum(0) / np.maximum(n - 1, 1))
    held = np.where(~ic)[0]
    q = task.logc[held]
    lv = np.unique(q)
    base = cf.predict_interp(task, ic, lv).reshape(len(lv), cf.D)[np.searchsorted(lv, q)]
    W, J = np.nonzero(task.m[~ic].reshape(len(held), cf.D))
    x = q[W]
    i = np.clip(np.searchsorted(lvc, x), 1, L - 1)
    gap = (lvc[i] - lvc[i - 1]) * ((x > lvc[0]) & (x < lvc[-1]))
    n = len(J)
    cols = [J, J // cf.NF, J % cf.NF, x - lvc[0], x - lvc[-1], np.clip(x - lvc[-1], 0, None), np.clip(lvc[0] - x, 0, None),
            np.abs(x[:, None] - lvc[None, :]).min(1), gap, M[0, J], M[L // 2, J], M[-1, J], np.abs(M[:, J]).max(0),
            base[W, J], np.abs(base[W, J]), sd[0, J], sd[L // 2, J], sd[-1, J], sd[:, J].mean(0),
            np.full(n, np.abs(M[-1]).mean()), np.full(n, sd.mean()), np.full(n, np.abs(M).max())]
    return np.column_stack(cols).astype(np.float32), J


def attach(parts, tasks):
    for f, P in parts.items():
        X, J = zip(*(covariates(t, ctx) for t in tasks if t.fold == f and K < len(t.levels) for ctx in cf.designs(t, K)))
        P['X'] = np.concatenate(X)
        assert np.array_equal(np.concatenate(J), P['dims']), f'fold {f}: covariate rows do not match saved entries'


def width_model(parts, folds, rng):
    X = np.concatenate([parts[g]['X'] for g in folds])
    e = np.concatenate([parts[g]['errs'] for g in folds]).astype(np.float64)
    idx = rng.choice(len(X), min(ROWS, len(X)), replace=False)
    model = HistGradientBoostingRegressor(**WIDTH).fit(X[idx], e[idx])
    return lambda Z: np.maximum(model.predict(Z), FLOOR)


def intervals(parts, test):
    rows, per_fold = [], {}
    for f in test:
        cal = [g for g in sorted(parts) if g != f]
        rng = np.random.default_rng(0)
        P = parts[f]
        e, d = (np.concatenate([parts[g][n] for g in cal]) for n in ('errs', 'dims'))
        plain = np.array([sc.quantile(e[d == j]) for j in range(cf.D)])[P['dims']]
        scores, scale = [], np.zeros(len(P['errs']))
        for g in cal:
            model = width_model(parts, [h for h in cal if h != g], rng)
            scores.append(parts[g]['errs'] / model(parts[g]['X']))
            scale += model(P['X']) / len(cal)
        learned = sc.quantile(np.concatenate(scores)) * scale
        hit_p, hit_l = P['errs'] <= plain, P['errs'] <= learned
        per_fold[f'fold{f}'] = dict(plain=dict(coverage=round(float(hit_p.mean()), 4), half_width=round(float(plain.mean()), 3)),
                                    learned=dict(coverage=round(float(hit_l.mean()), 4), half_width=round(float(learned.mean()), 3)))
        for c in np.unique(P['chem']):
            m = P['chem'] == c
            rows.append((m.sum(), hit_p[m].sum(), hit_l[m].sum(), plain[m].sum(), learned[m].sum()))
    a = np.array(rows, float)
    rng = np.random.default_rng(0)
    return dict(
        test_folds=list(test), chemicals=len(a), wells=int(a[:, 0].sum()),
        plain=dict(coverage=round(a[:, 1].sum() / a[:, 0].sum(), 4), coverage_ci95=sc.boot_ratio(a[:, 1], a[:, 0], rng),
                   half_width=round(a[:, 3].sum() / a[:, 0].sum(), 3)),
        learned=dict(coverage=round(a[:, 2].sum() / a[:, 0].sum(), 4), coverage_ci95=sc.boot_ratio(a[:, 2], a[:, 0], rng),
                     chemical_mean_coverage=round(float(np.mean(a[:, 2] / a[:, 0])), 4),
                     half_width=round(a[:, 4].sum() / a[:, 0].sum(), 3)),
        width_ratio_learned_over_plain=dict(value=round(a[:, 4].sum() / a[:, 3].sum(), 4), ci95=sc.boot_ratio(a[:, 4], a[:, 3], rng)),
        per_fold=per_fold)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('npz', type=Path, nargs='+')
    p.add_argument('--test', type=int, nargs='+', default=[1, 2, 3, 4])
    p.add_argument('--cache', type=Path, default=ROOT / '.cache' / 'neurochip_twin')
    p.add_argument('--out', type=Path)
    a = p.parse_args()
    files = cf.fetch(a.cache)
    parts = sc.load(a.npz)
    attach(parts, cf.load_tasks(files['data_bundle/nfa_tasks.npz']))
    res = intervals(parts, a.test)
    res['comparator'] = COMPARATOR
    res['code_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    text = json.dumps(res, indent=1) + '\n'
    if a.out:
        a.out.write_text(text)
    print(text, end='')


if __name__ == '__main__':
    main()

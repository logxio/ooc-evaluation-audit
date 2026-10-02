#!/usr/bin/env python3
"""Forecast the unmeasured concentrations of a neural MEA chip screen from a few measured ones.

Benchmark: US EPA Network Formation Assay (rat primary cortical neurons on 48-well MEA plates,
recorded at DIV 5/7/9/12; 17 network features), 243 chemicals and 6,902 exposed wells, as
packaged by the public NeuroChip Twin v2 repository (code MIT, EPA data public domain) at the
pinned commit below. Folds, context designs, target transform, curve metric and the paired
chemical bootstrap follow that repository's R2 protocol line by line, so its published
per-chemical results are a direct, same-design comparator. The evaluation helpers below are
ports of that protocol (MIT, Copyright (c) 2026 Francisco Angulo de Lafuente); `--check`
verifies that the ported baselines reproduce the published per-chemical baseline errors.

Method (AnchorBoost): start from log-linear interpolation between the measured concentrations
(the strongest published baseline at three measured levels), then predict the remaining
residual for every (DIV, feature) output with one gradient-boosted tree model. The model is
trained only on training-fold chemicals, on every possible sparse design of each training
chemical, and sees: the interpolation anchor, local slopes and extrapolation distances,
whole-chemical activity summaries, the deviation of a per-output Hill fit and of an analog-
chemical forecast from the anchor, and the DIV and feature index of each output.
Absolute-error loss matches the curve MAE target.

Run: python chip_forecast.py --folds 1 2 3 4 --k 3     (primary; a few minutes per fold on a laptop CPU)
     python chip_forecast.py --check                   (baseline reproduction only)
"""
import argparse
import csv
import hashlib
import io
import itertools
import json
import time
import urllib.request
from pathlib import Path

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor

ROOT = Path(__file__).resolve().parent
COMMIT = 'f9848800dfab66a8bc005e6b3087153eeaabe9ac'
SOURCE = f'https://raw.githubusercontent.com/Agnuxo1/neurochip-twin/{COMMIT}/'
FILES = {'data_bundle/nfa_tasks.npz': 'e1f056ef33f568052fb8dfdba6e095f7b575c7f78d96768e34469918559008d2',
         'results/trajectory_cv_per_chemical.csv': '0d013127aef781ca5e1de04088532e2e19223364173a198e0686941c04f93abc'}
ND, NF, D = 4, 17, 68
KS = [1, 2, 3, 4]
GRID = np.linspace(-3.0, 2.5, 23)
AC50 = np.linspace(-3.5, 2.5, 31)
HILL = np.array([0.7, 1.0, 1.5, 2.5, 4.0])
MODEL = dict(loss='absolute_error', max_iter=600, learning_rate=0.05, max_leaf_nodes=127,
             min_samples_leaf=50, early_stopping=False, random_state=0)
N_PCA = 0
ABLATIONS = ['no_anchor', 'no_hill', 'no_analog', 'five_designs']


def fetch(cache):
    """Download the two pinned public files once and verify their SHA-256."""
    cache.mkdir(parents=True, exist_ok=True)
    out = {}
    for name, sha in FILES.items():
        path = cache / Path(name).name
        if not path.exists():
            with urllib.request.urlopen(SOURCE + name, timeout=120) as r:
                path.write_bytes(r.read())
        got = hashlib.sha256(path.read_bytes()).hexdigest()
        if got != sha:
            raise ValueError(f'{name}: SHA-256 {got} differs from pinned {sha}')
        out[name] = path
    return out


class Task:
    """One chemical: wells x (DIV, feature) responses in the published transformed units."""

    def __init__(self, chem, fold, label, logc, y, m):
        self.chem, self.fold, self.label = chem, fold, label
        self.logc, self.y, self.m = logc, y, m
        self.levels = np.unique(logc)
        self.lvidx = np.searchsorted(self.levels, logc)
        num = np.zeros((len(self.levels), ND, NF))
        den = np.zeros((len(self.levels), ND, NF))
        np.add.at(num, self.lvidx, y * m)
        np.add.at(den, self.lvidx, m)
        self.ok = den > 0
        self.mu = np.where(self.ok, num / np.maximum(den, 1), 0.0).astype(np.float32)


def load_tasks(path):
    z = np.load(path, allow_pickle=False)
    off = z['offsets']
    return [Task(str(c), int(z['fold'][i]), str(z['label'][i]), z['logc'][off[i]:off[i + 1]],
                 z['y'][off[i]:off[i + 1]].astype(np.float32), z['m'][off[i]:off[i + 1]])
            for i, c in enumerate(z['chem'])]


def designs(task, k, n=5):
    """The published seeded context designs: n distinct sets of k measured levels per chemical."""
    rng = np.random.default_rng(int(hashlib.sha256(f'{task.chem}|{k}'.encode()).hexdigest()[:8], 16))
    out, seen = [], set()
    for _ in range(n * 4):
        lv = tuple(sorted(rng.choice(task.levels, size=k, replace=False).tolist())) if k else ()
        if lv not in seen:
            seen.add(lv)
            out.append(np.array(lv, np.float32))
        if len(out) == n or k == 0:
            break
    return out


def all_designs(task, k):
    return [np.array(c, np.float32) for c in itertools.combinations(task.levels.tolist(), k)]


def level_means(task, sel):
    rows = np.unique(task.lvidx[sel])
    if np.array_equal(np.isin(task.lvidx, rows), sel):
        return task.levels[rows], task.mu[rows], task.ok[rows]
    lv = np.unique(task.logc[sel])
    mu = np.zeros((len(lv), ND, NF), np.float32)
    ok = np.zeros((len(lv), ND, NF), bool)
    for i, value in enumerate(lv):
        idx = sel & (task.logc == value)
        num, den = (task.y[idx] * task.m[idx]).sum(0), task.m[idx].sum(0)
        ok[i] = den > 0
        mu[i] = np.where(ok[i], num / np.maximum(den, 1), 0.0)
    return lv, mu, ok


def interp_rows(lv, mu, ok, q):
    """Piecewise-linear in log concentration between level means, flat outside (published baseline)."""
    q = np.asarray(q, np.float64)
    shape = mu.shape[1:]
    M, O = mu.reshape(len(lv), -1), ok.reshape(len(lv), -1)
    out = np.zeros((len(q), M.shape[1]), np.float32)
    full = O.all(0)
    if full.any():
        if len(lv) == 1:
            out[:, full] = M[0, full]
        else:
            i = np.clip(np.searchsorted(lv, q), 1, len(lv) - 1)
            x0, x1 = lv[i - 1], lv[i]
            w = np.clip((q - x0) / np.where(x1 > x0, x1 - x0, 1), 0, 1)[:, None]
            out[:, full] = M[i - 1][:, full] * (1 - w) + M[i][:, full] * w
    for j in np.where(~full & O.any(0))[0]:
        g = O[:, j]
        out[:, j] = np.interp(q, lv[g], M[g, j])
    return out.reshape((len(q),) + shape)


def predict_interp(task, ic, q):
    if not ic.any():
        return np.zeros((len(q), ND, NF), np.float32)
    return interp_rows(*level_means(task, ic), q)


def predict_hill(task, ic, q):
    """Per-output Hill curve with vehicle bottom, exhaustive (AC50, slope) grid (published baseline)."""
    lv, mu, ok = level_means(task, ic) if ic.any() else (np.array([]), None, None)
    if len(lv) < 3:
        return predict_interp(task, ic, q)

    def basis(x):
        return 1.0 / (1.0 + 10 ** (HILL[None, :, None] * (AC50[:, None, None] - x[None, None, :])))
    Bc, Bq = basis(lv), basis(np.asarray(q, np.float64))
    Y, W = mu.reshape(len(lv), -1), ok.reshape(len(lv), -1).astype(np.float64)
    num = np.einsum('ahl,lk->ahk', Bc, Y * W)
    den = np.einsum('ahl,lk->ahk', Bc ** 2, W) + 1e-9
    top = np.clip(num / den, -10.0, 10.0)
    resid = np.einsum('lk,lk->k', W, Y ** 2)[None, None] - 2 * top * num + top ** 2 * den
    a_i, h_i = np.unravel_index(resid.reshape(-1, Y.shape[1]).argmin(0), resid.shape[:2])
    k = np.arange(Y.shape[1])
    return (Bq[a_i, h_i, :].T * top[a_i, h_i, k][None, :]).reshape(len(q), ND, NF).astype(np.float32)


class Analog:
    """Distance-weighted analog chemicals over training profiles (published kNN baseline).

    exclude_self removes the query chemical from its own neighbours when building training rows."""

    def __init__(self, train, k=10, exclude_self=False):
        self.k = k
        self.P = np.stack([interp_rows(t.levels, t.mu, t.ok, GRID) for t in train])
        self.index = {t.chem: i for i, t in enumerate(train)} if exclude_self else {}

    def at(self, x):
        i = np.clip(np.searchsorted(GRID, x), 1, len(GRID) - 1)
        w = np.clip((x - GRID[i - 1]) / (GRID[i] - GRID[i - 1]), 0, 1)
        return self.P[:, i - 1] * (1 - w)[None, :, None, None] + self.P[:, i] * w[None, :, None, None]

    def predict(self, task, ic, q):
        q = np.asarray(q, np.float64)
        if not ic.any():
            return self.at(q).mean(0).astype(np.float32)
        lv, mu, ok = level_means(task, ic)
        d2 = (((self.at(lv) - mu[None]) ** 2) * ok[None]).sum((1, 2, 3)) / max(ok.sum(), 1)
        if task.chem in self.index:
            d2[self.index[task.chem]] = np.inf
        nn = np.argsort(d2)[:self.k]
        w = 1.0 / (d2[nn] + 1e-3)
        return np.tensordot(w / w.sum(), self.at(q)[nn], axes=1).astype(np.float32)


class Profiles:
    """Principal components of measured level-mean profiles, fitted on training chemicals."""

    def __init__(self, train, n=None):
        n = N_PCA if n is None else n
        V = np.concatenate([(t.mu * t.ok).reshape(len(t.levels), -1) for t in train]).astype(np.float64)
        self.mean = V.mean(0)
        self.W = np.linalg.svd(V - self.mean, full_matrices=False)[2][:n]

    def __call__(self, M):
        return (M - self.mean) @ self.W.T


def features(task, ic, q, analog, profiles, ablation=None):
    """Anchor (Q, 68) and one feature row per (query level, output): (Q, 68, F)."""
    lv, mu, ok = level_means(task, ic)
    L, Q = len(lv), len(q)
    base = interp_rows(lv, mu, ok, q).reshape(Q, D)
    M = mu.reshape(L, D)
    if L > 1:
        up = (M[-1] - M[-2]) / (lv[-1] - lv[-2])
        low = (M[1] - M[0]) / (lv[1] - lv[0])
        span = (M[-1] - M[0]) / (lv[-1] - lv[0])
        i = np.clip(np.searchsorted(lv, q), 1, L - 1)
        gap = (lv[i] - lv[i - 1]) * ((q > lv[0]) & (q < lv[-1]))
    else:  # one measured level carries no slope or interior gap
        up = low = span = np.zeros(D)
        gap = np.zeros(Q)
    above, below = np.clip(q - lv[-1], 0, None), np.clip(lv[0] - q, 0, None)
    hill = predict_hill(task, ic, q).reshape(Q, D) - base
    near = analog.predict(task, ic, q).reshape(Q, D) - base
    P = profiles(M * ok.reshape(L, D))
    cols = [base, up, low, span, M[-1], M[0], M[L // 2], above[:, None], below[:, None], gap[:, None],
            q[:, None], lv[-1], lv[0], np.abs(M[-1]).mean(), np.abs(M[-1] - M[0]).mean(), np.abs(M).max(),
            M[-1].mean()]
    if ablation != 'no_hill':
        cols.append(hill)
    if ablation != 'no_analog':
        cols += [near, np.abs(near).mean(1)[:, None]]
    cols += list(P[-1]) + list(P[0]) + list(P[-1] - P[-2] if L > 1 else 0 * P[0])
    cols += [np.arange(D) // NF, np.arange(D) % NF]
    out = np.empty((Q, D, len(cols)), np.float64)
    for c, v in enumerate(cols):
        out[:, :, c] = v
    return base, out


class AnchorBoost:
    def __init__(self, train, k, params=None, ablation=None):
        self.ablation = ablation
        self.analog_train = Analog(train, exclude_self=True)
        self.analog = Analog(train)
        self.profiles = Profiles(train)
        design = designs if ablation == 'five_designs' else all_designs
        rows = [(t, ctx) for t in train if k < len(t.levels) for ctx in design(t, k)]
        sizes = []
        for t, ctx in rows:
            keep = ~np.isin(t.levels, ctx)
            sizes.append(int(t.ok[keep].sum()))
        n_feat = features(train[0], np.isin(train[0].logc, all_designs(train[0], k)[0]),
                          train[0].levels[:1], self.analog, self.profiles, ablation)[1].shape[-1]
        X = np.empty((sum(sizes), n_feat), np.float64)
        y = np.empty(sum(sizes), np.float64)
        at = 0
        for (t, ctx), size in zip(rows, sizes):
            ic = np.isin(t.logc, ctx)
            lv, mu, ok = level_means(t, ~ic)
            base, f = features(t, ic, lv, self.analog_train, self.profiles, ablation)
            keep = ok.reshape(-1)
            X[at:at + size] = f.reshape(-1, n_feat)[keep]
            y[at:at + size] = (mu.reshape(len(lv), D) - base * (ablation != 'no_anchor')).ravel()[keep]
            at += size
        self.rows = int(len(y))
        self.model = HistGradientBoostingRegressor(**(params or MODEL)).fit(X, y)

    def __call__(self, task, ic, q):
        base, f = features(task, ic, q, self.analog, self.profiles, self.ablation)
        pred = self.model.predict(f.reshape(-1, f.shape[-1])).reshape(len(q), D)
        return (pred + base * (self.ablation != 'no_anchor')).reshape(len(q), ND, NF)


def errors(pred, task, it):
    lv, mu, ok = level_means(task, it)
    curve = float(np.abs(pred - mu)[ok].mean()) if ok.any() else float('nan')
    pw, mm = pred[np.searchsorted(lv, task.logc[it])], task.m[it]
    well = float(np.abs(pw - task.y[it])[mm].mean()) if mm.any() else float('nan')
    return curve, well


def paired(a, b, n=4000, seed=0):
    """Published paired bootstrap over chemicals of mean(a - b); negative favours a."""
    keys = sorted(set(a) & set(b))
    d = np.array([a[x] - b[x] for x in keys])
    rng = np.random.default_rng(seed)
    boot = np.array([d[rng.integers(0, len(d), len(d))].mean() for _ in range(n)])
    return dict(mean_diff=round(float(d.mean()), 4), ci95=[round(float(np.percentile(boot, 2.5)), 4),
                round(float(np.percentile(boot, 97.5)), 4)],
                rel_change_pct=round(float(100 * d.mean() / np.mean([b[x] for x in keys])), 2),
                n_chemicals=len(keys), frac_chem_improved=round(float((d < 0).mean()), 3))


def published(path):
    out = {}
    with open(path, newline='') as f:
        for r in csv.DictReader(f):
            out.setdefault((int(r['k']), r['method']), {})[r['chemical']] = float(r['curve_mae'])
    return out


def check(tasks, pub):
    """Reproduce the published per-chemical baseline curve errors with the ported helpers."""
    report = {}
    for k in KS:
        for fold in sorted({t.fold for t in tasks}):
            analog = Analog([t for t in tasks if t.fold != fold])
            for t in (t for t in tasks if t.fold == fold and k < len(t.levels)):
                acc = {'loglinear_interp': [], 'hill_per_endpoint': [], 'analog_knn': []}
                for ctx in designs(t, k):
                    ic = np.isin(t.logc, ctx)
                    lv = np.unique(t.logc[~ic])
                    acc['loglinear_interp'].append(errors(predict_interp(t, ic, lv), t, ~ic)[0])
                    acc['hill_per_endpoint'].append(errors(predict_hill(t, ic, lv), t, ~ic)[0])
                    acc['analog_knn'].append(errors(analog.predict(t, ic, lv), t, ~ic)[0])
                for name, values in acc.items():
                    gap = abs(float(np.nanmean(values)) - pub[(k, name)][t.chem])
                    cell = report.setdefault(f'k{k}_{name}', dict(chemicals=0, max_abs_diff=0.0))
                    cell['chemicals'] += 1
                    cell['max_abs_diff'] = max(cell['max_abs_diff'], round(gap, 6))
    return report


def run(tasks, folds, ks, params=None, ablation=None):
    rows, times = [], {}
    for k in ks:
        for fold in folds:
            start = time.time()
            train = [t for t in tasks if t.fold != fold]
            model = AnchorBoost(train, k, params, ablation)
            analog = Analog(train)
            for t in (t for t in tasks if t.fold == fold and k < len(t.levels)):
                acc = {}
                for ctx in designs(t, k):
                    ic = np.isin(t.logc, ctx)
                    lv = np.unique(t.logc[~ic])
                    for name, fn in [('anchorboost', model), ('loglinear_interp', predict_interp),
                                     ('hill_per_endpoint', predict_hill), ('analog_knn', analog.predict)]:
                        acc.setdefault(name, []).append(errors(fn(t, ic, lv), t, ~ic))
                for name, v in acc.items():
                    v = np.array(v, float)
                    rows.append(dict(chemical=t.chem, fold=fold, k=k, method=name, label=t.label,
                                     curve_mae=float(np.nanmean(v[:, 0])), well_mae=float(np.nanmean(v[:, 1]))))
            times[f'k{k}_fold{fold}'] = dict(seconds=round(time.time() - start, 1), training_rows=model.rows)
    return rows, times


def summarize(rows, pub, folds, ks):
    out = {}
    for k in ks:
        ours = {r['chemical']: r['curve_mae'] for r in rows if r['k'] == k and r['method'] == 'anchorboost' and r['fold'] in folds}
        cell = dict(n_chemicals=len(ours), anchorboost=round(float(np.mean(list(ours.values()))), 4), versus={})
        for name in ['loglinear_interp', 'hill_per_endpoint', 'analog_knn']:
            mine = {r['chemical']: r['curve_mae'] for r in rows if r['k'] == k and r['method'] == name and r['fold'] in folds}
            cell[name] = round(float(np.mean(list(mine.values()))), 4)
            cell['versus'][name] = paired(ours, mine)
        nt = {c: v for c, v in pub[(k, 'neurotrajectory')].items() if c in ours}
        cell['published_neural_process'] = round(float(np.mean(list(nt.values()))), 4)
        cell['versus']['published_neural_process'] = paired(ours, nt)
        out[f'k{k}'] = cell
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--cache', type=Path, default=ROOT / '.cache' / 'neurochip_twin')
    p.add_argument('--folds', type=int, nargs='+', default=[1, 2, 3, 4])
    p.add_argument('--k', type=int, nargs='+', default=[3])
    p.add_argument('--check', action='store_true')
    p.add_argument('--ablation', choices=ABLATIONS)
    p.add_argument('--merge', type=Path, nargs='+', help='summarize per-fold CSVs written by earlier runs')
    p.add_argument('--out', type=Path, default=ROOT / 'chip_forecast_result.json')
    a = p.parse_args()
    files = fetch(a.cache)
    tasks = load_tasks(files['data_bundle/nfa_tasks.npz'])
    pub = published(files['results/trajectory_cv_per_chemical.csv'])
    if a.check:
        print(json.dumps(check(tasks, pub), indent=1))
        return
    if a.merge:
        rows, times = [], {}
        for path in a.merge:
            with path.open(newline='') as f:
                rows += [dict(r, fold=int(r['fold']), k=int(r['k']), curve_mae=float(r['curve_mae']),
                              well_mae=float(r['well_mae'])) for r in csv.DictReader(f)]
            times.update(json.loads(path.with_suffix('.json').read_text())['timing'])
    else:
        rows, times = run(tasks, a.folds, a.k, ablation=a.ablation)
    result = dict(schema='chip_forecast.result.v1', source=dict(commit=COMMIT, files=FILES),
                  folds=a.folds, ks=a.k, model=dict(MODEL, n_pca=N_PCA), ablation=a.ablation, timing=times,
                  summary=summarize(rows, pub, a.folds, a.k),
                  summary_by_fold={f'fold{f}': summarize(rows, pub, [f], a.k) for f in sorted({r['fold'] for r in rows})},
                  summary_folds_1to4=summarize(rows, pub, [f for f in a.folds if f != 0], a.k) if 0 in a.folds else None,
                  code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    a.out.write_text(json.dumps(result, indent=1) + '\n')
    with a.out.with_suffix('.csv').open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(json.dumps(result['summary'], indent=1))


if __name__ == '__main__':
    main()

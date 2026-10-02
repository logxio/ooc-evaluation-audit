#!/usr/bin/env python3
"""Design Replay forecasting of unmeasured concentrations, with cross-conformal intervals.

Builds on chip_forecast.py (same pinned data, folds, context designs, curve metric and paired chemical bootstrap) and
adds one mechanism, analog design replay: the test chemical's own measurement design is replayed on its most similar
training chemicals, and the residual that log-linear interpolation leaves on them at each unmeasured concentration is
transferred to the query as a feature, together with its spread across the analogs. Training already replays every
sparse design of every training chemical (episode replay). Without analog replay the feature matrix is exactly the
chip_forecast.py one, so the published AnchorBoost results are this model's ablation.

Each run also writes the absolute error of every held-out well, so --conformal can form cross-conformal 90% intervals:
per output, the interval half-width for a test fold is the finite-sample 90% quantile of the absolute well errors of the
other folds' chemicals, each predicted by the model that never trained on them.

Run: python chip_forecast_replay.py --folds 1 2 3 4 --k 3 --out replay_k3.json
     python chip_forecast_replay.py --conformal replay_fold*.npz
"""
import argparse
import csv
import hashlib
import json
import math
import time
from pathlib import Path

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor

import chip_forecast as cf

ROOT = Path(__file__).resolve().parent
SELF_REPLAY = False   # self replay errors as point-model features (fold-0 development 1.0614 against 1.0625)
REPLICATES = False    # replicate-aware context: spread of replicate wells at the measured concentrations
TRAIN_DESIGNS = 0     # designs per training chemical: 0 = every design; N = seeded random N of them
ENSEMBLE = 1          # members with feature subsampling 0.8 and seeds 0..n-1; 1 is the frozen single model
N_REPLAY = 0          # analog replay: 0 disables (fold-0 development: 10 analogs 1.0626, 20 analogs 1.0594, none 1.0625)
LEVEL = 0.90


def analog_replay(analog, task, ic, q):
    """Weighted mean and spread of the interpolation residual left on the nearest analogs under this design."""
    lv, mu, ok = cf.level_means(task, ic)
    A = analog.at(lv).reshape(len(analog.P), len(lv), -1)
    d2 = (((A - mu.reshape(len(lv), -1)[None]) ** 2) * ok.reshape(len(lv), -1)[None]).sum((1, 2)) / max(ok.sum(), 1)
    if task.chem in analog.index:
        d2[analog.index[task.chem]] = np.inf
    nn = np.argsort(d2)[:N_REPLAY]
    w = 1.0 / (d2[nn] + 1e-3)
    w = w / w.sum()
    near = A[nn]                                                   # (n, L, 68) analogs at the measured concentrations
    at_q = analog.at(np.asarray(q, np.float64)).reshape(len(analog.P), len(q), -1)[nn]
    if len(lv) == 1:
        interp = np.repeat(near[:, :1], len(q), axis=1)
    else:
        i = np.clip(np.searchsorted(lv, q), 1, len(lv) - 1)
        t = np.clip((q - lv[i - 1]) / (lv[i] - lv[i - 1]), 0, 1)[None, :, None]
        interp = near[:, i - 1] * (1 - t) + near[:, i] * t
    resid = at_q - interp                                          # (n, Q, 68)
    mean = np.tensordot(w, resid, axes=1)
    spread = np.sqrt(np.tensordot(w, (resid - mean[None]) ** 2, axes=1))
    return mean, spread


def halves(train):
    """Deterministic two-way split of training chemicals for cross-fitted self replay."""
    key = lambda t: int(hashlib.sha256(t.chem.encode()).hexdigest()[:8], 16) % 2  # noqa: E731
    return [t for t in train if key(t) == 0], [t for t in train if key(t) == 1]


def self_replay(helpers, task, ic):
    """Error of a (k-1)-concentration model at each measured concentration, predicted from the other measured ones.

    helpers: models that never trained on this chemical; their predictions are averaged. Returns the measured
    levels and an (L, 68) error array (0 where unobserved)."""
    lv, mu, ok = cf.level_means(task, ic)
    errs = np.zeros((len(lv), cf.D))
    for i, m in enumerate(lv):
        sub = np.isin(task.logc, np.delete(lv, i))
        pred = np.mean([h(task, sub, np.array([m]))[0] for h in helpers], 0).reshape(-1)
        errs[i] = np.where(ok[i].reshape(-1), mu[i].reshape(-1) - pred, 0.0)
    return lv, errs


def self_features(lv, errs, q):
    near = errs[np.abs(lv[None, :] - q[:, None]).argmin(1)]               # (Q, 68) error at the nearest measured level
    top = np.broadcast_to(errs[-1], near.shape)                           # error at the highest measured level
    mean = np.broadcast_to(errs.mean(0), near.shape)
    scale = np.full(near.shape, np.abs(errs).mean())
    return np.stack([near, top, mean, scale], -1)


def replicate_spread(task, ic):
    """Per measured level and output: standard deviation of the replicate wells (0 with fewer than two wells)."""
    lv = np.unique(task.logc[ic])
    out = np.zeros((len(lv), cf.D))
    for i, level in enumerate(lv):
        sel = ic & (task.logc == level)
        y, m = task.y[sel].reshape(sel.sum(), -1), task.m[sel].reshape(sel.sum(), -1)
        n = m.sum(0)
        mean = np.where(n > 0, (y * m).sum(0) / np.maximum(n, 1), 0.0)
        var = np.where(n > 1, (((y - mean) ** 2) * m).sum(0) / np.maximum(n - 1, 1), 0.0)
        out[i] = np.sqrt(var)
    return lv, out


def replicate_features(task, ic, q):
    lv, sd = replicate_spread(task, ic)
    near = sd[np.abs(lv[None, :] - q[:, None]).argmin(1)]
    return np.stack([near, np.broadcast_to(sd[-1], near.shape), np.broadcast_to(sd[0], near.shape),
                     np.broadcast_to(sd.mean(0), near.shape), np.full(near.shape, sd.mean())], -1)


def features(task, ic, q, analog, profiles, ablation=None, selfcheck=None, size=None):
    base, f = cf.features(task, ic, q, analog, profiles)
    parts = [f]
    if REPLICATES and ablation != 'no_replicates':
        parts.append(replicate_features(task, ic, q))
    if size is not None:
        parts.append(np.full(f.shape[:2] + (1,), float(size)))
    if N_REPLAY and ablation != 'no_replay':
        art, spread = analog_replay(analog, task, ic, q)
        parts.append(np.stack([art, spread, np.broadcast_to(np.abs(art).mean(1, keepdims=True), art.shape)], -1))
    if selfcheck is not None:
        parts.append(self_features(*selfcheck, q))
    return base, np.concatenate(parts, -1)


def sampled_designs(task, k):
    designs = cf.all_designs(task, k)
    if not TRAIN_DESIGNS or TRAIN_DESIGNS >= len(designs):
        return designs
    rng = np.random.default_rng(int(hashlib.sha256(f'{task.chem}|{k}|{TRAIN_DESIGNS}'.encode()).hexdigest()[:8], 16))
    return [designs[i] for i in sorted(rng.choice(len(designs), TRAIN_DESIGNS, replace=False))]


class ReplayBoost:
    def __init__(self, train, k, ablation=None, cross_size=False):
        self.ablation = ablation
        self.cross_size = cross_size
        self.analog_train = cf.Analog(train, exclude_self=True)
        self.analog = cf.Analog(train)
        self.profiles = cf.Profiles(train)
        self.self_replay = SELF_REPLAY and k >= 2 and ablation != 'no_self_replay' and not cross_size
        if self.self_replay:
            a, b = halves(train)
            self.helpers = {0: cf.AnchorBoost(b, k - 1), 1: cf.AnchorBoost(a, k - 1)}   # helper i never saw half i
            side = {t.chem: i for i, h in enumerate((a, b)) for t in h}
        span = [s for s in (k - 1, k, k + 1) if s >= 1] if cross_size else [k]
        rows = [(t, ctx) for t in train for s in span if s < len(t.levels) for ctx in sampled_designs(t, s)]
        sizes = [int(t.ok[~np.isin(t.levels, ctx)].sum()) for t, ctx in rows]
        X = y = None
        at = 0
        for (t, ctx), size in zip(rows, sizes):
            ic = np.isin(t.logc, ctx)
            lv, mu, ok = cf.level_means(t, ~ic)
            check = self_replay([self.helpers[side[t.chem]]], t, ic) if self.self_replay else None
            base, f = features(t, ic, lv, self.analog_train, self.profiles, ablation, check, len(ctx) if cross_size else None)
            if X is None:
                X = np.empty((sum(sizes), f.shape[-1]), np.float64)
                y = np.empty(sum(sizes), np.float64)
            keep = ok.reshape(-1)
            X[at:at + size] = f.reshape(-1, f.shape[-1])[keep]
            y[at:at + size] = (mu.reshape(len(lv), cf.D) - base).ravel()[keep]
            at += size
        self.rows = int(len(y))
        params = [cf.MODEL] if ENSEMBLE == 1 else [dict(cf.MODEL, max_features=0.8, random_state=i) for i in range(ENSEMBLE)]
        self.models = [HistGradientBoostingRegressor(**pr).fit(X, y) for pr in params]

    def __call__(self, task, ic, q):
        check = self_replay(list(self.helpers.values()), task, ic) if self.self_replay else None
        size = len(np.unique(task.logc[ic])) if self.cross_size else None
        base, f = features(task, ic, q, self.analog, self.profiles, self.ablation, check, size)
        F = f.reshape(-1, f.shape[-1])
        return (base + np.mean([m.predict(F) for m in self.models], 0).reshape(len(q), cf.D)).reshape(len(q), cf.ND, cf.NF)


def run(tasks, folds, ks, ablation=None, residuals=None, cross_size=False):
    name = ablation or ('crosssize' if cross_size else 'designreplay')
    rows, times, store = [], {}, {}
    for k in ks:
        for fold in folds:
            start = time.time()
            train = [t for t in tasks if t.fold != fold]
            model = ReplayBoost(train, k, ablation, cross_size)
            analog = cf.Analog(train)
            dims, errs, cids = [], [], []
            for ci, t in enumerate(t for t in tasks if t.fold == fold and k < len(t.levels)):
                acc = {}
                for ctx in cf.designs(t, k):
                    ic = np.isin(t.logc, ctx)
                    lv = np.unique(t.logc[~ic])
                    pred = model(t, ic, lv)
                    for method, fn in [(name, None), ('loglinear_interp', cf.predict_interp),
                                       ('hill_per_endpoint', cf.predict_hill), ('analog_knn', analog.predict)]:
                        acc.setdefault(method, []).append(cf.errors(pred if fn is None else fn(t, ic, lv), t, ~ic))
                    err = np.abs(pred[np.searchsorted(lv, t.logc[~ic])] - t.y[~ic])
                    mm = t.m[~ic]
                    dims.append(np.broadcast_to(np.arange(cf.D).reshape(cf.ND, cf.NF), err.shape)[mm])
                    errs.append(err[mm])
                    cids.append(np.full(int(mm.sum()), ci))
                for method, v in acc.items():
                    v = np.array(v, float)
                    rows.append(dict(chemical=t.chem, fold=fold, k=k, method=method, label=t.label,
                                     curve_mae=float(np.nanmean(v[:, 0])), well_mae=float(np.nanmean(v[:, 1]))))
            store[(k, fold)] = dict(dims=np.concatenate(dims).astype(np.int16), errs=np.concatenate(errs).astype(np.float32),
                                    chem=np.concatenate(cids).astype(np.int16))
            times[f'k{k}_fold{fold}'] = dict(seconds=round(time.time() - start, 1), training_rows=model.rows)
    if residuals:
        np.savez_compressed(residuals, **{f'k{k}_fold{f}_{n}': v[n] for (k, f), v in store.items() for n in ('dims', 'errs', 'chem')})
    return rows, times


def conformal(paths):
    """Cross-conformal coverage: each fold's per-output quantile comes from the other folds' held-out errors."""
    parts = {}
    for path in paths:
        z = np.load(path)
        for key in z.files:
            k, fold, name = key.split('_')
            parts.setdefault((int(k[1:]), int(fold[4:])), {})[name] = z[key]
    out = {}
    for k in sorted({k for k, _ in parts}):
        folds = sorted(f for kk, f in parts if kk == k)
        cover, width, chem_cov = [], [], []
        per_fold = {}
        for f in folds:
            cal_d = np.concatenate([parts[(k, g)]['dims'] for g in folds if g != f])
            cal_e = np.concatenate([parts[(k, g)]['errs'] for g in folds if g != f])
            half = np.empty(cf.D)
            for j in range(cf.D):
                e = np.sort(cal_e[cal_d == j])
                r = min(len(e) - 1, math.ceil((len(e) + 1) * LEVEL) - 1)
                half[j] = e[r]
            d, e = parts[(k, f)]['dims'], parts[(k, f)]['errs']
            inside = e <= half[d]
            per_fold[f'fold{f}'] = dict(coverage=round(float(inside.mean()), 4), mean_half_width=round(float(half[d].mean()), 3), wells=int(len(e)))
            cover.append(inside), width.append(half[d])
            c = parts[(k, f)]['chem']
            chem_cov += [(inside[c == i].sum(), (c == i).sum()) for i in np.unique(c)]
        cov = np.concatenate([c for c, f in zip(cover, folds)])
        hits, tot = np.array(chem_cov, float).T
        rng = np.random.default_rng(0)
        boot = [hits[s].sum() / tot[s].sum() for s in (rng.integers(0, len(hits), len(hits)) for _ in range(4000))]
        out[f'k{k}'] = dict(level=LEVEL, folds=folds, coverage_all=round(float(cov.mean()), 4),
                            coverage_ci95_chemical_bootstrap=[round(float(np.percentile(boot, 2.5)), 4), round(float(np.percentile(boot, 97.5)), 4)],
                            mean_half_width_all=round(float(np.concatenate(width).mean()), 3), per_fold=per_fold)
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--cache', type=Path, default=ROOT / '.cache' / 'neurochip_twin')
    p.add_argument('--folds', type=int, nargs='+', default=[1, 2, 3, 4])
    p.add_argument('--k', type=int, nargs='+', default=[3])
    p.add_argument('--ablation', choices=['no_replay', 'no_self_replay', 'no_replicates'])
    p.add_argument('--out', type=Path, default=ROOT / 'chip_forecast_replay_result.json')
    p.add_argument('--residuals', type=Path, help='write held-out absolute well errors for the conformal step')
    p.add_argument('--conformal', type=Path, nargs='+', help='summarise cross-conformal coverage from residual files')
    p.add_argument('--n-replay', type=int, default=N_REPLAY, help='analogs replayed per design')
    p.add_argument('--cross-size', action='store_true', help='train on designs with k-1, k and k+1 measured levels')
    p.add_argument('--replicates', action='store_true', help='add replicate-well spread at the measured concentrations')
    p.add_argument('--self-replay', action='store_true', help='self replay errors as features')
    p.add_argument('--ensemble', type=int, default=ENSEMBLE, help='members with feature subsampling')
    p.add_argument('--train-designs', type=int, default=TRAIN_DESIGNS, help='designs per training chemical (0 = all)')
    a = p.parse_args()
    globals()['N_REPLAY'] = a.n_replay
    globals()['REPLICATES'] = a.replicates
    globals()['SELF_REPLAY'] = a.self_replay
    globals()['ENSEMBLE'] = a.ensemble
    globals()['TRAIN_DESIGNS'] = a.train_designs
    if a.conformal:
        print(json.dumps(conformal(a.conformal), indent=1))
        return
    files = cf.fetch(a.cache)
    tasks = cf.load_tasks(files['data_bundle/nfa_tasks.npz'])
    pub = cf.published(files['results/trajectory_cv_per_chemical.csv'])
    rows, times = run(tasks, a.folds, a.k, a.ablation, a.residuals, a.cross_size)
    name = a.ablation or ('crosssize' if a.cross_size else 'designreplay')
    as_main = [dict(r, method='anchorboost') if r['method'] == name else r for r in rows]   # summarize() reads 'anchorboost'
    result = dict(schema='chip_forecast.replay.result.v1', source=dict(commit=cf.COMMIT, files=cf.FILES), folds=a.folds, ks=a.k,
                  model=dict(cf.MODEL, n_replay=N_REPLAY, replicates=REPLICATES, ensemble=ENSEMBLE, cross_size=a.cross_size, train_designs=TRAIN_DESIGNS), ablation=a.ablation, timing=times,
                  summary=cf.summarize(as_main, pub, a.folds, a.k),
                  summary_by_fold={f'fold{f}': cf.summarize(as_main, pub, [f], a.k) for f in a.folds},
                  code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  base_code_sha256=hashlib.sha256(Path(cf.__file__).read_bytes()).hexdigest())
    a.out.write_text(json.dumps(result, indent=1) + '\n')
    with a.out.with_suffix('.csv').open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(json.dumps(result['summary'], indent=1))


if __name__ == '__main__':
    main()

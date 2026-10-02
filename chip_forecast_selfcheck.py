#!/usr/bin/env python3
"""Self-check: each forecast first re-predicts the concentrations it already measured.

Point forecasts are the frozen AnchorBoost of chip_forecast.py. A helper of the same kind trained with one measured
concentration fewer re-predicts every measured concentration from the other measured ones; its mean absolute error
on these known values is the chemical's self-check score. The score is used twice:
  intervals  normalised cross-conformal 90% intervals: |error| / score is calibrated per output on the other folds'
             chemicals (each predicted by the model that never trained on them); the half-width is the calibrated
             quantile times the chemical's own score, so the interval widens where the self-check fails;
  decision   chemicals ranked by score receive the full concentration series first ("measure more"); the forecast
             error that measuring removes is compared with simple ranking rules at a fixed share of chemicals.
Run: python chip_forecast_selfcheck.py --folds 0 1 2 3 4 --k 3 --out selfcheck_fold.npz   (one or more folds)
     python chip_forecast_selfcheck.py --analyze selfcheck_fold*.npz
"""
import argparse
import hashlib
import json
import math
import time
from pathlib import Path

import numpy as np

import chip_forecast as cf

ROOT = Path(__file__).resolve().parent
LEVEL = 0.90
BUDGETS = (0.10, 0.20, 0.30)
SIMPLE = ('activity', 'departure')


def self_check(helper, task, ic):
    """Mean absolute error of the helper on each measured concentration predicted from the others."""
    lv, mu, ok = cf.level_means(task, ic)
    errs = []
    for i, m in enumerate(lv):
        sub = np.isin(task.logc, np.delete(lv, i))
        pred = helper(task, sub, np.array([m]))[0]
        errs.append(np.abs(mu[i] - pred)[ok[i]])
    return float(np.mean(np.concatenate(errs)))


def run(tasks, folds, k):
    out, times = {}, {}
    for fold in folds:
        start = time.time()
        train = [t for t in tasks if t.fold != fold]
        model, helper = cf.AnchorBoost(train, k), cf.AnchorBoost(train, k - 1)
        rec = dict(chem=[], design=[], dims=[], errs=[], score=[], curve=[], scores_chem={n: [] for n in ('selfcheck',) + SIMPLE}, names=[])
        for ci, t in enumerate(t for t in tasks if t.fold == fold and k < len(t.levels)):
            curves, s_self, s_act, s_dep = [], [], [], []
            for di, ctx in enumerate(cf.designs(t, k)):
                ic = np.isin(t.logc, ctx)
                lv = np.unique(t.logc[~ic])
                pred = model(t, ic, lv)
                curves.append(cf.errors(pred, t, ~ic)[0])
                lvc, muc, okc = cf.level_means(t, ic)
                s = self_check(helper, t, ic)
                s_self.append(s)
                s_act.append(float(np.abs(muc[okc]).mean()))
                interp = cf.predict_interp(t, ic, lv)
                _, mut, okt = cf.level_means(t, ~ic)
                s_dep.append(float(np.abs(pred - interp)[okt].mean()))
                err = np.abs(pred[np.searchsorted(lv, t.logc[~ic])] - t.y[~ic])
                mm = t.m[~ic]
                n = int(mm.sum())
                rec['dims'].append(np.broadcast_to(np.arange(cf.D).reshape(cf.ND, cf.NF), err.shape)[mm])
                rec['errs'].append(err[mm])
                rec['chem'].append(np.full(n, ci))
                rec['design'].append(np.full(n, di))
                rec['score'].append(np.full(n, s))
            rec['names'].append(t.chem)
            rec['curve'].append(float(np.mean(curves)))
            for n, v in (('selfcheck', s_self), ('activity', s_act), ('departure', s_dep)):
                rec['scores_chem'][n].append(float(np.mean(v)))
        out[fold] = rec
        times[f'fold{fold}'] = dict(seconds=round(time.time() - start, 1))
    return out, times


def save(out, times, path, k):
    arrays = {}
    for fold, r in out.items():
        for n in ('chem', 'design', 'dims', 'errs', 'score'):
            arrays[f'fold{fold}_{n}'] = np.concatenate(r[n]).astype(np.float32 if n in ('errs', 'score') else np.int16)
        arrays[f'fold{fold}_curve'] = np.array(r['curve'])
        arrays[f'fold{fold}_names'] = np.array(r['names'])
        for n, v in r['scores_chem'].items():
            arrays[f'fold{fold}_chemscore_{n}'] = np.array(v)
    np.savez_compressed(path, **arrays)
    path.with_suffix('.json').write_text(json.dumps(dict(k=k, folds=sorted(out), timing=times,
                                                         code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()), indent=1) + '\n')


def load(paths):
    parts = {}
    for path in paths:
        z = np.load(path)
        for key in z.files:
            fold, name = key.split('_', 1)
            parts.setdefault(int(fold[4:]), {})[name] = z[key]
    return parts


def quantile(values):
    v = np.sort(values)
    return v[min(len(v) - 1, math.ceil((len(v) + 1) * LEVEL) - 1)]


def boot_ratio(num, den, rng, n=4000):
    """Chemical bootstrap of sum(num)/sum(den) with paired resampling."""
    idx = [rng.integers(0, len(num), len(num)) for _ in range(n)]
    vals = np.array([num[i].sum() / den[i].sum() for i in idx])
    return [round(float(np.percentile(vals, 2.5)), 4), round(float(np.percentile(vals, 97.5)), 4)]


def intervals(parts, test_folds):
    """Plain and self-check-normalised cross-conformal intervals; widths compared per chemical."""
    folds = sorted(parts)
    res, rows = {}, []
    for f in test_folds:
        cal = [g for g in folds if g != f]
        d, e, s = (np.concatenate([parts[g][n] for g in cal]) for n in ('dims', 'errs', 'score'))
        scale = float(np.median(np.concatenate([parts[g]['chemscore_selfcheck'] for g in cal])))
        plain = np.array([quantile(e[d == j]) for j in range(cf.D)])
        norm = np.array([quantile(e[d == j] / (s[d == j] + scale)) for j in range(cf.D)])
        P = parts[f]
        hp = plain[P['dims']]
        hn = norm[P['dims']] * (P['score'] + scale)
        for c in np.unique(P['chem']):
            m = P['chem'] == c
            rows.append((f, int(c), m.sum(), (P['errs'][m] <= hp[m]).sum(), (P['errs'][m] <= hn[m]).sum(), hp[m].sum(), hn[m].sum()))
    a = np.array(rows, float)
    rng = np.random.default_rng(0)
    res['plain'] = dict(coverage=round(a[:, 3].sum() / a[:, 2].sum(), 4), coverage_ci95=boot_ratio(a[:, 3], a[:, 2], rng),
                        mean_half_width=round(a[:, 5].sum() / a[:, 2].sum(), 3))
    res['selfcheck'] = dict(coverage=round(a[:, 4].sum() / a[:, 2].sum(), 4), coverage_ci95=boot_ratio(a[:, 4], a[:, 2], rng),
                            mean_half_width=round(a[:, 6].sum() / a[:, 2].sum(), 3))
    res['width_ratio_selfcheck_over_plain'] = dict(value=round(a[:, 6].sum() / a[:, 5].sum(), 4), ci95=boot_ratio(a[:, 6], a[:, 5], rng))
    res['wells'] = int(a[:, 2].sum())
    res['chemicals'] = len(a)
    return res


def removed(curve, score, budget):
    """Share of total forecast error removed by fully measuring the top-scoring chemicals."""
    n = int(round(budget * len(curve)))
    order = np.argsort(-score, kind='stable')
    return curve[order[:n]].sum() / curve.sum()


def decisions(parts, test_folds, dev_fold=0):
    """Measure-more ranking: self-check against simple rules; the best simple rule is chosen on the development fold."""
    def pooled(folds, name):
        return (np.concatenate([parts[f]['curve'] for f in folds]), np.concatenate([parts[f][f'chemscore_{name}'] for f in folds]))
    dev = {n: removed(*pooled([dev_fold], n), 0.20) for n in SIMPLE}
    best = max(dev, key=dev.get)
    curve, s_self = pooled(test_folds, 'selfcheck')
    _, s_best = pooled(test_folds, best)
    rng = np.random.default_rng(0)
    out = dict(best_simple_rule_on_dev_fold=best, dev_fold_removed_at_20pct={n: round(v, 4) for n, v in dev.items()}, budgets={})
    for b in BUDGETS:
        cell = {n: round(removed(curve, pooled(test_folds, n)[1], b), 4) for n in ('selfcheck',) + SIMPLE}
        cell['random_expected'] = b
        cell['oracle'] = round(removed(curve, curve, b), 4)
        diffs = []
        for _ in range(4000):
            i = rng.integers(0, len(curve), len(curve))
            diffs.append(removed(curve[i], s_self[i], b) - removed(curve[i], s_best[i], b))
        cell['selfcheck_minus_best_simple'] = dict(value=round(cell['selfcheck'] - cell[best], 4),
                                                   ci95=[round(float(np.percentile(diffs, 2.5)), 4), round(float(np.percentile(diffs, 97.5)), 4)])
        out['budgets'][f'{int(b * 100)}pct'] = cell
    out['chemicals'] = len(curve)
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--cache', type=Path, default=ROOT / '.cache' / 'neurochip_twin')
    p.add_argument('--folds', type=int, nargs='+', default=[0, 1, 2, 3, 4])
    p.add_argument('--k', type=int, default=3)
    p.add_argument('--out', type=Path, default=ROOT / 'chip_forecast_selfcheck.npz')
    p.add_argument('--analyze', type=Path, nargs='+')
    a = p.parse_args()
    if a.analyze:
        parts = load(a.analyze)
        test = [f for f in sorted(parts) if f != 0]
        print(json.dumps(dict(intervals=intervals(parts, test), decisions=decisions(parts, test)), indent=1))
        return
    files = cf.fetch(a.cache)
    tasks = cf.load_tasks(files['data_bundle/nfa_tasks.npz'])
    out, times = run(tasks, a.folds, a.k)
    save(out, times, a.out, a.k)
    print(json.dumps(times))


if __name__ == '__main__':
    main()

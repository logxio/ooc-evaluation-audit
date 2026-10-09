#!/usr/bin/env python3
"""TabPFN-2 teacher for ab_v3: inner out-of-fold predictions on every canonical training row, or the outer test re-run.

Unit (--fold f --k k --inner j): library and context come from the inner training chemicals (outer training
chemicals outside inner fold j). Context: 10,000 cells drawn uniformly without replacement from their canonical rows
with default_rng(1000k + f + 100000(j + 1)); features are the TP2V member's 46 columns (30 AnchorBoost-v2 DWC columns
+ CheMeleon PCA16 of the fold), target response minus anchor. TabPFN-2 (n_estimators 8, random_state 0,
fit_with_cache, columns 20 and 21 categorical), as ab_v2/tp2_run.py. Every canonical row of the inner-fold-j
chemicals is predicted with the test construction (library without them), on the designs that carry teacher
rows (v3common.kept_designs: the five kit designs plus 24 hashed designs per chemical). Outputs mean, median and quantiles
0.1/0.25/0.75/0.9, written at response level with the anchor.

--outer: the TP2V member itself (S1's context draw default_rng(1000k + f) over all outer training rows, library =
all outer training chemicals) on the kit designs of the fold-f chemicals, same outputs, kit format. Its median is
checked against ab_v2/runs_tp2/TP2V_chemeleon/fold{f}_k{k}.npz.

  python teach_tp2.py --fold 0 --k 3 --inner 2 --device cuda      -> teachers/tp2/f0_k3_j2.npz (+ .json)
  python teach_tp2.py --fold 0 --k 3 --outer --device cuda         -> teachers/tp2/outer_f0_k3.npz (+ .json)
"""
import argparse
import hashlib
import json
import os
import platform
import resource
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import v3common as V  # noqa: E402

D = V.D
N_CONTEXT = 10000
WEIGHTS = ('tabpfn-v2-regressor.ckpt', '2ab5a07d5c41dfe6db9aa7ae106fc6de898326c2765be66505a07e2868c10736')


def context(fm, pairs, sizes, zraw, n, seed):
    """S1's pooled context draw over the given pairs' canonical cells: features, anchor and response."""
    off = np.concatenate([[0], np.cumsum(sizes)])
    rng = np.random.default_rng(seed)
    pick = np.sort(rng.choice(int(off[-1]), size=min(n, int(off[-1])), replace=False))
    p_of = np.searchsorted(off, pick, side='right') - 1
    X = base = y = None
    for p in np.unique(p_of):
        sel = np.where(p_of == p)[0]
        t, ctx = pairs[p]
        ic = np.isin(t.logc, ctx)
        lv, qi, oi = V.pair_cells(t, ctx)
        b, f = fm._design(t, ic, lv, fm.analog_train, True)
        mu = t.mu[~np.isin(t.levels, ctx)].reshape(len(lv), D)
        cell = pick[sel] - off[p]
        q_, o_ = qi[cell], oi[cell]
        if X is None:
            X = np.empty((len(pick), f.shape[-1] + 16))
            base, y = np.empty(len(pick)), np.empty(len(pick))
        X[sel, :f.shape[-1]] = f[q_, o_]
        X[sel, f.shape[-1]:] = zraw[t.chem]
        base[sel], y[sel] = b[q_, o_], mu[q_, o_]
    return X, base, y


def regressor(device):
    from tabpfn import TabPFNRegressor
    from tabpfn.constants import ModelVersion
    return TabPFNRegressor.create_default_for_version(ModelVersion('v2'), device=device, n_estimators=8, random_state=0,
                                                      fit_mode='fit_with_cache', categorical_features_indices=[20, 21])


def predict_main(reg, X, batch):
    out = {c: np.empty(len(X)) for c in V.T_COLS}
    for s in range(0, len(X), batch):
        r = slice(s, s + batch)
        m = reg.predict(X[r], output_type='main', quantiles=V.T_QUANTILES)
        out['mean'][r], out['median'][r] = m['mean'], m['median']
        for name, q in zip(('q10', 'q25', 'q75', 'q90'), m['quantiles']):
            out[name][r] = q
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--fold', type=int, required=True)
    p.add_argument('--k', type=int, required=True)
    p.add_argument('--inner', type=int)
    p.add_argument('--outer', action='store_true')
    p.add_argument('--device', default='cuda')
    p.add_argument('--batch', type=int, default=4000)
    p.add_argument('--max-rows', type=int, default=0, help='smoke test: predict only this many rows')
    p.add_argument('--weights', type=Path, default=Path(os.environ.get('ABV3_TP2_WEIGHTS', V.HERE / 'tp2_weights')))
    p.add_argument('--out', type=Path, default=V.HERE / 'teachers' / 'tp2')
    a = p.parse_args()
    assert a.outer != (a.inner is not None), 'give --inner j or --outer'
    name = f'outer_f{a.fold}_k{a.k}' if a.outer else f'f{a.fold}_k{a.k}_j{a.inner}'
    out = a.out / f'{name}.npz'
    if out.exists():
        print(json.dumps({'exists': str(out)}))
        return
    t0 = time.time()
    assert V.sha(a.weights / WEIGHTS[0]) == WEIGHTS[1], 'TabPFN-2 weights differ from the pinned file'
    os.environ.setdefault('TABPFN_MODEL_CACHE_DIR', str(a.weights))
    cf, abv2, tasks, meta, identity, zraw = V.load_env(a.fold)
    train, pairs, sizes, offsets = V.canonical(cf, tasks, a.fold, a.k)
    if a.outer:
        lib = train
        cpairs, csizes = pairs, sizes
        seed = 1000 * a.k + a.fold
    else:
        inner = V.inner_assignment(a.fold, tasks, identity)
        lib = [t for t in train if inner[t.chem] != a.inner]
        keep = np.array([inner[t.chem] != a.inner for t, _ in pairs])
        cpairs = [pq for pq, kp in zip(pairs, keep) if kp]
        csizes = sizes[keep]
        seed = 1000 * a.k + a.fold + 100000 * (a.inner + 1)
    fm = V.feature_maker(cf, abv2, lib, meta)
    Xc, bc, yc = context(fm, cpairs, csizes, zraw, N_CONTEXT, seed)
    t_ctx = time.time() - t0
    # rows to predict
    X, base, where = [], [], []
    if a.outer:
        km = V.KitMap(a.k)
        for t in (t for t in tasks if t.fold == a.fold and a.k < len(t.levels)):
            for di, ctx in enumerate(cf.designs(t, a.k)):
                ic = np.isin(t.logc, ctx)
                lv, qi, oi = V.pair_cells(t, ctx)
                b, f = fm._design(t, ic, lv, fm.analog, False)
                X.append(np.concatenate([f[qi, oi], np.repeat(zraw[t.chem][None], len(qi), 0)], 1))
                base.append(b[qi, oi])
                where.append(np.stack([[km.qid[(t.chem, di, km.ci(lv[j]))] for j in qi], oi], 1))
    else:
        kept = V.kept_mask(cf, pairs, a.k)
        for pi, (t, ctx) in enumerate(pairs):
            if inner[t.chem] != a.inner or not kept[pi]:
                continue
            ic = np.isin(t.logc, ctx)
            lv, qi, oi = V.pair_cells(t, ctx)
            b, f = fm._design(t, ic, lv, fm.analog, False)
            X.append(np.concatenate([f[qi, oi], np.repeat(zraw[t.chem][None], len(qi), 0)], 1))
            base.append(b[qi, oi])
            where.append(np.arange(offsets[pi], offsets[pi + 1], dtype=np.int64))
    X, base, where = np.concatenate(X), np.concatenate(base), np.concatenate(where)
    if a.max_rows:
        X, base, where = X[:a.max_rows], base[:a.max_rows], where[:a.max_rows]
    t_feat = time.time() - t0
    import tabpfn
    import torch
    reg = regressor(a.device).fit(Xc, yc - bc)
    pred = predict_main(reg, X, a.batch)
    a.out.mkdir(parents=True, exist_ok=True)
    res = {}
    if a.outer:
        for c in V.T_COLS:
            P = np.full((km.n, D), np.nan)
            P[where[:, 0], where[:, 1]] = pred[c] + base
            res[c] = P
        ref = V.R / 'ab_v2' / 'runs_tp2' / 'TP2V_chemeleon' / f'fold{a.fold}_k{a.k}.npz'
        check = None
        if ref.exists() and not a.max_rows:
            with np.load(ref) as z:
                M = z[f'k{a.k}']
            sel = km.fold == a.fold
            check = float(np.nanmax(np.abs(M[sel] - res['median'][sel])))
    else:
        res = {c: (pred[c] + base).astype(np.float32) for c in V.T_COLS}
        res['rows'] = where
        res['base'] = base
        check = None
    np.savez_compressed(out, **res)
    log = dict(unit=name, fold=a.fold, k=a.k, inner=a.inner, outer=a.outer, context_rows=int(len(yc)), context_seed=seed,
               library_chemicals=len(lib), predicted_rows=int(len(X)), canonical_rows=int(offsets[-1]),
               canonical_fingerprint=hashlib.sha256(sizes.tobytes()).hexdigest()[:16], n_features=int(X.shape[1]),
               max_abs_diff_median_vs_TP2V_member=check, seconds=round(time.time() - t0, 1),
               context_seconds=round(t_ctx, 1), feature_seconds=round(t_feat, 1), tabpfn=tabpfn.__version__,
               torch=torch.__version__, numpy=np.__version__, device=a.device, platform=platform.platform(),
               gpu=torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
               peak_gpu_gb=round(torch.cuda.max_memory_allocated() / 1e9, 3) if torch.cuda.is_available() else None,
               peak_rss_gb=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1e9 if sys.platform == 'darwin' else 1e6), 3),
               weights_sha256=WEIGHTS[1], output_sha256=V.sha(out))
    out.with_suffix('.json').write_text(json.dumps(log, indent=1) + '\n')
    print(json.dumps({k: log[k] for k in ('unit', 'predicted_rows', 'seconds', 'feature_seconds', 'max_abs_diff_median_vs_TP2V_member')}))


if __name__ == '__main__':
    main()

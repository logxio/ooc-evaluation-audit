#!/usr/bin/env python3
"""Fit the selected commercial residual stack on one held-out fold.

SBr fits a conservative five-bag GBM to the response residual above the
inner-selected TabPFN-2 + LPM blend. SBZ adds CheMeleon PCA16 and a structure
weighted analog feature. Both use the frozen 200-iteration booster settings.
Training rows use the five kit designs and 24 hashed designs per chemical;
the teacher block comes from inner out-of-fold predictions. Held-out designs
use outer teacher predictions. The command is called by train.py.
"""
import argparse
import json
import os
import platform
import resource
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import v3common as V  # noqa: E402

D = V.D
BLACKSWAN = Path(os.environ.get('ABV3_BLACKSWAN', V.HERE))
CONS = dict(loss='absolute_error', max_iter=200, learning_rate=0.03, max_leaf_nodes=31, min_samples_leaf=500,
            l2_regularization=1.0, early_stopping=False, random_state=0)
CANDS = {
    'SBr': dict(teach=True, raw_struct=False, mix_lam=0.0, params=CONS, resid=True),
    'SBZ': dict(teach=True, raw_struct=True, mix_lam=4.0, params=CONS, resid=True),
}
N_TEACH = 10


def teacher_block(T, L, base):
    """T (..., 6) TabPFN-2 mean, median, q10, q25, q75, q90; L (..., 2) LPM seed mean, seed SD; base (...)."""
    tmean, tmed, q10, q25, q75, q90 = (T[..., i] for i in range(6))
    lm, lsd = L[..., 0], L[..., 1]
    return np.stack([tmed - base, tmean - base, q10 - base, q25 - base, q75 - base, q90 - base, lm - base, lsd,
                     tmed - lm, q90 - q10], -1)


class AnalogView:
    """The release cf.Analog through blackswan's Analog interface: at(x) -> (n, Q, 68), dist2 = the release distance."""

    def __init__(self, analog):
        self.a, self.index = analog, analog.index

    def at(self, x):
        A = self.a.at(np.asarray(x, np.float64))
        return A.reshape(A.shape[0], A.shape[1], D)

    def dist2(self, lv, mu, ok, name=None):
        d2 = (((self.at(lv) - mu[None]) ** 2) * ok[None]).sum((1, 2)) / max(ok.sum(), 1)
        if name in self.index:
            d2[self.index[name]] = np.inf
        return d2


def make_model(abv2):
    class AnchorBoostV3(abv2.AnchorBoostV2):
        def __init__(self, cf, train, k, meta, cfg, spec, zraw=None, struct=None, teach_rows=None, soft=None, blend=None):
            self.spec = spec
            self.zraw = zraw
            self._teach_rows = teach_rows      # (T (N, 6), L (N, 2)) aligned to the canonical rows of `train`
            self._soft = soft                  # (beta, wT, wL) for the distiller
            self._blend = blend                # (wT, wL) of the T+L team for residual stacking
            self._struct = struct
            self._names = [t.chem for t in train]
            self._at = {c: i for i, c in enumerate(self._names)}
            self._keep = {t.chem: V.kept_designs(cf, t, k) for t in train if k < len(t.levels)}
            super().__init__(cf, train, k, meta, cfg)

        def _design(self, task, ic, q, analog, training):
            base, f = super()._design(task, ic, q, analog, training)
            extra = []
            if self.spec['raw_struct']:
                extra += list(np.asarray(self.zraw[task.chem], np.float64))
            if self.spec['mix_lam'] > 0:
                import blocks as B
                lv, mu, ok = self.cf.level_means(task, ic)
                d2s = self._struct.dist2(task.chem, self._names)
                if d2s is not None and training and task.chem in self._at:
                    d2s = d2s.copy()
                    d2s[self._at[task.chem]] = np.inf
                p = B.mixed_neighbours(AnalogView(analog), lv, mu.reshape(len(lv), D), ok.reshape(len(lv), D), q,
                                       task.chem if training else None, d2s, self.spec['mix_lam']).reshape(len(q), D) - base
                extra += [p, np.abs(p).mean(1)[:, None]]
            if not extra:
                return base, f
            out = np.empty(f.shape[:2] + (f.shape[2] + len(extra),), np.float64)
            out[:, :, :f.shape[2]] = f
            for c, v in enumerate(extra):
                out[:, :, f.shape[2] + c] = v
            return base, out

        def _rows(self, train):
            # abv2.AnchorBoostV2._rows restricted to the designs that carry teacher rows (v3common.kept_designs)
            cf = self.cf
            rows = [(t, ctx) for t in train if self.k < len(t.levels) for ctx in cf.all_designs(t, self.k)
                    if V.design_key(ctx) in self._keep[t.chem]]
            sizes = [int(t.ok[~np.isin(t.levels, ctx)].sum()) for t, ctx in rows]
            t0, c0 = rows[0]
            n_feat = self._design(t0, np.isin(t0.logc, c0), t0.levels[:1], self.analog, False)[1].shape[-1]
            X = np.empty((sum(sizes), n_feat), np.float64)
            y = np.empty(sum(sizes), np.float64)
            chem = np.empty(sum(sizes), object)
            at = 0
            for (t, ctx), size in zip(rows, sizes):
                ic = np.isin(t.logc, ctx)
                lv, mu, ok = cf.level_means(t, ~ic)
                base, f = self._design(t, ic, lv, self.analog_train, True)
                keep = ok.reshape(-1)
                X[at:at + size] = f.reshape(-1, n_feat)[keep]
                y[at:at + size] = (mu.reshape(len(lv), D) - base).ravel()[keep]
                chem[at:at + size] = t.chem
                at += size
            base = X[:, 0]
            if self._teach_rows is not None:
                T, L = self._teach_rows
                if self._soft is not None:
                    beta, wt, wl = self._soft
                    if beta > 0:
                        mix = (wt * (T[:, 1].astype(np.float64) - base) + wl * (L[:, 0].astype(np.float64) - base)) / (wt + wl)
                        y = (1 - beta) * y + beta * mix
                if self.spec.get('resid'):
                    wt, wl = self._blend
                    y = y - (wt * (T[:, 1].astype(np.float64) - base) + wl * (L[:, 0].astype(np.float64) - base))
                if self.spec['teach']:
                    X = np.hstack([X, teacher_block(T.astype(np.float64), L.astype(np.float64), base)])
            self._teach_rows = None
            return X, y, chem

        def predict_design(self, task, ic, q, teach=None):
            base, f = self._design(task, ic, q, self.analog, False)
            F = f.reshape(-1, f.shape[-1])
            if self.spec['teach']:
                T, L = teach
                F = np.hstack([F, teacher_block(T, L, base).reshape(-1, N_TEACH)])
            pred = np.mean([m.predict(F) for m in self.models], axis=0).reshape(len(q), D)
            if self.spec.get('resid'):
                T, L = teach
                wt, wl = self._blend
                blend = wt * (T[..., 1] - base) + wl * (L[..., 0] - base)
                pred = pred + np.where(np.isfinite(blend), blend, 0.0)
            return pred + base

    return AnchorBoostV3


def load_teach(f, k):
    with np.load(HERE / 'teachers' / f'T_f{f}_k{k}.npz') as z:
        T = np.stack([z[c] for c in V.T_COLS], 1)
        tfp = str(z['fingerprint'])
    with np.load(HERE / 'teachers' / f'L_f{f}_k{k}.npz') as z:
        L = np.stack([z['mean'], z['sd']], 1)
        lfp = str(z['fingerprint'])
    return T, L, tfp, lfp


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--mode', choices=['inner', 'outer'], required=True)
    p.add_argument('--cand', choices=sorted(CANDS), required=True)
    p.add_argument('--fold', type=int, required=True)
    p.add_argument('--inner', type=int)
    p.add_argument('--k', type=int, required=True)
    p.add_argument('--beta', type=float, default=None)
    p.add_argument('--wt', type=float, default=None)
    p.add_argument('--wl', type=float, default=None)
    p.add_argument('--seed', type=int, default=0, help='bagging seed; outputs of seed s > 0 go to runs/<cand>_s<s>/ (second vote)')
    a = p.parse_args()
    spec = CANDS[a.cand]
    if a.mode == 'inner':
        out = HERE / 'inner' / a.cand / f'f{a.fold}_j{a.inner}_k{a.k}.npz'
    else:
        out = HERE / 'runs' / (a.cand if a.seed == 0 else f'{a.cand}_s{a.seed}') / f'fold{a.fold}_k{a.k}.npz'
    if out.exists():
        print(json.dumps({'exists': str(out)}))
        return
    t0 = time.time()
    cf, abv2, tasks, meta, identity, zraw = V.load_env(a.fold)
    sys.path.insert(0, str(BLACKSWAN))
    struct = None
    if spec['mix_lam'] > 0:
        import blocks as B
        s = np.load(V.STRUCT / 'structure_pca.npz')
        struct = B.Struct([str(c) for c in s['chemicals']], s[f'chemeleon_fold{a.fold}'])
    train, pairs, sizes, offsets = V.canonical(cf, tasks, a.fold, a.k)
    T, L, tfp, lfp = load_teach(a.fold, a.k)
    import hashlib
    fp = hashlib.sha256(sizes.tobytes()).hexdigest()[:16]
    assert tfp == fp and lfp == fp and len(T) == offsets[-1], 'teacher arrays are not aligned to the canonical rows'
    kept = V.kept_mask(cf, pairs, a.k)
    if a.mode == 'inner':
        inner = V.inner_assignment(a.fold, tasks, identity)
        lib = [t for t in train if inner[t.chem] != a.inner]
        use = kept & np.array([inner[t.chem] != a.inner for t, _ in pairs])
        n_bag = 1
    else:
        lib = train
        use = kept
        n_bag = 5
    rows = np.repeat(use, sizes)
    rows_T, rows_L = T[rows], L[rows]
    assert np.isfinite(rows_T).all() and np.isfinite(rows_L).all(), 'teacher rows missing on kept designs'
    cfg = dict(V.DWC, n_bag=n_bag, params=spec['params'], seed=a.seed)
    soft = (a.beta, a.wt, a.wl) if a.cand.startswith('DI') else None
    if a.cand.startswith('DI'):
        assert a.beta is not None and a.wt is not None and a.wl is not None, 'DI and DIZ need --beta --wt --wl'
    Model = make_model(abv2)
    blend = None
    if spec.get('resid'):
        assert a.wt is not None and a.wl is not None, 'residual stackers need --wt --wl (T+L team weights)'
        blend = (a.wt, a.wl)
    model = Model(cf, lib, a.k, meta, cfg, spec, zraw=zraw, struct=struct, teach_rows=(rows_T, rows_L), soft=soft, blend=blend)
    t_fit = time.time() - t0
    km = V.KitMap(a.k)
    P = np.full((km.n, D), np.nan)
    n = 0
    if a.mode == 'inner':
        index = V.pairs_lookup(pairs)
        targets = [t for t in train if inner[t.chem] == a.inner and a.k < len(t.levels)]
    else:
        targets = [t for t in tasks if t.fold == a.fold and a.k < len(t.levels)]
        z = np.load(HERE / 'teachers' / 'tp2' / f'outer_f{a.fold}_k{a.k}.npz')
        To = np.stack([z[c] for c in V.T_COLS], -1)
        zl = np.load(HERE / 'teachers' / f'L_test_k{a.k}.npz')
        Lo = np.stack([zl['mean'], zl['sd']], -1)
    for t in targets:
        for di, ctx in enumerate(cf.designs(t, a.k)):
            ic = np.isin(t.logc, ctx)
            lv = np.unique(t.logc[~ic])
            qid = np.array([km.qid[(t.chem, di, km.ci(x))] for x in lv])
            teach = None
            if spec['teach']:
                if a.mode == 'inner':
                    pi = index[(t.chem, tuple(np.asarray(ctx, np.float32).tolist()))]
                    lv2, qi, oi = V.pair_cells(t, ctx)
                    assert np.allclose(lv2, lv)
                    Tq = np.full((len(lv), D, 6), np.nan)
                    Lq = np.full((len(lv), D, 2), np.nan)
                    Tq[qi, oi] = T[offsets[pi]:offsets[pi + 1]]
                    Lq[qi, oi] = L[offsets[pi]:offsets[pi + 1]]
                else:
                    Tq, Lq = To[qid], Lo[qid]
                teach = (Tq.astype(np.float64), Lq.astype(np.float64))
            P[qid] = model.predict_design(t, ic, lv, teach)
            n += len(lv)
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out, **{f'k{a.k}': P})
    log = dict(mode=a.mode, cand=a.cand, spec=spec, fold=a.fold, inner=a.inner, k=a.k, soft=soft, blend=blend, n_bag=n_bag,
               library_chemicals=len(lib), predicted_chemicals=len(targets), query_rows=n, training_rows=model.rows,
               n_features=model.n_features, fit_seconds=round(t_fit, 1),
               seconds=round(time.time() - t0, 1), canonical_fingerprint=fp, python=sys.version.split()[0],
               numpy=np.__version__, sklearn=__import__('sklearn').__version__, platform=platform.platform(),
               threads=os.environ.get('OMP_NUM_THREADS'),
               peak_rss_gb=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1e9 if sys.platform == 'darwin' else 1e6), 3),
               output_sha256=V.sha(out))
    out.with_suffix('.json').write_text(json.dumps(log, indent=1) + '\n')
    print(json.dumps({k: log[k] for k in ('mode', 'cand', 'fold', 'inner', 'k', 'training_rows', 'n_features', 'fit_seconds', 'seconds', 'peak_rss_gb')}))


if __name__ == '__main__':
    main()

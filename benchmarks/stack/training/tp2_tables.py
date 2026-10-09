#!/usr/bin/env python3
"""Feature tables for the TabPFN-2 member of AnchorBoost-v2: one row per (chemical, design, unmeasured tested
concentration, output) cell, for the training-chemical context and the test designs of one fold and k.

Rows, designs, the 10,000-cell pooled context sample (default_rng(1000 * k + fold) over the full training design
enumeration) and the residual target follow S1 / S3 (sota_baselines/tabpfn/tabpfn_run.py, sota_baselines_3/
s3_features.py, read only). Columns: 'ab22' = the release AnchorBoost features; 'v2' = the same 22 plus the DWS
neighbour columns of abv2 (date, similarity-weighted date, Monroe structure neighbours), training rows built exactly
as the booster's training rows (no row sees its own identity group). PCA16 structure columns of the fold (CheMeleon by
default; Monroe is out after the pretraining-label overlap check) are appended in both cases. DIV and feature index stay at columns 20 and 21 (categorical).

  python tp2_tables.py --features v2 --fold 0 --k 3      -> tp2/tables/{test,context}_<features>_fold<f>_k<k>.npz
"""
import argparse
import csv
import json
import os
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import v3common as V  # noqa: E402

D = 68
N_CONTEXT = 10000


def feature_maker(cf, abv2, train, meta, features, cand):
    return V.feature_maker(cf, abv2, train, meta)


def build(fold, k, features, out, struct='chemeleon', cand='DWC', draw=0, part='both'):
    cf, abv2, tasks, meta, identity, zraw = V.load_env(fold)
    kit = V.KIT
    z = np.load(kit / 'data' / 'matrix.npz')
    conc = z['log10_conc_um']
    chem_index = {str(c): i for i, c in enumerate(z['chemicals'])}
    qid = {(r['chemical'], int(r['design']), int(r['conc_index'])): int(r['query_id'])
           for r in csv.DictReader((kit / 'tasks' / f'k{k}_queries.csv').open())}
    s = np.load(V.STRUCT / 'structure_pca.npz')
    Z = s[f'{struct}_fold{fold}'].astype(np.float64)
    assert [str(c) for c in s['chemicals']] == [str(c) for c in z['chemicals']]
    train = [t for t in tasks if t.fold != fold]
    fm = feature_maker(cf, abv2, train, meta, features, cand)
    out.mkdir(parents=True, exist_ok=True)
    # test rows
    X, base, q, o, c = [], [], [], [], []
    for t in (t for t in tasks if t.fold == fold and k < len(t.levels)):
        for di, ctx in enumerate(cf.designs(t, k)):
            ic = np.isin(t.logc, ctx)
            lv = t.levels[~np.isin(t.levels, ctx)]
            b, f = fm._design(t, ic, lv, fm.analog, False)
            ok = t.ok[~np.isin(t.levels, ctx)].reshape(len(lv), D)
            qi, oi = np.nonzero(ok)
            X.append(np.concatenate([f[qi, oi], Z[chem_index[t.chem]][None].repeat(len(qi), 0)], 1))
            base.append(b[qi, oi]); o.append(oi)
            q.append([qid[(t.chem, di, int(np.searchsorted(conc, lv[j])))] for j in qi])
            c.append(np.full(len(qi), chem_index[t.chem], np.int64))
    tag = f'{features}_{struct}'
    if part != 'context':
      np.savez_compressed(out / f'test_{tag}_fold{fold}_k{k}.npz', X=np.concatenate(X), base=np.concatenate(base),
                        query=np.concatenate(q).astype(np.int64), output=np.concatenate(o).astype(np.int64), chem=np.concatenate(c))
    # pooled context, S1's sample
    tr = [t for t in train if k < len(t.levels)]
    pairs, cp, cq, co = [], [], [], []
    for ti, t in enumerate(tr):
        for ctx in cf.all_designs(t, k):
            ok = t.ok[~np.isin(t.levels, ctx)].reshape(-1, D)
            qi, oi = np.nonzero(ok)
            cp.append(np.full(len(qi), len(pairs), np.int64)); cq.append(qi); co.append(oi)
            pairs.append((ti, ctx))
    cp, cq, co = np.concatenate(cp), np.concatenate(cq), np.concatenate(co)
    rng = np.random.default_rng(1000 * k + fold + 100000 * draw)   # draw 0 = S1's sample
    pick = np.sort(rng.choice(len(cp), size=min(N_CONTEXT, len(cp)), replace=False))
    order = np.argsort(cp[pick], kind='stable')
    rows = pick[order]
    feats, bb, yy, ch = None, np.empty(len(pick)), np.empty(len(pick)), np.empty(len(pick), np.int64)
    start = 0
    while start < len(rows):
        p = cp[rows[start]]
        stop = start
        while stop < len(rows) and cp[rows[stop]] == p:
            stop += 1
        ti, ctx = pairs[p]
        t = tr[ti]
        ic = np.isin(t.logc, ctx)
        lv = t.levels[~np.isin(t.levels, ctx)]
        b, f = fm._design(t, ic, lv, fm.analog_train, True)
        mu = t.mu[~np.isin(t.levels, ctx)].reshape(len(lv), D)
        sel = rows[start:stop]
        if feats is None:
            feats = np.empty((len(pick), f.shape[-1] + Z.shape[1]))
        feats[order[start:stop], :f.shape[-1]] = f[cq[sel], co[sel]]
        feats[order[start:stop], f.shape[-1]:] = Z[chem_index[t.chem]]
        bb[order[start:stop]] = b[cq[sel], co[sel]]
        yy[order[start:stop]] = mu[cq[sel], co[sel]]
        ch[order[start:stop]] = chem_index[t.chem]
        start = stop
    test_chems = {chem_index[t.chem] for t in tasks if t.fold == fold}
    assert not set(ch.tolist()) & test_chems, 'a test chemical is in the context'
    np.savez_compressed(out / (f'context_{tag}_fold{fold}_k{k}.npz' if draw == 0 else f'context_{tag}_d{draw}_fold{fold}_k{k}.npz'), X=feats, base=bb, y=yy, output=co[pick].astype(np.int64),
                        chem=ch, enumerated=len(cp))
    print(json.dumps(dict(features=features, struct=struct, cand=cand, draw=draw, fold=fold, k=k, test_rows=int(sum(len(x) for x in q)), context_rows=len(pick),
                          n_features=int(feats.shape[1]))))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--features', choices=['ab22', 'v2'], required=True)
    p.add_argument('--fold', type=int, required=True)
    p.add_argument('--k', type=int, required=True)
    p.add_argument('--struct', default='chemeleon', choices=['chemeleon', 'morgan'])
    p.add_argument('--cand', default='DWC', help='abv2 candidate whose neighbour columns the v2 table carries')
    p.add_argument('--draw', type=int, default=0, help='context sample: 0 = S1 rng(1000k+f), d adds 100000*d')
    p.add_argument('--part', default='both', choices=['both', 'context'])
    p.add_argument('--out', type=Path, default=HERE / 'tp2' / 'tables')
    a = p.parse_args()
    build(a.fold, a.k, a.features, a.out, a.struct, a.cand, a.draw, a.part)


if __name__ == '__main__':
    main()

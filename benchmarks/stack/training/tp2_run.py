#!/usr/bin/env python3
"""TabPFN-2 member of AnchorBoost-v2 on one fold and k (tables from tp2_tables.py).

TabPFN-2 regressor (Prior Labs License 1.1: Apache 2.0 plus attribution, commercial use allowed; weights
tabpfn-v2-regressor.ckpt sha256 2ab5a07d...), n_estimators 8, random_state 0, fit_mode fit_with_cache, DIV and
feature index categorical (columns 20, 21), target = response minus the interpolation anchor, output = median
(P8's decoding). One fit on the 10,000-cell pooled context, all test cells predicted in batches; query rows never
attend to each other. Writes kit-format predictions (key k{k}, rows aligned to kit/tasks/k{k}_queries.csv).

  python tp2_run.py --features v2 --fold 0 --k 3 --device cuda   -> tp2/runs/TP2<f>/fold<f>_k<k>.npz
"""
import argparse
import csv
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
WEIGHTS = ('tabpfn-v2-regressor.ckpt', '2ab5a07d5c41dfe6db9aa7ae106fc6de898326c2765be66505a07e2868c10736')
D = 68
NAME = {'ab22': 'TP2S', 'v2': 'TP2V'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--features', choices=['ab22', 'v2'], required=True)
    p.add_argument('--fold', type=int, required=True)
    p.add_argument('--k', type=int, required=True)
    p.add_argument('--struct', default='chemeleon', choices=['chemeleon', 'morgan'])
    p.add_argument('--draw', type=int, default=0)
    p.add_argument('--device', default='cuda')
    p.add_argument('--batch', type=int, default=4000)
    p.add_argument('--weights', type=Path, default=HERE / 'tp2_weights')
    p.add_argument('--tables', type=Path, default=HERE / 'tp2' / 'tables')
    p.add_argument('--kit', type=Path, default=HERE / 'kit')
    a = p.parse_args()
    tag = f'{a.features}_{a.struct}'
    dsuf = '' if a.draw == 0 else f'_d{a.draw}'
    out = HERE / 'tp2' / 'runs' / f'{NAME[a.features]}_{a.struct}{dsuf}' / f'fold{a.fold}_k{a.k}.npz'
    if out.exists():
        print(json.dumps({'exists': str(out)}))
        return
    t0 = time.time()
    assert sha(a.weights / WEIGHTS[0]) == WEIGHTS[1], 'TabPFN-2 weights differ from the pinned file'
    os.environ.setdefault('TABPFN_MODEL_CACHE_DIR', str(a.weights))
    ctx = dict(np.load(a.tables / f'context_{tag}{dsuf}_fold{a.fold}_k{a.k}.npz'))
    test = dict(np.load(a.tables / f'test_{tag}_fold{a.fold}_k{a.k}.npz'))
    assert not np.isin(ctx['chem'], np.unique(test['chem'])).any(), 'a test chemical is in the context'
    from tabpfn import TabPFNRegressor
    from tabpfn.constants import ModelVersion
    import tabpfn
    import torch
    reg = TabPFNRegressor.create_default_for_version(ModelVersion('v2'), device=a.device, n_estimators=8, random_state=0,
                                                     fit_mode='fit_with_cache', categorical_features_indices=[20, 21])
    reg.fit(ctx['X'], ctx['y'] - ctx['base'])
    pred = np.empty(len(test['X']))
    for s in range(0, len(pred), a.batch):
        r = slice(s, s + a.batch)
        pred[r] = reg.predict(test['X'][r], output_type='median')
    n_q = sum(1 for _ in csv.DictReader((a.kit / 'tasks' / f'k{a.k}_queries.csv').open()))
    P = np.full((n_q, D), np.nan)
    P[test['query'], test['output']] = pred + test['base']
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out, **{f'k{a.k}': P})
    log = dict(member=NAME[a.features], features=a.features, struct=a.struct, fold=a.fold, k=a.k, context_rows=int(len(ctx['y'])),
               test_cells=int(len(pred)), n_features=int(test['X'].shape[1]), seconds=round(time.time() - t0, 1),
               tabpfn=tabpfn.__version__, torch=torch.__version__, device=a.device,
               gpu=torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
               peak_gpu_gb=round(torch.cuda.max_memory_allocated() / 1e9, 3) if torch.cuda.is_available() else None,
               weights_sha256=WEIGHTS[1], output_sha256=sha(out))
    out.with_suffix('.json').write_text(json.dumps(log, indent=1) + '\n')
    print(json.dumps({k: log[k] for k in ('member', 'fold', 'k', 'test_cells', 'seconds', 'peak_gpu_gb')}))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""LPM teacher for ab_v3: inner out-of-fold predictions on every canonical training row (k = 1-4) for one seed.

Unit (--fold f --inner j --seed s): S5's frozen LPM (vendor/lpm/lpm_run.py, unchanged: LINCS architecture, recording-
date context, dose lookup, inference-time optimisation lambda 0.1 for 200 steps) trained on the wells of the outer
training chemicals outside inner fold j. For every k, every design that carries teacher rows (v3common.kept_designs) of every
inner-fold-j chemical gets its compound embedding from its revealed cells only and the level means at its unrevealed tested
concentrations; designs go through the optimiser in chunks (each design has its own embedding and loss term, so
chunking changes nothing). Writes teachers/lpm/f{f}_j{j}_s{seed}.npz with rows_k{k} (canonical indices) and pred_k{k}.

  python teach_lpm.py --fold 0 --inner 2 --seed 13 --device cuda
"""
import argparse
import hashlib
import json
import os
import platform
import resource
import sys
import time
import warnings
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import v3common as V  # noqa: E402

os.environ.setdefault('S5_KIT', str(V.KIT))
os.environ.setdefault('S5_HERE', str(HERE / 'vendor' / 'lpm'))
sys.path.insert(0, str(HERE / 'vendor' / 'lpm'))
LPM_SHA = '1a60304ca9c01c984558f19bc3a7b2ce539e0987d4ed780ed274b6d6310b2fb2'
FROZEN = dict(arch='lincs', context='date', dose='lookup', lam=0.1, steps=200)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--fold', type=int, required=True)
    p.add_argument('--inner', type=int, required=True)
    p.add_argument('--seed', type=int, required=True)
    p.add_argument('--device', default='cuda')
    p.add_argument('--chunk', type=int, default=1200)
    p.add_argument('--ks', type=int, nargs='+', default=list(V.KS))
    p.add_argument('--epochs', type=int, default=None, help='smoke test only')
    p.add_argument('--max-designs', type=int, default=0, help='smoke test only')
    p.add_argument('--out', type=Path, default=HERE / 'teachers' / 'lpm')
    a = p.parse_args()
    out = a.out / f'f{a.fold}_j{a.inner}_s{a.seed}.npz'
    if out.exists():
        print(json.dumps({'exists': str(out)}))
        return
    assert V.sha(HERE / 'vendor' / 'lpm' / 'lpm_run.py') == LPM_SHA, 'vendor/lpm/lpm_run.py differs from S5'
    warnings.simplefilter('ignore')
    t0 = time.time()
    import torch
    import lpm_run as L
    from common import load_kit
    cf, abv2, tasks, meta, identity, zraw = V.load_env(a.fold)
    inner = V.inner_assignment(a.fold, tasks, identity)
    hold = {c for c, j in inner.items() if j == a.inner}
    kit, wells = load_kit(), L.load_wells()
    row = {c: i for i, c in enumerate(kit['chemicals'])}
    kit_train = dict(kit)
    folds = kit['folds'].copy()
    folds[[row[c] for c in hold]] = a.fold          # inner-fold-j chemicals leave the training wells
    kit_train['folds'] = folds
    model, voc, hist = L.train_model(kit_train, wells, a.fold, FROZEN['arch'], FROZEN['context'], FROZEN['dose'],
                                     a.seed, a.device, epochs=a.epochs)
    assert not any(row[c] in voc.comp for c in hold), 'an inner-fold chemical is in the LPM vocabulary'
    t_train = time.time() - t0
    conc = kit['conc']

    def ci(x):
        i = int(np.argmin(np.abs(conc - float(x))))
        assert abs(conc[i] - float(x)) < 1e-4
        return i

    res, counts = {}, {}
    for k in a.ks:
        train, pairs, sizes, offsets = V.canonical(cf, tasks, a.fold, k)
        kept = V.kept_mask(cf, pairs, k)
        todo = []
        for pi, (t, ctx) in enumerate(pairs):
            if t.chem not in hold or not kept[pi]:
                continue
            lv, qi, oi = V.pair_cells(t, ctx)
            todo.append(dict(task_id=len(todo), row=row[t.chem], seen=sorted(ci(x) for x in ctx),
                             queries=[(-1, ci(x)) for x in lv], pi=pi, qi=qi, oi=oi))
        if a.max_designs:
            todo = todo[:a.max_designs]
        rows, pred = [], []
        for s in range(0, len(todo), a.chunk):
            chunk = todo[s:s + a.chunk]
            for d, t in enumerate(chunk):
                t['task_id'] = d
            batch = L.Batch(kit, wells, voc, chunk, a.device)
            emb = L.fit_embeddings(model, kit, voc, batch, FROZEN['lam'], checkpoints=(FROZEN['steps'],))[FROZEN['steps']]
            got = L.predict(model, kit, voc, batch, emb)
            for t in chunk:
                Pq = got[t['task_id']]
                rows.append(np.arange(offsets[t['pi']], offsets[t['pi'] + 1], dtype=np.int64))
                pred.append(Pq[t['qi'], t['oi']].astype(np.float32))
            del batch, emb
            if a.device == 'cuda':
                torch.cuda.empty_cache()
        res[f'rows_k{k}'] = np.concatenate(rows)
        res[f'pred_k{k}'] = np.concatenate(pred)
        counts[f'k{k}'] = dict(designs=len(todo), rows=int(len(res[f'rows_k{k}'])), canonical_rows=int(offsets[-1]),
                               canonical_fingerprint=hashlib.sha256(sizes.tobytes()).hexdigest()[:16])
    a.out.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out, **res)
    log = dict(unit=out.stem, fold=a.fold, inner=a.inner, seed=a.seed, frozen=FROZEN, hold_chemicals=len(hold),
               train_chemicals=len(voc.comp), final_train_mse=hist[-1], epochs=len(hist), counts=counts,
               seconds=round(time.time() - t0, 1), train_seconds=round(t_train, 1), torch=torch.__version__,
               numpy=np.__version__, device=a.device, platform=platform.platform(),
               gpu=torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
               peak_gpu_gb=round(torch.cuda.max_memory_allocated() / 1e9, 3) if torch.cuda.is_available() else None,
               peak_rss_gb=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1e9 if sys.platform == 'darwin' else 1e6), 3),
               lpm_run_sha256=LPM_SHA, output_sha256=V.sha(out))
    out.with_suffix('.json').write_text(json.dumps(log, indent=1) + '\n')
    print(json.dumps({k: log[k] for k in ('unit', 'seconds', 'train_seconds', 'counts')}))


if __name__ == '__main__':
    main()

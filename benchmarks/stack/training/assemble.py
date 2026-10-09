#!/usr/bin/env python3
"""Merge teacher units into canonical out-of-fold arrays and kit-format readouts (ab_v3).

  python assemble.py teachers --seeds 13-32      -> teachers/T_f{f}_k{k}.npz, L_f{f}_k{k}.npz (canonical rows, every row
                                                    covered exactly once), L_test_k{k}.npz (S5 seed files, same seeds),
                                                    oof/T_f{f}_k{k}.npz, oof/L_f{f}_k{k}.npz (kit format, training chemicals)
  python assemble.py inner G A ST STZ STZr       -> oof/<cand>_f{f}_k{k}.npz merged from inner/<cand>/f{f}_j{j}_k{k}.npz
"""
import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import v3common as V  # noqa: E402

D = V.D
S5_SEEDS = HERE / 'vendor' / 'lpm' / 'preds' / 'lpm_seeds'


def seeds_arg(s):
    lo, hi = s.split('-') if '-' in s else (s, s)
    return list(range(int(lo), int(hi) + 1))


def teachers(seeds, folds, ks, source_teachers):
    out = HERE / 'teachers'
    (HERE / 'oof').mkdir(exist_ok=True)
    receipt = {}
    for f in folds:
        cf, abv2, tasks, meta, identity, zraw = V.load_env(f)
        inner = V.inner_assignment(f, tasks, identity)
        train = [t for t in tasks if t.fold != f]
        for k in ks:
            tr, pairs, sizes, offsets = V.canonical(cf, tasks, f, k)
            fp = hashlib.sha256(sizes.tobytes()).hexdigest()[:16]
            N = int(offsets[-1])
            T = {c: np.full(N, np.nan, np.float32) for c in V.T_COLS}
            seen = np.zeros(N, np.int8)
            for j in range(V.N_INNER):
                z = np.load(source_teachers / 'tp2' / f'f{f}_k{k}_j{j}.npz')
                r = z['rows']
                for c in V.T_COLS:
                    T[c][r] = z[c]
                seen[r] += 1
                meta_j = json.loads((source_teachers / 'tp2' / f'f{f}_k{k}_j{j}.json').read_text())
                assert meta_j['canonical_fingerprint'] == fp
            kept = np.repeat(V.kept_mask(cf, pairs, k), sizes)
            assert (seen[kept] == 1).all() and (seen[~kept] <= 1).all(), f'f{f} k{k}: TabPFN-2 rows covered {np.bincount(seen)}'
            for c in V.T_COLS:
                T[c][~kept] = np.nan
            np.savez_compressed(out / f'T_f{f}_k{k}.npz', fingerprint=fp, **T)
            Ls = np.full((len(seeds), N), np.nan, np.float32)
            for si, s in enumerate(seeds):
                cover = np.zeros(N, np.int8)
                for j in range(V.N_INNER):
                    z = np.load(source_teachers / 'lpm' / f'f{f}_j{j}_s{s}.npz')
                    r = z[f'rows_k{k}']
                    Ls[si, r] = z[f'pred_k{k}']
                    cover[r] += 1
                assert (cover[kept] == 1).all() and (cover[~kept] <= 1).all(), f'f{f} k{k} seed {s}: LPM rows covered {np.bincount(cover)}'
                Ls[si, ~kept] = np.nan
            np.savez_compressed(out / f'L_f{f}_k{k}.npz', fingerprint=fp, seeds=np.array(seeds), mean=Ls.mean(0),
                                sd=Ls.std(0))
            km = V.KitMap(k)
            chems = {t.chem for t in train}
            for name, vals in (('T', T['median']), ('L', Ls.mean(0))):
                P = V.scatter_kit(km, cf, tasks, f, k, chems, vals, pairs, offsets)
                np.savez_compressed(HERE / 'oof' / f'{name}_f{f}_k{k}.npz', **{f'k{k}': P})
            receipt[f'f{f}_k{k}'] = dict(rows=N, fingerprint=fp, seeds=len(seeds),
                                        inner_sizes=[sum(1 for t in train if inner[t.chem] == j) for j in range(V.N_INNER)])
            print(f'f{f} k{k}: {N} rows, T and L complete ({len(seeds)} seeds)', flush=True)
    for k in ks:
        if source_teachers != out and (source_teachers / f'L_test_k{k}.npz').exists():
            shutil.copy2(source_teachers / f'L_test_k{k}.npz', out / f'L_test_k{k}.npz')
        else:
            runs = [np.load(S5_SEEDS / f'f{folds[0]}_k{k}_s{s}.npz')[f'k{k}'] for s in seeds]
            np.savez_compressed(out / f'L_test_k{k}.npz', seeds=np.array(seeds), mean=np.mean(runs, 0), sd=np.std(runs, 0))
    (out / 'assemble_receipt.json').write_text(json.dumps(dict(seeds=seeds, units=receipt), indent=1) + '\n')


def inner(cands, folds, ks):
    (HERE / 'oof').mkdir(exist_ok=True)
    for cand in cands:
        for f in folds:
            for k in ks:
                P = None
                for j in range(V.N_INNER):
                    with np.load(HERE / 'inner' / cand / f'f{f}_j{j}_k{k}.npz') as z:
                        Q = z[f'k{k}']
                    if P is None:
                        P = np.full_like(Q, np.nan)
                    rows = np.isfinite(Q).any(1)
                    assert not np.isfinite(P[rows]).any(), f'{cand} f{f} k{k}: inner folds overlap'
                    P[rows] = Q[rows]
                np.savez_compressed(HERE / 'oof' / f'{cand}_f{f}_k{k}.npz', **{f'k{k}': P})
        print(cand, 'merged', flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('what', choices=['teachers', 'inner'])
    p.add_argument('cands', nargs='*')
    p.add_argument('--seeds', type=seeds_arg, default=list(range(13, 33)))
    p.add_argument('--folds', type=int, nargs='+', default=[0, 1, 2, 3, 4])
    p.add_argument('--ks', type=int, nargs='+', default=[1, 2, 3, 4])
    p.add_argument('--source-teachers', type=Path, default=HERE / 'teachers')
    p.add_argument('--only-outer-lpm', action='store_true')
    a = p.parse_args()
    if a.what == 'teachers':
        if a.only_outer_lpm:
            out = HERE / 'teachers'
            out.mkdir(parents=True, exist_ok=True)
            for k in a.ks:
                runs = [np.load(S5_SEEDS / f'f{a.folds[0]}_k{k}_s{s}.npz')[f'k{k}'] for s in a.seeds]
                np.savez_compressed(out / f'L_test_k{k}.npz', seeds=np.array(a.seeds),
                                    mean=np.mean(runs, 0), sd=np.std(runs, 0))
            return
        teachers(a.seeds, a.folds, a.ks, a.source_teachers)
    else:
        inner(a.cands, a.folds, a.ks)


if __name__ == '__main__':
    main()

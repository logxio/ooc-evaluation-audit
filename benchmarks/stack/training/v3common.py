#!/usr/bin/env python3
"""Shared pieces of ab_v3: environment, inner folds, the canonical training-row enumeration and kit lookups.

Canonical rows of outer fold f and k are the AnchorBoost training rows in the release order (abv2.AnchorBoostV2._rows):
training chemicals (package fold != f) in package order, every design of chip_forecast.all_designs(t, k), and inside a
design the measured cells of the unrevealed levels in (level, output) row-major order. Teacher out-of-fold arrays,
the stacker's teacher columns and the distiller's soft targets are all aligned to this enumeration.

Inner folds: the identity groups of the outer fold's training chemicals, ordered by sha256('ab_v3|inner|f|group'),
group at rank r goes to inner fold r mod 5. Every member, teacher and stacker uses the same inner folds.
"""
from __future__ import annotations

import csv
import hashlib
import os
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
R = HERE
KIT = Path(os.environ.get('ABV3_KIT', HERE / 'kit'))
RELEASE = Path(os.environ.get('ABV3_RELEASE', HERE.parents[2]))
DATA = Path(os.environ.get('ABV3_DATA', RELEASE / 'benchmarks' / 'strong_baseline' / 'ablation' / 'source' / 'nfa_tasks.npz'))
STRUCT = Path(os.environ.get('ABV3_STRUCT', HERE / 'embeddings'))
CF_SHA = '3d02dd3a1bc57e8c53f701a6005c8d5e9d8ad6a15a57cdec3f22b27066015897'
DATA_SHA = 'e1f056ef33f568052fb8dfdba6e095f7b575c7f78d96768e34469918559008d2'
ABV2_SHA = 'e6fa879eafec086cfcd204302b31b330c8f5d47e49d9d397dcbe0758328583f5'
D = 68
N_INNER = 5
KS = (1, 2, 3, 4)
DWC = dict(blocks=['date', 'datew', 'struct'], params=None, struct_m=10, n_bag=5, bag_frac=0.8, seed=0)
RELEASE_CFG = dict(blocks=[], params=None)
T_COLS = ('mean', 'median', 'q10', 'q25', 'q75', 'q90')   # TabPFN-2 outputs, response level
T_QUANTILES = [0.1, 0.25, 0.75, 0.9]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


_ENV = {}


def load_env(fold):
    """chip_forecast, abv2, release tasks, metadata with the fold's CheMeleon PCA16, identity map, raw PCA16 rows."""
    if fold in _ENV:
        return _ENV[fold]
    assert sha(RELEASE / 'chip_forecast.py') == CF_SHA, 'release chip_forecast.py differs from the pinned file'
    assert sha(DATA) == DATA_SHA, 'nfa_tasks.npz differs from the pinned file'
    assert sha(HERE / 'vendor' / 'abv2.py') == ABV2_SHA, 'vendor/abv2.py differs from ab_v2/abv2.py'
    for p in (str(RELEASE), str(HERE / 'vendor')):
        if p not in sys.path:
            sys.path.insert(0, p)
    import chip_forecast as cf
    import abv2
    tasks = cf.load_tasks(DATA)
    z = np.load(DATA, allow_pickle=False)
    chem = list(csv.DictReader((KIT / 'data' / 'chemicals.csv').open()))
    identity = {c['chemical']: c['identity_group'] for c in chem}
    s = np.load(STRUCT / 'structure_pca.npz')
    names = [str(c) for c in s['chemicals']]
    Z = s[f'chemeleon_fold{fold}'].astype(np.float64)
    struct = {c: (Z[i] if np.isfinite(Z[i]).all() and np.abs(Z[i]).sum() > 0 else None) for i, c in enumerate(names)}
    zraw = {c: Z[i] for i, c in enumerate(names)}
    meta = abv2.kit_meta(tasks, z['plate'], identity, struct)
    _ENV[fold] = (cf, abv2, tasks, meta, identity, zraw)
    return _ENV[fold]


def inner_assignment(f, tasks, identity):
    """{training chemical: inner fold 0..4} for outer fold f (identity groups kept together)."""
    train = [t for t in tasks if t.fold != f]
    groups = sorted({identity[t.chem] for t in train},
                    key=lambda g: hashlib.sha256(f'ab_v3|inner|{f}|{g}'.encode()).hexdigest())
    at = {g: i % N_INNER for i, g in enumerate(groups)}
    return {t.chem: at[identity[t.chem]] for t in train}


def canonical(cf, tasks, f, k):
    """Training chemicals, (task, design) pairs, cells per pair and row offsets of outer fold f at k."""
    train = [t for t in tasks if t.fold != f]
    pairs = [(t, ctx) for t in train if k < len(t.levels) for ctx in cf.all_designs(t, k)]
    sizes = np.array([int(t.ok[~np.isin(t.levels, ctx)].sum()) for t, ctx in pairs], np.int64)
    offsets = np.concatenate([[0], np.cumsum(sizes)]).astype(np.int64)
    return train, pairs, sizes, offsets


CAP = 24


def design_key(ctx):
    return tuple(np.asarray(ctx, np.float32).tolist())


def kept_designs(cf, t, k):
    """Designs that carry teacher rows: chemical t's five kit designs plus the CAP designs with the smallest
    sha256('ab_v3|cap|<chemical>|<k>|<levels>'); every design when the chemical has CAP + 5 or fewer."""
    alld = [design_key(c) for c in cf.all_designs(t, k)]
    kit = {design_key(c) for c in cf.designs(t, k)}
    ranked = sorted(alld, key=lambda d: hashlib.sha256(f'ab_v3|cap|{t.chem}|{k}|{d}'.encode()).hexdigest())
    return kit | set(ranked[:CAP])


def kept_mask(cf, pairs, k):
    """Per canonical pair: does it carry teacher rows."""
    cache = {}
    out = np.zeros(len(pairs), bool)
    for i, (t, ctx) in enumerate(pairs):
        if t.chem not in cache:
            cache[t.chem] = kept_designs(cf, t, k)
        out[i] = design_key(ctx) in cache[t.chem]
    return out


def pair_cells(t, ctx):
    """Unrevealed levels and the (level, output) indices of their measured cells, in canonical order."""
    keep = ~np.isin(t.levels, ctx)
    lv = t.levels[keep]
    qi, oi = np.nonzero(t.ok[keep].reshape(len(lv), D))
    return lv, qi, oi


class KitMap:
    """Kit query rows: (chemical, kit design, conc index) -> query id, and level -> conc index."""

    def __init__(self, k):
        z = np.load(KIT / 'data' / 'matrix.npz')
        self.conc = z['log10_conc_um'].astype(np.float64)
        self.kit_row = {str(c): i for i, c in enumerate(z['chemicals'])}
        rows = list(csv.DictReader((KIT / 'tasks' / f'k{k}_queries.csv').open()))
        self.n = len(rows)
        self.qid = {(r['chemical'], int(r['design']), int(r['conc_index'])): int(r['query_id']) for r in rows}
        self.fold = np.array([int(r['fold']) for r in rows])

    def ci(self, level):
        i = int(np.argmin(np.abs(self.conc - float(level))))
        assert abs(self.conc[i] - float(level)) < 1e-4, level
        return i


def kit_design_blocks(cf, t, k, pairs_index, offsets):
    """For chemical t's five kit designs: (kit design index, canonical pair index, unrevealed levels, qi, oi)."""
    out = []
    for di, ctx in enumerate(cf.designs(t, k)):
        p = pairs_index[(t.chem, tuple(np.asarray(ctx, np.float32).tolist()))]
        lv, qi, oi = pair_cells(t, ctx)
        out.append((di, p, lv, qi, oi))
    return out


def pairs_lookup(pairs):
    return {(t.chem, tuple(np.asarray(ctx, np.float32).tolist())): i for i, (t, ctx) in enumerate(pairs)}


def scatter_kit(km, cf, tasks, f, k, chems, values, pairs, offsets):
    """Kit-format (n_queries, 68) array from canonical-row values for the five kit designs of the given chemicals."""
    index = pairs_lookup(pairs)
    P = np.full((km.n, D), np.nan)
    for t in tasks:
        if t.chem not in chems or k >= len(t.levels):
            continue
        for di, p, lv, qi, oi in kit_design_blocks(cf, t, k, index, offsets):
            q = np.array([km.qid[(t.chem, di, km.ci(lv[j]))] for j in qi], np.int64)
            P[q, oi] = values[offsets[p]:offsets[p + 1]]
    return P


def feature_maker(cf, abv2, train, meta, cfg=DWC):
    """abv2 feature machinery (no booster) with the given training chemicals as library."""
    m = object.__new__(abv2.AnchorBoostV2)
    m.cf, m.meta, m.k = cf, meta, None
    m.blocks = list(cfg['blocks'])
    m.pool, m.isolate, m.batch_dropout, m.seed = False, None, 0.0, 0
    m.analog_train = cf.Analog(train, exclude_self=True)
    m.analog = cf.Analog(train)
    m.profiles = cf.Profiles(train)
    m.lib = abv2.Library(cf, train, meta, int(cfg.get('struct_m', 10)), cfg.get('struct_temp')) if m.blocks else None
    return m

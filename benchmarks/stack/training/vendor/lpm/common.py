"""Shared loading, fallback and fold-0 scoring for the S5 competitors (N2, SNN, LPM) on the kit.

The kit is read only. A task is one (test chemical, design); its allowed inputs are every cell of the
chemicals outside its fold plus the k revealed concentrations of the test chemical.
"""
import csv
import os
from collections import defaultdict
from pathlib import Path

import numpy as np

KIT = Path(os.environ.get('S5_KIT', Path(__file__).resolve().parents[2] / 'kit'))
HERE = Path(os.environ.get('S5_HERE', Path(__file__).resolve().parent))
D = 68
NC = 35


def load_kit():
    z = np.load(KIT / 'data' / 'matrix.npz')
    return dict(Y=z['Y'].astype(np.float64), folds=z['folds'].astype(int), chemicals=[str(c) for c in z['chemicals']],
                conc=z['log10_conc_um'].astype(np.float64), tested=z['tested'],
                identity=[str(g) for g in z['identity_groups']])


def load_tasks(k, folds=None):
    """Tasks of tasks/k{k}_designs.csv with their query rows; folds limits which tasks are returned."""
    z = np.load(KIT / 'data' / 'matrix.npz')
    row = {str(c): i for i, c in enumerate(z['chemicals'])}
    designs = list(csv.DictReader((KIT / 'tasks' / f'k{k}_designs.csv').open()))
    queries = list(csv.DictReader((KIT / 'tasks' / f'k{k}_queries.csv').open()))
    by_task = defaultdict(list)
    for q in queries:
        by_task[int(q['task_id'])].append((int(q['query_id']), int(q['conc_index'])))
    tasks = []
    for d in designs:
        if folds is not None and int(d['fold']) not in folds:
            continue
        tasks.append(dict(task_id=int(d['task_id']), fold=int(d['fold']), chemical=d['chemical'], row=row[d['chemical']],
                          design=int(d['design']), seen=[int(x) for x in d['observed_conc_index'].split(';')],
                          queries=by_task[int(d['task_id'])]))
    return tasks, len(queries)


def interpolation(Y, conc, i, seen, cs):
    """Log-linear interpolation of chemical i's revealed values at concentrations cs, (len(cs), 68); 0 where an
    output has no valid revealed value (kit/example_knn.py fallback)."""
    seen = np.asarray(seen)
    out = np.zeros((len(cs), D))
    for o in range(D):
        v = Y[i, seen, o]
        ok = ~np.isnan(v)
        if ok.any():
            out[:, o] = np.interp(conc[np.asarray(cs)], conc[seen][ok], v[ok])
    return out


def output_sd(Y, rows):
    """Per-output standard deviation over every measured cell of the given chemicals, (68,)."""
    return np.nanstd(Y[rows].reshape(-1, D), axis=0)


def curve_mae(Y, tasks, pred_by_task):
    """Kit curve error: per design, mean |error| over valid query cells; per chemical, mean over its designs;
    returns (mean over chemicals, {chemical: error}). pred_by_task[task_id] is (n_queries, 68) in query order."""
    per_chem = defaultdict(list)
    for t in tasks:
        P = pred_by_task[t['task_id']]
        truth = Y[t['row'], [c for _, c in t['queries']]]
        ok = ~np.isnan(truth)
        if np.isnan(P[ok]).any():
            raise ValueError(f"NaN prediction at a measured cell: {t['chemical']} design {t['design']}")
        per_chem[t['chemical']].append(float(np.abs(P - truth)[ok].mean()))
    errs = {c: float(np.mean(v)) for c, v in per_chem.items()}
    return float(np.mean([errs[c] for c in sorted(errs)])), errs


def to_query_array(tasks, pred_by_task, n_queries):
    """Stack per-task predictions into the kit's (n_queries, 68) array aligned to tasks/k{k}_queries.csv."""
    P = np.full((n_queries, D), np.nan)
    for t in tasks:
        for r, (qid, _) in enumerate(t['queries']):
            P[qid] = pred_by_task[t['task_id']][r]
    return P

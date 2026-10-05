#!/usr/bin/env python3
"""Retrospective drug-disjoint prediction, training-only rules, and group CRC.

The A40 AnchorBoost architecture is refitted, including its analog library, for
each training set. Historical forecasts are used only in a separate replay row.
Run --help for the prepare / probe / fit / evaluate / summarize entry points.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import math
import os
import resource
import subprocess
import sys
import threading
import time
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path

os.environ.setdefault('OMP_NUM_THREADS', '4')
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
os.environ.setdefault('VECLIB_MAXIMUM_THREADS', '1')

import joblib
import numpy as np
import pandas as pd
import psutil
import rdata
import sklearn
from threadpoolctl import threadpool_limits

import chip_forecast as cf

ROOT = Path(__file__).resolve().parent
RAW_URL = ('https://raw.githubusercontent.com/USEPA/CompTox-DNT-NFA-Refinement/'
           '01adf3e1a0068c87fe221d60df36b9f96c4b4b1d/source_files/All_DIV_Data.Rdata')
LOCAL_INPUTS = {'raw': ROOT / '.cache' / 'epa' / 'All_DIV_Data.Rdata',
                'legacy_result': ROOT / 'chip_forecast_decision.json'}
REDACTIONS = ROOT / 'results' / 'REDACTIONS.json'
FEATURES = ['meanfiringrate', 'burst.per.min', 'mean.isis', 'per.spikes.in.burst',
            'mean.dur', 'mean.IBIs', 'nAE', 'nABE', 'ns.n', 'ns.peak.m',
            'ns.durn.m', 'ns.percent.of.spikes.in.ns', 'ns.mean.insis',
            'ns.durn.sd', 'ns.mean.spikes.in.ns', 'r', 'mi']
DAYS = [5, 7, 9, 12]
BATCH = ['apid.short', 'date', 'DIV']
METHODS = ['anchorboost', 'loglinear', 'measured_only']
ALPHA = .10
MARGIN_GRID = [-1.] + [i / 100 for i in range(101)]
# Conservative, pre-outcome active-moiety groups. These are partition groups,
# not assertions that formulations, mixtures, or stereoisomers have equal effects.
PARENT_GROUPS = [
    ['Phenobarbital', 'Phenobarbital sodium'],
    ['Bis(tributyltin)oxide', 'Tributyltin chloride', 'Tributyltin methacrylate'],
    ['Manganese dichloride', 'Manganese(II) acetate'],
    ['Allethrin', 'S-Bioallethrin'],
    ['DDT', "o,p'-DDT"],
]


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def frozen_sha(path):
    """Hash cited by freeze records. A published copy listed in results/REDACTIONS.json, whose local
    paths became placeholders, counts only when its SHA-256 equals the listed redacted hash."""
    actual = sha(path)
    if REDACTIONS.exists():
        for item in load(REDACTIONS)['files']:
            if item['redacted_sha256'] == actual and Path(item['path']).name == Path(path).name:
                return item['original_sha256']
    return actual


def utc():
    return datetime.now(timezone.utc).isoformat()


def dump(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n')


def load(path):
    return json.loads(Path(path).read_text())


def write_csv(path, rows):
    with Path(path).open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def limits():
    """Own-process RSS guard; finite stages are also capped by the runner."""
    proc = psutil.Process()
    def watch():
        while True:
            if proc.memory_info().rss > 4_000_000_000:
                print('ERROR: process RSS exceeded 4 GB', file=sys.stderr, flush=True)
                os._exit(70)
            time.sleep(.25)
    threading.Thread(target=watch, daemon=True).start()


def runtime(start):
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return {'seconds': time.monotonic() - start,
            'peak_rss_bytes': int(rss if sys.platform == 'darwin' else rss * 1024)}


def raw_frame(path):
    f = rdata.read_rda(io.BytesIO(Path(path).read_bytes()))['rval.dat'].copy()
    f.columns = [str(x) for x in f.columns]
    for col in f.select_dtypes(include='category').columns:
        f[col] = f[col].astype(object)
    a = f[FEATURES].to_numpy(float)
    f[FEATURES] = np.where(np.isfinite(a), a, np.nan)  # canonicalize R NA payload
    for col in ['treatment', 'spid', 'apid.short', 'well']:
        f[col] = f[col].astype(str)
    if set(f.units) != {'uM'} or set(f.DIV) != set(DAYS):
        raise ValueError('Unexpected units or developmental days')
    if f[['treatment', 'spid', 'apid.short', 'date']].isna().any().any():
        raise ValueError('Missing identity or plate/date key')
    return f


def prepare(args):
    out = args.out
    if (out / 'protocol.json').exists():
        raise FileExistsError('Existing protocol; use the existing frozen run or a new output directory')
    start = time.monotonic()
    f = raw_frame(args.raw)
    bundle = np.load(args.bundle, allow_pickle=False)
    assignments = load(args.identities)['assignments']
    by_name = defaultdict(list)
    for row in assignments:
        by_name[row['chemical']].append(row)
    identity = {}
    for name, fold in zip(bundle['chem'].tolist(), bundle['fold'].tolist()):
        ids = {r['dtxsid'] for r in by_name[name]}
        folds = {r['fold'] for r in by_name[name]}
        if len(ids) != 1 or None in ids or folds != {fold}:
            raise ValueError(f'Ambiguous chemical identity/fold: {name}')
        rows = f[(f.treatment == name) & (f.dose > 0)]
        spids = sorted(rows.spid.unique().tolist())
        if not set(spids) <= {r['spid'] for r in by_name[name]}:
            raise ValueError(f'Unmapped sample identifiers: {name}')
        identifier = next(iter(ids))
        identity[name] = dict(chemical=name, dtxsid=identifier, drug_group=identifier,
                              original_fold=int(fold), fold=int(fold), spids=spids,
                              source_files=sorted(rows.srcf.unique().tolist()),
                              batches=sorted({f'{p}|{d}' for p, d in rows[['apid.short', 'date']].itertuples(index=False, name=None)}),
                              donor=None)
    for names in PARENT_GROUPS:
        records = [identity[name] for name in names]
        group = 'parent:' + min(r['dtxsid'] for r in records)
        fold = min(r['original_fold'] for r in records)
        for r in records:
            r.update(drug_group=group, fold=fold)
    groups = defaultdict(list)
    for name, row in identity.items():
        groups[row['drug_group']].append(name)
    if any(len({identity[n]['fold'] for n in names}) != 1 for names in groups.values()):
        raise ValueError('Identity crosses outer folds')
    splits = {}
    for outer in range(5):
        other = [i for i in range(5) if i != outer]
        fit_folds, cal_folds = other[:2], other[2:]
        stage = {'train': [], 'calibration': [], 'test': []}
        for name, row in identity.items():
            role = 'test' if row['fold'] == outer else 'train' if row['fold'] in fit_folds else 'calibration'
            stage[role].append(name)
        train_groups = sorted({identity[n]['drug_group'] for n in stage['train']},
                              key=lambda g: digest(['inner-v1', outer, g]))
        inner = {g: i % 2 for i, g in enumerate(train_groups)}
        stage['inner'] = {str(i): [n for n in stage['train'] if inner[identity[n]['drug_group']] == i] for i in range(2)}
        stage['outer_fold'] = outer
        stage['fit_folds'], stage['calibration_folds'] = fit_folds, cal_folds
        stage['group_counts'] = {role: len({identity[n]['drug_group'] for n in stage[role]}) for role in ['train', 'calibration', 'test']}
        stage['batch_overlap'] = {}
        for a, b in [('train', 'calibration'), ('train', 'test'), ('calibration', 'test')]:
            aa = {x for n in stage[a] for x in identity[n]['batches']}
            bb = {x for n in stage[b] for x in identity[n]['batches']}
            stage['batch_overlap'][f'{a}_{b}'] = sorted(aa & bb)
        for a, b in [('train', 'calibration'), ('train', 'test'), ('calibration', 'test')]:
            if {identity[n]['drug_group'] for n in stage[a]} & {identity[n]['drug_group'] for n in stage[b]}:
                raise ValueError('Drug overlap')
        splits[str(outer)] = stage
    inputs = {key: {'path': str(path.resolve()), 'sha256': sha(path)} for key, path in
              [('raw', args.raw), ('bundle_metadata', args.bundle), ('identities', args.identities),
               ('legacy_result', ROOT / 'chip_forecast_decision.json')]}
    protocol = dict(schema='paper.nested_decision.v1', created_utc=utc(),
        status='Retrospective re-splitting of previously inspected public data; execution freeze is not prospective preregistration.',
        question='Does drug-disjoint prediction plus group-level calibration substantiate reliable release and savings relative to three-point fallback?',
        expected_before_run={'release_share': [.5, .95], 'error_all_designs': [.03, .16],
                             'gain_over_measured_only': [-.10, .20], 'interpretation': 'Planning ranges, not acceptance criteria.'},
        outer_order=[0, 1, 2, 3, 4], primary_folds=[1, 2, 3, 4], secondary_folds=[0],
        identity='DTXSID and sample identifiers plus frozen conservative active-moiety groups; all source files of an identity share a role.',
        conservative_parent_groups=PARENT_GROUPS, drug_groups=len(groups), substances=len(identity),
        missing_keys={'donor': 'No donor identifier in the raw 30-column table.',
                      'biological_batch': 'plate/date and source file available; plate/date is a technical batch, not donor or culture preparation.'},
        preprocessing='Fit asinh scales, per-DIV robust SD, and plate/date/DIV vehicle centers using only controls on training-associated plate/date keys. Unseen batches use the training median of batch centers per DIV. Calibration/test controls never fit or update this map. Inner fits repeat the whole transformation using inner-training drugs only.',
        endpoint='inactive=1 iff maximum absolute masked DIV-mean over all concentrations and 17 features is <3 in that fit training-derived assay scale; threshold equality is active. Units/labels may differ between outer fits and from historical globally normalized replay.',
        model={'class': 'chip_forecast.AnchorBoost', 'params': cf.MODEL, 'n_pca': cf.N_PCA,
               'historical_selection': 'A40 architecture/parameters were developed on already-seen data; this evaluates a fixed retrospective procedure.'},
        designs='Five published SHA-seeded k=3 designs per substance; all C(L,3) training designs; k=3 controls excluded from exposed-well budget.',
        rule='Two group-disjoint inner fits generate training-only out-of-fold scores. Equal-drug weighted balanced accuracy selects cutoff, lowest cutoff breaks ties. Weighted training ECDF gives absolute rank margin. Final predictor trains all and only outer-training drugs.',
        intervals='Per-output 90th percentile across training drugs of the maximum absolute inner-held-out level-mean residual over their designs/targets; fixed before calibration, descriptive bands with no interval coverage theorem claimed.',
        risk={'alpha': ALPHA, 'unit': 'drug_group', 'within_drug': 'arithmetic mean over all substance/design rows of the group',
              'loss': 'L_g(lambda)=mean_d[1(margin_gd>lambda)*1(call_gd!=truth_gd)] in [0,1]',
              'selection': 'first increasing lambda with (sum_g L_g(lambda)+1)/(n_calibration_drugs+1)<=alpha; otherwise lambda=1 and all fall back',
              'margin_grid': MARGIN_GRID, 'scope': 'Expected marginal drug loss under independent training and exchangeable calibration/future drug loss functions; no conditional released-error or finite-batch guarantee. Shared batches and legacy stratified folds limit a literal exchangeability claim.'},
        comparators=['loglinear with its own training-only cutoff and group CRC',
                     'measured_only with its own training-only cutoff and group CRC (historical three-point fallback comparator)',
                     'observed_active_fallback: release only when the measured three-point endpoint is >=3; otherwise full measurement',
                     'full_measurement: reference endpoint from every exposed well'],
        cost='An accepted design costs its measured exposed wells; fallback costs all exposed wells, reusing the initial three levels. Report both full-series and calibrated measured-only fallback denominators, plus the observed-active fallback. This is counterfactual exposed-well replay, excluding controls, repeats, failed assays and overhead.',
        selection_order=['identity/splits/protocol freeze', 'inner training and held-out training predictions',
                         'training-only cutoffs/ranks/interval widths freeze', 'final training model freeze',
                         'calibration forecasts and drug loss curves', 'final thresholds freeze',
                         'test context-only forecasts/decisions freeze', 'test full-series outcomes score'],
        inputs=inputs, dependencies={'numpy': np.__version__, 'pandas': pd.__version__, 'sklearn': sklearn.__version__, 'rdata': rdata.__version__},
        code_sha256={Path(__file__).name: sha(__file__), 'chip_forecast.py': sha(ROOT / 'chip_forecast.py')},
        resource_limit_bytes=4_000_000_000)
    dump(out / 'identities.json', identity)
    dump(out / 'splits.json', splits)
    protocol['splits_sha256'] = sha(out / 'splits.json')
    protocol['identities_sha256'] = sha(out / 'identities.json')
    dump(out / 'protocol.json', protocol)
    dump(out / 'prepare_runtime.json', runtime(start))
    print(json.dumps({'prepared': str(out), 'substances': len(identity), 'drug_groups': len(groups),
                      'split_counts': {k: v['group_counts'] for k, v in splits.items()}, **runtime(start)}), flush=True)


def input_path(protocol, key):
    """Repository copy of a frozen input, else its recorded path; the SHA-256 must match the protocol."""
    item = protocol['inputs'][key]
    path = next((p for p in (LOCAL_INPUTS[key], Path(item['path'])) if p.exists()), LOCAL_INPUTS[key])
    if not path.exists() and key == 'raw':
        path.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(RAW_URL, timeout=120) as r:
            path.write_bytes(r.read())
    if sha(path) != item['sha256']:
        raise ValueError(f'Input differs from frozen protocol: {key}')
    return path


def read_run(out):
    protocol = load(out / 'protocol.json')
    # A code change after a protocol froze is accepted only as a recorded amendment
    # that maps the frozen hash to the current one (paper_nested_decision_amendments.json).
    amendments = ROOT / 'paper_nested_decision_amendments.json'
    for name, expected in protocol['code_sha256'].items():
        actual = sha(ROOT / name)
        if actual != expected and not (amendments.exists() and any(
                a['file'] == name and a['frozen_sha256'] == expected and a['amended_sha256'] == actual
                for a in load(amendments)['amendments'])):
            raise ValueError(f'Code differs from frozen protocol: {name}')
    for name in ['splits', 'identities']:
        if frozen_sha(out / f'{name}.json') != protocol[f'{name}_sha256']:
            raise ValueError(f'Frozen {name} changed')
    return protocol, load(out / 'identities.json'), load(out / 'splits.json')


def controls_for(frame, names):
    train = frame[(frame.treatment.isin(names)) & (frame.dose > 0)]
    keys = set(train[['apid.short', 'date']].itertuples(index=False, name=None))
    controls = frame[frame.dose == 0].copy()
    controls = controls[[k in keys for k in controls[['apid.short', 'date']].itertuples(index=False, name=None)]]
    if controls.empty:
        raise ValueError('No training-associated vehicle controls')
    # A physical control can be repeated under different treatment labels.
    conflicting = controls.groupby(BATCH + ['well'], observed=True)[FEATURES].nunique(dropna=False).gt(1).any(axis=1)
    if conflicting.any():
        raise ValueError('Conflicting duplicate vehicle measurements')
    return controls.drop_duplicates(BATCH + ['well'])


def batch_key(p, d, day):
    return f'{p}|{int(d)}|{int(day)}'


def fit_transform(frame, names):
    v = controls_for(frame, names)
    result = {'training_names': sorted(names), 'n_vehicle_rows': len(v), 'features': {}}
    for feature in FEATURES:
        positive = v.loc[(v.DIV == 12) & (v[feature] > 0), feature]
        c = float(positive.median() / 4) if len(positive) else 1.
        tmp = v[BATCH].copy()
        tmp['g'] = np.arcsinh(v[feature].to_numpy(float) / c)
        grp = tmp.groupby(BATCH, observed=True)['g']
        centers = grp.median()
        mad = grp.apply(lambda x: 1.4826 * np.nanmedian(np.abs(x - np.nanmedian(x))) if x.notna().sum() >= 3 else np.nan)
        sd, fallback = [], []
        for day in DAYS:
            m = float(mad.xs(day, level='DIV').median())
            center = float(centers.xs(day, level='DIV').median())
            if not np.isfinite(center):
                raise ValueError(f'No finite training center: {feature}, DIV {day}')
            sd.append(max(m, .05) if np.isfinite(m) else 1.)
            fallback.append(center)
        result['features'][feature] = {'c': c, 'sd': sd, 'fallback_center': fallback,
              'centers': {batch_key(*key): float(value) for key, value in centers.items() if np.isfinite(value)}}
    return result


def make_tasks(frame, names, identities, transform):
    """Transform requested role only; prediction later receives context-only Task objects."""
    f = frame[(frame.treatment.isin(names)) & (frame.dose > 0)].copy()
    keys = [batch_key(*r) for r in f[BATCH].itertuples(index=False, name=None)]
    day_idx = np.array([DAYS.index(int(day)) for day in f.DIV])
    for feature in FEATURES:
        tr = transform['features'][feature]
        centers = np.array([tr['centers'].get(key, tr['fallback_center'][d]) for key, d in zip(keys, day_idx)])
        val = (np.arcsinh(f[feature].to_numpy(float) / tr['c']) - centers) / np.array(tr['sd'])[day_idx]
        f['z_' + feature] = np.clip(val, -10., 10.)
    columns = ['z_' + x for x in FEATURES]
    tasks = []
    for name in sorted(names):
        part = f[f.treatment == name]
        well_keys = ['spid', 'apid.short', 'date', 'well', 'dose']
        if part.duplicated(well_keys + ['DIV']).any():
            raise ValueError(f'Duplicate physical exposed well/day: {name}')
        index = pd.MultiIndex.from_frame(part[well_keys])
        wells = index.unique().sort_values()
        yi = pd.MultiIndex.from_frame(part[well_keys + ['DIV']])
        grid = pd.MultiIndex.from_tuples([(*key, day) for key in wells for day in DAYS], names=well_keys + ['DIV'])
        values = pd.DataFrame(part[columns].to_numpy(float), index=yi).reindex(grid).to_numpy().reshape(len(wells), 4, 17)
        mask = np.isfinite(values)
        logc = np.log10(np.array([key[-1] for key in wells], float)).astype(np.float32)
        task = cf.Task(name, identities[name]['fold'], 'unused', logc,
                       np.where(mask, values, 0).astype(np.float32), mask)
        task.group = identities[name]['drug_group']
        task.well_keys = [list(key) for key in wells]
        tasks.append(task)
    return tasks


def effect(mu, ok):
    den = ok.sum(axis=1)
    values = np.sum(mu * ok, axis=1) / np.maximum(den, 1)
    return float(np.abs(values).max())


def forecast(model, tasks, fold, role):
    """No unmeasured responses or masks are passed to the prediction functions."""
    records, points = [], {key: [] for key in ['chemical', 'design', 'level', 'logc', 'anchorboost', 'loglinear']}
    for t in tasks:
        for di, ctx in enumerate(cf.designs(t, 3)):
            chosen = np.isin(t.logc, ctx)
            query = t.levels[~np.isin(t.levels, ctx)]
            context = cf.Task(t.chem, t.fold, 'unused', t.logc[chosen], t.y[chosen], t.m[chosen])
            predictions = {'anchorboost': model(context, np.ones(len(context.logc), bool), query),
                           'loglinear': cf.predict_interp(context, np.ones(len(context.logc), bool), query)}
            measured = effect(context.mu, context.ok)
            row = dict(outer_fold=fold, role=role, chemical=t.chem, drug_group=t.group, design=di,
                       context_levels=[int(x) for x in np.searchsorted(t.levels, ctx)],
                       context_logc=[float(x) for x in ctx], wells_measured=int(chosen.sum()), wells_full=len(t.logc),
                       measured_only=measured)
            for method, pred in predictions.items():
                row[method] = max(measured, float(np.abs(pred.mean(axis=1)).max()))
            records.append(row)
            for i, q in enumerate(query):
                points['chemical'].append(t.chem)
                points['design'].append(di)
                points['level'].append(int(np.searchsorted(t.levels, q)))
                points['logc'].append(float(q))
                for method in predictions:
                    points[method].append(predictions[method][i])
    return records, {k: np.asarray(v) for k, v in points.items()}


def labels(tasks):
    return {t.chem: int(effect(t.mu, t.ok) < 3.) for t in tasks}


def fit_stage(args):
    start = time.monotonic()
    protocol, ids, splits = read_run(args.out)
    sp = splits[str(args.fold)]
    folder = args.out / f'fold{args.fold}'
    folder.mkdir(exist_ok=True)
    if args.stage == 'outer':
        names, held = sp['train'], []
    else:
        inner = int(args.stage[-1])
        held = sp['inner'][str(inner)]
        names = [n for n in sp['train'] if n not in held]
    frame = raw_frame(input_path(protocol, 'raw'))
    transform = fit_transform(frame, names)
    train = make_tasks(frame, names, ids, transform)
    dump(folder / f'{args.stage}_transform.json', transform)
    with threadpool_limits(limits=4, user_api='openmp'), threadpool_limits(limits=1, user_api='blas'):
        model = cf.AnchorBoost(train, 3)
        if held:
            tasks = make_tasks(frame, held, ids, transform)
            records, points = forecast(model, tasks, args.fold, args.stage)
            truth = labels(tasks)
            for r in records:
                r['truth'] = truth[r['chemical']]
            # Targets are exposed only after these inner-validation predictions.
            by_name = {t.chem: t for t in tasks}
            points['truth'] = np.array([by_name[str(c)].mu[l] for c, l in zip(points['chemical'], points['level'])])
            points['mask'] = np.array([by_name[str(c)].ok[l] for c, l in zip(points['chemical'], points['level'])])
            dump(folder / f'{args.stage}_records.json', records)
            np.savez_compressed(folder / f'{args.stage}_points.npz', **points)
        else:
            joblib.dump(model, folder / 'outer_model.joblib', compress=3)
    detail = dict(stage=args.stage, training_names=sorted(names), training_drugs=len({ids[n]['drug_group'] for n in names}),
                  training_rows=model.rows, transform_sha256=sha(folder / f'{args.stage}_transform.json'),
                  protocol_sha256=frozen_sha(args.out / 'protocol.json'), **runtime(start))
    dump(folder / f'{args.stage}_runtime.json', detail)
    print(json.dumps(detail), flush=True)


def weights(records):
    counts = defaultdict(int)
    for r in records:
        counts[r['drug_group']] += 1
    return np.array([1 / counts[r['drug_group']] for r in records])


def fit_rules(records, point_sets, ids):
    rules = {}
    y = np.array([r['truth'] for r in records])
    w = weights(records)
    for method in METHODS:
        x = np.array([r[method] for r in records])
        ordered = np.unique(x)
        choices = np.r_[ordered[0] - max(1., abs(ordered[0]) * .01),
                        (ordered[:-1] + ordered[1:]) / 2, ordered[-1] + max(1., abs(ordered[-1]) * .01)]
        def objective(c):
            return np.mean([np.sum(w[y == label] * ((x[y == label] <= c) == label)) / w[y == label].sum() for label in np.unique(y)])
        cutoff = min(choices, key=lambda c: (-objective(c), c))
        rules[method] = {'cutoff': float(cutoff), 'reference': x.tolist(), 'weights': w.tolist(),
                         'inner_balanced_accuracy': float(objective(cutoff))}
    widths = {}
    for method in ['anchorboost', 'loglinear']:
        by_group = {}
        for p in point_sets:
            for c, pred, target, mask in zip(p['chemical'], p[method], p['truth'], p['mask']):
                g = ids[str(c)]['drug_group']
                residual = np.where(mask, np.abs(pred - target), np.nan)
                if g not in by_group:
                    by_group[g] = residual.copy()
                else:
                    by_group[g] = np.fmax(by_group[g], residual)
        vals = np.stack(list(by_group.values()))
        if np.isnan(vals).all(axis=0).any():
            raise ValueError('An interval output lacks training residuals')
        widths[method] = np.nanquantile(vals, .9, axis=0, method='higher').tolist()
    return {'methods': rules, 'interval_half_widths': widths, 'margin_grid': MARGIN_GRID, 'alpha': ALPHA,
            'training_record_sha256': digest(records), 'created_utc': utc()}


GRID_EXACT = {g: Fraction(-1) if g == -1. else Fraction(i - 1, 100) for i, g in enumerate(MARGIN_GRID)}


class Margin(float):
    """Rank margin: the float of the frozen formula, carrying its exact value num/den.

    Rank weights are 1/5, 1/10, 1/15, so exact margins can sit on a grid value j/100.
    Order comparisons with a grid value or another Margin use integer cross-multiplication,
    so no release depends on the last bit of a floating-point sum. The float value,
    JSON output and equality stay those of the frozen code. Against any other float the
    comparison keeps float semantics.
    """

    def __new__(cls, value, num, den):
        self = super().__new__(cls, value)
        self.num, self.den = num, den
        return self

    def __getnewargs__(self):
        return float(self), self.num, self.den

    def _sign(self, other):
        if isinstance(other, Margin):
            num, den = other.num, other.den
        elif isinstance(other, float) and other in GRID_EXACT:
            num, den = GRID_EXACT[other].numerator, GRID_EXACT[other].denominator
        else:
            return None
        left, right = self.num * den, num * self.den
        return (left > right) - (left < right)

    def __gt__(self, other):
        s = self._sign(other)
        return float.__gt__(self, other) if s is None else s > 0

    def __ge__(self, other):
        s = self._sign(other)
        return float.__ge__(self, other) if s is None else s >= 0

    def __lt__(self, other):
        s = self._sign(other)
        return float.__lt__(self, other) if s is None else s < 0

    def __le__(self, other):
        s = self._sign(other)
        return float.__le__(self, other) if s is None else s <= 0


def apply_rule(rule, x):
    ref = np.array(rule['reference'])
    w = np.array(rule['weights'])
    def rank(value):
        return float(w @ ((ref < value) + .5 * (ref == value)) / w.sum())
    margin = abs(rank(x) - rank(rule['cutoff']))
    # Exact twin: weights 1/d become integer counts scale/d on scale = lcm(d).
    dens = [int(round(1 / v)) for v in rule['weights']]
    if any(1 / d != v for d, v in zip(dens, rule['weights'])):
        raise ValueError('A rank weight is not the reciprocal of an integer')
    scale = math.lcm(*dens)
    counts = np.array([scale // d for d in dens], dtype=np.int64)
    def rank2(value):
        return 2 * int(counts[ref < value].sum()) + int(counts[ref == value].sum())
    exact = Fraction(abs(rank2(x) - rank2(rule['cutoff'])), 2 * int(counts.sum()))
    if abs(margin - exact.numerator / exact.denominator) > 1e-12:
        raise AssertionError(f'Float margin {margin!r} departs from exact {exact} by more than 1e-12')
    return int(x <= rule['cutoff']), Margin(margin, exact.numerator, exact.denominator)


def apply_rules(records, rules):
    result = []
    for row in records:
        r = dict(row)
        for method in METHODS:
            call, margin = apply_rule(rules['methods'][method], r[method])
            # Margin: stored as the frozen float, compared with grid values exactly.
            r[method + '_call'], r[method + '_margin'] = call, margin
        result.append(r)
    return result


def calibrate(records, method, alpha=ALPHA):
    by_group = defaultdict(list)
    for r in records:
        by_group[r['drug_group']].append(r)
    n = len(by_group)
    curve = []
    last_loss = None
    ok = []
    level = Fraction(repr(alpha))  # the decimal level read exactly: .10 -> 1/10
    for margin in MARGIN_GRID:
        # Exact for Margin values from apply_rules: integer cross-multiplication with j/100.
        flags = [[r[method + '_margin'] > margin and r[method + '_call'] != r['truth'] for r in rows] for rows in by_group.values()]
        loss = [float(np.mean(f)) for f in flags]
        if last_loss is not None and np.any(np.array(loss) > np.array(last_loss)):
            raise AssertionError('Drug loss must be monotone nonincreasing')
        last_loss = loss
        curve.append({'margin': margin, 'loss_sum': sum(loss), 'corrected': (sum(loss) + 1.) / (n + 1),
                      'calibration_drugs': n,
                      'released_designs': sum(r[method + '_margin'] > margin for r in records)})
        # Feasibility from integer group counts, so the float sum order cannot decide it.
        ok.append((sum(Fraction(int(sum(f)), len(f)) for f in flags) + 1) / (n + 1) <= level)
    feasible = [r for r, good in zip(curve, ok) if good]
    choice = feasible[0] if feasible else curve[-1]
    return {'margin': choice['margin'], 'calibration_drugs': n, 'finite_grid_feasible': bool(feasible),
            'corrected_risk': choice['corrected'], 'alpha': alpha, 'curve': curve,
            'fallback': 'none' if feasible else 'all_retest_due_to_finite_sample_correction',
            'calibration_records_sha256': digest(records)}


def evaluate(args):
    start = time.monotonic()
    protocol, ids, splits = read_run(args.out)
    sp, folder = splits[str(args.fold)], args.out / f'fold{args.fold}'
    records = load(folder / 'inner0_records.json') + load(folder / 'inner1_records.json')
    point_sets = [np.load(folder / f'inner{i}_points.npz') for i in range(2)]
    rules = fit_rules(records, point_sets, ids)
    dump(folder / 'training_rules.json', rules)
    model = joblib.load(folder / 'outer_model.joblib')
    transform = load(folder / 'outer_transform.json')
    frame = raw_frame(input_path(protocol, 'raw'))
    with threadpool_limits(limits=4, user_api='openmp'), threadpool_limits(limits=1, user_api='blas'):
        cal = make_tasks(frame, sp['calibration'], ids, transform)
        cal_rows, cal_points = forecast(model, cal, args.fold, 'calibration')
        cal_rows = apply_rules(cal_rows, rules)
        cal_truth = labels(cal)
        for r in cal_rows:
            r['truth'] = cal_truth[r['chemical']]
        certificates = {method: calibrate(cal_rows, method) for method in METHODS}
        dump(folder / 'calibration_design_decisions.json', cal_rows)
        np.savez_compressed(folder / 'calibration_predictions.npz', **cal_points)
        dump(folder / 'calibration.json', certificates)
        freeze = {'created_utc': utc(), 'protocol_sha256': frozen_sha(args.out / 'protocol.json'),
                  'rules_sha256': sha(folder / 'training_rules.json'), 'calibration_sha256': sha(folder / 'calibration.json'),
                  'model_sha256': sha(folder / 'outer_model.joblib'), 'transform_sha256': sha(folder / 'outer_transform.json'),
                  'test_drugs_sha256': digest(sorted({ids[n]['drug_group'] for n in sp['test']})),
                  'test_response_access': 'Test target responses have not entered predictor, rule, interval or threshold fitting.'}
        dump(folder / 'pretest_freeze.json', freeze)
        test = make_tasks(frame, sp['test'], ids, transform)
        test_rows, points = forecast(model, test, args.fold, 'test')
        test_rows = apply_rules(test_rows, rules)
        for r in test_rows:
            for method in METHODS:
                r[method + '_release'] = r[method + '_margin'] > certificates[method]['margin']
            r['observed_active_fallback_call'] = int(r['measured_only'] < 3.)
            r['observed_active_fallback_release'] = r['measured_only'] >= 3.
        for method in ['anchorboost', 'loglinear']:
            q = np.array(rules['interval_half_widths'][method])
            points[method + '_lower'] = points[method] - q
            points[method + '_upper'] = points[method] + q
        np.savez_compressed(folder / 'test_predictions.npz', **points)
        dump(folder / 'test_decisions_frozen.json', test_rows)
        dump(folder / 'prediction_freeze.json', {'created_utc': utc(), 'pretest_freeze_sha256': sha(folder / 'pretest_freeze.json'),
             'predictions_sha256': sha(folder / 'test_predictions.npz'), 'decisions_sha256': sha(folder / 'test_decisions_frozen.json')})
    # Reveal the reference endpoints and point targets only after saving decisions.
    truth = labels(test)
    for r in test_rows:
        r['truth'] = truth[r['chemical']]
    by_name = {t.chem: t for t in test}
    points['truth'] = np.array([by_name[str(c)].mu[l] for c, l in zip(points['chemical'], points['level'])])
    points['mask'] = np.array([by_name[str(c)].ok[l] for c, l in zip(points['chemical'], points['level'])])
    np.savez_compressed(folder / 'test_scored_points.npz', **points)
    dump(folder / 'design_decisions.json', test_rows)
    dump(folder / 'drug_decisions.json', drug_rows(test_rows))
    summary = summarize_rows(test_rows)
    summary['curve_prediction'] = curve_summary(points, ids)
    summary['runtime'] = runtime(start)
    summary['pretest_freeze_sha256'] = sha(folder / 'pretest_freeze.json')
    dump(folder / 'summary.json', summary)
    print(json.dumps({'fold': args.fold, 'methods': summary['methods'], 'runtime': summary['runtime']}), flush=True)


def drug_rows(rows):
    grouped = defaultdict(list)
    for r in rows:
        grouped[(r['outer_fold'], r['drug_group'])].append(r)
    result = []
    for (fold, group), rr in sorted(grouped.items()):
        for method in METHODS + ['observed_active_fallback']:
            release = np.array([r[method + '_release'] for r in rr])
            wrong = np.array([r[method + '_call'] != r['truth'] for r in rr])
            n_release, n_error = int(release.sum()), int((release & wrong).sum())
            result.append(dict(outer_fold=fold, drug_group=group, chemical=';'.join(sorted({r['chemical'] for r in rr})),
                method=method, designs=len(rr), released=n_release, wrong_released=n_error,
                drug_loss=n_error / len(rr), released_error=n_error / n_release if n_release else None,
                release_rate=n_release / len(rr), full_coverage_errors=int(wrong.sum()),
                full_coverage_error_rate=float(wrong.mean()),
                wells_used=sum(r['wells_measured'] if r[method + '_release'] else r['wells_full'] for r in rr),
                wells_full=sum(r['wells_full'] for r in rr)))
    return result


def summarize_rows(rows):
    drugs = drug_rows(rows)
    summary = {'designs': len(rows), 'substances': len({r['chemical'] for r in rows}),
               'drugs': len({r['drug_group'] for r in rows}), 'methods': {}}
    for method in METHODS + ['observed_active_fallback']:
        dd = [r for r in drugs if r['method'] == method]
        n, released = len(rows), sum(r['released'] for r in dd)
        wrong = sum(r['wrong_released'] for r in dd)
        used, full = sum(r['wells_used'] for r in dd), sum(r['wells_full'] for r in dd)
        summary['methods'][method] = dict(released=released, wrong_released=wrong, error_all_designs=wrong / n,
            error_released=wrong / released if released else None, drug_mean_loss=float(np.mean([r['drug_loss'] for r in dd])),
            drug_mean_release_rate=float(np.mean([r['release_rate'] for r in dd])), release_rate=released / n,
            full_coverage_errors=sum(r['full_coverage_errors'] for r in dd),
            full_coverage_error_rate=sum(r['full_coverage_errors'] for r in dd) / n,
            wells_used=used, wells_full=full, savings_vs_full=1 - used / full)
    for cell in summary['methods'].values():
        for baseline in ['measured_only', 'observed_active_fallback']:
            denom = summary['methods'][baseline]['wells_used']
            cell[f'savings_vs_{baseline}_fallback'] = 1 - cell['wells_used'] / denom
    summary['full_measurement'] = {'wells_used': summary['methods']['anchorboost']['wells_full'],
                                   'reference_disagreement': 0, 'scope': 'Reference by definition, not biological ground truth.'}
    return summary


def curve_summary(points, ids):
    result = {}
    for method in ['anchorboost', 'loglinear']:
        acc = defaultdict(list)
        coverage = defaultdict(list)
        for c, pred, truth, mask, low, high in zip(points['chemical'], points[method], points['truth'], points['mask'],
                                                 points[method + '_lower'], points[method + '_upper']):
            if mask.any():
                g = ids[str(c)]['drug_group']
                acc[g].append(float(np.abs(pred - truth)[mask].mean()))
                coverage[g].append(float(((truth >= low) & (truth <= high))[mask].mean()))
        result[method] = {'drug_mean_target_level_mae': float(np.mean([np.mean(v) for v in acc.values()])),
                          'drug_mean_interval_point_coverage': float(np.mean([np.mean(v) for v in coverage.values()])),
                          'mean_half_width': float(np.mean((points[method + '_upper'] - points[method + '_lower']) / 2)),
                          'interval_scope': 'Training-only descriptive level-mean bands, no promised coverage.'}
    return result


def bootstrap(rows):
    dd = drug_rows(rows)
    groups = sorted({r['drug_group'] for r in dd})
    lookup = {(r['drug_group'], r['method']): r for r in dd}
    rng = np.random.default_rng(0)
    result = {}
    for comparator in ['loglinear', 'measured_only', 'observed_active_fallback']:
        a = np.array([[lookup[g, 'anchorboost'][k] - lookup[g, comparator][k]
                       for k in ['drug_loss', 'release_rate', 'full_coverage_error_rate']] for g in groups])
        sampled = a[rng.integers(0, len(a), size=(4000, len(a)))].mean(axis=1)
        result[comparator] = {k: {'difference': float(a[:, j].mean()), 'ci95': np.quantile(sampled[:, j], [.025, .975]).tolist()}
                             for j, k in enumerate(['drug_loss', 'release_rate', 'full_coverage_error_rate'])}
    return result


def summarize(args):
    protocol, ids, splits = read_run(args.out)
    rows = []
    for fold in protocol['outer_order']:
        folder = args.out / f'fold{fold}'
        freeze = load(folder / 'prediction_freeze.json')
        if frozen_sha(folder / 'test_predictions.npz') != freeze['predictions_sha256'] or frozen_sha(folder / 'test_decisions_frozen.json') != freeze['decisions_sha256']:
            raise ValueError('Test forecast freeze changed')
        rows += load(folder / 'design_decisions.json')
    primary = [r for r in rows if r['outer_fold'] in protocol['primary_folds']]
    legacy = load(input_path(protocol, 'legacy_result'))
    result = {'schema': 'paper.nested_summary.v1', 'created_utc': utc(), 'protocol_sha256': frozen_sha(args.out / 'protocol.json'),
        'status': protocol['status'], 'primary_folds_1_to_4': summarize_rows(primary), 'all_five_outer_folds': summarize_rows(rows),
        'by_fold': {str(f): load(args.out / f'fold{f}' / 'summary.json') for f in range(5)},
        'primary_paired_drug_bootstrap': bootstrap(primary),
        'legacy_970_design_replay': {'status': 'Historical replay only; predictor/calibration leakage and design-level calibration denominator.',
             'source_sha256': protocol['inputs']['legacy_result']['sha256'],
             'anchorboost': legacy['anchorboost'], 'measured_only': legacy['measured_only'],
             'endpoint_comparability': 'Old global vehicle normalization and substance split; new train-only normalization and conservative drug groups change the evaluated experiment.'},
        'limitations': [protocol['status'], protocol['model']['historical_selection'], protocol['risk']['scope'],
                       protocol['cost'], 'Donor/culture batch keys absent; plate/date overlap is measured, not eliminated.',
                       'The activity reference is an assay summary, not a clinical toxicity label.',
                       'Shared technical batches and previously label-stratified folds do not establish calibration/test exchangeability.']}
    dump(args.out / 'summary.json', result)
    dump(args.out / 'design_decisions.json', rows)
    write_csv(args.out / 'drug_decisions.csv', drug_rows(rows))
    flat = [dict(r, context_levels=';'.join(map(str, r['context_levels'])), context_logc=';'.join(map(str, r['context_logc']))) for r in rows]
    write_csv(args.out / 'design_decisions.csv', flat)
    print(json.dumps(result['primary_folds_1_to_4'], indent=2), flush=True)


def probe(args):
    start = time.monotonic()
    protocol, ids, splits = read_run(args.out)
    frame = raw_frame(input_path(protocol, 'raw'))
    names = splits['0']['train'][:12]
    tr = fit_transform(frame, names)
    train = make_tasks(frame, names, ids, tr)
    params = dict(cf.MODEL, max_iter=12)
    with threadpool_limits(limits=4, user_api='openmp'), threadpool_limits(limits=1, user_api='blas'):
        model = cf.AnchorBoost(train, 3, params=params)
        records, points = forecast(model, train[:1], 0, 'resource_probe_only')
    result = dict(training_substances=len(names), training_rows=model.rows, max_iter=12,
                  status='Resource/function probe on outer-training drugs only; no evaluation score used for selection.', **runtime(start))
    dump(args.out / 'probe.json', result)
    print(json.dumps(result), flush=True)


def run(args):
    """Finite owned batch; every compute subprocess has a five-minute ceiling."""
    script = str(Path(__file__).resolve())
    for fold in args.folds:
        for stage in ['inner0', 'inner1', 'outer']:
            target = args.out / f'fold{fold}' / f'{stage}_runtime.json'
            if target.exists():
                continue
            subprocess.run([sys.executable, script, 'fit', '--out', str(args.out), '--fold', str(fold), '--stage', stage],
                           check=True, timeout=295)
        if not (args.out / f'fold{fold}' / 'summary.json').exists():
            subprocess.run([sys.executable, script, 'evaluate', '--out', str(args.out), '--fold', str(fold)], check=True, timeout=295)
    if all((args.out / f'fold{f}' / 'summary.json').exists() for f in range(5)):
        subprocess.run([sys.executable, script, 'summarize', '--out', str(args.out)], check=True, timeout=295)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['prepare', 'probe', 'fit', 'evaluate', 'summarize', 'run'])
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--raw', type=Path)
    p.add_argument('--bundle', type=Path)
    p.add_argument('--identities', type=Path)
    p.add_argument('--fold', type=int, choices=range(5), default=0)
    p.add_argument('--folds', type=int, nargs='+', default=list(range(5)))
    p.add_argument('--stage', choices=['inner0', 'inner1', 'outer'], default='outer')
    args = p.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    limits()
    globals()[{'fit': 'fit_stage'}.get(args.action, args.action)](args)


if __name__ == '__main__':
    main()

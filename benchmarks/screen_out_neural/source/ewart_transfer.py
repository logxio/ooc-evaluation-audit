#!/usr/bin/env python3
"""Run the prospectively specified Ewart transfer experiment with frozen source."""
import os
for _name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS'):
    os.environ[_name] = '1'
import argparse
import csv
import hashlib
import importlib.util
import itertools
import json
import resource
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import sklearn

ROOT = Path(__file__).resolve().parent
INPUT_SHA = '326c494f0ebdae41bd7ea5b425d3697d5e48b5685ac033bb719ff1e7713f3b8c'
MODEL_SHA = '3d02dd3a1bc57e8c53f701a6005c8d5e9d8ad6a15a57cdec3f22b27066015897'
ENDPOINTS = ('ALBUMIN', 'ALT', 'Morphology')
PREPARATIONS = ('author_units', 'lowest_centered')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def write_csv(path, rows):
    with path.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def load_model():
    source = ROOT / 'raw/chip_forecast.py'
    if sha(source) != MODEL_SHA or sha(ROOT / 'ewart_readings.csv') != INPUT_SHA:
        raise ValueError('Frozen source or data checksum mismatch')
    spec = importlib.util.spec_from_file_location('frozen_chip_forecast', source)
    cf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cf)
    cf.ND = cf.NF = cf.D = 1
    return cf


def load_tasks(cf, endpoint, preparation):
    rows = defaultdict(list)
    with (ROOT / 'ewart_readings.csv').open(newline='') as f:
        for row in csv.DictReader(f):
            if row['sheet'] == endpoint:
                dose = float(row['concentration_as_published'])
                value = float(row['value_as_published']) if row['value_as_published'] else None
                rows[row['compound']].append((dose, value))
    tasks, references, counts = [], {}, {}
    for fold, (compound, observations) in enumerate(sorted(rows.items())):
        available = sorted({c for c, y in observations if y is not None})
        ref = float(np.mean([y for c, y in observations if c == available[0] and y is not None]))
        references[compound] = ref if preparation == 'lowest_centered' else 0.0
        usable = [(c, y) for c, y in observations if c in available]
        logc = np.log10([c for c, _ in usable]).astype(np.float32)
        mask = np.array([y is not None for _, y in usable], bool)[:, None, None]
        # Masked storage follows Task's API; blanks never enter observed means/losses.
        y = np.array([v - references[compound] if v is not None else 0 for _, v in usable], np.float32)[:, None, None]
        tasks.append(cf.Task(compound, fold, endpoint, logc, y, mask))
        counts[compound] = dict(n_observations=int(mask.sum()), n_available_concentrations=len(available),
                               concentrations=available, reference=references[compound])
    return tasks, references, counts


def contexts(task, endpoint):
    pairs = list(itertools.combinations(task.levels[1:].tolist(), 2))
    seed = int(hashlib.sha256(f'ewart-transfer-v1|{endpoint}|{task.chem}'.encode()).hexdigest()[:8], 16)
    order = np.random.default_rng(seed).permutation(len(pairs))[:5]
    return [np.array([task.levels[0], *pairs[i]], np.float32) for i in order]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe', action='store_true')
    args = parser.parse_args()
    started = time.monotonic()
    cf = load_model()
    protocol_sha = sha(ROOT / 'ewart_protocol.md')
    fold_rows, predictions, summaries, counts = [], [], {}, {}
    fits = 0
    for preparation in PREPARATIONS[:1] if args.probe else PREPARATIONS:
        summaries[preparation] = {}
        for endpoint in ENDPOINTS[:1] if args.probe else ENDPOINTS:
            tasks, references, counts[endpoint] = load_tasks(cf, endpoint, preparation)
            endpoint_rows = []
            for held_out in tasks[:1] if args.probe else tasks:
                train = [t for t in tasks if t.chem != held_out.chem]
                assert len(train) == 5 and all(t.chem != held_out.chem for t in train)
                model = cf.AnchorBoost(train, 3)
                fits += 1
                errors = {'anchorboost': [], 'loglinear_interp': []}
                for design_id, ctx in enumerate(contexts(held_out, endpoint)):
                    ic = np.isin(held_out.logc, ctx)
                    q, mu, ok = cf.level_means(held_out, ~ic)
                    assert len(ctx) == 3 and held_out.levels[0] in ctx and len(q) >= 2
                    for method, fn in (('anchorboost', model), ('loglinear_interp', cf.predict_interp)):
                        pred = fn(held_out, ic, q)
                        if not np.isfinite(pred).all():
                            raise ValueError('Nonfinite model output')
                        errors[method].append(cf.errors(pred, held_out, ~ic)[0])
                        for i, dose in enumerate(q):
                            predictions.append(dict(preparation=preparation, endpoint=endpoint,
                                chemical=held_out.chem, fold=held_out.fold, design=design_id,
                                context_log10='|'.join(map(str, ctx.tolist())), query_log10=float(dose),
                                method=method, target=float(mu[i, 0, 0]), prediction=float(pred[i, 0, 0]),
                                reference=references[held_out.chem],
                                prediction_published_units=float(pred[i, 0, 0]) + references[held_out.chem]))
                a, b = (float(np.mean(errors[m])) for m in ('anchorboost', 'loglinear_interp'))
                row = dict(preparation=preparation, endpoint=endpoint, chemical=held_out.chem,
                           fold=held_out.fold, n_designs=5, anchorboost=a, loglinear_interp=b,
                           difference=a-b, outcome='win' if a < b else 'loss' if a > b else 'tie',
                           training_rows=model.rows, n_train_drugs=len(train))
                endpoint_rows.append(row)
                fold_rows.append(row)
                print(json.dumps(row), flush=True)
            ours = {r['chemical']: r['anchorboost'] for r in endpoint_rows}
            baseline = {r['chemical']: r['loglinear_interp'] for r in endpoint_rows}
            pair = cf.paired(ours, baseline)
            summaries[preparation][endpoint] = dict(
                n_drugs=len(ours), anchorboost_mae=float(np.mean(list(ours.values()))),
                loglinear_mae=float(np.mean(list(baseline.values()))), paired=pair,
                lower_error_pct=-pair['rel_change_pct'],
                fold_outcomes={s: sum(r['outcome'] == s for r in endpoint_rows) for s in ('win','loss','tie')},
                folds=endpoint_rows)
    result = dict(schema='ewart-transfer.v1', status='complete' if not args.probe else 'resource_probe',
        platform='perfused liver-chip', n_drugs=6, n_endpoints=3, n_source_positions=210,
        n_numeric_observations=204, n_missing_observations=6, n_folds=6,
        primary_preparation='author_units', model_fits=fits, input_sha256=INPUT_SHA,
        model_sha256=MODEL_SHA, protocol_sha256=protocol_sha, adapter_sha256=sha(Path(__file__)),
        model_parameters=cf.MODEL, runtime_dimensions=dict(ND=1, NF=1, D=1),
        dependency_versions=dict(numpy=np.__version__, sklearn=sklearn.__version__),
        summary=summaries, curve_counts=counts,
        interpretation='Endpoint-specific leave-one-drug-out transfer in published units; separate from unchanged-protocol fourth-benchmark availability.')
    if args.probe:
        write_json(ROOT / 'ewart_transfer_probe.json', result)
    else:
        existing = json.loads((ROOT / 'result.json').read_text())
        existing['ewart_transfer'] = result
        write_json(ROOT / 'result.json', existing)
        write_csv(ROOT / 'ewart_folds.csv', fold_rows)
        write_csv(ROOT / 'ewart_predictions.csv', predictions)
    write_json(ROOT / ('ewart_transfer_probe_resource.json' if args.probe else 'ewart_transfer_resource.json'),
        dict(seconds=round(time.monotonic()-started, 4), model_fits=fits,
             peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == 'darwin' else 1024)))
    assert sha(ROOT / 'raw/chip_forecast.py') == MODEL_SHA
    assert sha(ROOT / 'ewart_protocol.md') == protocol_sha


if __name__ == '__main__':
    main()

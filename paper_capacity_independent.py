#!/usr/bin/env python3
"""Run the frozen Bircsak protocol using only a custodian's isolated packet.

Commands: validate, probe, predict, score. Score opens the revealed reference
only after a custodian receipt matches the previously sealed prediction hashes.
No raw-digitization path or sealed-reference discovery exists in this module.
"""
import os
for _key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS'):
    os.environ[_key] = '1'
import argparse
import csv
import hashlib
import io
import itertools
import json
import math
import signal
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import joblib
import numpy as np
import paper_capacity as core

PROTOCOL_SHA = '8213c89526adfad2ef5f5702634520b931010436ff8317bf5c5ded3e06a286fb'
PACKET_FILES = ('training.csv', 'calibration.csv', 'test_contexts.csv',
                'test_dose_metadata.csv', 'source_owner_receipt.json', 'reference_commitment.json')
CSV_FILES = PACKET_FILES[:4]
KEY = ('dataset', 'compound', 'endpoint', 'configuration', 'time', 'concentration', 'concentration_unit')
META = set(KEY) | {'value_unit', 'curve_id', 'point_id', 'dose_index', 'source_locator', 'is_context', 'donor', 'batch', 'chip_id'}
RESPONSE_REQUIRED = set(KEY) | {'value', 'value_unit', 'curve_id', 'point_id', 'error_abs', 'source_locator'}
METHODS = ('selected', 'fixed50', 'interpolation')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def instant(value):
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    require(dt.tzinfo is not None, 'timestamp requires an explicit timezone')
    return dt


def save(path, data):
    with path.open('x') as f:
        json.dump(data, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())


def table(path, rows):
    require(bool(rows), f'{path.name}: empty output')
    with path.open('x', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
        f.flush()
        os.fsync(f.fileno())


def read_json(path):
    return json.loads(path.read_text())


def save_validation(out, report):
    path = out/'packet_validation.json'
    if path.exists():
        previous = read_json(path)
        require(all(previous[k] == report[k] for k in ('status', 'files', 'issues')),
                'packet validation changed; preserve this audit and use a fresh output directory')
    else:
        save(path, report)


def load_model_source():
    cf = core.load_cf()
    # Register the pinned module so joblib can serialize its estimator wrapper.
    sys.modules[cf.__name__] = cf
    return cf


def csv_rows(path, metadata=False):
    with path.open(newline='') as f:
        reader = csv.DictReader(f)
        fields = set(reader.fieldnames or [])
        if metadata:
            # Reject unexpected columns before reading even one response-bearing row.
            require(fields <= META, f'{path.name}: disallowed metadata columns {sorted(fields-META)}')
            require(set(KEY) | {'value_unit', 'curve_id', 'point_id', 'is_context'} <= fields,
                    f'{path.name}: required metadata columns missing')
        else:
            require(RESPONSE_REQUIRED <= fields, f'{path.name}: missing columns {sorted(RESPONSE_REQUIRED-fields)}')
        return list(reader)


def key(row):
    return tuple(format(float(row[k]), '.17g') if k == 'concentration' else row[k] for k in KEY)


def keys_hash(rows):
    # Custodian v1 commits canonical CSV bytes and preserves source dose strings.
    unique = {tuple(r[k] for k in KEY) for r in rows}
    ordered = sorted(unique, key=lambda r: (*r[:5], Decimal(r[5]), r[6]))
    stream = io.StringIO(newline='')
    writer = csv.writer(stream, lineterminator='\n')
    writer.writerow(KEY)
    writer.writerows(ordered)
    return hashlib.sha256(stream.getvalue().encode('utf-8')).hexdigest()


def read_commitment(path):
    raw = read_json(path)
    require(raw['schema'] == 'bircsak.reference.commitment.v1', 'unsupported custodian commitment schema')
    require(raw['row_key_fields'] == list(KEY), 'committed key fields differ')
    require(raw['reference_status'] == 'sealed_unrevealed', 'pre-prediction reference commitment is not sealed')
    return dict(raw, owner_session=raw['custodian_session'], keys_sha256=raw['row_key_set_sha256'])


def group(rows):
    result = defaultdict(list)
    for row in rows:
        result[(row['compound'], row['endpoint'])].append(row)
    for curve in result.values():
        curve.sort(key=lambda r: float(r['concentration']))
    return dict(result)


def indices(n):
    return [0, (n-1)//3, 2*(n-1)//3]


def context_rows(rows):
    return [rows[i] for i in indices(len(rows))]


def implementation_hashes():
    return {'runner': core.sha(Path(__file__)), 'capacity_core': core.sha(Path(core.__file__)),
            'model_source': core.sha(core.MODEL)}


def protocol(path):
    require(core.sha(path) == PROTOCOL_SHA, 'independent protocol differs from the frozen JSON')
    p = read_json(path)
    require(core.candidates() == p['candidate_family'], 'candidate family differs from frozen protocol')
    require(core.sha(core.MODEL) == p['model_source_sha256'], 'model source hash changed')
    old = read_json(path.parent/'protocol.json')
    require(core.sha(path.parent/'protocol.json') == p['candidate_family_sha256'], 'candidate source protocol changed')
    require(core.sha(Path(core.__file__)) == old['evaluator_sha256'], 'frozen capacity implementation changed')
    return p


def validate(packet, p):
    """Read the six allowlisted packet files; collect every missing curve/response."""
    issues, data, inventory = [], {}, []
    missing = [name for name in PACKET_FILES if not (packet/name).is_file()]
    issues += [f'missing file: {name}' for name in missing]
    hashes = {name: core.sha(packet/name) for name in PACKET_FILES if name not in missing}
    for name in CSV_FILES:
        if name in missing:
            data[name] = []
            continue
        try:
            data[name] = csv_rows(packet/name, metadata=name == 'test_dose_metadata.csv')
        except (ValueError, UnicodeError, csv.Error) as exc:
            issues.append(str(exc))
            data[name] = []
    missing_response_rows = []
    for name, rows in data.items():
        seen, point_ids = set(), set()
        for i, row in enumerate(rows, 2):
            label = f'{name}:{i}:{row.get("compound", "?")}/{row.get("endpoint", "?")}'
            try:
                require(None not in row and all(v is not None for v in row.values()), 'malformed CSV row')
                require(row['dataset'] == p['source'], 'dataset mismatch')
                for field in KEY + ('value_unit', 'curve_id', 'point_id'):
                    require(bool(row.get(field)), f'empty {field}')
                dose = float(row['concentration'])
                require(math.isfinite(dose) and dose > 0, 'dose must be finite and positive')
                k = key(row)
                require(k not in seen, 'duplicate dose/curve key')
                require(row['point_id'] not in point_ids, 'duplicate point_id')
                seen.add(k)
                point_ids.add(row['point_id'])
                if name != 'test_dose_metadata.csv':
                    if row['value'].strip() == '':
                        missing_response_rows.append(label)
                    require(math.isfinite(float(row['value'])), 'missing or nonfinite response')
                    require(math.isfinite(float(row['error_abs'])) and float(row['error_abs']) > 0,
                            'digitization error_abs must be finite and positive')
                    require(bool(row['source_locator']), 'source locator missing')
                else:
                    require(row['is_context'].lower() in ('true', 'false', '1', '0'), 'invalid is_context')
            except (KeyError, ValueError, TypeError) as exc:
                issues.append(f'{label}: {exc}')
    # Inventory is based on actual rows, never on a directory's claimed drug count.
    partitions = [('training.csv', 'training_drugs'), ('calibration.csv', 'calibration_drugs'),
                  ('test_dose_metadata.csv', 'test_drugs'), ('test_contexts.csv', 'test_drugs')]
    groups = {}
    for name, member_key in partitions:
        expected = set(itertools.product(p[member_key], p['endpoints']))
        try:
            gg = group(data[name])
        except (KeyError, ValueError):
            gg = {}
        groups[name] = gg
        for unexpected in sorted(set(gg)-expected):
            issues.append(f'{name}: unexpected curve {unexpected}')
        for drug, endpoint in sorted(expected):
            curve = gg.get((drug, endpoint), [])
            inventory.append(dict(partition=name, compound=drug, endpoint=endpoint, rows=len(curve)))
            if not curve:
                issues.append(f'{name}: missing curve {drug}/{endpoint}')
                continue
            minimum = 3 if name == 'test_contexts.csv' else 4
            if len(curve) < minimum or name == 'test_contexts.csv' and len(curve) != 3:
                issues.append(f'{name}:{drug}/{endpoint}: {len(curve)} rows, expected {minimum}' +
                              (' exactly' if name == 'test_contexts.csv' else ' or more'))
            for field in ('configuration', 'time', 'concentration_unit', 'value_unit', 'curve_id'):
                if len({r.get(field) for r in curve}) != 1:
                    issues.append(f'{name}:{drug}/{endpoint}: mixed {field}')
            try:
                logs = np.log10([float(r['concentration']) for r in curve]).astype(np.float32)
                if len(np.unique(logs)) != len(curve):
                    issues.append(f'{name}:{drug}/{endpoint}: dose collision in frozen float32 log10 representation')
            except (KeyError, ValueError):
                pass  # The row errors above remain fatal; no curve is dropped from the report.
    for endpoint in p['endpoints']:
        for field in ('configuration', 'time', 'concentration_unit', 'value_unit'):
            values = {r.get(field) for rows in data.values() for r in rows if r.get('endpoint') == endpoint}
            if len(values) > 1:
                issues.append(f'{endpoint}: inconsistent {field} across partitions: {sorted(values, key=str)}')
    meta = groups['test_dose_metadata.csv']
    ctx = groups['test_contexts.csv']
    for curve_key, rows in meta.items():
        if len(rows) < 4:
            continue
        try:
            expected = context_rows(rows)
            actual = ctx.get(curve_key, [])
            require({key(r) for r in expected} == {key(r) for r in actual}, 'context indices differ from frozen rule')
            require({r['point_id'] for r in expected} == {r['point_id'] for r in actual}, 'context point IDs differ')
            flagged = [r for r in rows if r['is_context'].lower() in ('true', '1')]
            require({key(r) for r in flagged} == {key(r) for r in expected}, 'is_context flags differ')
        except (KeyError, ValueError) as exc:
            issues.append(f'test:{curve_key}: {exc}')
    receipt, commitment = {}, {}
    try:
        if 'source_owner_receipt.json' not in missing:
            raw = read_json(packet/'source_owner_receipt.json')
            require(raw['schema'] == 'bircsak.source-owner-receipt.v1', 'unsupported custodian receipt schema')
            require(raw['status'] == 'qualified_and_exported', 'custodian export incomplete')
            require(raw['reference_status'] == 'sealed_unrevealed', 'custodian reference already exposed')
            receipt = dict(raw, owner_session=raw['custodian_session'],
                           evidence_kind=raw.get('evidence_kind', 'independent_candidate_attributed_exposure'))
            require(raw['protocol']['sha256'] == PROTOCOL_SHA, 'receipt protocol hash differs')
            require(bool(receipt['owner_session']), 'data owner missing')
            require(receipt['owner_session'] != os.getenv('AGENT_THREAD_ID', ''), 'data owner equals forecasting owner')
            require(receipt['evidence_kind'] in ('independent_candidate_attributed_exposure', 'synthetic_structural_test'), 'unknown evidence_kind')
            require(instant(receipt['created_at']) <= datetime.now(timezone.utc), 'source receipt timestamp is in the future')
            require(receipt['qc']['status'] == 'passed' and len(receipt['qc']['verification_sha256']) == 64, 'source QC receipt missing')
            require(receipt['license'] == 'CC BY 4.0', 'source license differs from registered source')
            require(isinstance(receipt['aliases'], dict), 'alias mapping missing')
            old_hashes = p['source_snapshot_sha256']
            if receipt['source_snapshot_sha256'] != old_hashes:
                amendment = receipt['input_amendment']
                require(amendment['previous_hashes'] == old_hashes and amendment['new_hashes'] == receipt['source_snapshot_sha256'], 'input amendment hash mismatch')
                require(bool(amendment['reason']), 'input amendment reason missing')
                require(instant(amendment['declared_at']) <= instant(receipt['created_at']), 'amendment postdates source receipt')
            for split in ('training', 'calibration', 'test'):
                require(receipt['split_compounds'][split] == p[split+'_drugs'], f'owner {split} membership differs')
            registered = receipt['registration']
            require(len(registered) == 42, 'source owner must register all 42 curves')
            require({(r['compound'], r['endpoint']) for r in registered} ==
                    set(itertools.product(p['training_drugs']+p['calibration_drugs']+p['test_drugs'],p['endpoints'])),
                    'registered curve identities differ')
            for r in registered:
                name = 'test_dose_metadata.csv' if r['split']=='test' else r['split']+'.csv'
                rows = groups[name].get((r['compound'],r['endpoint']), [])
                require(len(rows) == r['positive_doses'], f'owner registered dose count differs: {r["curve_id"]}')
                require(all(x['curve_id'] == r['curve_id'] for x in rows), f'owner curve ID differs: {r["curve_id"]}')
            exposure = receipt['development_exposure']['per_test_compound']
            require(len(exposure)==6 and {e['compound'] for e in exposure}==set(p['test_drugs']), 'exposure must cover six test drugs')
            for e in exposure:
                require(e['source_preparation_only'] is True and e['predictor_fits_by_this_owner']==0
                        and e['predictor_selection_by_this_owner'] is False and e['response_based_model_tuning_by_this_owner'] is False,
                        f'{e["compound"]}: data owner performed model development')
                require(all(e[k] for k in ('forecast_owner_report','controller_report','scope_limit')), 'attributed exposure reports missing')
        if 'reference_commitment.json' not in missing:
            commitment = read_commitment(packet/'reference_commitment.json')
            require(commitment['protocol_sha256'] == PROTOCOL_SHA, 'commitment protocol differs')
            require(commitment['owner_session'] == receipt.get('owner_session'), 'commitment owner differs')
            require(len(commitment['reference_sha256']) == 64 and all(c in '0123456789abcdef' for c in commitment['reference_sha256']), 'reference hash invalid')
            require(commitment['rows'] == len(data['test_dose_metadata.csv']), 'committed reference row count differs')
            require(commitment['keys_sha256'] == keys_hash(data['test_dose_metadata.csv']), 'committed key set differs')
            instant(commitment['sealed_at'])
    except (KeyError, ValueError, TypeError) as exc:
        issues.append(f'custodian receipt/commitment: {exc}')
    report = dict(status='qualified' if not issues else 'missing_input' if missing else 'invalid_input',
                  checked_at=core.now(), protocol_sha256=PROTOCOL_SHA, evidence_kind=receipt.get('evidence_kind'),
                  missing_files=missing, issues=issues, missing_response_rows=missing_response_rows,
                  expected_drugs={'training': 6, 'calibration': 9, 'test': 6}, expected_distinct_curves=42,
                  actual_curves={name: len(groups[name]) for name, _ in partitions},
                  actual_drugs={name: len({k[0] for k in groups[name]}) for name, _ in partitions},
                  actual_distinct_curves=len(set().union(*(set(groups[name]) for name, _ in partitions))),
                  exposure_scope=receipt.get('development_exposure', {}),
                  curve_inventory=inventory, files=hashes,
                  key_availability={name: {k: sum(bool(r.get(k)) for r in data[name]) for k in ('donor','batch','chip_id')}
                                    for name in CSV_FILES})
    return report, data, receipt, commitment


def accepted(packet, p, out):
    report, data, receipt, commitment = validate(packet, p)
    if report['status'] != 'qualified':
        save_validation(out, report)
        raise ValueError(f'packet {report["status"]}; see {out / "packet_validation.json"}')
    return report, data, receipt, commitment


def task(cf, rows):
    require(bool(rows), 'empty curve')
    yy = np.asarray([float(r['value']) for r in rows], np.float32)
    return cf.Task(rows[0]['compound'], 0, rows[0]['endpoint'],
                   np.log10([float(r['concentration']) for r in rows]).astype(np.float32),
                   yy[:, None, None], np.ones((len(yy), 1, 1), bool))


def predict_candidates(cf, observed, queries, models):
    require(len(observed) == 3, 'predictor requires exactly three observations')
    observed_task = task(cf, observed)
    q = np.log10([float(r['concentration']) for r in queries]).astype(np.float32)
    keep = np.ones(3, bool)
    base = cf.predict_interp(observed_task, keep, q).ravel().astype(float)
    raw = {rule: model(observed_task, keep, q).ravel() for rule, model in models.items()}
    values = {'interpolation': base}
    for cand in core.candidates()[1:]:
        if cand['rule'] in raw:
            values[cand['id']] = base + cand['alpha'] * (raw[cand['rule']] - base)
    require(all(np.isfinite(v).all() for v in values.values()), 'nonfinite prediction')
    return values


def select_training(cf, curves, drugs, fits):
    """The interface contains training curves only, excluding calibration/test."""
    tasks = {drug: task(cf, curves[drug]) for drug in drugs}
    folds = []
    for val in drugs:
        training = [tasks[d] for d in drugs if d != val]
        models = {rule: fits.get(training, rule) for rule in core.RULES}
        observed = context_rows(curves[val])
        observed_keys = {key(r) for r in observed}
        queries = [r for r in curves[val] if key(r) not in observed_keys]
        preds = predict_candidates(cf, observed, queries, models)
        target = np.array([float(r['value']) for r in queries])
        folds.append(dict(validation_drug=val, training_drugs=[t.chem for t in training],
                          training_rows=core.row_count(training),
                          candidate_mae={c: float(np.abs(v-target).mean()) for c, v in preds.items()}))
    candidates = [{**c, 'inner_mae': float(np.mean([f['candidate_mae'][c['id']] for f in folds]))}
                  for c in core.candidates()]
    best = min(c['inner_mae'] for c in candidates)
    selected = next(c for c in candidates if c['inner_mae'] <= best+1e-12)
    return selected, candidates, folds, [tasks[d] for d in drugs]


def probe(packet, p, out):
    report, data, _, _ = accepted(packet, p, out)
    start = time.monotonic()
    cf = load_model_source()
    curves = group(data['training.csv'])
    endpoint = p['endpoints'][0]
    drugs = sorted(p['training_drugs'], key=lambda d: (len(curves[(d, endpoint)]), d))[:2]
    train = [task(cf, curves[(d, endpoint)]) for d in drugs]
    model = core.Fits(cf).get(train, 'fixed2')
    result = dict(status='passed', evidence_kind=report['evidence_kind'], input_files=report['files'],
                  protocol_sha256=PROTOCOL_SHA, code=implementation_hashes(), endpoint=endpoint, drugs=drugs,
                  seconds=time.monotonic()-start, peak_rss_bytes=core.rss(), **core.leaf_stats(model))
    save(out/'probe.json', result)
    return {k: result[k] for k in ('status','seconds','peak_rss_bytes','training_rows')}


def action(observed, preds):
    lowest = float(observed[0]['value'])
    threshold = 0.5*lowest
    if lowest <= 0:
        decision, reason = 'measure_next', 'nonpositive_lowest_context'
    elif any(float(r['value']) <= threshold for r in observed):
        decision, reason = 'report_reduction', 'observed_reduction'
    elif any(r['upper'] <= threshold for r in preds):
        decision, reason = 'report_reduction', 'upper_bound_below_threshold'
    elif all(float(r['value']) > threshold for r in observed) and all(r['lower'] > threshold for r in preds):
        decision, reason = 'report_no_reduction', 'all_lower_bounds_above_threshold'
    else:
        decision, reason = 'measure_next', 'threshold_ambiguous'
    observed_log = [math.log10(float(r['concentration'])) for r in observed]
    def priority(r):
        logdose = math.log10(float(r['concentration']))
        return (r['lower'] <= threshold <= r['upper'],
                min(abs(logdose-x) for x in observed_log), float(r['concentration']))
    chosen = max(preds, key=priority)
    return dict(decision=decision, reason=reason, threshold=threshold,
                next_concentration=chosen['concentration'], next_point_id=chosen['point_id'])


def predict(packet, p, out):
    report, data, receipt, commitment = accepted(packet, p, out)
    probe_result = read_json(out/'probe.json')
    require(probe_result['status'] == 'passed' and probe_result['input_files'] == report['files'], 'matching input probe required')
    require(probe_result['code'] == implementation_hashes(), 'probe implementation changed')
    require(not (out/'prediction_manifest.json').exists(), 'predictions already sealed; reuse the existing manifest')
    start = time.monotonic()
    cf = load_model_source()
    gg = {name: group(data[name]) for name in CSV_FILES}
    models_by_endpoint, selection_rows, fit_audit, artifact_names = {}, [], [], ['probe.json']
    save_validation(out, report)
    artifact_names.append('packet_validation.json')
    # Complete and seal all candidate selections before using calibration responses.
    for endpoint in p['endpoints']:
        curves = {d: gg['training.csv'][(d, endpoint)] for d in p['training_drugs']}
        fits = core.Fits(cf)
        selected, candidates, folds, train = select_training(cf, curves, p['training_drugs'], fits)
        models = {'fixed50': fits.get(train, 'fixed50')}
        if selected['rule'] != 'none':
            models[selected['rule']] = fits.get(train, selected['rule'])
        model_hashes = {}
        for rule, model in models.items():
            name = f'model_{endpoint}_{rule}.joblib'
            require(not (out/name).exists(), f'output already exists: {name}')
            joblib.dump(model, out/name)
            model_hashes[rule] = core.sha(out/name)
            artifact_names.append(name)
        selection_rows.append(dict(endpoint=endpoint, selected_at=core.now(), selected=selected,
                                   candidates=candidates, inner_folds=folds, final_training_rows=core.row_count(train),
                                   models=model_hashes))
        fit_audit.extend(dict(endpoint=endpoint, **r) for r in fits.audit)
        models_by_endpoint[endpoint] = (models, selected, model_hashes)
        # Inner fitted estimators can be released; only the final endpoint models survive.
        fits.cache.clear()
    save(out/'selection.json', dict(protocol_sha256=PROTOCOL_SHA, endpoints=selection_rows))
    save(out/'fit_audit.json', fit_audit)
    artifact_names += ['selection.json','fit_audit.json']
    eps, scales, cal_rows = {}, {}, []
    for endpoint in p['endpoints']:
        train_values = [abs(float(r['value'])) for r in data['training.csv'] if r['endpoint'] == endpoint]
        eps[endpoint] = max(1e-12, 1e-6*float(np.median(train_values)))
        models, selected, _ = models_by_endpoint[endpoint]
        for drug in p['calibration_drugs']:
            rows = gg['calibration.csv'][(drug, endpoint)]
            observed = context_rows(rows)
            observed_keys = {key(r) for r in observed}
            queries = [r for r in rows if key(r) not in observed_keys]
            preds = predict_candidates(cf, observed, queries, models)
            scale = max(abs(float(observed[0]['value'])), eps[endpoint])
            for method, candidate in [('selected',selected['id']),('fixed50','fixed50_a1'),('interpolation','interpolation')]:
                for row, value in zip(queries, preds[candidate]):
                    error = abs(float(value)-float(row['value']))
                    cal_rows.append(dict(compound=drug, endpoint=endpoint, point_id=row['point_id'], method=method,
                                         prediction=float(value), reference=float(row['value']), scale=scale,
                                         absolute_error=error, normalized_error=error/scale))
    calibration = dict(coverage=0.9, n_drugs=9, quantile_rank=9, eps=eps, methods={})
    for method in METHODS:
        scores = {d: max(r['normalized_error'] for r in cal_rows if r['compound']==d and r['method']==method)
                  for d in p['calibration_drugs']}
        require(len(scores)==9, 'nine calibration drug scores required')
        calibration['methods'][method] = dict(drug_scores=scores, q=sorted(scores.values())[8])
    save(out/'calibration.json', calibration)
    table(out/'calibration_predictions.csv', cal_rows)
    artifact_names += ['calibration.json','calibration_predictions.csv']
    predictions, choices = [], []
    for endpoint in p['endpoints']:
        models, selected, model_hashes = models_by_endpoint[endpoint]
        for drug in p['test_drugs']:
            observed = gg['test_contexts.csv'][(drug, endpoint)]
            queries = [r for r in gg['test_dose_metadata.csv'][(drug, endpoint)]
                       if r['is_context'].lower() in ('false','0')]
            preds = predict_candidates(cf, observed, queries, models)
            context_ids = '|'.join(r['point_id'] for r in observed)
            scale = max(abs(float(observed[0]['value'])), eps[endpoint])
            for method, candidate in [('selected',selected['id']),('fixed50','fixed50_a1'),('interpolation','interpolation')]:
                halfwidth = calibration['methods'][method]['q']*scale
                method_rows = []
                for row, value in zip(queries, preds[candidate]):
                    rec = {k:row[k] for k in KEY}
                    rule = selected['rule'] if method == 'selected' else 'fixed50' if method == 'fixed50' else 'none'
                    rec.update(point_id=row['point_id'], curve_id=row['curve_id'], value_unit=row['value_unit'],
                               method=method, candidate=candidate, prediction=float(value), lower=float(value-halfwidth),
                               upper=float(value+halfwidth), context_point_ids=context_ids,
                               model_hash=model_hashes.get(rule, p['model_source_sha256']), protocol_hash=PROTOCOL_SHA)
                    method_rows.append(rec)
                predictions.extend(method_rows)
                choices.append(dict(dataset=p['source'], compound=drug, endpoint=endpoint, method=method,
                                    context_point_ids=context_ids, **action(observed, method_rows)))
    table(out/'predictions.csv', predictions)
    table(out/'choices.csv', choices)
    artifact_names += ['predictions.csv','choices.csv']
    require(report['files'] == {name:core.sha(packet/name) for name in PACKET_FILES}, 'packet changed during prediction')
    require(core.rss() < 4_000_000_000, '4 GB measured RSS exceeded')
    manifest = dict(status='predictions_sealed', sealed_at=core.now(), protocol_sha256=PROTOCOL_SHA,
                    evidence_kind=receipt['evidence_kind'], source_owner=receipt['owner_session'],
                    reference_commitment_sha256=report['files']['reference_commitment.json'],
                    input_files=report['files'], code=implementation_hashes(),
                    artifacts={name:core.sha(out/name) for name in artifact_names},
                    test_drugs=p['test_drugs'], endpoints=p['endpoints'], test_curves=12,
                    prediction_rows=len(predictions), action_rows=len(choices), model_fits=len(fit_audit),
                    seconds=time.monotonic()-start, peak_rss_bytes=core.rss(),
                    versions={'numpy':np.__version__, 'sklearn':core.sklearn.__version__},
                    reference_opened=False)
    require(instant(commitment['sealed_at']) <= instant(manifest['sealed_at']), 'reference commitment postdates predictions')
    save(out/'prediction_manifest.json', manifest)
    return dict(status=manifest['status'], manifest_sha256=core.sha(out/'prediction_manifest.json'),
                prediction_rows=len(predictions), action_rows=len(choices), seconds=manifest['seconds'],
                peak_rss_bytes=manifest['peak_rss_bytes'], reference_opened=False)


def reveal_permission(packet, p, out, receipt_path):
    """This function has no reference-path parameter and cannot read references."""
    manifest = read_json(out/'prediction_manifest.json')
    require(manifest['status'] == 'predictions_sealed', 'sealed predictions required')
    require(manifest['protocol_sha256'] == PROTOCOL_SHA, 'sealed protocol mismatch')
    require(manifest['code'] == implementation_hashes(), 'implementation changed after prediction; explicit version reconciliation required')
    for name, digest in manifest['artifacts'].items():
        require(core.sha(out/name) == digest, f'sealed artifact hash mismatch: {name}')
    for name, digest in manifest['input_files'].items():
        require(core.sha(packet/name) == digest, f'sealed packet hash mismatch: {name}')
    commitment = read_commitment(packet/'reference_commitment.json')
    receipt = read_json(receipt_path)
    for field, expected in [('prediction_manifest_sha256',core.sha(out/'prediction_manifest.json')),
                            ('predictions_sha256',manifest['artifacts']['predictions.csv']),
                            ('choices_sha256',manifest['artifacts']['choices.csv']),
                            ('reference_commitment_sha256',manifest['reference_commitment_sha256']),
                            ('reference_sha256',commitment['reference_sha256']),
                            ('owner_session',manifest['source_owner'])]:
        require(receipt.get(field) == expected, f'reveal receipt mismatch: {field}')
    require(receipt.get('status') == 'released_after_prediction_seal', 'custodian release status missing')
    require(instant(manifest['sealed_at']) <= instant(receipt['received_prediction_at']) <= instant(receipt['released_at'])
            <= datetime.now(timezone.utc), 'reveal chronology invalid')
    return manifest, commitment, receipt


def score(packet, p, out, reference, receipt_path):
    manifest, commitment, receipt = reveal_permission(packet, p, out, receipt_path)
    # First access to any full test reference occurs below, after permission above.
    require(core.sha(reference) == commitment['reference_sha256'], 'revealed reference differs from pre-prediction commitment')
    refs = csv_rows(reference)
    require(len(refs)==commitment['rows'] and keys_hash(refs)==commitment['keys_sha256'], 'revealed reference key set differs')
    reference_index = {key(r):r for r in refs}
    require(len(reference_index)==len(refs), 'duplicate reference key')
    missing_responses = []
    for row in refs:
        try:
            require(math.isfinite(float(row['value'])), 'nonfinite')
        except (ValueError, TypeError):
            missing_responses.append(row['point_id'])
    require(not missing_responses, f'missing/nonfinite reference responses: {missing_responses}')
    contexts = csv_rows(packet/'test_contexts.csv')
    for row in contexts:
        require(reference_index[key(row)]['point_id']==row['point_id'] and
                float(reference_index[key(row)]['value'])==float(row['value']), 'revealed context differs from observed context')
    with (out/'predictions.csv').open() as f:
        predictions = list(csv.DictReader(f))
    with (out/'choices.csv').open() as f:
        choices = list(csv.DictReader(f))
    scored, curve_scores = [], []
    for row in predictions:
        ref = reference_index[key(row)]
        require(ref['point_id']==row['point_id'], 'revealed point ID mismatch')
        value = float(ref['value'])
        scored.append(dict(**row, reference=value, absolute_error=abs(float(row['prediction'])-value),
                           covered=float(row['lower']) <= value <= float(row['upper'])))
    reference_curves = group(refs)
    for choice in choices:
        drug, endpoint, method = (choice[k] for k in ('compound','endpoint','method'))
        rows = [r for r in scored if (r['compound'],r['endpoint'],r['method'])==(drug,endpoint,method)]
        require(bool(rows), f'empty scored curve: {drug}/{endpoint}/{method}')
        truth_reduction = any(float(r['value']) <= float(choice['threshold']) for r in reference_curves[(drug,endpoint)])
        reported = choice['decision'] != 'measure_next'
        wrong = reported and ((choice['decision']=='report_reduction') != truth_reduction)
        nxt = next(r for r in rows if r['point_id']==choice['next_point_id'])
        curve_scores.append(dict(compound=drug,endpoint=endpoint,method=method,n_query=len(rows),
                                 mae=float(np.mean([r['absolute_error'] for r in rows])),
                                 curve_covered=all(r['covered'] for r in rows), decision=choice['decision'],
                                 truth_reduction=truth_reduction, reported=reported, wrong_report=wrong,
                                 next_point_id=nxt['point_id'], next_absolute_error=nxt['absolute_error']))
    require(len(curve_scores)==36, 'expected 12 test curves for each of three methods')
    summaries, paired, coverage = [], [], []
    for endpoint in p['endpoints']:
        for method in METHODS:
            rr=[r for r in curve_scores if r['endpoint']==endpoint and r['method']==method]
            n_report=sum(r['reported'] for r in rr)
            wrong=sum(r['wrong_report'] for r in rr)
            summaries.append(dict(endpoint=endpoint,method=method,n_drugs=len(rr),
                                  mae=float(np.mean([r['mae'] for r in rr])), decisions=dict(Counter(r['decision'] for r in rr)),
                                  wrong_reports=wrong,reported=n_report,wrong_per_all=wrong/len(rr),
                                  wrong_per_reported=wrong/n_report if n_report else None,
                                  mean_next_absolute_error=float(np.mean([r['next_absolute_error'] for r in rr]))))
        for other in ('fixed50','interpolation'):
            diffs={d:next(r['mae'] for r in curve_scores if (r['compound'],r['endpoint'],r['method'])==(d,endpoint,'selected'))-
                     next(r['mae'] for r in curve_scores if (r['compound'],r['endpoint'],r['method'])==(d,endpoint,other))
                   for d in p['test_drugs']}
            paired.append(dict(endpoint=endpoint,contrast='selected_minus_'+other,drug_differences=diffs,
                               mean_difference=float(np.mean(list(diffs.values())))))
    for method in METHODS:
        by_drug={d:all(r['curve_covered'] for r in curve_scores if r['compound']==d and r['method']==method) for d in p['test_drugs']}
        coverage.append(dict(method=method,drug_simultaneous_coverage=by_drug,fraction=sum(by_drug.values())/6))
    table(out/'scored_predictions.csv',scored)
    table(out/'scores_by_curve.csv',curve_scores)
    result=dict(status='scored_after_custodian_release',scored_at=core.now(),evidence_kind=manifest['evidence_kind'],
                n_test_drugs=6,n_test_curves=12,summary=summaries,paired=paired,coverage=coverage,
                prediction_manifest_sha256=core.sha(out/'prediction_manifest.json'),
                reveal_receipt_sha256=core.sha(receipt_path),reference_sha256=core.sha(reference),
                files={name:core.sha(out/name) for name in ('scored_predictions.csv','scores_by_curve.csv')})
    save(out/'scores.json',result)
    return dict(status=result['status'],n_test_drugs=6,n_test_curves=12,evidence_kind=manifest['evidence_kind'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['validate','probe','predict','score'])
    parser.add_argument('--protocol',type=Path,required=True)
    parser.add_argument('--packet',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--reference',type=Path)
    parser.add_argument('--reveal-receipt',type=Path)
    args=parser.parse_args()
    signal.alarm(295)
    args.out.mkdir(parents=True,exist_ok=True)
    try:
        p=protocol(args.protocol)
        if args.command=='validate':
            report,*_=validate(args.packet,p)
            save_validation(args.out,report)
            print(json.dumps({k:report[k] for k in ('status','missing_files','issues','actual_curves')},ensure_ascii=False))
            return 0 if report['status']=='qualified' else 2
        if args.command=='score':
            require(args.reference is not None and args.reveal_receipt is not None,'score requires --reference and --reveal-receipt')
            result=score(args.packet,p,args.out,args.reference,args.reveal_receipt)
        else:
            require(args.reference is None and args.reveal_receipt is None,'reference arguments belong to the score command only')
            result=globals()[args.command](args.packet,p,args.out)
        print(json.dumps(result,ensure_ascii=False))
        return 0
    except (ValueError,KeyError,OSError) as exc:
        print(json.dumps({'status':'error','error':str(exc)},ensure_ascii=False),file=sys.stderr)
        return 2


if __name__=='__main__':
    sys.exit(main())

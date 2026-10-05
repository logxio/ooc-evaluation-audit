#!/usr/bin/env python3
"""Independently reconcile sealed Bircsak predictions with the authorized reveal.

Reads existing predictions only. Uses no estimator, fitting, candidate selection,
or model loading. Writes an audit receipt and reviewer-friendly result tables.
"""
import argparse
import csv
import hashlib
import json
import math
import resource
import signal
import statistics
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

METHODS = ('selected', 'fixed50', 'interpolation')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


REDACTIONS = Path(__file__).resolve().with_name('results') / 'REDACTIONS.json'


def frozen_sha(path):
    """Hash cited by the sealed records; a published copy listed in results/REDACTIONS.json counts
    only when its SHA-256 equals the listed redacted hash."""
    actual = sha(path)
    if REDACTIONS.exists():
        for item in js(REDACTIONS)['files']:
            if item['redacted_sha256'] == actual and Path(item['path']).name == path.name:
                return item['original_sha256']
    return actual


def js(path):
    return json.loads(path.read_text())


def csvread(path):
    with path.open(newline='') as f:
        return list(csv.DictReader(f))


def close(a, b):
    assert math.isclose(float(a), float(b), rel_tol=1e-12, abs_tol=1e-10), (a, b)


def write_table(path, rows):
    assert rows
    with path.open('x', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def audit(run, packet):
    started = time.monotonic()
    manifest = js(run/'prediction_manifest.json')
    protocol = js(run.parent/'independent_protocol.json')
    scores = js(run/'scores.json')
    receipt = js(packet/'reveal_receipt.json')
    assert receipt['prediction_manifest_sha256'] == sha(run/'prediction_manifest.json') == scores['prediction_manifest_sha256']
    assert receipt['status'] == 'released_after_prediction_seal'
    assert frozen_sha(packet/'reveal_receipt.json') == scores['reveal_receipt_sha256']
    assert datetime.fromisoformat(manifest['sealed_at']) <= datetime.fromisoformat(receipt['received_prediction_at'])
    assert datetime.fromisoformat(receipt['received_prediction_at']) <= datetime.fromisoformat(receipt['released_at'])
    assert datetime.fromisoformat(receipt['released_at']) < datetime.fromisoformat(scores['scored_at'])
    for name, digest in manifest['artifacts'].items():
        assert frozen_sha(run/name) == digest, name
    for name, digest in manifest['input_files'].items():
        assert frozen_sha(packet/name) == digest, name
    for name, digest in scores['files'].items():
        assert frozen_sha(run/name) == digest, name
    assert frozen_sha(Path(__file__).with_name('paper_capacity_independent.py')) == manifest['code']['runner']
    assert sha(Path(__file__).with_name('paper_capacity.py')) == manifest['code']['capacity_core']
    assert sha(run.parent/'independent_protocol.json') == manifest['protocol_sha256']
    assert sha(packet/'reference_reveal.csv') == receipt['reference_sha256'] == scores['reference_sha256']
    reference = csvread(packet/'reference_reveal.csv')
    refs = {r['point_id']: r for r in reference}
    assert len(refs) == len(reference) == 82
    assert all(math.isfinite(float(r['value'])) for r in reference)
    contexts = csvread(packet/'test_contexts.csv')
    metadata = csvread(packet/'test_dose_metadata.csv')
    assert len(metadata) == 82 and len(contexts) == 36
    assert {r['point_id'] for r in metadata} == set(refs)
    context_ids = {r['point_id'] for r in contexts}
    query_ids = set(refs)-context_ids
    assert len(query_ids) == 46
    assert context_ids == {r['point_id'] for r in metadata if r['is_context'].lower() in ('true','1')}
    for r in contexts:
        assert r['value'] == refs[r['point_id']]['value'], r['point_id']
    predictions = csvread(run/'predictions.csv')
    choices = csvread(run/'choices.csv')
    point_scores = csvread(run/'scored_predictions.csv')
    curve_scores = csvread(run/'scores_by_curve.csv')
    assert len(predictions) == len(point_scores) == 138
    assert len(choices) == len(curve_scores) == 36
    assert {(r['point_id'],r['method']) for r in predictions} == {(pid,m) for pid in query_ids for m in METHODS}
    expected_curves = {(d,e,m) for d in protocol['test_drugs'] for e in protocol['endpoints'] for m in METHODS}
    assert {(r['compound'],r['endpoint'],r['method']) for r in choices} == expected_curves
    assert {(r['compound'],r['endpoint'],r['method']) for r in curve_scores} == expected_curves
    point_index = {(r['point_id'],r['method']): r for r in point_scores}
    choice_index = {(r['compound'],r['endpoint'],r['method']): r for r in choices}
    derived, misses = {}, []
    for prediction in predictions:
        pid, method = prediction['point_id'], prediction['method']
        ref = refs[pid]
        observed = point_index[(pid,method)]
        for field in ('dataset','compound','endpoint','configuration','time','concentration','concentration_unit','curve_id','value_unit'):
            assert prediction[field] == ref[field], (pid,field)
        for field, value in prediction.items():
            assert observed[field] == value, (pid,field)
        y = float(ref['value'])
        err = abs(float(prediction['prediction'])-y)
        covered = float(prediction['lower']) <= y <= float(prediction['upper'])
        close(observed['reference'], y)
        close(observed['absolute_error'], err)
        assert (observed['covered']=='True') == covered
        derived[(pid,method)] = dict(error=err,covered=covered,width=float(prediction['upper'])-float(prediction['lower']))
        if not covered:
            misses.append(dict(compound=ref['compound'],endpoint=ref['endpoint'],method=method,
                               concentration=ref['concentration'],concentration_unit=ref['concentration_unit'],
                               prediction=prediction['prediction'],lower=prediction['lower'],upper=prediction['upper'],
                               reference=y,error_abs=ref['error_abs'],point_id=pid,
                               distance_outside_interval=max(float(prediction['lower'])-y,y-float(prediction['upper']),0)))
    by_curve = {}
    for r in curve_scores:
        k = (r['compound'],r['endpoint'],r['method'])
        points = [p for p in predictions if (p['compound'],p['endpoint'],p['method']) == k]
        assert len(points) == int(r['n_query'])
        errors = [derived[(p['point_id'],k[2])]['error'] for p in points]
        covered = all(derived[(p['point_id'],k[2])]['covered'] for p in points)
        close(r['mae'], statistics.mean(errors))
        assert (r['curve_covered']=='True') == covered
        choice = choice_index[k]
        next_pid = choice['next_point_id']
        assert next_pid in {p['point_id'] for p in points}
        close(r['next_absolute_error'], derived[(next_pid,k[2])]['error'])
        truth = any(float(x['value']) <= float(choice['threshold']) for x in reference
                    if (x['compound'],x['endpoint']) == k[:2])
        assert (r['truth_reduction']=='True') == truth
        assert r['decision'] == choice['decision']
        reported = choice['decision'] in ('report_reduction','report_no_reduction')
        wrong = reported and (truth != (choice['decision']=='report_reduction'))
        assert (r['reported']=='True') == reported and (r['wrong_report']=='True') == wrong
        by_curve[k] = dict(mae=statistics.mean(errors),covered=covered,reported=reported,wrong=wrong,
                           next_error=derived[(next_pid,k[2])]['error'],truth=truth,decision=choice['decision'],
                           next_concentration=choice['next_concentration'],next_point_id=next_pid)
    for summary in scores['summary']:
        rr = [by_curve[(d,summary['endpoint'],summary['method'])] for d in protocol['test_drugs']]
        close(summary['mae'],statistics.mean(r['mae'] for r in rr))
        close(summary['mean_next_absolute_error'],statistics.mean(r['next_error'] for r in rr))
        assert summary['decisions'] == dict(Counter(r['decision'] for r in rr))
        assert summary['reported'] == sum(r['reported'] for r in rr)
        assert summary['wrong_reports'] == sum(r['wrong'] for r in rr)
        close(summary['wrong_per_all'],sum(r['wrong'] for r in rr)/6)
        if not summary['reported']:
            assert summary['wrong_per_reported'] is None
    for contrast in scores['paired']:
        other = contrast['contrast'].removeprefix('selected_minus_')
        for drug, difference in contrast['drug_differences'].items():
            close(difference,by_curve[(drug,contrast['endpoint'],'selected')]['mae']-by_curve[(drug,contrast['endpoint'],other)]['mae'])
        close(contrast['mean_difference'],statistics.mean(contrast['drug_differences'].values()))
    for coverage in scores['coverage']:
        actual = {d:all(by_curve[(d,e,coverage['method'])]['covered'] for e in protocol['endpoints']) for d in protocol['test_drugs']}
        assert actual == coverage['drug_simultaneous_coverage']
        close(coverage['fraction'],sum(actual.values())/6)
    wide = []
    for endpoint in protocol['endpoints']:
        for drug in protocol['test_drugs']:
            r0 = next(r for r in reference if r['compound']==drug and r['endpoint']==endpoint)
            row = dict(compound=drug,endpoint=endpoint,value_unit=r0['value_unit'])
            for method in METHODS:
                r = by_curve[(drug,endpoint,method)]
                for field in ('mae','covered','decision','next_concentration','next_error'):
                    row[method+'_'+field] = r[field]
            row['selected_minus_interpolation'] = row['selected_mae']-row['interpolation_mae']
            row['selected_minus_fixed50'] = row['selected_mae']-row['fixed50_mae']
            row['truth_reduction'] = by_curve[(drug,endpoint,'selected')]['truth']
            wide.append(row)
    intervals = []
    cal = js(run/'calibration.json')
    for endpoint in protocol['endpoints']:
        for method in METHODS:
            pp = [r for r in predictions if r['endpoint']==endpoint and r['method']==method]
            widths = [derived[(r['point_id'],method)]['width'] for r in pp]
            # Give each curve equal weight, matching the drug-macro target.
            curve_widths = [statistics.mean(derived[(r['point_id'],method)]['width'] for r in pp if r['compound']==d)
                            for d in protocol['test_drugs']]
            intervals.append(dict(endpoint=endpoint,method=method,value_unit=pp[0]['value_unit'],nominal_coverage=0.9,
                                  calibration_drugs=9,quantile_rank=9,q=cal['methods'][method]['q'],
                                  full_width_per_context_scale=2*cal['methods'][method]['q'],
                                  mean_width=statistics.mean(curve_widths),min_width=min(widths),max_width=max(widths),
                                  points_covered=sum(derived[(r['point_id'],method)]['covered'] for r in pp),point_total=len(pp),
                                  curves_covered=sum(by_curve[(d,endpoint,method)]['covered'] for d in protocol['test_drugs']),curve_total=6,
                                  lower_below_zero=sum(float(r['lower'])<0 for r in pp),
                                  upper_above_100=sum(float(r['upper'])>100 for r in pp) if endpoint=='VIABILITY' else None))
    contrasts=[]
    for entry in scores['paired']:
        other=entry['contrast'].removeprefix('selected_minus_')
        baseline=next(s['mae'] for s in scores['summary'] if s['endpoint']==entry['endpoint'] and s['method']==other)
        deltas=list(entry['drug_differences'].values())
        contrasts.append(dict(endpoint=entry['endpoint'],contrast=entry['contrast'],mean_difference=entry['mean_difference'],
                              relative_mae_change_pct=100*entry['mean_difference']/baseline,
                              improved=sum(x < -1e-10 for x in deltas),equal=sum(abs(x)<=1e-10 for x in deltas),
                              worsened=sum(x > 1e-10 for x in deltas),n_drugs=6))
    for filename,rows in [('drug_endpoint_results.csv',wide),('interval_summary.csv',intervals),('paired_summary.csv',contrasts)]:
        write_table(run/filename,rows)
    if misses:
        write_table(run/'interval_misses.csv',misses)
    result=dict(status='passed',audit_kind='independent point-id reconciliation from authorized revealed references',
                n_reference_rows=82,n_observed_rows=36,n_hidden_query_points=46,n_methods=3,n_test_drugs=6,n_test_curves=12,
                n_scored_points=138,n_scored_curve_methods=36,missing_response_rows=0,excluded_rows=0,
                frozen_predictions_choices_selection_calibration_code_unchanged=True,
                per_point_errors_verified=True,per_drug_macro_errors_verified=True,coverage_verified=True,
                decisions_and_report_denominators_verified=True,next_point_errors_verified=True,
                interval_misses=len(misses),all_methods_same_next_dose=all(len({by_curve[(d,e,m)]['next_point_id'] for m in METHODS})==1
                                                                        for d in protocol['test_drugs'] for e in protocol['endpoints']),
                all_next_doses_highest_registered=all(float(by_curve[(d,e,m)]['next_concentration'])==
                  max(float(r['concentration']) for r in reference if r['compound']==d and r['endpoint']==e)
                  for d in protocol['test_drugs'] for e in protocol['endpoints'] for m in METHODS),
                seconds=time.monotonic()-started,peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=='darwin' else 1024),
                model_fits=0,code_fixes=0,scores_sha256=sha(run/'scores.json'),auditor_sha256=sha(Path(__file__)),
                reference_sha256=sha(packet/'reference_reveal.csv'),prediction_manifest_sha256=sha(run/'prediction_manifest.json'),
                derived_files={name:sha(run/name) for name in ('drug_endpoint_results.csv','interval_summary.csv','paired_summary.csv')})
    if misses:
        result['derived_files']['interval_misses.csv']=sha(run/'interval_misses.csv')
    with (run/'score_audit.json').open('x') as f:
        json.dump(result,f,ensure_ascii=False,indent=2,allow_nan=False)
        f.write('\n')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--packet',type=Path,required=True)
    args=parser.parse_args()
    signal.alarm(295)
    print(json.dumps(audit(args.run,args.packet),ensure_ascii=False))


if __name__=='__main__':
    main()

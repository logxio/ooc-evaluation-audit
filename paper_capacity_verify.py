#!/usr/bin/env python3
"""Verify the frozen capacity run and reconcile legacy float32 MAE arithmetic.

The evaluator and its frozen protocol remain byte-for-byte unchanged. This
verification-only addendum distinguishes prediction identity from the legacy
float32 subtraction/reduction used for interpolation.
"""
import argparse
import csv
import json
import signal
from collections import defaultdict
from pathlib import Path

import paper_capacity as pc
import numpy as np


def main():
    a = argparse.ArgumentParser(description=__doc__)
    a.add_argument('--out', type=Path, required=True)
    a.add_argument('--inputs', type=Path, help='folder holding runs/chip-evidence-s1/expand; default is the original working-tree layout')
    args = a.parse_args()
    out = args.out
    if args.inputs:
        # Relocate the frozen evaluator's input root; every input SHA-256 is still checked.
        pc.ROOT = args.inputs.resolve()
        pc.EXP = pc.ROOT / 'runs/chip-evidence-s1/expand'
        pc.MODEL = Path(pc.__file__).resolve().parent / 'benchmarks/ooc/raw/chip_forecast.py'
    signal.alarm(295)
    p = pc.checked_protocol(out)
    summary = json.loads((out/'summary.json').read_text())
    pp = list(csv.DictReader((out/'outer_predictions.csv').open()))
    ff = list(csv.DictReader((out/'outer_drugs.csv').open()))
    legacy = list(csv.DictReader((pc.EXP/'folds.csv').open()))
    assert pc.sha(pc.EXP/'folds.csv') == p['source_legacy_folds_sha256']
    assert len(ff)==27 and len({r['compound'] for r in ff})==11
    assert summary['predictions_before_scoring_sha256']==pc.sha(out/'predictions_before_scoring.csv')
    max_fixed50 = max_raw_ll = max_reconciled_ll = 0.
    precision = []
    for f in ff:
        def same(r):
            return all(r[k]==f[k] for k in ['dataset','endpoint','compound'])
        old = next(r for r in legacy if same(r))
        max_fixed50 = max(max_fixed50, abs(float(f['fixed50_mae'])-float(old['frozen'])))
        max_raw_ll = max(max_raw_ll, abs(float(f['loglinear_mae'])-float(old['loglinear'])))
        for method in ['selected','fixed50','loglinear']:
            rows = [r for r in pp if same(r) and r['method']==method]
            dd = defaultdict(list)
            for r in rows:
                assert abs(abs(float(r['prediction'])-float(r['target']))-float(r['absolute_error']))<1e-12
                dd[r['design']].append(r)
            value = np.mean([np.mean([float(r['absolute_error']) for r in e]) for e in dd.values()])
            assert abs(value-float(f[method+'_mae']))<1e-12
            if method == 'loglinear':
                legacy_value = float(np.mean([float(np.abs(
                    np.array([float(r['prediction']) for r in e], np.float32)-
                    np.array([float(r['target']) for r in e], np.float32)).mean()) for e in dd.values()]))
                residual = abs(legacy_value-float(old['loglinear']))
                max_reconciled_ll=max(max_reconciled_ll,residual)
                precision.append(dict(dataset=f['dataset'],endpoint=f['endpoint'],compound=f['compound'],
                    current_float64_mae=value, original_float32_mae=float(old['loglinear']),
                    reconstructed_float32_mae=legacy_value, residual=residual))
    # No relaxed tolerance: the original arithmetic must reproduce exactly.
    assert max_fixed50 == 0.0
    assert max_reconciled_ll == 0.0
    sels = [json.loads(line) for line in (out/'selection_before_test.jsonl').read_text().splitlines()]
    assert len(sels)==27
    for s in sels:
        assert s['outer_test_drug'] not in s['outer_training_drugs']
        assert len(s['candidates'])==13
        for inner in s['inner_folds']:
            assert s['outer_test_drug'] not in inner['inner_training_drugs']+[inner['inner_validation_drug']]
            assert inner['inner_validation_drug'] not in inner['inner_training_drugs']
            assert set(inner['inner_training_drugs']+[inner['inner_validation_drug']])==set(s['outer_training_drugs'])
        for candidate in s['candidates']:
            mean=np.mean([r['candidate_drug_mae'][candidate['id']] for r in s['inner_folds']])
            assert abs(mean-candidate['inner_mean_drug_mae'])<1e-12
        best=min(c['inner_mean_drug_mae'] for c in s['candidates'])
        assert s['selected']==next(c for c in s['candidates'] if c['inner_mean_drug_mae']<=best+1e-12)
        assert all(s['selected_at']<r['predicted_at'] for r in pp if r['dataset']==s['dataset'] and r['endpoint']==s['endpoint'] and r['compound']==s['outer_test_drug'])
    for s in summary['summary']:
        rows=[r for r in ff if r['dataset']==s['dataset'] and r['endpoint']==s['endpoint']]
        for method in ['selected','fixed50','loglinear']:
            assert abs(np.mean([float(r[method+'_mae']) for r in rows])-s['mae'][method])<1e-12
        for c in s['comparisons']:
            a,b=c.split('_minus_')
            result=pc.paired([float(r[a+'_mae']) for r in rows],[float(r[b+'_mae']) for r in rows])
            for key,value in result.items():
                assert value==s['comparisons'][c][key]
    cf=pc.load_cf()
    input_checks=[]
    for cell in p['primary_endpoints']:
        for t in pc.load_tasks(cf,p,cell)[0]:
            for ix,ctx in enumerate(pc.contexts(t,cell)):
                obs=pc.observed_task(cf,t,ctx)
                poison=t.y.copy()
                poison[~np.isin(t.logc,ctx)]=1e8
                changed=cf.Task(t.chem,t.fold,t.label,t.logc,poison,t.m)
                assert np.array_equal(obs.y,pc.observed_task(cf,changed,ctx).y)
                q=t.levels[~np.isin(t.levels,ctx)]
                pred=cf.predict_interp(obs,np.ones(len(obs.y),bool),q).ravel()
                for j,dose in enumerate(q):
                    saved=next(r for r in pp if r['dataset']==cell['dataset'] and r['endpoint']==cell['endpoint'] and r['compound']==t.chem and int(r['design'])==ix and float(r['query_log10'])==float(dose) and r['method']=='loglinear')
                    assert float(pred[j])==float(saved['prediction'])
            input_checks.append([cell['dataset'],cell['endpoint'],t.chem])
    pc.dump(out/'precision_reconciliation.json',dict(
        cause='Legacy interpolation error subtraction and query reduction use float32; current saved point errors use float64. Predictions match exactly.',
        initial_verifier_failure='AssertionError: 1.3987223326239473e-06 at max_legacy < 1e-9',
        original_evaluator_and_protocol_unchanged=True, candidate_or_model_changes=0, reruns=0,
        max_current_vs_legacy_interpolation_mae=max_raw_ll, max_fixed50_difference=max_fixed50,
        max_after_restoring_original_float32_arithmetic=max_reconciled_ll, rows=precision))
    pc.dump(out/'verification.json',dict(status='pass', checked_at=pc.now(), outer_folds=27,
        candidates_per_fold=13, legacy_fixed50_max_absolute_difference=max_fixed50,
        interpolation_prediction_difference=0.0, legacy_interpolation_arithmetic_max_difference=max_reconciled_ll,
        nested_drug_disjointness=True, candidate_scores_recomputed=True, all_point_and_drug_metrics_recomputed=True,
        hidden_target_perturbation_passed=len(input_checks), selections_before_predictions=True,
        original_strict_verifier='failed on explained interpolation float32/float64 aggregation; retained unchanged',
        files={name:pc.sha(out/name) for name in ['protocol.json','summary.json','selection_before_test.jsonl','fit_audit.json','outer_drugs.csv','outer_predictions.csv','predictions_before_scoring.csv','key_audit.json','precision_reconciliation.json']},
        verifier_sha256=pc.sha(Path(__file__))))
    print(json.dumps(dict(status='pass',outer_folds=27,fixed50_difference=max_fixed50,
                         interpolation_prediction_difference=0.0,legacy_float32_difference=max_reconciled_ll)))


if __name__=='__main__':
    main()

#!/usr/bin/env python3
"""Independent arithmetic and hidden-response invariance checks for the nested run."""
import argparse
import itertools
import json
import warnings
from pathlib import Path

import joblib
import numpy as np
from sklearn.exceptions import InconsistentVersionWarning

import paper_nested_decision as nd


def row(group, error=False, margin=.5):
    return {'drug_group': group, 'truth': 0, 'anchorboost_call': int(error), 'anchorboost_margin': margin}


def arithmetic():
    small = nd.calibrate([row(str(i)) for i in range(8)], 'anchorboost')
    assert not small['finite_grid_feasible'] and small['margin'] == 1.
    enough = nd.calibrate([row(str(i)) for i in range(9)], 'anchorboost')
    assert enough['finite_grid_feasible'] and enough['margin'] == -1.
    data = [row(str(i), i < 10, .2 if i < 10 else .6) for i in range(99)]
    original = nd.calibrate(data, 'anchorboost')
    assert original['margin'] == .2
    duplicated = nd.calibrate(data + [dict(data[0])] * 50, 'anchorboost')
    assert duplicated['curve'] == original['curve'] or all(
        a['corrected'] == b['corrected'] for a, b in zip(duplicated['curve'], original['curve']))
    # Strict > makes losses right-continuous at the confidence threshold.
    assert original['curve'][21]['margin'] == .2 and original['curve'][21]['loss_sum'] == 0
    # Exhaustive exchangeable leave-one-out risk on a fixed population of loss functions.
    population = [row(str(i), i % 2 == 0, m) for i, m in enumerate([.1, .2, .4, .7, .9])]
    errors = []
    for hold in range(5):
        cert = nd.calibrate([r for i, r in enumerate(population) if i != hold], 'anchorboost', alpha=.3)
        r = population[hold]
        errors.append(r['anchorboost_margin'] > cert['margin'] and r['anchorboost_call'] != r['truth'])
    assert np.mean(errors) <= .3
    conditional_example = [row(str(i), i < 12, .9 if i == 0 else .1) for i in range(20)]
    marginal = nd.calibrate(conditional_example, 'anchorboost')
    accepted = [r for r in conditional_example if r['anchorboost_margin'] > marginal['margin']]
    assert len(accepted) == 1 and accepted[0]['anchorboost_call'] != accepted[0]['truth']
    assert marginal['corrected_risk'] <= .1
    return {'finite_sample_n8_all_fallback': True, 'n9_zero_loss_feasible': True,
            'drug_replication_invariant': True, 'strict_margin_right_continuity': True,
            'exhaustive_exchangeable_toy_risk': float(np.mean(errors)),
            'marginal_control_allows_conditional_error_one': True}


def check_run(out):
    protocol, ids, splits = nd.read_run(out)
    result = arithmetic()
    raw = nd.input_path(protocol, 'raw')
    assert nd.sha(raw) == protocol['inputs']['raw']['sha256']
    for sp in splits.values():
        parts = [{ids[n]['drug_group'] for n in sp[role]} for role in ['train', 'calibration', 'test']]
        assert all(not (a & b) for a, b in itertools.combinations(parts, 2))
    result['all_outer_identity_disjoint'] = True
    completed = []
    for f in range(5):
        folder = out / f'fold{f}'
        if not (folder / 'summary.json').exists():
            continue
        rows = nd.load(folder / 'design_decisions.json')
        saved = nd.load(folder / 'summary.json')
        sp = splits[str(f)]
        outer_runtime = nd.load(folder / 'outer_runtime.json')
        assert sorted(outer_runtime['training_names']) == sorted(sp['train'])
        assert nd.load(folder / 'outer_transform.json')['training_names'] == sorted(sp['train'])
        with warnings.catch_warnings():
            warnings.simplefilter('error', InconsistentVersionWarning)
            fitted_model = joblib.load(folder / 'outer_model.joblib')
        assert fitted_model.model.n_iter_ == 600
        assert len(fitted_model.analog.P) == len(sp['train'])
        assert fitted_model.rows == outer_runtime['training_rows']
        del fitted_model
        pretest = nd.load(folder / 'pretest_freeze.json')
        execution_protocol = folder / 'execution_protocol.json'
        if execution_protocol.exists():
            assert pretest['protocol_sha256'] == nd.frozen_sha(execution_protocol)
            remote_protocol = nd.load(execution_protocol)
            assert remote_protocol.pop('execution_parent_protocol_sha256') == nd.frozen_sha(out / 'protocol.json')
            remote_protocol.pop('execution_path_amendment')
            for name in ['raw', 'legacy_result']:
                remote_protocol['inputs'][name]['path'] = protocol['inputs'][name]['path']
            assert remote_protocol == protocol
        else:
            assert pretest['protocol_sha256'] == nd.frozen_sha(out / 'protocol.json')
        for key, filename in [('rules', 'training_rules.json'), ('calibration', 'calibration.json'),
                              ('model', 'outer_model.joblib'), ('transform', 'outer_transform.json')]:
            assert pretest[key + '_sha256'] == nd.frozen_sha(folder / filename)
        for inner in range(2):
            info = nd.load(folder / f'inner{inner}_runtime.json')
            held = sp['inner'][str(inner)]
            assert set(info['training_names']) == set(sp['train']) - set(held)
            assert not ({ids[n]['drug_group'] for n in held} & {ids[n]['drug_group'] for n in info['training_names']})
        rebuilt = nd.summarize_rows(rows)
        assert saved['methods'] == rebuilt['methods']
        cal = nd.load(folder / 'calibration_design_decisions.json')
        cert = nd.load(folder / 'calibration.json')
        for method in nd.METHODS:
            assert nd.calibrate(cal, method) == cert[method]
            assert cert[method]['calibration_drugs'] == sp['group_counts']['calibration']
        frozen = nd.load(folder / 'test_decisions_frozen.json')
        assert all('truth' not in r for r in frozen)
        assert all({k: v for k, v in r.items() if k != 'truth'} == a for r, a in zip(rows, frozen))
        assert all(r['observed_active_fallback_call'] == r['truth'] for r in rows if r['observed_active_fallback_release'])
        points = np.load(folder / 'test_scored_points.npz')
        assert all(np.isfinite(points[k]).all() for k in ['anchorboost', 'loglinear'])
        completed.append(f)
    result['completed_outer_folds_verified'] = completed
    if (out / 'fold0' / 'outer_model.joblib').exists():
        sp = splits['0']
        frame = nd.raw_frame(raw)
        tr = nd.load(out / 'fold0' / 'outer_transform.json')
        task = nd.make_tasks(frame, sp['test'][:1], ids, tr)[0]
        model = joblib.load(out / 'fold0' / 'outer_model.joblib')
        # Deliberately destroy every held-out response and mask for one fixed design.
        ctx = nd.cf.designs(task, 3)[0]
        observed = np.isin(task.logc, ctx)
        rows_before, before = nd.forecast(model, [task], 0, 'invariance_check')
        corrupt_y, corrupt_m = task.y.copy(), task.m.copy()
        corrupt_y[~observed] = 1e6
        corrupt_m[~observed] = False
        altered = nd.cf.Task(task.chem, task.fold, 'unused', task.logc, corrupt_y, corrupt_m)
        altered.group = task.group
        rows_after, after = nd.forecast(model, [altered], 0, 'invariance_check')
        assert rows_before[0] == rows_after[0]
        select = before['design'] == 0
        for method in ['anchorboost', 'loglinear']:
            assert np.array_equal(before[method][select], after[method][select])
        result['hidden_target_value_and_mask_invariance'] = True
        result['hidden_target_max_prediction_change'] = float(np.max(np.abs(before['anchorboost'][select] - after['anchorboost'][select])))
        # Held-out-only control rows do not enter fit_transform.
        train_batch = set(frame.loc[frame.treatment.isin(sp['train']) & (frame.dose > 0), ['apid.short', 'date']].itertuples(index=False, name=None))
        hold_controls = (frame.dose == 0) & np.array([key not in train_batch for key in frame[['apid.short', 'date']].itertuples(index=False, name=None)])
        tr_before = nd.fit_transform(frame, sp['train'])
        frame.loc[hold_controls, nd.FEATURES] = 1e9
        tr_after = nd.fit_transform(frame, sp['train'])
        assert tr_before == tr_after
        result['heldout_only_control_invariance'] = True
        result['heldout_only_control_rows_perturbed'] = int(hold_controls.sum())
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path)
    a = parser.parse_args()
    result = check_run(a.out) if a.out else arithmetic()
    if a.out:
        nd.dump(a.out / 'verification.json', result)
    print(json.dumps(result, indent=2))

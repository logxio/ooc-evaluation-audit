#!/usr/bin/env python3
"""Split conformal risk control for a frozen two-readout release rule.

Training fixes cutoffs, reference distributions and the threshold family. Only a
separate calibration sample selects the release margin. Every deployed decision
uses the identical fitted model and predict function. Loss is wrong release per
patient, including patients sent to retest in the denominator.
"""
import hashlib
import json
import math

GRID = [-1.0] + [i / 100 for i in range(101)]
GUARANTEE = ("Conditional on independent training, exchangeable calibration and future patients "
             "give expected wrong-release loss per patient <= alpha, averaging over calibration "
             "and the future patient. Error among released patients and a realised batch rate "
             "are reported separately.")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def check_rows(rows, labels=True):
    if not rows:
        raise ValueError('A non-empty patient table is required')
    ids = [r['patient'] for r in rows]
    if len(ids) != len(set(ids)):
        raise ValueError('Use one independent row per patient; duplicate patient IDs were supplied')
    for r in rows:
        if len(r['x']) != 2 or any(not math.isfinite(v) for v in r['x']):
            raise ValueError('Each patient needs two finite readouts')
        if labels and r['y'] not in (0, 1):
            raise ValueError('Outcome must be binary')


def cutoff(values, truth):
    classes = sorted(set(truth))
    ordered = sorted(set(values))
    choices = [ordered[0] - max(1., abs(ordered[0]) * .01)]
    choices += [(a + b) / 2 for a, b in zip(ordered, ordered[1:])]
    choices += [ordered[-1] + max(1., abs(ordered[-1]) * .01)]
    def objective(c):
        return sum(sum(int(x <= c) == y for x, y in zip(values, truth) if y == k) /
                   sum(y == k for y in truth) for k in classes) / len(classes)
    return min(choices, key=lambda c: (-objective(c), c))


def fit(training):
    check_rows(training)
    cols = [[r['x'][j] for r in training] for j in (0, 1)]
    model = {'schema': 'release.model.v2',
             'cutoffs': [cutoff(v, [r['y'] for r in training]) for v in cols],
             'reference': [sorted(v) for v in cols], 'margin_grid': GRID,
             'training_ids': sorted(r['patient'] for r in training),
             'training_sha256': digest(training)}
    model['model_sha256'] = digest(model)
    return model


def predict(model, rows):
    check_rows(rows, labels=False)
    if digest({k: v for k, v in model.items() if k != 'model_sha256'}) != model['model_sha256']:
        raise ValueError('Frozen model hash differs from the saved cutoffs/reference/grid')
    def ecdf(values, x):
        return (sum(v < x for v in values) + .5 * sum(v == x for v in values)) / len(values)
    result = []
    for row in rows:
        calls = [int(v <= c) for v, c in zip(row['x'], model['cutoffs'])]
        margin = min(abs(ecdf(ref, v) - ecdf(ref, c)) for v, c, ref in
                     zip(row['x'], model['cutoffs'], model['reference']))
        result.append({'patient': row['patient'], 'calls': calls, 'agree': calls[0] == calls[1],
                       'margin': margin, 'prediction': calls[0]})
    return result


def calibrate(model, calibration, alpha):
    check_rows(calibration)
    if not 0 < alpha < 1:
        raise ValueError('alpha must be strictly between zero and one')
    if set(model['training_ids']) & {r['patient'] for r in calibration}:
        raise ValueError('Training and calibration patients must be disjoint')
    cases = predict(model, calibration)
    n = len(cases)
    chosen = 1.0
    feasible = False
    for lam in model['margin_grid']:
        e = sum(c['agree'] and c['margin'] > lam and c['prediction'] != r['y']
                for c, r in zip(cases, calibration))
        if (e + 1) / (n + 1) <= alpha:
            chosen, feasible = lam, True
            break
    cert = {'schema': 'release.certificate.v2', 'model': model, 'alpha': alpha,
            'margin': chosen, 'calibration_ids': sorted(r['patient'] for r in calibration),
            'calibration_sha256': digest(calibration), 'calibration_patients': n,
            'finite_grid_feasible': feasible, 'guarantee': GUARANTEE,
            'guarantee_scope': 'expected_overall_wrong_release_under_exchangeability'}
    applied = apply(cert, calibration)
    errors = sum(c['released'] and c['prediction'] != r['y'] for c, r in zip(applied, calibration))
    cert['calibration_released'] = sum(c['released'] for c in applied)
    cert['calibration_wrong'] = errors
    cert['calibration_statistic'] = (errors + 1) / (n + 1)
    cert['fallback'] = 'none' if feasible else 'all_retest'
    return cert


def apply(certificate, rows):
    return [dict(c, released=c['agree'] and c['margin'] > certificate['margin'])
            for c in predict(certificate['model'], rows)]


def measure(certificate, rows, cost=.25):
    check_rows(rows)
    cases = apply(certificate, rows)
    n = len(rows)
    released = sum(c['released'] for c in cases)
    wrong = sum(c['released'] and c['prediction'] != r['y'] for c, r in zip(cases, rows))
    return {'patients': n, 'released': released, 'wrong_released': wrong,
            'released_correct': released - wrong, 'retests': n - released,
            'coverage': released / n, 'overall_wrong_release': wrong / n,
            'released_error_rate': wrong / released if released else None,
            'released_accuracy': 1 - wrong / released if released else None,
            'observed_within_alpha': wrong / n <= certificate['alpha'],
            'conditional_error_within_alpha': wrong / released <= certificate['alpha'] if released else None,
            'loss': (wrong + cost * (n - released)) / n, 'rows': cases}

#!/usr/bin/env python3
"""Training-only rank pooling with shrunk source intercepts for selective release.

Source reference distributions and every coefficient are learned on training
patients only. Calibration and deployment call the same saved score function.
Scores rank confidence; their numeric values are not calibrated probabilities.
"""
import math

from release_calibration import check_rows, digest, fit, predict

GRID = [-1.0] + [i / 200 for i in range(101)]


def rank(reference, x):
    return (sum(v < x for v in reference) + .5 * sum(v == x for v in reference)) / len(reference)


def features(model, source, row):
    ref = model['sources'][source]['reference']
    z = [.5 - rank(ref[j], row['x'][j]) for j in (0, 1)]
    return [1., z[0], z[1], z[0] * z[1], abs(z[0] - z[1])] + [
        float(source == s) for s in model['source_order']]


def sigmoid(value):
    return 1 / (1 + math.exp(-max(-30., min(30., value))))


def fit_pooled(training):
    """Fixed ridge penalties: 2 for shared slopes; 8 for source intercepts."""
    for rows in training.values():
        check_rows(rows)
    model = {'schema': 'release.pooled_signal.v1', 'sources': {},
             'source_order': sorted(training), 'margin_grid': GRID,
             'training_sha256': digest(training), 'iterations': 1500,
             'shared_ridge': 2., 'source_ridge': 8.}
    for source, rows in training.items():
        local = fit(rows)
        calls = predict(local, rows)
        accuracies = [sum(c['calls'][j] == r['y'] for c, r in zip(calls, rows)) / len(rows) for j in (0, 1)]
        model['sources'][source] = {'reference': local['reference'],
                                    'training_ids': local['training_ids'],
                                    'training_sha256': digest(rows),
                                    'fixed_baseline_model': local,
                                    'baseline_channel': max((0, 1), key=lambda j: (accuracies[j], -j))}
    examples = [(features(model, s, r), r['y']) for s, rows in training.items() for r in rows]
    beta = [0.] * (5 + len(training))
    penalties = [.01] + [model['shared_ridge']] * 4 + [model['source_ridge']] * len(training)
    for _ in range(model['iterations']):
        grad = [pen * value for pen, value in zip(penalties, beta)]
        for x, y in examples:
            error = sigmoid(sum(b * v for b, v in zip(beta, x))) - y
            for j, v in enumerate(x):
                grad[j] += error * v
        beta = [b - .5 * g / len(examples) for b, g in zip(beta, grad)]
    model['coefficients'] = beta
    model['model_sha256'] = digest(model)
    return model


def score(model, source, rows, method='pooled'):
    check_rows(rows, labels=False)
    if digest({k: v for k, v in model.items() if k != 'model_sha256'}) != model['model_sha256']:
        raise ValueError('The frozen pooled model hash differs')
    if source not in model['sources']:
        raise ValueError('The source needs an independent training reference before calibration')
    result = []
    local = model['sources'][source]
    for row in rows:
        if method == 'pooled':
            p = sigmoid(sum(b * v for b, v in zip(model['coefficients'], features(model, source, row))))
            prediction, confidence = int(p >= .5), abs(p - .5)
        elif method == 'fixed_single':
            j = local['baseline_channel']
            c = local['fixed_baseline_model']['cutoffs'][j]
            ref = local['reference'][j]
            prediction = int(row['x'][j] <= c)
            confidence = abs(rank(ref, row['x'][j]) - rank(ref, c)) / 2
        else:
            raise ValueError('Unknown scoring method')
        result.append({'patient': row['patient'], 'prediction': prediction, 'margin': confidence})
    return result


def counts(cases, labels, margin):
    truth = {r['patient']: r['y'] for r in labels}
    selected = [c for c in cases if c['margin'] > margin]
    return len(selected), sum(c['prediction'] != truth[c['patient']] for c in selected)


def certify(model, source, training, calibration, alpha=.1, eta=.05 / 3, method='pooled'):
    from conditional_calibration import binomial_cdf, upper_bound
    local = model['sources'][source]
    check_rows(calibration)
    if digest(training) != local['training_sha256']:
        raise ValueError('Training data differ from the frozen model')
    if set(local['training_ids']) & {r['patient'] for r in calibration}:
        raise ValueError('Training and calibration patients overlap')
    cal_cases = score(model, source, calibration, method)
    train_cases = score(model, source, training, method)
    crc_margin = .5
    for margin in GRID:
        _, errors = counts(cal_cases, calibration, margin)
        if (errors + 1) / (len(calibration) + 1) <= alpha:
            crc_margin = margin
            break
    ordering = []
    for margin in GRID[:-1]:
        accepted, errors = counts(train_cases, training, margin)
        ordering.append((upper_bound(errors, accepted, eta), -accepted, margin))
    ordering.sort()
    passed, tests = [], []
    for _, _, margin in ordering:
        accepted, errors = counts(cal_cases, calibration, margin)
        p = binomial_cdf(errors, accepted, alpha) if accepted else 1.
        tests.append({'margin': margin, 'accepted': accepted, 'errors': errors, 'p_value': p})
        if p > eta:
            break
        passed.append(margin)
    return {'schema': 'release.pooled_certificate.v1', 'model_sha256': model['model_sha256'],
            'source': source, 'method': method, 'alpha': alpha, 'eta': eta,
            'calibration_sha256': digest(calibration),
            'calibration_ids': sorted(r['patient'] for r in calibration),
            'overall_margin': crc_margin, 'conditional_margin': min(passed) if passed else .5,
            'conditional_certified': bool(passed), 'conditional_tests': tests,
            'order_sha256': digest(ordering),
            'scope': 'Sourcewise calibration only. Overall CRC is in expectation under exchangeability; conditional LTT needs iid patients. No cross-source calibration pooling.'}


def summary(cases, labels, margin):
    accepted, errors = counts(cases, labels, margin)
    return {'patients': len(labels), 'released': accepted, 'retests': len(labels) - accepted,
            'wrong_released': errors, 'coverage': accepted / len(labels),
            'overall_wrong_release': errors / len(labels),
            'released_error': errors / accepted if accepted else None,
            'released_accuracy': 1 - errors / accepted if accepted else None}

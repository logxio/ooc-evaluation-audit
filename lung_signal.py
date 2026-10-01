#!/usr/bin/env python3
"""Training-only drug-specific shrinkage of a log-IC50 response threshold.

The fixed baseline uses 0.625 micromolar, a tested concentration. The candidate
learns only on designated training patients. Each drug threshold is shrunk
toward the pooled training threshold with weight n/(n+8); a local fit requires
four patients and both classes. Calibration never changes these numeric objects.
"""
import math

from release_calibration import cutoff, digest
from conditional_calibration import upper_bound, binomial_cdf
from pooled_signal import counts

GRID = [-1.] + [i / 100 for i in range(101)]


def log_ic50(value):
    x = float(str(value).strip().lstrip('>'))
    if x <= 0 or not math.isfinite(x):
        raise ValueError('IC50 must be positive and finite')
    return math.log10(x)


def fit(training):
    values = [log_ic50(r['ic50_raw']) for r in training]
    global_cut = cutoff(values, [r['y'] for r in training])
    thresholds = {}
    for drug in sorted({r['regimen'] for r in training}):
        rows = [r for r in training if r['regimen'] == drug]
        local = cutoff([log_ic50(r['ic50_raw']) for r in rows], [r['y'] for r in rows]) if len(rows) >= 4 and len({r['y'] for r in rows}) == 2 else global_cut
        weight = len(rows) / (len(rows) + 8)
        thresholds[drug] = weight * local + (1 - weight) * global_cut
    reference = sorted(log_ic50(r['ic50_raw']) - thresholds[r['regimen']] for r in training)
    base_reference = sorted(x - math.log10(.625) for x in values)
    model = {'schema': 'release.lung_signal.v1', 'global_cut': global_cut,
             'drug_cuts': thresholds, 'reference': reference, 'baseline_reference': base_reference,
             'grid': GRID, 'training_ids': [r['patient'] for r in training],
             'training_sha256': digest(training), 'fixed_baseline_micromolar': .625,
             'shrinkage_numerator': 'n', 'shrinkage_extra_count': 8}
    model['model_sha256'] = digest(model)
    return model


def predict(model, rows, method='shrinkage'):
    if digest({k: v for k, v in model.items() if k != 'model_sha256'}) != model['model_sha256']:
        raise ValueError('Frozen model hash differs')
    def ecdf(ref, x):
        return (sum(v < x for v in ref) + .5 * sum(v == x for v in ref)) / len(ref)
    cases = []
    for r in rows:
        threshold = model['drug_cuts'].get(r['regimen'], model['global_cut']) if method == 'shrinkage' else math.log10(.625)
        ref = model['reference'] if method == 'shrinkage' else model['baseline_reference']
        z = log_ic50(r['ic50_raw']) - threshold
        prediction = int(z <= 0)
        ambiguous = str(r['ic50_raw']).startswith('>') and prediction == 1
        cases.append({'patient': r['patient'], 'prediction': prediction,
                      'margin': -1. if ambiguous else abs(ecdf(ref, z) - ecdf(ref, 0)),
                      'censored_threshold_ambiguous': ambiguous})
    return cases


def calibrate(model, training, calibration, method='shrinkage', alpha=.1, eta=.05):
    if digest(training) != model['training_sha256']:
        raise ValueError('Training differs from frozen model')
    if set(model['training_ids']) & {r['patient'] for r in calibration}:
        raise ValueError('Training/calibration overlap')
    train_cases, cal_cases = predict(model, training, method), predict(model, calibration, method)
    overall = 1.
    for margin in GRID:
        _, e = counts(cal_cases, calibration, margin)
        if (e + 1) / (len(calibration) + 1) <= alpha:
            overall = margin
            break
    ordering = []
    for margin in GRID[:-1]:
        n, e = counts(train_cases, training, margin)
        ordering.append((upper_bound(e, n, eta), -n, margin))
    ordering.sort()
    passed, tests = [], []
    for _, _, margin in ordering:
        n, e = counts(cal_cases, calibration, margin)
        p = binomial_cdf(e, n, alpha) if n else 1.
        tests.append({'margin': margin, 'accepted': n, 'errors': e, 'p_value': p})
        if p > eta:
            break
        passed.append(margin)
    return {'model_sha256': model['model_sha256'], 'method': method, 'alpha': alpha, 'eta': eta,
            'calibration_ids': [r['patient'] for r in calibration], 'calibration_sha256': digest(calibration),
            'overall_margin': overall, 'conditional_margin': min(passed) if passed else 1.,
            'conditional_certified': bool(passed), 'conditional_tests': tests,
            'ordering_sha256': digest(ordering)}

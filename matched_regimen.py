#!/usr/bin/env python3
"""Single matched-regimen readout on the fixed, previously seen rectal split.

Combined treatment is one measured assay, not two independent readouts. The
same training-only cutoff and reference are used in calibration and deployment.
"""
import argparse
import hashlib
import json
from pathlib import Path

from blind2_predict import RECTAL
from blind2_score import RECTAL_CLINICAL
from calibration_replay import split, SEED
from conditional_calibration import binomial_cdf, upper_bound
from release_calibration import cutoff, digest
from pooled_signal import rank, counts, summary

GRID = [-1.] + [i / 100 for i in range(101)]


def fit(training):
    values = [r['x'] for r in training]
    model = {'cutoff': cutoff(values, [r['y'] for r in training]), 'reference': sorted(values),
             'grid': GRID, 'training_ids': sorted(r['patient'] for r in training),
             'training_sha256': digest(training), 'signal': 'one measured combined-regimen assay'}
    model['model_sha256'] = digest(model)
    return model


def predict(model, rows):
    if digest({k: v for k, v in model.items() if k != 'model_sha256'}) != model['model_sha256']:
        raise ValueError('Frozen model hash differs')
    return [{'patient': r['patient'], 'prediction': int(r['x'] <= model['cutoff']),
             'margin': abs(rank(model['reference'], r['x']) - rank(model['reference'], model['cutoff']))}
            for r in rows]


def calibrate(model, training, calibration, alpha=.1, eta=.05):
    if digest(training) != model['training_sha256']:
        raise ValueError('Training differs from fitted model')
    if set(model['training_ids']) & {r['patient'] for r in calibration}:
        raise ValueError('Patient overlap between training and calibration')
    train_cases, cal_cases = predict(model, training), predict(model, calibration)
    overall = 1.
    for margin in GRID:
        _, errors = counts(cal_cases, calibration, margin)
        if (errors + 1) / (len(calibration) + 1) <= alpha:
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
        tests.append({'margin': margin, 'calibration_released': n, 'calibration_wrong': e,
                      'upper': upper_bound(e, n, eta), 'p': p})
        if p > eta:
            break
        passed.append(margin)
    return {'model_sha256': model['model_sha256'], 'alpha': alpha, 'eta': eta,
            'overall_margin': overall, 'conditional_margin': min(passed) if passed else 1.,
            'conditional_certified': bool(passed), 'tests': tests,
            'calibration_sha256': digest(calibration), 'order_sha256': digest(ordering)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=Path('matched_regimen.json'))
    parser.add_argument('--freeze', type=Path, default=Path('matched_regimen_frozen.json'))
    args = parser.parse_args()
    rows = [{'patient': 'Patient' + str(p), 'x': v[3],
             'y': int(RECTAL_CLINICAL[p][1].lower() in ('0', '1', 'ccr', 'pcr'))}
            for p, v in RECTAL.items() if 'radiation' in RECTAL_CLINICAL[p][0].lower()]
    training, cal, test = split('rectal_2025', rows)
    model = fit(training)
    cert = calibrate(model, training, cal)
    future = predict(model, [{'patient': r['patient'], 'x': r['x']} for r in test])
    cal_cases = predict(model, cal)
    modes = {}
    for mode, margin in [('fixed_threshold', -1.), ('overall_crc', cert['overall_margin']),
                         ('conditional_ltt', cert['conditional_margin'])]:
        pilot = summary(cal_cases, cal, margin)
        released = sum(c['margin'] > margin for c in future)
        modes[mode] = {'margin': margin, 'forecast': {'released': released, 'retests': len(test) - released,
            'accuracy': (pilot['released'] - pilot['wrong_released'] + .5) / (pilot['released'] + 1) if pilot['released'] else None},
            'calibration': pilot}
    frozen = {'schema': 'release.matched_regimen.freeze.v1', 'model': model, 'certificate': cert,
              'seed': SEED, 'test_predictions': future, 'modes': modes,
              'status': 'Previously seen retrospective cohort; one prespecified signal change, no fresh clinical outcomes.'}
    args.freeze.write_text(json.dumps(frozen, indent=2, allow_nan=False) + '\n')
    result = {'schema': 'release.matched_regimen.result.v1',
              'freeze_sha256': hashlib.sha256(args.freeze.read_bytes()).hexdigest(),
              'status': frozen['status'], 'split': [len(training), len(cal), len(test)],
              'conditional_scope': '95% for this prespecified source and method only, assuming iid calibration/future patients; no joint guarantee across sources or methods.',
              'modes': {mode: dict(val, test=summary(future, test, val['margin'])) for mode, val in modes.items()},
              'conditional_first_test': cert['tests'][0],
              'conditional_certified': cert['conditional_certified']}
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()

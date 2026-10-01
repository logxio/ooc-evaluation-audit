#!/usr/bin/env python3
"""Calibrate conditional error among released patients with exact binomial LTT.

The primary fixed-sequence order is determined entirely from training data.
For each prespecified alpha, delta is shared across the three sources. All-retest
has undefined conditional error and never counts as achieving nonzero coverage.
This script reuses the fixed retrospective split; it does not tune on test data.

    python conditional_calibration.py --out conditional_calibration.json
"""
import argparse
import json
import math
from pathlib import Path

from release_calibration import GRID, apply, check_rows, digest, fit, measure, predict


def binomial_cdf(errors, accepted, probability):
    """Exact finite binomial sum, evaluated in log space with standard library."""
    if not 0 <= errors <= accepted or not 0 <= probability <= 1:
        raise ValueError('Invalid binomial arguments')
    if errors == accepted or probability == 0:
        return 1.0
    if probability == 1:
        return 0.0
    logs = [math.lgamma(accepted + 1) - math.lgamma(k + 1) - math.lgamma(accepted - k + 1)
            + k * math.log(probability) + (accepted - k) * math.log1p(-probability)
            for k in range(errors + 1)]
    largest = max(logs)
    return min(1.0, math.exp(largest) * math.fsum(math.exp(v - largest) for v in logs))


def upper_bound(errors, accepted, eta):
    """One-sided exact Clopper-Pearson upper endpoint at confidence 1-eta."""
    if not 0 < eta < 1 or not 0 <= errors <= accepted:
        raise ValueError('Invalid confidence-bound arguments')
    if accepted == 0 or errors == accepted:
        return 1.0
    if errors == 0:
        return -math.expm1(math.log(eta) / accepted)
    lo, hi = 0.0, 1.0
    for _ in range(64):
        mid = (lo + hi) / 2
        if binomial_cdf(errors, accepted, mid) > eta:
            lo = mid
        else:
            hi = mid
    return hi


def counts(cases, rows, margin):
    accepted = [c for c in cases if c['agree'] and c['margin'] > margin]
    truth = {r['patient']: r['y'] for r in rows}
    return len(accepted), sum(c['prediction'] != truth[c['patient']] for c in accepted)


def zero_error_minimum(alpha, eta):
    return math.ceil(math.log(eta) / math.log1p(-alpha))


def calibrate_conditional(model, training, calibration, alpha, eta):
    check_rows(training)
    check_rows(calibration)
    if digest(training) != model['training_sha256']:
        raise ValueError('Ordering must use the fitted training table')
    if set(model['training_ids']) & {r['patient'] for r in calibration}:
        raise ValueError('Training and calibration patients overlap')
    train_cases = predict(model, training)
    # Ordering never reads calibration labels, release counts or test information.
    ordering = []
    for margin in model['margin_grid']:
        if margin == 1.0:
            continue  # Always empty: conditional population error is undefined.
        m, e = counts(train_cases, training, margin)
        ordering.append({'margin': margin, 'training_released': m, 'training_wrong': e,
                         'training_order_score': upper_bound(e, m, eta)})
    ordering.sort(key=lambda x: (x['training_order_score'], -x['training_released'], x['margin']))
    order_sha = digest(ordering)
    cal_cases = predict(model, calibration)
    tested, rejected = [], []
    for candidate in ordering:
        margin = candidate['margin']
        m, e = counts(cal_cases, calibration, margin)
        p = binomial_cdf(e, m, alpha) if m else 1.0
        reject = bool(m and p <= eta)
        tested.append(dict(candidate, calibration_released=m, calibration_wrong=e,
                           p_value=p, test_level=eta, rejected=reject,
                           pointwise_upper=upper_bound(e, m, eta)))
        if not reject:
            break
        rejected.append(margin)
    margin = min(rejected) if rejected else 1.0
    return {'schema': 'release.conditional.certificate.v1', 'model': model, 'alpha': alpha,
            'margin': margin, 'fallback': 'none' if rejected else 'all_retest',
            'calibration_ids': sorted(r['patient'] for r in calibration),
            'calibration_sha256': digest(calibration), 'source_test_level': eta,
            'ordering_sha256': order_sha, 'training_only_order': ordering,
            'tests': tested, 'rejected_margins': rejected,
            'certified_conditional_target': bool(rejected),
            'guarantee_scope': 'high_probability_conditional_released_error_under_iid_patients'}


def run_source(name, rows, delta, source_count):
    from calibration_replay import ALPHAS, split
    training, calibration, test = split(name, rows)
    if len({r['patient'] for r in training + calibration + test}) != len(rows):
        raise ValueError('Split contains duplicate or overlapping patients')
    model = fit(training)
    eta = delta / source_count
    cal_cases = predict(model, calibration)
    bonferroni_eta = eta / len(GRID)
    bounds = []
    for margin in GRID:
        m, e = counts(cal_cases, calibration, margin)
        bounds.append({'margin': margin, 'calibration_released': m, 'calibration_wrong': e,
                       'simultaneous_upper': upper_bound(e, m, bonferroni_eta)})
    result = {'source': name, 'split': {'training': len(training), 'calibration': len(calibration),
                                     'test': len(test)},
              'model_sha256': model['model_sha256'], 'levels': [],
              'bonferroni_comparison': {'eta': bonferroni_eta, 'bounds': bounds}}
    for alpha in ALPHAS:
        cert = calibrate_conditional(model, training, calibration, alpha, eta)
        future_inputs = [{'patient': r['patient'], 'x': r['x']} for r in test]
        frozen_calls = apply(cert, future_inputs)
        cal = measure(cert, calibration)
        # This pilot estimate is descriptive and uses calibration only.
        forecast = {'basis': 'calibration-only retrospective pilot; selection can make it optimistic',
                    'expected_releases': len(test) * cal['coverage'],
                    'expected_retests': len(test) * (1 - cal['coverage']),
                    'released_accuracy_smoothed': ((cal['released_correct'] + .5) / (cal['released'] + 1)
                                                   if cal['released'] else None)}
        frozen_sha = digest({'certificate': cert, 'calls': frozen_calls, 'pilot_forecast': forecast})
        observed = measure(cert, test)
        eligible_bonferroni = [b for b in bounds if b['calibration_released'] and b['simultaneous_upper'] <= alpha]
        result['levels'].append({'alpha': alpha, 'certificate': cert,
                                'calibration': {k: v for k, v in cal.items() if k != 'rows'},
                                'test': {k: v for k, v in observed.items() if k != 'rows'},
                                'test_predictions': frozen_calls, 'pilot_forecast': forecast,
                                'before_scoring_object_sha256': frozen_sha,
                                'nonzero_coverage_target_met': bool(cert['certified_conditional_target'] and observed['released']),
                                'bonferroni_comparison_has_nonempty_certificate': bool(eligible_bonferroni),
                                'zero_error_accepted_minimum': {
                                    'single_rule_single_source_95pct': zero_error_minimum(alpha, delta),
                                    'fixed_sequence_joint_sources_95pct': zero_error_minimum(alpha, eta),
                                    'bonferroni_joint_sources_95pct': zero_error_minimum(alpha, bonferroni_eta)}})
    return result


def main():
    from calibration_replay import SEED, sources
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--third-xlsx', type=Path)
    parser.add_argument('--out', type=Path, default=Path('conditional_calibration.json'))
    parser.add_argument('--delta', type=float, default=.05)
    args = parser.parse_args()
    if not 0 < args.delta < 1:
        parser.error('delta must be strictly between zero and one')
    data = sources(args.third_xlsx)
    results = {name: run_source(name, rows, args.delta, len(data)) for name, rows in data.items()}
    output = {'schema': 'release.conditional.replay.v1', 'seed': SEED, 'delta': args.delta,
              'data_status': 'retrospective replay of previously seen outcomes; fixed existing thirds split',
              'method': 'exact binomial fixed-sequence LTT with training-only order and stop at first non-rejection',
              'guarantee': 'For each fixed alpha separately, probability of any selected source rule having conditional released error above alpha is <=delta, under sourcewise iid calibration/future patients conditional on independent training.',
              'alpha_family_scope': 'Sensitivity levels are separate prespecified targets; no simultaneous 95% guarantee across alpha or selection of alpha from test.',
              'all_retest_meaning': 'No nonempty conditional-risk certificate; conditional error undefined and nonzero-coverage objective unmet.',
              'comparison_scope': 'Bonferroni bounds are simultaneous across all 3*102 candidates and therefore also support all alpha values; they do not select the primary deployment.',
              'references': ['https://arxiv.org/abs/2110.01052', 'https://arxiv.org/abs/2208.02814'],
              'sources': results}
    args.out.write_text(json.dumps(output, indent=2, allow_nan=False) + '\n')
    print(json.dumps({n: {'split': s['split'], 'levels': [
        {'alpha': l['alpha'], 'margin': l['certificate']['margin'],
         'calibration_released': l['calibration']['released'], 'test_released': l['test']['released'],
         'test_wrong': l['test']['wrong_released'], 'conditional_target_met': l['nonzero_coverage_target_met'],
         'first_test': l['certificate']['tests'][0],
         'zero_error_accepted_minimum': l['zero_error_accepted_minimum']}
        for l in s['levels']]} for n, s in results.items()}, indent=2))


if __name__ == '__main__':
    main()

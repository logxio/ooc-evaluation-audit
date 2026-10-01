#!/usr/bin/env python3
"""Empirically calibrate the two-readout release rule, and correct its
forecast for shared errors.

1. Release certificate. A call is released only when the two readouts agree and both sit
   farther than a threshold from their own cutoffs (margin, measured as the gap in each
   readout's empirical distribution). Conformal risk control (Angelopoulos, Bates, Fisch,
   Lei and Schuster, ICLR 2024) picks the threshold on a pilot of n patients with outcomes:
   the smallest one whose released errors e satisfy (e + 1) / (n + 1) <= alpha. The current
   data-dependent cutoffs and margins have no established conformal guarantee. Every setting is also
   checked by nested leave-one-out: the threshold is recalibrated without each patient and
   applied to that patient.
2. Shared-error correction. The independence forecast of release_theory.py runs high when
   both readouts fail on the same patients. One extra number, the correlation rho between
   the two readouts' right/wrong indicators, gives released share p1p2 + q1q2 + 2k and
   released accuracy (p1p2 + k) / (p1p2 + q1q2 + 2k), with k = rho * sqrt(p1q1p2q2). Rho is
   carried into each cohort from the other cohorts only (leave one cohort out).
"""

import argparse
import json
import math
import statistics
from pathlib import Path

import blind_consensus_score as blind
from blind_consensus import calls, patient_auc
from chip_clinic import (FIGURE_SHA256, FIGURE_URL, PATIENTS, SOURCE_SHA256, SOURCE_URL,
                         evaluate, read_chip, read_clinical, source_bytes)
from consensus_external import POST_NAT, PRE_NAT

ALPHAS = (0.10, 0.15, 0.20)
COHORT = {'colorectal chip, optimized': 'colorectal', 'colorectal chip, original': 'colorectal',
          'osteosarcoma organoids, post-treatment': 'osteosarcoma',
          'osteosarcoma organoids, pre-treatment': 'osteosarcoma',
          'blind biliary organoids': 'biliary', 'blind gastric organoids': 'gastric'}


def ecdf(values):
    ordered = sorted(values)
    n = len(ordered)
    def f(x):
        below = sum(v < x for v in ordered)
        equal = sum(v == x for v in ordered)
        return (below + 0.5 * equal) / n
    return f


def patient(call_a, call_b, truth, margin):
    agree = call_a == call_b
    return {'agree': agree, 'wrong': agree and call_a != truth,
            'a_right': call_a == truth, 'b_right': call_b == truth,
            'margin': margin if agree else -math.inf}


def colorectal(chip, truth, condition):
    readouts = []
    for key in ('vessel', 'tumoroid'):
        values = [chip[p][key][condition] for p in PATIENTS]
        ev = evaluate(truth, values)
        f = ecdf(values)
        readouts.append((ev['predictions'], [abs(f(x) - f(c)) for x, c in zip(values, ev['training_cutoffs'])]))
    (ca, ma), (cb, mb) = readouts
    return [patient(a, b, t, min(x, y)) for a, b, t, x, y in zip(ca, cb, truth, ma, mb)]


def osteosarcoma(table):
    rows = [r for r in table if r[4] != 'NA']
    # published binary calls carry no margin: every agreed call ties at 1
    return [patient(int(r[1] == 'S'), int(r[2] in ('II', 'III')), int(r[4] == 'CR'), 1.0) for r in rows]


def blind_cohort(cohort, frozen, words):
    auc = patient_auc()[cohort]
    sensitive, medians = calls(auc)
    frozen_calls = {p: v['drug_sensitive'] for p, v in frozen['cohorts'][cohort]['primary_median_split'].items()}
    assert sensitive == frozen_calls, 'recomputed calls differ from the frozen prediction file'
    cdf = {d: ecdf([v[d] for v in auc.values() if d in v]) for d in medians}
    keys = {blind.norm(k): k for k in auc}
    table = blind.BILIARY if cohort == 'biliary' else blind.GASTRIC
    _, scored = blind.score(table, cohort, frozen, words)
    out = []
    for r in scored:
        if not r['evaluable']:
            continue
        key = keys[blind.ALIASES.get(blind.norm(r['patient']), blind.norm(r['patient']))]
        a, b = r['pair'].split('+')
        margin = min(abs(cdf[d](auc[key][d]) - cdf[d](medians[d])) for d in (a, b))
        out.append(patient(int(r['single'][a] == 'responder'), int(r['single'][b] == 'responder'),
                           int(r['truth'] == 'responder'), margin))
    return out


def calibrate(rows, alpha):
    """Conformal risk control: smallest threshold with (released errors + 1) / (n + 1) <= alpha."""
    n = len(rows)
    for lam in [-1.0] + sorted({r['margin'] for r in rows if r['agree']}):
        errors = sum(r['margin'] > lam and r['wrong'] for r in rows)
        if (errors + 1) / (n + 1) <= alpha:
            return lam
    return math.inf


def certificate(rows, alpha):
    n = len(rows)
    lam = calibrate(rows, alpha)
    released = sum(r['margin'] > lam for r in rows)
    errors = sum(r['margin'] > lam and r['wrong'] for r in rows)
    loo_released = loo_errors = 0
    for j, r in enumerate(rows):
        lam_j = calibrate(rows[:j] + rows[j + 1:], alpha)
        loo_released += r['margin'] > lam_j
        loo_errors += r['margin'] > lam_j and r['wrong']
    return {'alpha': alpha, 'threshold': None if math.isinf(lam) else round(lam, 4),
            'released': released, 'released_wrong': errors, 'retests': n - released,
            'pilot_bound': round((errors + 1) / (n + 1), 4),
            'nested_loo_released': loo_released, 'nested_loo_released_wrong': loo_errors,
            'nested_loo_wrong_rate': round(loo_errors / n, 4)}


def rho_of(p1, p2, both_wrong):
    spread = math.sqrt(p1 * (1 - p1) * p2 * (1 - p2))
    return (both_wrong - (1 - p1) * (1 - p2)) / spread


def forecast(p1, p2, rho):
    k = rho * math.sqrt(p1 * (1 - p1) * p2 * (1 - p2))
    right, wrong = p1 * p2 + k, (1 - p1) * (1 - p2) + k
    return right / (right + wrong), right + wrong


def describe(name, rows):
    n = len(rows)
    agreed = [r for r in rows if r['agree']]
    errors = sum(r['wrong'] for r in agreed)
    p1 = sum(r['a_right'] for r in rows) / n
    p2 = sum(r['b_right'] for r in rows) / n
    both_wrong = sum(not r['a_right'] and not r['b_right'] for r in rows) / n
    return {'setting': name, 'patients': n, 'readout_accuracy': [round(p1, 4), round(p2, 4)],
            'agreed': len(agreed), 'agreed_wrong': errors,
            'agreement_rule_certifiable_alpha': round((errors + 1) / (n + 1), 4),
            'certificates': [certificate(rows, a) for a in ALPHAS],
            '_p': (p1, p2, both_wrong)}


def correction(settings):
    for s in settings:
        p1, p2, both_wrong = s['_p']
        s['error_correlation'] = round(rho_of(p1, p2, both_wrong), 4)
    out = []
    for s in settings:
        p1, p2, _ = s['_p']
        others = [t['error_correlation'] for t in settings if COHORT[t['setting']] != COHORT[s['setting']]]
        rho = statistics.mean(others)
        acc, share = forecast(p1, p2, rho)
        acc0, share0 = forecast(p1, p2, 0.0)
        observed = (s['agreed'] - s['agreed_wrong']) / s['agreed']
        out.append({'setting': s['setting'], 'rho_from_other_cohorts': round(rho, 4),
                    'released_accuracy': round(observed, 4),
                    'forecast_independent': round(acc0, 4), 'forecast_corrected': round(acc, 4),
                    'released': s['agreed'], 'released_forecast_independent': round(s['patients'] * share0, 2),
                    'released_forecast_corrected': round(s['patients'] * share, 2),
                    'beats_better_readout': observed > max(p1, p2),
                    'beats_better_readout_corrected': acc > max(p1, p2)})
    mae = lambda key: round(statistics.mean(abs(r['released_accuracy'] - r[key]) for r in out), 4)
    top = lambda key: round(max(abs(r['released_accuracy'] - r[key]) for r in out), 4)
    return out, {'settings': len(out),
                 'mean_error_correlation': round(statistics.mean(s['error_correlation'] for s in settings), 4),
                 'released_accuracy_mae_independent': mae('forecast_independent'),
                 'released_accuracy_mae_corrected': mae('forecast_corrected'),
                 'released_accuracy_max_error_independent': top('forecast_independent'),
                 'released_accuracy_max_error_corrected': top('forecast_corrected'),
                 'beats_better_readout_sorted_corrected': sum(r['beats_better_readout'] == r['beats_better_readout_corrected'] for r in out)}


def pilot_sizes():
    """Smallest pilot n that certifies alpha when it holds e released errors: (e + 1)/(n + 1) <= alpha."""
    return {str(a): {str(e): math.ceil((e + 1) / a - 1 - 1e-9) for e in range(4)} for a in (0.05, 0.10, 0.20)}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--source-zip', type=Path, help='local Dai source ZIP')
    parser.add_argument('--figure', type=Path, help='local Dai Figure 5 image')
    parser.add_argument('--predictions', type=Path, default=Path('blind_predictions.json'))
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    chip = read_chip(source_bytes(args.source_zip, SOURCE_URL, SOURCE_SHA256))
    clinical = read_clinical(source_bytes(args.figure, FIGURE_URL, FIGURE_SHA256))
    truth = [clinical[p] for p in PATIENTS]
    frozen = json.loads(args.predictions.read_text())
    registered = {k: tuple(v) for k, v in frozen['outcome_words']['disease_control_primary'].items()}
    amended = {k: registered[k] + blind.AMENDMENT.get(k, ()) for k in registered}
    cohorts = [('colorectal chip, optimized', colorectal(chip, truth, 'optimized')),
               ('colorectal chip, original', colorectal(chip, truth, 'original')),
               ('osteosarcoma organoids, post-treatment', osteosarcoma(POST_NAT)),
               ('osteosarcoma organoids, pre-treatment', osteosarcoma(PRE_NAT)),
               ('blind biliary organoids', blind_cohort('biliary', frozen, amended)),
               ('blind gastric organoids', blind_cohort('gastric', frozen, amended))]
    settings = [describe(name, rows) for name, rows in cohorts]
    corrected, fit = correction(settings)
    for s in settings:
        s.pop('_p')
    pooled = {}
    for a in ALPHAS:
        rows = [c for s in settings for c in s['certificates'] if c['alpha'] == a]
        n = sum(s['patients'] for s in settings)
        pooled[str(a)] = {'patients': n, 'released': sum(r['released'] for r in rows),
                          'nested_loo_released': sum(r['nested_loo_released'] for r in rows),
                          'nested_loo_released_wrong': sum(r['nested_loo_released_wrong'] for r in rows),
                          'nested_loo_wrong_rate': round(sum(r['nested_loo_released_wrong'] for r in rows) / n, 4)}
    result = {'schema': 'release.certificate.v1',
              'method': 'conformal risk control on the released-and-wrong loss; margin = min over the two readouts of the empirical-CDF gap to the cutoff',
              'guarantee_status': 'unestablished',
              'interpretation': 'Empirical calibration. Leave-one-out here recalibrates the margin only; previously constructed patient cutoffs and empirical-CDF margins remain fixed. A formal guarantee for this data-dependent loss family has not been established.',
              'settings': settings, 'settings_pooled_by_alpha': pooled,
              'pilot_size_to_certify': pilot_sizes(),
              'shared_error_forecast': corrected, 'shared_error_fit': fit}
    if args.out:
        args.out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()

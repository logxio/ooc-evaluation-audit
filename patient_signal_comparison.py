#!/usr/bin/env python3
"""Paired, exploratory comparison of treatment-aligned patient readout signals.

Uses existing public patient tables and their original train/calibration/test
split. The protocol records the prior outcome exposure and the subgroup scope.
All fitting and baseline selection use training patients only.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import random
import resource
import sys
import time

from blind2_predict import RECTAL, RECTAL_CHANNELS
from blind2_score import RECTAL_CLINICAL
from calibration_replay import split
from matched_regimen import fit, predict, calibrate
from release_calibration import digest, fit as pair_fit, calibrate as pair_calibrate, apply as pair_apply

ROOT = Path(__file__).resolve().parent
PROTOCOL = ROOT / 'patient_signal_comparison_protocol.json'
PROTOCOL_SHA = 'd9e4cfe7ac18dde812daae4170a388c0091d992d843a3ccd00f0d4e9b2b84150'


def balanced_accuracy(cases, rows):
    classes = sorted({r['y'] for r in rows})
    return sum(sum(c['prediction'] == r['y'] for c, r in zip(cases, rows) if r['y'] == y) /
               sum(r['y'] == y for r in rows) for y in classes) / len(classes)


def scalar(rows, channel):
    return [dict(r, x=r['x'][channel]) for r in rows]


def exact_p(positive, negative):
    n = positive + negative
    return min(1., 2 * sum(math.comb(n, k) for k in range(min(positive, negative) + 1)) / 2**n) if n else 1.


def quantile(ordered, p):
    i = (len(ordered) - 1) * p
    low = int(i)
    return ordered[low] + (i - low) * (ordered[min(low + 1, len(ordered) - 1)] - ordered[low])


def paired_effect(groups, column, replicates, name):
    """Bootstrap patient pairs inside each source; preserve original source sizes."""
    data = [[r[column] for r in rows] for rows in groups]
    n = sum(map(len, data))
    rng = random.Random('patient-signal-comparison-20261002-v1|' + name)
    boot = sorted(sum(sum(rng.choice(values) for _ in values) for values in data) / n
                  for _ in range(replicates))
    values = [v for group in data for v in group]
    pos, neg = sum(v > 0 for v in values), sum(v < 0 for v in values)
    return {'patients': n, 'estimate': sum(values) / n,
            'paired_patient_bootstrap_95_percent_ci': [quantile(boot, .025), quantile(boot, .975)],
            'bootstrap_replicates': replicates, 'positive_discordances': pos, 'negative_discordances': neg,
            'exact_two_sided_mcnemar_p': exact_p(pos, neg),
            'bootstrap_scope': 'Conditional on these fixed fitted models; training uncertainty is not resampled.'}


def summarize(rows, prefix):
    n = len(rows)
    released = sum(r[prefix + '_release'] for r in rows)
    wrong = sum(r[prefix + '_release'] and r[prefix + '_prediction'] != r['outcome'] for r in rows)
    return {'patients': n, 'released': released, 'wrong_released': wrong,
            'coverage': released / n, 'overall_wrong_release': wrong / n,
            'released_error': wrong / released if released else None,
            'full_coverage_errors': sum(r[prefix + '_prediction'] != r['outcome'] for r in rows)}


def compare(rows, replicates, name, risk_comparable=True):
    new, baseline = summarize(rows, 'new'), summarize(rows, 'baseline')
    coverage = paired_effect([rows], 'coverage_difference', replicates, name + '|coverage')
    error = paired_effect([rows], 'error_reduction', replicates, name + '|error')
    return {'new': new, 'baseline': baseline, 'coverage_gain': coverage,
            'full_coverage_error_reduction': error,
            'observed_same_10_percent_overall_risk': new['overall_wrong_release'] <= .1 and baseline['overall_wrong_release'] <= .1,
            'gate_pass': risk_comparable and new['overall_wrong_release'] <= .1 and baseline['overall_wrong_release'] <= .1 and coverage['paired_patient_bootstrap_95_percent_ci'][0] > 0,
            'risk_comparable_calibration': risk_comparable,
            'paired_rows': rows}


def rectal(replicates):
    rows = [{'patient': 'Patient' + str(p), 'x': list(v),
             'y': int(RECTAL_CLINICAL[p][1].lower() in ('0', '1', 'ccr', 'pcr')),
             'regimen': RECTAL_CLINICAL[p][0],
             'three_component_match': all(t in RECTAL_CLINICAL[p][0].lower() for t in ('radiation', 'capecitabine', 'irinotecan'))}
            for p, v in RECTAL.items() if 'radiation' in RECTAL_CLINICAL[p][0].lower()]
    train, cal, test = split('rectal_2025', rows)
    models = [fit(scalar(train, j)) for j in range(4)]
    train_scores = [balanced_accuracy(predict(m, scalar(train, j)), train) for j, m in enumerate(models)]
    single = max(range(3), key=lambda j: (train_scores[j], -j))
    certificates = {key: calibrate(models[j], scalar(train, j), scalar(cal, j))
                    for key, j in [('new', 3), ('baseline', single)]}
    cases = {key: predict(models[j], scalar(test, j)) for key, j in [('new', 3), ('baseline', single)]}
    paired = []
    for i, row in enumerate(test):
        r = {'source': 'rectal_2025', 'patient': row['patient'], 'regimen': row['regimen'],
             'three_component_match': row['three_component_match'], 'outcome': row['y']}
        for key in ('new', 'baseline'):
            c = cases[key][i]
            r.update({key + '_prediction': c['prediction'], key + '_margin': c['margin'],
                      key + '_release': c['margin'] > certificates[key]['overall_margin'],
                      key + '_conditional_release': c['margin'] > certificates[key]['conditional_margin']})
        r['coverage_difference'] = int(r['new_release']) - int(r['baseline_release'])
        r['error_reduction'] = int(r['baseline_prediction'] != r['outcome']) - int(r['new_prediction'] != r['outcome'])
        paired.append(r)
    matched = [r for r in paired if r['three_component_match']]
    # Reproduce the older two-readout comparator under its correct name.
    old_train = [dict(r, x=r['x'][:2]) for r in train]
    old_cal = [dict(r, x=r['x'][:2]) for r in cal]
    old_test = [dict(r, x=r['x'][:2]) for r in test]
    old_model = pair_fit(old_train)
    old_cert = pair_calibrate(old_model, old_cal, .1)
    old_cases = pair_apply(old_cert, old_test)
    old_errors = sum(c['released'] and c['prediction'] != r['y'] for c, r in zip(old_cases, test))
    legacy_pairs = []
    for row, case in zip(paired, old_cases):
        legacy = dict(row, baseline_release=case['released'], baseline_prediction=case['prediction'])
        legacy['coverage_difference'] = int(legacy['new_release']) - int(legacy['baseline_release'])
        legacy['error_reduction'] = int(legacy['baseline_prediction'] != legacy['outcome']) - int(legacy['new_prediction'] != legacy['outcome'])
        legacy_pairs.append(legacy)
    result = {'split': {'training': len(train), 'calibration': len(cal), 'test': len(test)},
              'component_matching_by_split': {k: {'matching': sum(r['three_component_match'] for r in rs), 'total': len(rs)}
                                              for k, rs in [('training', train), ('calibration', cal), ('test', test)]},
              'clinical_mapping': 'Assay 5-FU is a proxy for capecitabine; the three-component subgroup additionally matches radiation and irinotecan. Full-population CRC does not automatically guarantee subgroup risk.',
              'training_balanced_accuracies': dict(zip(RECTAL_CHANNELS, train_scores)),
              'selected_single_component': RECTAL_CHANNELS[single],
              'models': {'new': models[3], 'baseline': models[single]}, 'certificates': certificates,
              'primary_three_component_match': compare(matched, replicates, 'rectal_match'),
              'all_43_sensitivity': compare(paired, replicates, 'rectal_all'),
              'conditional_10_percent': {key: {'certified': cert['conditional_certified'],
                  'released_all_43': sum(r[key + '_conditional_release'] for r in paired),
                  'released_matched': sum(r[key + '_conditional_release'] for r in matched),
                  'wrong_all_43': sum(r[key + '_conditional_release'] and r[key + '_prediction'] != r['outcome'] for r in paired)} for key, cert in certificates.items()},
              'old_two_readout_agreement': {'readouts': ['Irradiation', '5-FU'], 'alpha': .1,
                  'released': sum(c['released'] for c in old_cases), 'wrong_released': old_errors,
                  'description': 'Two-readout agreement, not a single-drug baseline. These sensitivity results retain the predeclared primary comparator and population.',
                  'all_43_sensitivity': compare(legacy_pairs, replicates, 'legacy_all'),
                  'three_component_match_sensitivity': compare([r for r in legacy_pairs if r['three_component_match']], replicates, 'legacy_match')}}
    return result, matched, paired


def tiriac(replicates):
    frozen = json.loads((ROOT / 'tiriac_frozen_predictions.json').read_text())
    outcomes = json.loads((ROOT / 'tiriac_outcomes.json').read_text())
    labels = {r['pdo_id']: r['outcome_6_months'] for r in outcomes['rows']}
    paired = []
    for c in frozen['cases']:
        if c['pdo'] not in frozen['primary']['pdo_ids']:
            continue
        p = c['subsets'][c['reported_regimen']]
        r = {'source': 'tiriac_2018', 'patient': c['patient'], 'pdo': c['pdo'],
             'regimen': c['reported_regimen'], 'outcome': labels[c['pdo']],
             'new_prediction': p['mean_rank_prediction'], 'baseline_prediction': p['fixed_anchor_prediction'],
             'new_release': True, 'baseline_release': True, 'coverage_difference': 0,
             'new_conditional_release': False, 'baseline_conditional_release': False}
        r['error_reduction'] = int(r['baseline_prediction'] != r['outcome']) - int(r['new_prediction'] != r['outcome'])
        paired.append(r)
    strict = [r for r in paired if r['pdo'] != 'hF28']
    return {'baseline': 'Prespecified fixed-anchor drug from the original freeze; no labelled independent training cohort exists to select the best single drug.',
            'signal': 'Mean reference percentile over reported regimen components, a constructed score rather than a measured combination assay.',
            'primary_7': compare(paired, replicates, 'tiriac_primary', False),
            'strict_6': compare(strict, replicates, 'tiriac_strict', False),
            'conditional_10_percent': {'calibration_patients': 0, 'new_releases': 0, 'baseline_releases': 0},
            'scope': 'Fixed full-coverage calls only. Observed error is not a risk-controlled 10% comparison.'}, paired


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--replicates', type=int, default=10000)
    parser.add_argument('--out', type=Path, default=ROOT / 'patient_signal_comparison_result.json')
    parser.add_argument('--csv', type=Path)
    args = parser.parse_args()
    started = time.monotonic()
    actual_hash = hashlib.sha256(PROTOCOL.read_bytes()).hexdigest()
    if actual_hash != PROTOCOL_SHA:
        raise ValueError('Patient comparison protocol checksum differs')
    r, matched, all_rectal = rectal(args.replicates)
    t, pancreas = tiriac(args.replicates)
    result = {'schema': 'release.patient_signal_comparison.result.v1', 'protocol_sha256': actual_hash,
              'status': 'Exploratory paired inference on previously seen outcomes; fixed split and training-only selection.',
              'rectal': r, 'tiriac': t,
              'cross_source_descriptive_full_coverage_error_reduction': {
                  'matched_rectal_plus_tiriac_primary': paired_effect([matched, pancreas], 'error_reduction', args.replicates, 'stratified_match'),
                  'all_rectal_plus_tiriac_primary': paired_effect([all_rectal, pancreas], 'error_reduction', args.replicates, 'stratified_all'),
                  'interpretation': 'Descriptive signal-construction effect using different clinical endpoints and differently chosen comparators. Tiriac uses fixed anchor, not training-best single drug. No joint risk guarantee or calibration-algorithm gain.'},
              'input_sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in
                              ['blind2_predict.py', 'blind2_score.py', 'tiriac_frozen_predictions.json', 'tiriac_outcomes.json']}}
    result['runtime'] = {'elapsed_seconds': time.monotonic() - started,
                         'peak_rss_bytes': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == 'darwin' else 1024),
                         'bootstrap_replicates': args.replicates}
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    if args.csv:
        rows = all_rectal + pancreas
        fields = sorted({k for row in rows for k in row})
        with args.csv.open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader(); writer.writerows(rows)
    print(json.dumps({'rectal': {k: {a: v for a, v in r[k].items() if a != 'paired_rows'} for k in ['primary_three_component_match', 'all_43_sensitivity']},
                      'selected_single': r['selected_single_component'],
                      'matching': r['component_matching_by_split'],
                      'tiriac': {k: {a: v for a, v in t[k].items() if a != 'paired_rows'} for k in ['primary_7', 'strict_6']},
                      'cross_source': result['cross_source_descriptive_full_coverage_error_reduction'],
                      'runtime': result['runtime']}, indent=2))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Freeze readout-only pharmacotyping before reading nine published outcomes.

Tiriac et al. 2018, doi:10.1158/2159-8290.CD-18-0349. Reference patients
exclude every clinically linked patient and all their sibling PDO cultures.
The assay is shared across drugs; independent measurement errors are not assumed.
"""
import argparse
import csv
import datetime
import hashlib
import itertools
import json
import statistics
from pathlib import Path

from release_calibration import digest

DRUGS = ['gemcitabine', 'paclitaxel', 'sn38', '5fu', 'oxaliplatin']
PILOT_ACCURACY = 8.5 / 12  # Jeffreys estimate from the previously seen Tan unique-patient 8/11.


def load(path):
    return list(csv.DictReader(path.open()))


def freeze(reference, clinical):
    if {r['patient_id'] for r in reference} & {r['patient_id'] for r in clinical}:
        raise ValueError('Reference and clinical patients overlap')
    if len({r['patient_id'] for r in clinical}) != len(clinical):
        raise ValueError('Use one record per clinical patient')
    patient_values = {}
    for r in reference:
        patient_values.setdefault(r['patient_id'], []).append(r)
    refs = {}
    for d in DRUGS:
        per_patient = [[float(r[d + '_auc']) for r in rs if r[d + '_auc'] not in ('', '#N/A')]
                       for rs in patient_values.values()]
        refs[d] = sorted(statistics.mean(v) for v in per_patient if v)
    cutoffs = {d: statistics.median(refs[d]) for d in DRUGS}
    model = {'reference': refs, 'cutoffs': cutoffs, 'reference_ids': sorted(patient_values),
             'reference_patients_by_drug': {d: len(refs[d]) for d in DRUGS},
             'missing_reference_rule': 'Exclude missing #N/A drug values, average observed sibling PDOs per patient per drug; never impute from clinical outcomes.',
             'margin_family': [0, .1, 1 / 6, .2, .3, .4, .5],
             'point_forecast_accuracy': PILOT_ACCURACY}
    model['model_sha256'] = digest(model)
    cases = []
    for r in clinical:
        values = {d: float(r[d + '_auc']) for d in DRUGS}
        calls = {d: int(values[d] <= cutoffs[d]) for d in DRUGS}
        ranks = {d: (sum(v < values[d] for v in refs[d]) + .5 * sum(v == values[d] for v in refs[d])) / len(refs[d]) for d in DRUGS}
        subsets = {}
        for size in range(1, 6):
            for drugs in itertools.combinations(DRUGS, size):
                key = '+'.join(sorted(drugs))
                mean_rank = statistics.mean(ranks[d] for d in drugs)
                subsets[key] = {'calls': {d: calls[d] for d in drugs},
                    'agreement_released': size >= 2 and len({calls[d] for d in drugs}) == 1,
                    'agreement_prediction': calls[drugs[0]],
                    'fixed_anchor_prediction': calls[next(d for d in ['gemcitabine', '5fu', 'sn38', 'oxaliplatin', 'paclitaxel'] if d in drugs)],
                    'mean_rank_prediction': int(mean_rank <= .5), 'mean_rank_margin': abs(mean_rank - .5)}
        cases.append({'patient': r['patient_id'], 'pdo': r['pdo_id'],
                      'reported_regimen': '+'.join(sorted(r['regimen'].split('+'))), 'subsets': subsets})
    eligible = [c for c in cases if c['pdo'] not in ('hF2', 'hF50')]
    released = sum(c['subsets'][c['reported_regimen']]['agreement_released'] for c in eligible)
    return {'schema': 'release.tiriac.freeze.v1', 'created_utc': datetime.datetime.now(datetime.UTC).isoformat(),
            'source_doi': '10.1158/2159-8290.CD-18-0349', 'model': model, 'cases': cases,
            'primary': {'patients': len(eligible), 'pdo_ids': [c['pdo'] for c in eligible],
                'endpoint': 'Progression-free survival at least 6 months; days divided by 30.4375. Event before threshold=0, known event-free at or beyond threshold=1. Censoring before threshold or unreadable endpoint is unavailable and excluded with reason.',
                'regimen': 'Reported components; hF2 excluded because sequential regimens are documented. hF50 has one drug and is outside the paired-readout primary. Sensitivity additionally removes hF28 whose sequence is uncertain.',
                'method': 'All reported component calls agree at independent-reference drug medians; disagreements retest.',
                'baseline': 'Fixed anchor drug at its independent-reference median, releases every eligible patient.',
                'secondary': 'Mean reference rank of all reported regimen components; fixed 0.5 threshold, or absolute margin >1/6. Every one of 31 drug subsets frozen for transparent sequential-regimen sensitivity.',
                'forecast': {'released': released, 'retests': len(eligible) - released,
                    'released_accuracy': PILOT_ACCURACY, 'expected_correct': released * PILOT_ACCURACY},
                'risk_10_percent': 'No outcome-labelled calibration from this source; high-probability conditional-risk mode sends every patient to retest. Uncertified observed error is reported separately.'},
            'blind_scope': 'Retrospective published outcomes unread by this workflow; figure layout and PDO/drug coordinates were exposed during extraction. This is outcome-value blind, not a prospectively recruited clinical trial.',
            'forecast_scope': 'Numerical point forecast transferred from previously seen Tan patients. It is not a certificate and depends on transport across cohorts/endpoints.'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference', type=Path, required=True)
    p.add_argument('--clinical-readouts', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    if args.out.exists():
        p.error('Keep the original freeze immutable; use a new output path for a separate experiment')
    result = freeze(load(args.reference), load(args.clinical_readouts))
    result['input_sha256'] = {k: hashlib.sha256(v.read_bytes()).hexdigest() for k, v in [('reference', args.reference), ('clinical_readouts', args.clinical_readouts)]}
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print(json.dumps({'sha256': hashlib.sha256(args.out.read_bytes()).hexdigest(), 'primary': result['primary']}))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Score the unchanged third blind-test calls against Tan et al. (2023).

The frozen prediction file was committed as 258e60f before outcome extraction.
Its citation said Wang; the DOI actually identifies Tan et al. Table S5 contains
reference-trial response rates and Table S8 contains PDTO predictions. Clinical
benefit labels and treatments are in Figures 4B and 5C, also named at freeze.
Figure S4 establishes immediate versus subsequent treatment. These source-location
corrections leave calls, thresholds, endpoints and drug mapping unchanged.

The inline records transcribe patient IDs, regimen names and the blue/yellow
clinical-benefit labels, not raw assay values or individual RECIST categories.
Optional --source-dir verifies the original images/PDF and checks every label
against the image colour. No original source files are redistributed.
"""

import argparse
import hashlib
import json
from pathlib import Path

from release_theory import setting

PREDICTIONS_SHA256 = '754902dc84e04ec5b9682cc379fe0ab50352e01af146c988fba6bf5498393342'
FREEZE_COMMIT = '258e60f5e5513fd69090385e70a9818f8468f20c'
TOLERANCE = 0.09
COSTS = (0.10, 0.25, 0.50)
SOURCE_BASE = 'https://pmc-oa-opendata.s3.amazonaws.com/PMC10783557.1/'
SOURCES = {
    'gr4.jpg': {'sha256': '97ea44947b2ee5415eb3a834957050e374f12de7fcb06197775dd2e49149d22a',
                'content': 'Figure 4B: community cohort, 29 treatments, 18 patients'},
    'gr5.jpg': {'sha256': 'b1d51e048ac300ff66c8a4c55068bee179a528568c7f4e9bf0362101840147fb',
                'content': 'Figure 5C: FORECAST-1, 10 treatments, 9 patients'},
    'mmc1.pdf': {'sha256': 'b2357dfaf12ea45aafa7b0250751ed510af59793e53258ed4c3ff1852b166a00',
                 'content': 'Figure S4, PDF page 5: immediate/subsequent treatment; S5 and S8 source corrections'},
}

# Figure row order: patient, chemotherapy, added targeted therapy, clinical benefit,
# author final PDTO prediction, Figure S4 panel and row. 1 = good/sensitive, 0 = poor/resistant.
COMMUNITY = (
    ('WCB015', 'FOLFOX', '', 0, 0, 'A', 1),
    ('WCB015', 'FOLFIRI', 'Bevacizumab', 0, 0, 'B', 1),
    ('WCB015', 'TAS102', '', 0, 0, 'B', 2),
    ('WCB027', 'Capecitabine', '', 0, 0, 'A', 2),
    ('WCB027', 'XELOX', '', 1, 1, 'B', 3),
    ('WCB041', 'Capecitabine', '', 0, 0, 'A', 3),
    ('WCB041', 'FOLFIRI', 'Bevacizumab', 1, 1, 'B', 4),
    ('WCB087', '5FU', '', 0, 0, 'A', 4),
    ('WCB091', 'FOLFOX', 'Bevacizumab', 1, 1, 'A', 5),
    ('WCB123', 'FOLFOX', '', 1, 1, 'A', 6),
    ('WCB123', 'FOLFOXIRI', '', 1, 1, 'B', 5),
    ('WCB139', '5FU', 'Bevacizumab', 1, 0, 'A', 7),
    ('WCB139', 'TAS102', '', 0, 0, 'B', 6),
    ('WCB146', '5FU', 'Bevacizumab', 1, 1, 'A', 8),
    ('WCB150', '5FU', 'Bevacizumab', 0, 0, 'A', 9),
    ('WCB150', 'FOLFIRI', '', 0, 0, 'B', 7),
    ('WCB150', 'TAS102', '', 0, 0, 'B', 8),
    ('WCB203', 'Capecitabine', 'Bevacizumab', 1, 1, 'A', 10),
    ('WCB203', 'Irinotecan', '', 1, 0, 'B', 9),
    ('WCB217', 'TAS102', '', 1, 0, 'A', 11),
    ('WCB221', 'FOLFOX', '', 1, 1, 'A', 12),
    ('WCB239', 'FOLFOX', 'Bevacizumab', 0, 1, 'A', 13),
    ('WCB239', 'FOLFIRI', 'Cetuximab', 1, 1, 'B', 10),
    ('WCB242', 'FOLFIRI', 'Panitumumab', 0, 0, 'A', 14),
    ('WCB245', 'FOLFOX', 'Cetuximab', 1, 0, 'A', 15),
    ('WCB254', 'FOLFOXIRI', '', 0, 0, 'A', 16),
    ('WCB254', 'FOLFOX', 'Cetuximab', 0, 0, 'B', 11),
    ('WCB291', '5FU', 'Bevacizumab', 0, 0, 'A', 17),
    ('WCB296', 'FOLFOXIRI', '', 1, 1, 'A', 18),
)
FORECAST = (
    ('WCB250', 'FOLFOX', '', 0, 0, 'A', 19),
    ('WCB251', 'TAS102', '', 0, 0, 'A', 20),
    ('WCB259', 'TAS102', '', 0, 0, 'A', 21),
    ('WCB259', 'CAPOX', '', 0, 0, 'B', 12),
    ('WCB262', 'FOLFIRI', 'Panitumumab', 1, 0, 'A', 22),
    ('WCB272', 'TAS102', '', 0, 0, 'A', 23),
    ('WCB278', 'FOLFIRI', 'Cetuximab', 0, 0, 'A', 24),
    ('WCB281', 'TAS102', '', 0, 0, 'A', 25),
    ('WCB288', 'FOLFOX', 'Bevacizumab', 0, 0, 'A', 26),
    ('WCB311', 'FOLFOX', '', 0, 0, 'A', 27),
)
PIXEL_Y = {
    'gr4.jpg': (391, 416, 441, 466, 491, 516, 541, 566, 590, 615, 641, 666, 691,
                716, 741, 765, 790, 815, 840, 865, 890, 915, 940, 965, 989, 1014, 1039, 1064, 1089),
    'gr5.jpg': (542, 564, 587, 610, 632, 655, 677, 700, 722, 745),
}


def verify_sources(source_dir):
    if source_dir is None:
        return {'status': 'not_requested', 'instruction': 'Pass --source-dir containing gr4.jpg, gr5.jpg and mmc1.pdf.'}
    from PIL import Image
    for filename, metadata in SOURCES.items():
        digest = hashlib.sha256((source_dir / filename).read_bytes()).hexdigest()
        if digest != metadata['sha256']:
            raise ValueError(f'{filename} changed: {digest}')
    # The original image dimensions and coordinates are pinned by their hashes.
    checked = 0
    for filename, records, x in [('gr4.jpg', COMMUNITY, 398), ('gr5.jpg', FORECAST, 405)]:
        with Image.open(source_dir / filename) as image:
            image = image.convert('RGB')
            for row, y in zip(records, PIXEL_Y[filename]):
                r, g, b = image.getpixel((x, y))
                if b > r + 60 and b > g + 30:
                    benefit = 1
                elif r > 180 and g > 90 and b < 70:
                    benefit = 0
                else:
                    raise ValueError(f'Unrecognized clinical-benefit colour: {filename}, y={y}, {(r, g, b)}')
                if benefit != row[3]:
                    raise ValueError(f'Clinical-benefit transcription mismatch: {filename}, {row[0]}, {row[1]}')
                checked += 1
    return {'status': 'verified', 'files': len(SOURCES), 'clinical_benefit_colours_checked': checked}


def clinical_rows(frozen):
    rows = []
    for cohort, figure, records in [('Community', '4B', COMMUNITY), ('FORECAST-1', '5C', FORECAST)]:
        for number, (patient, regimen, targeted, benefit, author, panel, phase_row) in enumerate(records, 1):
            pair = frozen['endpoints']['eligible_regimens'].get(regimen.upper())
            if frozen['patients'][patient]['cohort'] != cohort:
                raise ValueError(f'Cohort mismatch for {patient}')
            rows.append({
                'id': f'{figure}:{number}', 'patient': patient, 'cohort': cohort,
                'regimen': regimen, 'targeted_therapy': targeted or None,
                'clinical_benefit': bool(benefit), 'clinical_label': 'Good response' if benefit else 'Poor response',
                'truth': 'responder' if benefit else 'non_responder',
                'author_prediction': 'responder' if author else 'non_responder',
                'source': f'Figure {figure}, row {number}, patient-response column',
                'phase': 'immediate' if panel == 'A' else 'subsequent',
                'phase_source': f'Figure S4{panel}, row {phase_row}, Document S1 PDF page 5',
                'best_response': None, 'stable_disease_duration_weeks': None,
                'secondary_endpoint_status': 'not_available: only the composite clinical-benefit class is published for this treatment',
                'eligible': pair is not None, 'readout_pair': pair,
                'exclusion_reason': None if pair else f'{regimen} is outside the frozen two-drug regimen map',
                'mapping_note': ('Frozen FOLFOXIRI -> 5-FU + oxaliplatin mapping retained; irinotecan is also in the actual regimen.'
                                 if regimen == 'FOLFOXIRI' else 'Frozen regimen mapping retained.'),
            })
    return rows


def first_per_patient(rows):
    grouped = {}
    for row in rows:
        grouped.setdefault(row['patient'], []).append(row)
    result = []
    for patient, candidates in grouped.items():
        immediate = [r for r in candidates if r['phase'] == 'immediate']
        # Every patient has at most one immediate and at most one subsequent eligible row.
        # Thus S4 suffices without assuming that figure row order is chronological.
        if len(immediate) > 1 or (not immediate and len(candidates) > 1):
            raise ValueError(f'First eligible treatment cannot be resolved for {patient}')
        result.append(immediate[0] if immediate else candidates[0])
    return result


def analyse(name, rows, frozen, median_mode):
    scored = []
    for row in rows:
        table = (frozen['calls']['whole_table_median'] if median_mode == 'whole_table_median'
                 else frozen['calls']['within_cohort_median'][row['cohort']])
        patient = table['patients'][row['patient']]
        a, b = [int(patient['sensitive'][drug]) for drug in row['readout_pair']]
        combo = patient['pairs']['+'.join(row['readout_pair'])]['combination_readout'] == 'responder'
        truth = int(row['clinical_benefit'])
        scored.append({**row, 'calls': [a, b], 'combination_call': int(combo),
                       'released': a == b, 'correct': [a == truth, b == truth],
                       'combination_correct': combo == truth})
    a = [r['calls'][0] for r in scored]
    b = [r['calls'][1] for r in scored]
    truth = [int(r['clinical_benefit']) for r in scored]
    result = setting(name, a, b, truth)
    n = result.pop('patients')  # The common function's unit is a row; here it is a treatment.
    single_correct = [sum(r['correct'][i] for r in scored) for i in (0, 1)]
    combination_correct = sum(r['combination_correct'] for r in scored)
    p1, p2 = [c / n for c in single_correct]
    forecast = p1 * p2 / (p1 * p2 + (1-p1) * (1-p2))
    observed = result['released_correct'] / result['released']
    result.update({
        'treatments': n, 'unique_patients': len({r['patient'] for r in rows}),
        'median_mode': median_mode, 'responders': sum(truth), 'single_correct': single_correct,
        'retest_treatments': n-result['released'],
        'disagreement_wrong_by_single': [sum(not r['released'] and not r['correct'][i] for r in scored) for i in (0, 1)],
        'combination_readout': {'correct': combination_correct, 'treatments': n,
                                'accuracy': round(combination_correct / n, 4)},
        'forecast_gap': round(observed - forecast, 6),
        'release_minus_better_single_accuracy': round(observed - max(p1, p2), 6),
        'loss_per_treatment': {str(cost): round((result['shared_errors'] + cost * (n-result['released'])) / n, 6)
                               for cost in COSTS},
        'single_readout_loss': [round(1-p1, 6), round(1-p2, 6)],
        'formula_check': {'accuracy_sum_gt_one': p1 + p2 > 1,
                          'observed_below_forecast': observed < forecast,
                          'shared_errors_above_independence': result['shared_errors'] > n*(1-p1)*(1-p2),
                          'equivalence_holds': ((observed < forecast) == (result['shared_errors'] > n*(1-p1)*(1-p2)))
                                               if p1+p2 > 1 else None},
        'rows': scored,
    })
    return result


def assertions(analyses):
    primary = analyses['primary']
    n = primary['treatments']
    p1, p2 = [c/n for c in primary['single_correct']]
    p3 = []
    for key, result in analyses.items():
        n2 = result['treatments']
        if min(result['single_correct']) / n2 <= 0.5:
            p3.append({'analysis': key,
                       'holds': result['released_correct']/result['released'] <= max(result['single_correct'])/n2,
                       'observed': [result['released_accuracy'], max(result['readout_accuracy'])]})
    return {
        'P1': {'holds': primary['shared_errors'] > n*(1-p1)*(1-p2),
               'observed': primary['shared_errors'], 'independence_expected': n*(1-p1)*(1-p2)},
        'P2': {'holds': abs(primary['forecast_gap']) <= TOLERANCE,
               'observed_minus_formula': primary['forecast_gap'], 'tolerance': TOLERANCE},
        'P3': {'status': 'evaluated' if p3 else 'not_applicable',
               'holds': all(r['holds'] for r in p3) if p3 else None, 'analyses': p3},
        'P4': {'holds': primary['combination_readout']['correct'] >= max(primary['single_correct']),
               'combination_correct': primary['combination_readout']['correct'],
               'better_single_correct': max(primary['single_correct']), 'treatments': n},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--predictions', type=Path, default=Path(__file__).with_name('blind3_predictions.json'))
    parser.add_argument('--out', type=Path, default=Path(__file__).with_name('blind3_score.json'))
    parser.add_argument('--source-dir', type=Path)
    args = parser.parse_args()
    blob = args.predictions.read_bytes()
    digest = hashlib.sha256(blob).hexdigest()
    if digest != PREDICTIONS_SHA256:
        raise ValueError(f'Frozen predictions changed: {digest}')
    frozen = json.loads(blob)
    source_verification = verify_sources(args.source_dir)
    clinical = clinical_rows(frozen)
    eligible = [r for r in clinical if r['eligible']]
    first = first_per_patient(eligible)
    analyses = {}
    for mode in ('whole_table_median', 'within_cohort_median'):
        for selection, rows in [('all', eligible), ('first', first)]:
            for cohort in ('pooled', 'Community', 'FORECAST-1'):
                subset = rows if cohort == 'pooled' else [r for r in rows if r['cohort'] == cohort]
                key = ('primary' if (mode, selection, cohort) == ('whole_table_median', 'all', 'pooled')
                       else f'{mode}/{selection}/{cohort}')
                analyses[key] = analyse(key, subset, frozen, mode)
    published = {r['patient'] for r in clinical}
    evaluated = {r['patient'] for r in eligible}
    unscored = [{'patient': patient, 'cohort': metadata['cohort'],
                 'reason': ('Only treatments outside the frozen regimen map are published.' if patient in published
                            else 'No patient-linked clinical outcome is published in Figures 4B, 5C or S4.')}
                for patient, metadata in frozen['patients'].items() if patient not in evaluated]
    author_reference = {}
    for cohort in ('Community', 'FORECAST-1'):
        rows = [r for r in clinical if r['cohort'] == cohort]
        author_reference[cohort] = {'treatments': len(rows), 'unique_patients': len({r['patient'] for r in rows}),
                                    'clinical_benefits': sum(r['clinical_benefit'] for r in rows),
                                    'correct': sum(r['truth'] == r['author_prediction'] for r in rows)}
    if author_reference['Community']['correct'] != 24 or author_reference['FORECAST-1']['correct'] != 9:
        raise ValueError('Figure transcription disagrees with the published author totals')
    result = {
        'schema': 'blind3.consensus.score.v1', 'predictions_sha256': digest, 'freeze_commit': FREEZE_COMMIT,
        'article': {'authors': 'Tan et al.', 'year': 2023, 'doi': '10.1016/j.xcrm.2023.101335',
                    'url': 'https://pmc.ncbi.nlm.nih.gov/articles/PMC10783557/', 'license': 'CC BY-NC-ND 4.0'},
        'source_corrections': ['Frozen citation Wang corrected to Tan; frozen files remain unchanged.',
                               'S5 is reference-trial response rates; S8 is PDTO drug-panel predictions.',
                               'Clinical outcomes are from frozen-listed Figures 4B/5C, confirmed by Figure S4.'],
        'sources': {name: {**metadata, 'url': SOURCE_BASE + name} for name, metadata in SOURCES.items()},
        'source_verification': source_verification,
        'clinical_benefit_definition': frozen['endpoints']['clinical_benefit_primary'],
        'readout_order': ['5-FU', 'The frozen regimen-matched partner: oxaliplatin or irinotecan'],
        'formulas': {'independence_release_accuracy': 'p1*p2 / (p1*p2 + (1-p1)*(1-p2))',
                     'independence_shared_errors': 'n*(1-p1)*(1-p2)',
                     'release_loss': '(released_wrong + retest_cost*retest_treatments)/n',
                     'break_even_retest_cost_against_single_i': 'disagreement_wrong_by_single_i / retest_treatments',
                     'p1_p2_denominator': 'Observed accuracy of each single readout on the same eligible treatments.'},
        'units': {'assay_organoid_lines': 103, 'assay_unique_patients': len(frozen['patients']),
                  'published_clinical_treatments': len(clinical), 'published_clinical_patients': len(published),
                  'eligible_treatments': len(eligible), 'eligible_unique_patients': len(evaluated),
                  'excluded_published_treatments': len(clinical)-len(eligible), 'unscored_assay_patients': len(unscored)},
        'analyses': analyses, 'assertions': assertions(analyses), 'clinical_rows': clinical,
        'unscored_frozen_patients': unscored, 'author_reference_transcription_check': author_reference,
        'secondary_endpoints': {name: {'status': 'not_available', 'evaluable_treatments': 0,
                                     'reason': 'Figures 4B/5C/S4 publish only composite clinical benefit. Individual CR/PR/SD/PD and SD durations are absent; benefit cannot reconstruct these endpoints.'}
                               for name in ('disease_control', 'objective_response')},
        'limitations': [
            'This is a third outcome-blinded analysis of already published data, not a new prospective clinical trial.',
            'The validation unit is a treatment: 22 rows come from 18 patients. Repeated treatment lines are not independent patients.',
            'The 101-patient assay pool supplies frozen medians; only 18 patients have an eligible published clinical comparison.',
            'FOLFOXIRI maps to the FOLFOX pair by the frozen rule even though it is a three-drug regimen. Added antibodies are ignored as frozen.',
            'The combination comparator is the frozen median-split pan-matrix readout; the original authors use different cutoffs and include targeted treatment response.',
            'The two cohorts are from one study and share an assay platform. They are organoids, not perfused chips.',
            'Retest-cost calculations assume a resolving retest with the stated cost; no actual retest outcomes or clinical costs were measured.',
        ],
    }
    args.out.write_text(json.dumps(result, indent=1) + '\n')
    keys = ('treatments', 'unique_patients', 'single_correct', 'readout_accuracy', 'released', 'released_correct',
            'released_accuracy', 'released_accuracy_forecast', 'forecast_gap', 'shared_errors',
            'shared_errors_if_independent', 'combination_readout', 'break_even_retest_cost_vs_each_readout')
    print(json.dumps({'units': result['units'], 'analyses': {key: {k: v[k] for k in keys} for key, v in analyses.items()},
                      'assertions': result['assertions'], 'source_verification': source_verification}, indent=1))


if __name__ == '__main__':
    main()

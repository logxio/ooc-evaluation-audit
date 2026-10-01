#!/usr/bin/env python3
"""Post-outcome scope sensitivity of the third frozen-prediction analysis.

Read only blind3_score.json's original primary rows. Compare the original scope,
exclusion of FOLFOXIRI, exclusion of added antibodies, both exclusions, and the
first source-ordered treatment per patient after both exclusions. This is an
exploratory analysis selected after outcomes were seen, not another blind test.
The frozen predictions and the original primary analysis remain unchanged.

Uses only the Python standard library. No source files are downloaded.
"""

import argparse
import hashlib
import json
import resource
import sys
import time
from pathlib import Path

COSTS = (0.1, 0.25)


def first_per_patient(rows):
    """Preserve the source row order; do not invent a new chronological ordering."""
    selected = []
    seen = set()
    for row in rows:
        if row['patient'] not in seen:
            selected.append(row)
            seen.add(row['patient'])
    return selected


def ratio(numerator, denominator):
    return round(numerator / denominator, 8) if denominator else None


def analyse(rows, description):
    n = len(rows)
    scored = []
    for row in rows:
        truth = int(row['truth'] == 'responder')
        a, b = row['calls']
        combination = row['combination_call']
        if any(x not in (0, 1) for x in (truth, a, b, combination)):
            raise ValueError(f"Non-binary call in {row['id']}")
        scored.append({
            key: row[key] for key in ('id', 'patient', 'cohort', 'regimen', 'targeted_therapy',
                                     'source', 'phase', 'phase_source', 'readout_pair', 'truth',
                                     'calls', 'combination_call')
        } | {'correct': [a == truth, b == truth], 'combination_correct': combination == truth,
             'released': a == b, 'released_correct': a == b and a == truth})
    single_correct = [sum(row['correct'][i] for row in scored) for i in (0, 1)]
    singles = [{'correct': correct, 'wrong': n-correct, 'accuracy': ratio(correct, n),
                'loss': ratio(n-correct, n)} for correct in single_correct]
    combo_correct = sum(row['combination_correct'] for row in scored)
    released = sum(row['released'] for row in scored)
    released_correct = sum(row['released_correct'] for row in scored)
    released_wrong = released - released_correct
    retest = n-released
    better = [i for i, correct in enumerate(single_correct) if correct == max(single_correct)]
    best_wrong = n-max(single_correct)
    disagreement_errors = [sum(not row['released'] and not row['correct'][i] for row in scored)
                           for i in (0, 1)]
    costs = {}
    for cost in COSTS:
        loss_numerator = released_wrong + cost*retest
        costs[str(cost)] = {'release_and_retest_loss': ratio(loss_numerator, n),
                           'better_single_loss': ratio(best_wrong, n),
                           'release_minus_better_single_loss': ratio(loss_numerator-best_wrong, n),
                           'release_has_lower_loss': loss_numerator < best_wrong if n else None}
    return {
        'description': description, 'treatments': n, 'unique_patients': len({row['patient'] for row in rows}),
        'clinical_benefits': sum(row['truth'] == 'responder' for row in rows),
        'single_readouts': singles,
        'combination_readout': {'correct': combo_correct, 'wrong': n-combo_correct, 'accuracy': ratio(combo_correct, n)},
        'released': {'treatments': released, 'correct': released_correct, 'wrong': released_wrong,
                     'accuracy': ratio(released_correct, released), 'coverage': ratio(released, n)},
        'retest_treatments': retest,
        'better_single_indices_zero_based': better,
        'disagreement_errors_by_single': disagreement_errors,
        'break_even_retest_cost_vs_better_single': ratio(disagreement_errors[better[0]], retest) if n else None,
        'break_even_numerator': disagreement_errors[better[0]] if n else None,
        'break_even_denominator': retest,
        'cost_analysis': costs,
        'row_ids': [row['id'] for row in rows], 'rows': scored,
    }


def main():
    start = time.perf_counter()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--score', type=Path, default=Path(__file__).with_name('blind3_score.json'))
    parser.add_argument('--out', type=Path, default=Path(__file__).with_name('blind3_sensitivity.json'))
    args = parser.parse_args()
    blob = args.score.read_bytes()
    source = json.loads(blob)
    rows = source['analyses']['primary']['rows']
    no_triplet = [row for row in rows if row['regimen'] != 'FOLFOXIRI']
    no_antibody = [row for row in rows if row['targeted_therapy'] is None]
    strict = [row for row in rows if row['regimen'] != 'FOLFOXIRI' and row['targeted_therapy'] is None]
    definitions = {
        'original_primary': (rows, 'All original primary-analysis treatments.'),
        'exclude_folfoxiri': (no_triplet, 'Exclude regimen == FOLFOXIRI; retain added antibodies.'),
        'exclude_added_antibody': (no_antibody, 'Exclude targeted_therapy != null; retain FOLFOXIRI.'),
        'exclude_both': (strict, 'Exclude FOLFOXIRI and all non-null targeted_therapy.'),
        'strict_first_per_patient': (first_per_patient(strict),
                                     'After both exclusions, keep each patient\'s first retained row in original source order.'),
    }
    groups = {key: analyse(selected, description) for key, (selected, description) in definitions.items()}
    primary_ids = {row['id'] for row in rows}
    for key, group in groups.items():
        retained = set(group['row_ids'])
        group['excluded_row_ids'] = [row['id'] for row in rows if row['id'] in primary_ids-retained]
    peak_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    result = {
        'schema': 'blind3.scope_sensitivity.v1',
        'analysis_status': 'Exploratory post-outcome scope sensitivity; not a new blind test or a replacement primary analysis.',
        'source_file': 'blind3_score.json', 'source_score_sha256': hashlib.sha256(blob).hexdigest(),
        'source_predictions_sha256': source['predictions_sha256'], 'source_freeze_commit': source['freeze_commit'],
        'input_field': 'analyses.primary.rows',
        'readout_order': source['readout_order'],
        'added_antibody_values': sorted({row['targeted_therapy'] for row in rows if row['targeted_therapy'] is not None}),
        'formulas': {'accuracy': 'correct / evaluated treatments; released accuracy uses released treatments only',
                     'release_and_retest_loss': '(released_wrong + cost * retest_treatments) / treatments',
                     'single_loss': 'single_wrong / treatments',
                     'break_even_cost': 'disagreement errors of the better single readout / retest_treatments',
                     'cost_assumption': 'A retest resolves the call correctly at the stated relative cost; actual retests were not observed.'},
        'groups': groups,
        'limitations': [
            'The exclusion scopes were chosen after clinical outcomes and the primary result were available.',
            'The original frozen calls, thresholds, regimen mapping and primary score are unchanged.',
            'Treatments from the same patient are not independent patients.',
            'The last group preserves source order; phase and phase_source are retained for review.',
            'These small subsets describe scope dependence and do not establish a new prospective clinical performance guarantee.',
        ],
        'execution': {'elapsed_seconds_before_serialization': round(time.perf_counter()-start, 6),
                      'peak_resident_bytes': int(peak_rss if sys.platform == 'darwin' else peak_rss*1024)},
    }
    args.out.write_text(json.dumps(result, indent=2) + '\n')
    brief = {key: {k: value for k, value in group.items() if k not in ('rows', 'row_ids', 'excluded_row_ids')}
             for key, group in groups.items()}
    print(json.dumps({'groups': brief, 'execution': result['execution']}, indent=2))


if __name__ == '__main__':
    main()

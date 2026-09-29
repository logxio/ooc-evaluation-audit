#!/usr/bin/env python3
"""Predict what the two-readout release rule will do from each readout's own accuracy.

Two closed-form results, checked on the six cohort settings used in the report.

1. Break-even identity. Against either readout used alone, releasing only agreed calls pays
   off exactly when the retest cost is below the share of disagreements that readout gets
   wrong. With binary calls exactly one readout is wrong in every disagreement, so the two
   break-even costs sum to 1: the rule beats both readouts only when the retest cost is below
   the smaller share, which is never above 0.5.
2. Independence forecast. If the two readouts err independently, with accuracies p1 and p2,
   a share p1*p2 + (1-p1)*(1-p2) of patients is released and a released call is right with
   probability p1*p2 / (p1*p2 + (1-p1)*(1-p2)). That beats the better readout exactly when the
   weaker readout is better than a coin flip (min(p1, p2) > 0.5). When the readouts fail on
   the same patients, released calls are less accurate than forecast.
"""

import argparse
import json
from pathlib import Path

import blind_consensus_score as blind
from channel_consensus import one_condition
from chip_clinic import (FIGURE_SHA256, FIGURE_URL, PATIENTS, SOURCE_SHA256, SOURCE_URL,
                         read_chip, read_clinical, source_bytes)
from consensus_external import POST_NAT, PRE_NAT


def setting(name, a, b, truth):
    n = len(truth)
    right_a = [x == t for x, t in zip(a, truth)]
    right_b = [y == t for y, t in zip(b, truth)]
    p1, p2 = sum(right_a) / n, sum(right_b) / n
    agree = [x == y for x, y in zip(a, b)]
    released = sum(agree)
    correct = sum(g and ra for g, ra in zip(agree, right_a))
    shared = sum(not ra and not rb for ra, rb in zip(right_a, right_b))
    disagree = n - released
    both, neither = p1 * p2, (1 - p1) * (1 - p2)
    forecast = both / (both + neither)
    observed = correct / released
    b1 = sum(not g and not ra for g, ra in zip(agree, right_a)) / disagree if disagree else None
    b2 = sum(not g and not rb for g, rb in zip(agree, right_b)) / disagree if disagree else None
    return {'setting': name, 'patients': n, 'readout_accuracy': [round(p1, 4), round(p2, 4)],
            'released': released, 'released_correct': correct,
            'released_forecast': round(n * (both + neither), 2),
            'released_accuracy': round(observed, 4), 'released_accuracy_forecast': round(forecast, 4),
            'shared_errors': shared, 'shared_errors_if_independent': round(n * neither, 2),
            'beats_better_readout': observed > max(p1, p2),
            'beats_better_readout_forecast': min(p1, p2) > 0.5,
            'break_even_retest_cost_vs_each_readout': [round(b1, 4), round(b2, 4)] if disagree else None,
            'break_even_sum': round(b1 + b2, 9) if disagree else None}


def blind_rows(frozen, words, tag):
    rows = []
    for cohort, table in (('biliary', blind.BILIARY), ('gastric', blind.GASTRIC)):
        _, scored = blind.score(table, cohort, frozen, words)
        ev = [r for r in scored if r['evaluable']]
        drugs = [list(r['single'].values()) for r in ev]
        rows.append(setting(f'blind {cohort} organoids{tag}', [int(d[0] == 'responder') for d in drugs],
                            [int(d[1] == 'responder') for d in drugs], [int(r['truth'] == 'responder') for r in ev]))
    return rows


def fit(rows):
    errors = [abs(r['released_accuracy'] - r['released_accuracy_forecast']) for r in rows]
    return {'settings': len(rows),
            'released_accuracy_mean_absolute_error': round(sum(errors) / len(errors), 4),
            'released_accuracy_max_absolute_error': round(max(errors), 4),
            'beats_better_readout_forecast_right': sum(r['beats_better_readout'] == r['beats_better_readout_forecast'] for r in rows),
            'break_even_sums_equal_one': all(abs(r['break_even_sum'] - 1) < 1e-9 for r in rows if r['break_even_sum'] is not None)}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--source-zip', type=Path, help='local Dai source ZIP')
    parser.add_argument('--figure', type=Path, help='local Dai Figure 5 image')
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    chip = read_chip(source_bytes(args.source_zip, SOURCE_URL, SOURCE_SHA256))
    clinical = read_clinical(source_bytes(args.figure, FIGURE_URL, FIGURE_SHA256))
    truth = [clinical[p] for p in PATIENTS]
    rows = []
    for condition in ('optimized', 'original'):
        _, details = one_condition(condition, chip, truth)
        rows.append(setting(f'colorectal chip, {condition}', details['vessel_calls'], details['tumoroid_calls'], truth))
    for name, table in (('osteosarcoma organoids, post-treatment', POST_NAT),
                        ('osteosarcoma organoids, pre-treatment', PRE_NAT)):
        table = [r for r in table if r[4] != 'NA']
        rows.append(setting(name, [int(r[1] == 'S') for r in table],
                            [int(r[2] in ('II', 'III')) for r in table], [int(r[4] == 'CR') for r in table]))
    frozen = json.loads(Path('blind_predictions.json').read_text())
    registered = {k: tuple(v) for k, v in frozen['outcome_words']['disease_control_primary'].items()}
    amended = {k: registered[k] + blind.AMENDMENT.get(k, ()) for k in registered}
    rows += blind_rows(frozen, amended, '')
    sensitivity = blind_rows(frozen, registered, ', registered words only')
    result = {'schema': 'release.theory.v1', 'settings': rows, 'fit': fit(rows),
              'blind_registered_words': sensitivity, 'blind_registered_words_fit': fit(sensitivity)}
    if args.out:
        args.out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()

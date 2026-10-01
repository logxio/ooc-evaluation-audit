#!/usr/bin/env python3
"""One prespecified pooled-signal experiment on the existing patient split.

All three historical cohorts have previously seen outcomes. This comparison is
retrospective, and supplies an independently trained candidate for new outcomes.
"""
import argparse
import hashlib
import json
from pathlib import Path

from calibration_replay import sources, split, SEED
from pooled_signal import fit_pooled, score, certify, summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--third-xlsx', type=Path)
    p.add_argument('--out', type=Path, default=Path('pooled_replay.json'))
    p.add_argument('--freeze', type=Path, default=Path('pooled_replay_frozen.json'))
    args = p.parse_args()
    data = sources(args.third_xlsx)
    splits = {s: split(s, rows) for s, rows in data.items()}
    model = fit_pooled({s: rows[0] for s, rows in splits.items()})
    frozen = {'schema': 'release.pooled_replay.freeze.v1', 'model': model,
              'split_seed': SEED, 'status': 'retrospective previously seen outcomes', 'sources': {}}
    for s, (training, cal, test) in splits.items():
        frozen['sources'][s] = {'test_ids': [r['patient'] for r in test], 'methods': {}}
        unlabelled = [{'patient': r['patient'], 'x': r['x']} for r in test]
        for method in ('pooled', 'fixed_single'):
            certificate = certify(model, s, training, cal, method=method)
            cal_cases, future = score(model, s, cal, method), score(model, s, unlabelled, method)
            modes = {}
            for mode, threshold in [('uncontrolled', -1.), ('overall', certificate['overall_margin']),
                                    ('conditional', certificate['conditional_margin'])]:
                pilot = summary(cal_cases, cal, threshold)
                accepted = sum(c['margin'] > threshold for c in future)
                modes[mode] = {'margin': threshold, 'forecast': {
                    'release_count_from_unlabelled_inputs': accepted,
                    'retest_count_from_unlabelled_inputs': len(test) - accepted,
                    'calibration_accuracy_smoothed': (pilot['released'] - pilot['wrong_released'] + .5) / (pilot['released'] + 1) if pilot['released'] else None,
                    'calibration': pilot,
                    'scope': 'Point forecast; threshold selection can make calibration accuracy optimistic.'}}
            frozen['sources'][s]['methods'][method] = {'certificate': certificate, 'cases': future, 'modes': modes}
    args.freeze.write_text(json.dumps(frozen, indent=2, allow_nan=False) + '\n')
    freeze_sha = hashlib.sha256(args.freeze.read_bytes()).hexdigest()
    result = {'schema': 'release.pooled_replay.result.v1', 'frozen_sha256': freeze_sha,
              'model_sha256': model['model_sha256'], 'alpha': .1, 'joint_delta': .05,
              'status': frozen['status'], 'sources': {},
              'comparison': 'Fixed single readout is trained on source training only and releases everyone. The risk-matched ablation wraps that same signal in the identical CRC/LTT calibration. Only comparisons with the same risk definition can establish gain.'}
    for s, (_, _, test) in splits.items():
        result['sources'][s] = {}
        for method, detail in frozen['sources'][s]['methods'].items():
            result['sources'][s][method] = {mode: dict(summary(detail['cases'], test, val['margin']),
                margin=val['margin'], forecast=val['forecast']) for mode, val in detail['modes'].items()}
        pooled = result['sources'][s]['pooled']['overall']
        base = result['sources'][s]['fixed_single']['overall']
        result['sources'][s]['overall_matched_difference'] = {
            'released': pooled['released'] - base['released'],
            'coverage': pooled['coverage'] - base['coverage'],
            'wrong_released': pooled['wrong_released'] - base['wrong_released'],
            'both_observed_overall_within_alpha': pooled['overall_wrong_release'] <= .1 and base['overall_wrong_release'] <= .1}
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print(json.dumps({s: {m: {mode: {k: v for k, v in row.items() if k != 'forecast'} for mode, row in rows.items()}
                         if m != 'overall_matched_difference' else rows
                         for m, rows in methods.items()} for s, methods in result['sources'].items()}, indent=2))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Export the frozen nested run's point predictions and paper-facing tables."""
import argparse
import csv
import gzip
import json
import time
from pathlib import Path

import numpy as np

import paper_nested_decision as nd


def percent(x):
    return 'undefined (zero releases)' if x is None else f'{100*x:.2f}%'


def main(out):
    start = time.monotonic()
    nd.limits()
    result = nd.load(out / 'summary.json')
    nd.read_run(out)
    calibration_rows = []
    for fold in range(5):
        folder = out / f'fold{fold}'
        cert = nd.load(folder / 'calibration.json')
        for row in nd.load(folder / 'calibration_design_decisions.json'):
            for method in nd.METHODS:
                row[method + '_release'] = row[method + '_margin'] > cert[method]['margin']
            row['observed_active_fallback_call'] = int(row['measured_only'] < 3.)
            row['observed_active_fallback_release'] = row['measured_only'] >= 3.
            calibration_rows.append(row)
    nd.write_csv(out / 'calibration_drug_decisions.csv', nd.drug_rows(calibration_rows))
    nd.write_csv(out / 'calibration_design_decisions.csv', [dict(r, context_levels=';'.join(map(str, r['context_levels'])),
        context_logc=';'.join(map(str, r['context_logc']))) for r in calibration_rows])
    target = out / 'point_predictions.csv.gz'
    count = 0
    with gzip.open(target, 'wt', newline='') as f:
        w = csv.writer(f)
        w.writerow(['outer_fold', 'chemical', 'drug_group', 'design', 'level', 'log10_uM', 'DIV', 'feature',
                    'reference_available', 'reference_level_mean', 'anchorboost', 'anchorboost_lower', 'anchorboost_upper',
                    'loglinear', 'loglinear_lower', 'loglinear_upper'])
        ids = nd.load(out / 'identities.json')
        for fold in range(5):
            with np.load(out / f'fold{fold}' / 'test_scored_points.npz') as archive:
                p = {key: archive[key] for key in archive.files}
            for row in range(len(p['chemical'])):
                chem = str(p['chemical'][row])
                for day in range(4):
                    for feature in range(17):
                        mask = bool(p['mask'][row, day, feature])
                        val = [float(p[key][row, day, feature]) for key in
                               ['anchorboost', 'anchorboost_lower', 'anchorboost_upper', 'loglinear', 'loglinear_lower', 'loglinear_upper']]
                        w.writerow([fold, chem, ids[chem]['drug_group'], int(p['design'][row]), int(p['level'][row]),
                                    float(p['logc'][row]), nd.DAYS[day], nd.FEATURES[feature], int(mask),
                                    float(p['truth'][row, day, feature]) if mask else '', *val])
                        count += 1
    primary = result['primary_folds_1_to_4']
    methods = primary['methods']
    title = {'anchorboost': 'AnchorBoost + group CRC', 'loglinear': 'Log-linear + group CRC',
             'measured_only': 'Three measured points + group CRC', 'observed_active_fallback': 'Observed-active release; otherwise full measurement'}
    lines = ['# Retrospective drug-disjoint release evaluation', '',
             f"Primary folds 1–4 contain {primary['drugs']} drug groups, {primary['substances']} substances and {primary['designs']} alternative three-point designs. All five outer folds were completed; historical development fold 0 is reported separately.", '',
             '| Method | Released/designs | Wrong/all designs | Wrong/released | Full-coverage wrong/designs | Drug-mean wrong-release loss | Exposed wells used | Savings vs full | Savings vs three-point calibrated fallback |',
             '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for key, m in methods.items():
        lines.append(f"| {title[key]} | {m['released']}/{primary['designs']} ({percent(m['release_rate'])}) | {m['wrong_released']}/{primary['designs']} ({percent(m['error_all_designs'])}) | {m['wrong_released']}/{m['released']} ({percent(m['error_released'])}) | {m['full_coverage_errors']}/{primary['designs']} ({percent(m['full_coverage_error_rate'])}) | {percent(m['drug_mean_loss'])} | {m['wells_used']} | {percent(m['savings_vs_full'])} | {percent(m['savings_vs_measured_only_fallback'])} |")
    lines += ['', f"The full-series baseline uses {primary['full_measurement']['wells_used']} exposed wells across these alternative designs. Agreement with its own reference equals one by construction. Controls, repeats and overhead are outside all exposed-well counts.", '',
              '| Outer fold | Test drug groups | Test designs | AB release | AB wrong/all | AB wrong/released | AB drug loss | Measured-only release | Measured-only wrong/all |',
              '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for fold, value in result['by_fold'].items():
        a, b = value['methods']['anchorboost'], value['methods']['measured_only']
        lines.append(f"| {fold} | {value['drugs']} | {value['designs']} | {percent(a['release_rate'])} | {percent(a['error_all_designs'])} | {percent(a['error_released'])} | {percent(a['drug_mean_loss'])} | {percent(b['release_rate'])} | {percent(b['error_all_designs'])} |")
    lines += ['', '| Outer fold | Calibration drugs | AB margin | Corrected calibration loss | Feasible grid value |',
              '|---|---:|---:|---:|---|']
    for fold in range(5):
        cert = nd.load(out / f'fold{fold}' / 'calibration.json')['anchorboost']
        lines.append(f"| {fold} | {cert['calibration_drugs']} | {cert['margin']} | {percent(cert['corrected_risk'])} | {cert['finite_grid_feasible']} |")
    lines += ['', 'Margin −1 releases every design. Folds 2–4 selected it from calibration data. Every fitted fold had a feasible margin; the insufficient-calibration all-fallback branch is covered by the arithmetic check. Realized drug loss in fold 3 is 10.22%; in historical development fold 0 it is 10.20%.']
    lines += ['', '## Paired primary comparisons', '',
              'Differences are AnchorBoost minus comparator, with 4,000 drug bootstrap resamples at fixed fitted decisions. Intervals do not include refitting uncertainty.', '',
              '| Comparator | Drug loss difference [95% interval] | Release difference [95% interval] | Full-coverage error difference [95% interval] |',
              '|---|---:|---:|---:|']
    for key, stats in result['primary_paired_drug_bootstrap'].items():
        def text(metric):
            item = stats[metric]
            return f"{100*item['difference']:+.2f} pp [{100*item['ci95'][0]:+.2f}, {100*item['ci95'][1]:+.2f}]"
        lines.append(f"| {title[key]} | {text('drug_loss')} | {text('release_rate')} | {text('full_coverage_error_rate')} |")
    lines += ['', '## Historical replay, separate experiment', '',
              '| Method | Designs | Released | Wrong releases | Error/all | Error/released | Exposed wells used | Savings vs full |',
              '|---|---:|---:|---:|---:|---:|---:|---:|']
    for key in ['anchorboost', 'measured_only']:
        old = result['legacy_970_design_replay'][key]
        lines.append(f"| {key} | {old['designs']} | {old['released']} | {old['wrong_released']} | {percent(old['overall_wrong_release'])} | {percent(old['released_error'])} | {old['wells_used']} | {percent(old['wells_saved_fraction'])} |")
    a = methods['anchorboost']
    paired = result['primary_paired_drug_bootstrap']['measured_only']
    # This comparator has zero wrong-release loss for each drug, so its paired
    # bootstrap difference is also an absolute interval for AnchorBoost's loss.
    risk_ci = result['primary_paired_drug_bootstrap']['observed_active_fallback']['drug_loss']['ci95']
    decision = {'observed_drug_mean_loss_at_or_below_alpha': a['drug_mean_loss'] <= nd.ALPHA,
                'positive_release_gain_lower_bootstrap_bound': paired['release_rate']['ci95'][0] > 0,
                'lower_full_coverage_error_upper_bootstrap_bound': paired['full_coverage_error_rate']['ci95'][1] < 0,
                'conditional_error_at_or_below_alpha_descriptive_only': a['error_released'] is not None and a['error_released'] <= nd.ALPHA,
                'guarantee_interpretation': 'Theoretical marginal expected drug-risk statement requires independent training and exchangeable calibration/future groups. These retrospective, batch-sharing, historically stratified folds do not establish that condition.',
                'prospective_lab_savings_evidence': False,
                'drug_mean_loss_bootstrap_ci95_fixed_decisions': risk_ci,
                'drug_loss_upper_bootstrap_bound_at_or_below_alpha': risk_ci[1] <= nd.ALPHA,
                'point_prediction_rows': count,
                'point_predictions_sha256': nd.sha(target)}
    nd.dump(out / 'claim_assessment.json', decision)
    lines += ['', '## Claim scope', '',
              f"Observed primary drug loss at alpha=0.10: {decision['observed_drug_mean_loss_at_or_below_alpha']}. Positive release gain with a bootstrap lower bound above zero: {decision['positive_release_gain_lower_bootstrap_bound']}. Lower full-coverage error with an upper bound below zero: {decision['lower_full_coverage_error_upper_bootstrap_bound']}.", '',
              f"The primary drug-loss bootstrap interval at fixed decisions is [{percent(risk_ci[0])}, {percent(risk_ci[1])}]. Its upper end exceeds 10%. The supported empirical claim is increased release and lower exposed-well replay cost, with the observed risk and its uncertainty reported alongside the benefit.", '',
              'These are retrospective empirical comparisons. The mathematical CRC statement concerns expected marginal drug loss under exchangeability. Error among released designs, each realized batch risk, prospective laboratory savings, donor generalization and independent batch generalization remain different claims. Normalization and conservative identity grouping changed relative to the historical replay, so the difference between old and new totals does not isolate the effect of correcting a single leak.', '',
              'Implementation and artifacts: `protocol.json`, `splits.json`, `identities.json`, per-fold `pretest_freeze.json` and `prediction_freeze.json`, `point_predictions.csv.gz`, `drug_decisions.csv`, `design_decisions.csv`, `summary.json`, `verification.json`, and `data_flow.md`.', '']
    (out / 'results.md').write_text('\n'.join(lines))
    nd.dump(out / 'export_runtime.json', nd.runtime(start))
    print(json.dumps(decision, indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', required=True, type=Path)
    main(p.parse_args().out)

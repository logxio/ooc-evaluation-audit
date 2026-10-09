#!/usr/bin/env python3
"""Reaggregate frozen liver-chip predictions, replay paths and planning curves.

No estimators are loaded or fitted. Replay checks use saved state predictions;
calibration planning is recomputed from saved cross-fitted residuals. The saved
state predictions are authenticated inputs, not fresh model inference.
"""
import csv
import hashlib
import json
import math
import resource
import sys
import time
from collections import defaultdict
from fractions import Fraction
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = ROOT / 'results/final/bircsak'
CAPACITY = ROOT / 'results/capacity'
METHODS = ('selected', 'interpolation', 'fixed50')


def js(path):
    return json.loads(path.read_text())


def rows(path):
    with path.open(newline='') as f:
        return list(csv.DictReader(f))


def close(a, b):
    assert math.isclose(float(a), float(b), abs_tol=1e-8, rel_tol=1e-9), (a, b)


def verify_hashes():
    manifest = js(BASE / 'manifest.json')
    for name, digest in manifest['files'].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
    return len(manifest['files'])


def frozen_sha(path):
    """Validate public bytes and return the frozen pre-redaction digest."""
    relative = str(path.relative_to(ROOT))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    matches = [r for r in js(ROOT / 'results/REDACTIONS.json')['files'] if r['path'] == relative]
    if matches:
        assert len(matches) == 1 and digest == matches[0]['redacted_sha256']
        return matches[0]['original_sha256']
    return digest


def grouped(records, keys):
    out = defaultdict(list)
    for r in records:
        out[tuple(r[k] for k in keys)].append(r)
    return out


def initial():
    predictions = rows(CAPACITY / 'bircsak_run_v1/scored_predictions.csv')
    saved = js(CAPACITY / 'bircsak_run_v1/scores.json')
    curves = grouped(predictions, ('compound', 'endpoint', 'method'))
    choices = {(r['compound'], r['endpoint'], r['method']): r for r in rows(CAPACITY / 'bircsak_run_v1/choices.csv')}
    contexts = grouped(rows(CAPACITY / 'bircsak_packet/test_contexts.csv'), ('compound', 'endpoint'))
    out = {}
    for method in METHODS:
        coverage, maes, decisions, full_width = {}, defaultdict(list), defaultdict(int), defaultdict(list)
        for (drug, endpoint, m), pp in curves.items():
            if m != method:
                continue
            errors = [abs(float(r['prediction']) - float(r['reference'])) for r in pp]
            for r, error in zip(pp, errors):
                close(error, r['absolute_error'])
            covered = all(float(r['lower']) <= float(r['reference']) <= float(r['upper']) for r in pp)
            coverage[drug] = coverage.get(drug, True) and covered
            maes[endpoint].append(sum(errors) / len(errors))
            choice = choices[drug, endpoint, method]
            threshold = float(choice['threshold'])
            observed = [float(r['value']) for r in contexts[drug, endpoint]]
            if min(observed) <= threshold or any(float(r['upper']) <= threshold for r in pp):
                decision = 'report_reduction'
            elif min(observed) > threshold and all(float(r['lower']) > threshold for r in pp):
                decision = 'report_no_reduction'
            else:
                decision = 'measure_next'
            assert decision == choice['decision']
            decisions[decision] += 1
            full_width[endpoint].append(sum(float(r['upper']) - float(r['lower']) for r in pp) / len(pp))
        out[method] = dict(test_drugs=len(coverage), test_curves=sum(decisions.values()),
                           covered_drugs=sum(coverage.values()), drug_coverage=sum(coverage.values()) / len(coverage),
                           decisions=dict(decisions), mae={e: sum(v) / len(v) for e, v in maes.items()},
                           full_width={e: sum(v) / len(v) for e, v in full_width.items()})
        expected = next(x for x in saved['coverage'] if x['method'] == method)
        close(out[method]['drug_coverage'], expected['fraction'])
        for endpoint, value in out[method]['mae'].items():
            close(value, next(r['mae'] for r in saved['summary'] if r['method'] == method and r['endpoint'] == endpoint))
    return out


def replay():
    folder = BASE / 'sequential_replay'
    saved = js(folder / 'summary.json')
    terminal = rows(folder / 'terminal_paths.csv')
    steps = rows(folder / 'steps.csv')
    assert [r for r in steps if r['terminal'] == 'True'] == terminal
    reference = grouped(rows(CAPACITY / 'bircsak_packet/reference_reveal.csv'), ('compound', 'endpoint'))
    ref = {(drug, ep): {r['point_id']: r for r in rr} for (drug, ep), rr in reference.items()}
    initial_counts = {key: 3 for key in ref}
    for r in steps:
        key = r['compound'], r['endpoint']
        obs = [float(ref[key][i]['value']) for i in r['observed_point_ids'].split('|')]
        pp = json.loads(r['predictions_json'])
        threshold = float(r['threshold'])
        if min(obs) <= threshold or any(p['upper'] <= threshold for p in pp):
            decision = 'report_reduction'
        elif min(obs) > threshold and all(p['lower'] > threshold for p in pp):
            decision = 'report_no_reduction'
        else:
            decision = 'measure_next'
        assert r['decision'] == decision
        assert int(r['measured_count']) == len(obs)
        assert (r['terminal'] == 'True') == (decision != 'measure_next')
        n = len(ref[key]) - initial_counts[key]
        k = int(r['step'])
        weight = Fraction(math.factorial(n - k), math.factorial(n)) if r['policy'] == 'uniform_random' else Fraction(1)
        assert Fraction(r['reach_probability_exact']) == weight
        if decision != 'measure_next':
            truth = any(float(x['value']) <= threshold for x in ref[key].values())
            assert (r['correct'] == 'True') == ((decision == 'report_reduction') == truth)
            assert (r['early'] == 'True') == (len(obs) < len(ref[key]))
    metrics = ('hidden_used', 'measured_used', 'saved', 'early', 'wrong', 'early_wrong', 'reduction')
    per_curve = {}
    for key, rr in grouped(terminal, ('compound', 'endpoint', 'method', 'policy')).items():
        totals = {k: Fraction() for k in metrics}
        assert sum(Fraction(r['reach_probability_exact']) for r in rr) == 1
        for r in rr:
            w = Fraction(r['reach_probability_exact'])
            measured, full = int(r['measured_count']), int(r['full_count'])
            early, wrong = measured < full, r['correct'] != 'True'
            vals = (measured - 3, measured, full - measured, early, wrong, early and wrong, r['decision'] == 'report_reduction')
            for metric, value in zip(metrics, vals):
                totals[metric] += w * int(value)
        per_curve[key] = totals
    for row in rows(folder / 'curve_summary.csv'):
        key = tuple(row[x] for x in ('compound', 'endpoint', 'method', 'policy'))
        for metric, value in per_curve[key].items():
            assert Fraction(row[metric + '_exact']) == value
    out = {}
    for method, policies in saved['methods'].items():
        out[method] = {}
        for policy, cell in policies.items():
            totals = {m: sum((v[m] for k, v in per_curve.items() if k[2:] == (method, policy)), Fraction()) for m in metrics}
            for metric, value in totals.items():
                assert Fraction(cell[metric + '_exact']) == value
                close(cell[metric], value)
            out[method][policy] = {k: float(v) for k, v in totals.items()}
    zero = saved['zero_width_counterfactual']
    assert zero['reports'] == len(zero['per_curve']) == 12
    assert zero['wrong'] == sum(not r['correct'] for r in zero['per_curve']) == 7
    # Reconstruct the zero-width calls from the frozen prediction centers.
    pred = grouped(rows(CAPACITY / 'bircsak_run_v1/scored_predictions.csv'), ('compound', 'endpoint', 'method'))
    for r in zero['per_curve']:
        key = r['compound'], r['endpoint']
        hit = any(float(p['prediction']) <= r['threshold'] for p in pred[*key, 'selected'])
        assert r['decision'] == ('report_reduction' if hit else 'report_no_reduction')
        truth = any(float(p['value']) <= r['threshold'] for p in ref[key].values())
        assert r['correct'] == (hit == truth)
    return dict(curves=len(ref), initial_measurements=3 * len(ref),
                hidden_measurements=sum(len(v) - 3 for v in ref.values()),
                full_measurements=sum(len(v) for v in ref.values()),
                methods=out, zero_width_reports=zero['reports'], zero_width_wrong=zero['wrong'])


@lru_cache(maxsize=None)
def binomial_tail(n, k, numerator, denominator):
    p = numerator / denominator
    if p == 1:
        return 1.0
    return math.fsum(math.comb(n, j) * p ** j * (1 - p) ** (n - j) for j in range(k, n + 1))


def quant(values, weights, probability):
    total = 0.0
    for v, w in sorted(zip(values, weights), key=lambda x: x[0]):
        total += w
        if total >= probability - 1e-14:
            return v
    return max(values)


def calibration(initial_result):
    folder = BASE / 'calibration_size'
    scores = rows(folder / 'scores.csv')
    errors = defaultdict(list)
    for r in rows(folder / 'crossfit_predictions.csv'):
        error = abs(float(r['prediction']) - float(r['reference'])) / float(r['scale'])
        close(error, r['normalized_error'])
        errors[r['compound'], r['method']].append(error)
    for r in scores:
        for method in METHODS:
            close(max(errors[r['compound'], method]), r[method + '_score'])
    margins = rows(folder / 'decision_margins.csv')
    predictions = grouped(rows(CAPACITY / 'bircsak_run_v1/scored_predictions.csv'), ('compound', 'endpoint', 'method'))
    for r in margins:
        pp = predictions[r['compound'], r['endpoint'], r['method']]
        threshold, scale = float(r['threshold']), float(r['scale'])
        minimum = min(float(p['prediction']) for p in pp)
        close(abs(minimum - threshold) / scale, r['q_max'])
        assert r['call_at_zero_width'] == ('report_reduction' if minimum <= threshold else 'report_no_reduction')
    distributions = {}
    for key, rr in grouped(rows(folder / 'resampling_distribution.csv'), ('method', 'coverage', 'n')).items():
        method, coverage, n = key[0], float(key[1]), int(key[2])
        k = ((n + 1) * 9 + 9) // 10 if coverage == .9 else ((n + 1) * 4 + 4) // 5
        support = sorted(float(r[method + '_score']) for r in scores)
        if k > n:
            values, weights = [math.inf], [1.0]
        else:
            cdf = [binomial_tail(n, k, j, len(scores)) for j in range(1, len(scores) + 1)]
            values = support
            weights = [max(0.0, b - a) for a, b in zip([0.0] + cdf[:-1], cdf)]
        assert len(rr) == len(values)
        for r, v, w in zip(rr, values, weights):
            close(v, r['q'])
            close(w, r['probability'])
        distributions[key] = values, weights
    for r in rows(folder / 'width_curve.csv'):
        values, weights = distributions[r['method'], r['coverage'], r['n']]
        mm = [x for x in margins if x['method'] == r['method'] and x['endpoint'] == r['endpoint']]
        scale = sum(float(x['scale']) for x in mm) / len(mm)
        close(scale, r['mean_context_scale'])
        for label, probability in (('p10', .1), ('median', .5), ('p90', .9)):
            q = quant(values, weights, probability)
            close(q, r['normalized_halfwidth_' + label])
            close(q * scale, r['halfwidth_' + label])
            close(2 * q * scale, r['full_width_' + label])
    decisions = rows(folder / 'decision_curve.csv')
    for r in decisions:
        values, weights = distributions[r['method'], r['coverage'], r['n']]
        mm = [x for x in margins if x['method'] == r['method'] and (r['endpoint'] == 'ALL' or x['endpoint'] == r['endpoint'])]
        counts, wrong = [], []
        for q in values:
            resolved = [x for x in mm if q < float(x['q_max']) or (q == float(x['q_max']) and x['resolvable_when_q'] == '<=')]
            counts.append(len(resolved))
            wrong.append(sum((x['call_at_zero_width'] == 'report_reduction') != (x['truth_reduction'] == 'True') for x in resolved))
        for label, probability in (('p10', .1), ('median', .5), ('p90', .9)):
            close(quant(counts, weights, probability), r['resolvable_' + label])
        close(sum(v * w for v, w in zip(counts, weights)), r['resolvable_mean'])
        close(sum(v * w for v, w in zip(wrong, weights)), r['posthoc_wrong_reports_mean'])
        for label, threshold in (('at_least_one', 1), ('strict_majority', len(mm) // 2 + 1), ('all', len(mm))):
            close(sum(w for v, w in zip(counts, weights) if v >= threshold), r['p_' + label])
    summary = js(folder / 'summary.json')
    for r in summary['original_n9_anchor']:
        close(r['full_width'], initial_result['selected']['full_width'][r['endpoint']])
    selected = [r for r in decisions if r['method'] == 'selected' and r['endpoint'] == 'ALL']
    return dict(n_drugs=len(scores), n_min=min(int(r['n']) for r in selected), n_max=max(int(r['n']) for r in selected),
                selected_max_resolvable_median=max(int(r['resolvable_median']) for r in selected),
                selected_total_curves=12,
                selected_width_checkpoints=summary['selected_width_checkpoints'],
                original_n9_anchor=summary['original_n9_anchor'],
                verified_width_rows=len(rows(folder / 'width_curve.csv')), verified_decision_rows=len(decisions))


def calculate():
    for name in ('sequential_replay', 'calibration_size'):
        assert frozen_sha(BASE / name / 'protocol.json') == js(BASE / name / 'summary.json')['protocol_sha256']
    result = initial()
    return dict(initial=result, sequential_replay=replay(), calibration_size=calibration(result))


def main():
    assert len(sys.argv) == 2 and sys.argv[1] in ('summarize', 'verify'), 'Use: python paper_final_bircsak.py summarize'
    start = time.monotonic()
    hashes = verify_hashes()
    result = calculate()
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == 'darwin' else 1024)
    assert rss < 1_000_000_000
    print(json.dumps(dict(status='verified', input_hashes=hashes, new_fits=0,
                          replay_mode='aggregation and decision checks from authenticated saved predictions',
                          seconds=time.monotonic() - start, peak_rss_bytes=rss, tables=result), indent=2))


if __name__ == '__main__':
    main()

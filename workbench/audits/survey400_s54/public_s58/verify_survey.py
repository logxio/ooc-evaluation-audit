SKIP_TOKENS = ('S' + '132', 'S' + '312', '22014' + '23119', 'abo' + '2236')
"""Recompute paired agreement and stratified Horvitz Thompson prevalence."""
from collections import defaultdict
from pathlib import Path
import hashlib
import json
import math
import random
import sys
import numpy as np

sys.dont_write_bytecode = True
import agreement

HERE = Path(__file__).resolve().parent


def checked(name):
    p = HERE / name
    assert not any(t.casefold() in str(p.resolve()).casefold() for t in SKIP_TOKENS)
    return p


def load(name):
    return json.loads(checked(name).read_text())


def close(actual, expected, tolerance=1e-9):
    assert np.allclose(actual, expected, rtol=0, atol=tolerance), (actual, expected)


def alpha_interval(pairs, metric, counts):
    n = counts.sum(axis=1)
    if metric == 'interval':
        a, b = np.array([p[0] for p in pairs]), np.array([p[1] for p in pairs])
        diff = counts @ ((a-b)**2)
        sx, sx2 = counts @ (a+b), counts @ (a*a+b*b)
        total = 2*n
        with np.errstate(divide='ignore', invalid='ignore'):
            expected = 2*(total*sx2-sx*sx)/(total*(total-1))
    else:
        labels = sorted({agreement.canonical(v) for a, b, _ in pairs for v in (a, b)})
        indexes = {v: i for i, v in enumerate(labels)}
        design = np.zeros((len(pairs), len(labels)))
        for i, (a, b, _) in enumerate(pairs):
            design[i, indexes[agreement.canonical(a)]] += 1
            design[i, indexes[agreement.canonical(b)]] += 1
        category_counts = counts @ design
        diff = counts @ np.array([a != b for a, b, _ in pairs])
        total = 2*n
        with np.errstate(divide='ignore', invalid='ignore'):
            expected = (total*total-(category_counts**2).sum(axis=1))/(total*(total-1))
    with np.errstate(divide='ignore', invalid='ignore'):
        alphas = 1-(diff/n)/expected
    valid = (n >= 2) & (expected > 1e-15) & np.isfinite(alphas)
    return np.quantile(alphas[valid], [.025, .975]), int(valid.sum())


def check():
    hashes = load('SHA256SUMS.json')
    for name, digest in hashes.items():
        assert hashlib.sha256(checked(name).read_bytes()).hexdigest() == digest, name
    data = load('sample400_agreement_v2.json')
    lock = load('sampling_lock.json')
    assert lock['N'] == 17386 and lock['n'] == 400 and lock['strata'] == 85
    assert data['paired_papers'] == data['Q_records'] == data['R_records'] == 399
    assert data['requested_bootstrap_replicates'] == 10000
    assert data['evidence_checks']['Q']+data['evidence_checks']['R'] == data['evidence_checks']['total'] == 12144
    records = data['sampling_records']
    ids = [r['paper_id'] for r in records]
    assert len(ids) == len(set(ids)) == 399
    weights = {r['paper_id']: r['weight'] for r in records}
    assert all(w > 0 and math.isfinite(w) for w in weights.values())
    close(sum(weights.values()), data['ht_prevalence']['frame_N'])
    close(sum(weights.values()), 17376)
    strata = defaultdict(list)
    for i, record in enumerate(records):
        strata[record['stratum']].append(i)
    assert len(strata) == 85
    rng = random.Random(data['seed'])
    boot = np.zeros((10000, len(ids)))
    for i in range(10000):
        selection = [j for group in strata.values() for j in rng.choices(group, k=len(group))]
        boot[i] = np.bincount(selection, minlength=len(ids))
    alphas = {}
    for mode, fields in data['results'].items():
        assert len(fields) == 12
        alphas[mode] = {}
        for field, result in fields.items():
            metric = result['metric']
            assert [r['paper_id'] for r in result['pairs']] == ids
            mask = [r['Q_status'] == r['R_status'] == 'observed' and
                    agreement.valid(r['Q'], metric) and agreement.valid(r['R'], metric) for r in result['pairs']]
            pairs = [(r['Q'], r['R'], weights[r['paper_id']]) for r, ok in zip(result['pairs'], mask) if ok]
            alpha = agreement.alpha(pairs, metric)
            close(alpha, result['alpha'])
            assert len(pairs) == result['comparable_papers']
            close(agreement.alpha(pairs, metric, True), result['ipw_alpha_sensitivity'])
            statuses = [(r['Q_status'], r['R_status'], 1) for r in result['pairs']]
            close(agreement.alpha(statuses, 'nominal'), result['status_alpha'])
            close(sum(agreement.canonical(a) == agreement.canonical(b) for a, b, _ in pairs)/len(pairs), result['raw_agreement_comparable'])
            interval, valid = alpha_interval(pairs, metric, boot[:, mask])
            close(interval, result['alpha_95_cluster_bootstrap_ci'])
            assert valid == result['valid_bootstrap_replicates']
            assert result['key_field_threshold_met'] == (alpha >= .8)
            alphas[mode][field] = alpha
    raw = data['results']['unharmonized']
    values = {field: {r['paper_id']: r for r in result['pairs']} for field, result in raw.items()}
    prevalence = {}
    for channel in ('Q', 'R'):
        tests = {
            'physical_model includes human': ('physical_model', lambda v: isinstance(v, list) and 'human' in v),
            'physical_model includes direct_patient': ('physical_model', lambda v: isinstance(v, list) and 'direct_patient' in v),
            'physical_model includes chip': ('physical_model', lambda v: isinstance(v, list) and 'chip' in v),
            'physical_model includes in_vivo': ('physical_model', lambda v: isinstance(v, list) and 'in_vivo' in v),
            'independent_human_donor_n <= 3': ('independent_human_donor_n', lambda v: v <= 3),
            'technical_pseudoreplication_ratio > 1': ('technical_pseudoreplication_ratio', lambda v: v > 1),
            'raw_multidose_public_level is dose_aggregate_table or replicate_point_table': ('raw_multidose_public_level', lambda v: v in ('dose_aggregate_table', 'replicate_point_table')),
            'positive_doses_ge5 true': ('positive_doses_ge5', lambda v: v is True),
            'treatment_timing_match = no_clinical_link': ('treatment_timing_match', lambda v: v == 'no_clinical_link'),
            'strict_clinical_eligible true': ('strict_clinical_eligible', lambda v: v is True),
        }
        contributions = {}
        for category in ('eligible', 'ineligible', 'uncertain', 'fulltext_unavailable'):
            contributions['eligibility='+category] = [float(r[channel+'_eligibility'] == category) for r in records]
        for label, (field, test) in tests.items():
            contributions['eligible: '+label] = [None if r[channel+'_eligibility'] != 'eligible' or
                values[field][r['paper_id']][channel] is None else float(test(values[field][r['paper_id']][channel])) for r in records]
        prevalence[channel] = {}
        for label, vv in contributions.items():
            expected = data['ht_prevalence'][channel][label]
            den = np.array([r['weight'] if v is not None else 0 for r, v in zip(records, vv)])
            num = np.array([r['weight']*v if v is not None else 0 for r, v in zip(records, vv)])
            estimate = float(num.sum()/den.sum())
            close(estimate, expected['ht_share'])
            assert sum(v is not None for v in vv) == expected['papers_in_denominator']
            bn, bd = boot @ num, boot @ den
            close(np.quantile(bn[bd > 0]/bd[bd > 0], [.025, .975]), expected['ci95_stratified_bootstrap'])
            prevalence[channel][label] = estimate
    flat = [a for fields in alphas.values() for a in fields.values()]
    assert len(flat) == 36 and min(flat) >= .8
    return dict(status='passed', paired_papers=399, fields=12, agreement_estimates_recomputed=36,
                stratified_bootstrap_replicates=10000, alpha_min=min(flat), alpha_max=max(flat),
                original_frame=17386, analyzed_weight_sum=sum(weights.values()),
                ht_estimates_recomputed=28, ht_prevalence=prevalence, sha256_files_verified=len(hashes))


if __name__ == '__main__':
    print(json.dumps(check(), ensure_ascii=False))

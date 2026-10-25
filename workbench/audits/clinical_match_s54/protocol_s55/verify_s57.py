SKIP_TOKENS = ('S' + '132', 'S' + '312', '22014' + '23119', 'abo' + '2236')
"""Recompute patient AUC, study isolation and fixed budget summary estimates."""
from collections import defaultdict
from pathlib import Path
import hashlib
import json
import math
import numpy as np
from scipy.stats import rankdata
from scipy.special import expit

HERE = Path(__file__).resolve().parent


def checked(name):
    p = HERE / name
    assert not any(t.casefold() in str(p.resolve()).casefold() for t in SKIP_TOKENS)
    return p


def load(name):
    return json.loads(checked(name).read_text(), parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))


def groups(rows, eligible=True):
    result = defaultdict(list)
    for row in rows:
        assert row['y'] in (0, 1) and math.isfinite(row['x'])
        result[row['study']].append(row)
    return {s: g for s, g in result.items()
            if not eligible or min(sum(r['y'] for r in g), sum(1-r['y'] for r in g)) >= 2}


def auc(group):
    positive = [r['x'] for r in group if r['y'] == 1]
    negative = [r['x'] for r in group if r['y'] == 0]
    return sum((p < n) + .5*(p == n) for p in positive for n in negative) / (len(positive)*len(negative))


def bootstrap(rows, replicates=10000, seed=20261024):
    cohort = list(groups(rows).values())
    rng = np.random.default_rng(seed)
    values, denominator = np.zeros(replicates), np.zeros(replicates)
    for _ in range(len(cohort)):
        choices = rng.integers(0, len(cohort), replicates)
        for i, group in enumerate(cohort):
            indexes = np.flatnonzero(choices == i)
            x = np.array([r['x'] for r in group])
            y = np.array([r['y'] for r in group])
            m, n = int(y.sum()), int((1-y).sum())
            difference = x[y == 0][None, :] - x[y == 1][:, None]
            kernel = (difference > 0).astype(float) + .5*(difference == 0)
            wp = rng.multinomial(m, np.full(m, 1/m), len(indexes))
            wn = rng.multinomial(n, np.full(n, 1/n), len(indexes))
            values[indexes] += np.einsum('bi,ij,bj->b', wp, kernel, wn, optimize=True)
            denominator[indexes] += m*n
    weights = [sum(r['y'] for r in g)*sum(1-r['y'] for r in g) for g in cohort]
    return dict(auc=float(np.average([auc(g) for g in cohort], weights=weights)),
                ci95=np.quantile(values/denominator, [.025, .975]).tolist(), replicates=replicates)


def close(a, b, tolerance=1e-11):
    assert np.allclose(a, b, atol=tolerance, rtol=0), (a, b)


def check():
    hashes = load('SHA256SUMS.json')
    for name, digest in hashes.items():
        assert hashlib.sha256(checked(name).read_bytes()).hexdigest() == digest, name
    rows = load('j3_expanded_cohort.json')
    clinical = load('j3_expanded_loso.json')
    budget = load('j2_budget_monte_carlo.json')
    assert len(rows) == len({(r['study'], r['patient']) for r in rows}) == clinical['numeric_patients'] == 243
    assert clinical['matched_patients'] == len(rows) + sum(
        s.get('matched_new', 0) for s in clinical['source_audit'] if s.get('numeric_auc_cluster') is False
    ) + len(clinical['ren_occluded_curve_patients']) == 248
    cohort = groups(rows)
    assert len(cohort) == clinical['qualifying_clusters'] == budget['study_clusters'] == 8
    assert set(cohort) == set(clinical['loso'])
    for study, group in groups(rows, False).items():
        expected = clinical['by_study'][study]
        assert len(group) == expected['n'] and sum(r['y'] for r in group) == expected['favourable']
        if study in cohort:
            close(auc(group), expected['auc'])
    estimates = {}
    complete = [r for r in rows if r.get('match_kind', 'complete_exposure') in
                ('complete_exposure', 'active_metabolite', 'active_moiety_matrix')]
    assert len(complete) == 185 and len(groups(complete)) == 5
    for name, subset, expected in (
        ('pooled', rows, clinical['pooled_study_stratified_auc']),
        ('complete_exposure', complete, clinical['sensitivities']['complete_exposure_or_active_moiety']['auc']),
    ):
        result = bootstrap(subset)
        close(result['auc'], expected['auc'])
        close(result['ci95'], expected['ci95'])
        estimates[name] = result
    errors = []
    for study, item in clinical['loso'].items():
        assert study not in item['training_studies']
        assert set(item['training_studies']) == set(cohort) - {study}
        actual = {r['patient']: r for r in cohort[study]}
        assert len(item['predictions']) == len(actual) == item['n']
        assert len({p['patient'] for p in item['predictions']}) == len(actual)
        predictions = item['predictions']
        close([p['percentile'] for p in predictions], (rankdata([actual[p['patient']]['x'] for p in predictions])-.5)/len(actual))
        intercept, slope = item['training_logistic_coefficients']
        probabilities = np.array([p['p_favourable'] for p in predictions])
        outcomes = np.array([p['y'] for p in predictions])
        assert all(p['y'] == actual[p['patient']]['y'] for p in predictions)
        close(probabilities, expit(intercept-slope*np.array([p['percentile'] for p in predictions])))
        error = (probabilities-outcomes)**2
        errors.extend(error)
        close(float(error.mean()), item['brier'])
        pb, yb = probabilities.mean(), outcomes.mean()
        terms = dict(squared_mean_bias=(pb-yb)**2, forecast_variance=np.var(probabilities),
                     outcome_variance=np.var(outcomes), minus_twice_forecast_outcome_covariance=
                     -2*np.mean((probabilities-pb)*(outcomes-yb)))
        for key, value in terms.items():
            close(value, item['brier_decomposition'][key])
        close(sum(terms.values()), item['brier_decomposition']['sum'])
        close(auc([dict(x=-p['p_favourable'], y=p['y']) for p in predictions]), item['heldout_prediction_auc'])
    close(float(np.sqrt(np.mean(errors))), clinical['clinical_prediction_RMSE'])
    assert budget['draws'] == budget['bootstrap_replicates'] == 10000
    assert budget['cohort_sha256'] == clinical['source_sha256']['cohort'] == hashes['j3_expanded_cohort.json']
    deltas = {}
    for wells, block in budget['budgets'].items():
        assert set(block['by_study']) == set(cohort)
        for study, item in block['by_study'].items():
            assert item['n'] == len(cohort[study]) and item['favourable'] == sum(r['y'] for r in cohort[study])
            assert item['non_saturated'] == (item['n'] > (int(wells)-6)//30)
            assert item['adaptive_gate']['fit_uses_clinical_outcomes'] is False
            assert item['adaptive_gate']['held_out_data_used'] is False
            for design, result in item['designs'].items():
                assert result['mean_total_wells'] <= int(wells) and result.get('max_total_wells', 0) <= int(wells)
                if design in ('D_sparse', 'D_gate', 'D_gate_adaptive'):
                    diagnostics = result['paired_delong_all_intent_to_test']
                    assert diagnostics['attempted_draws'] == diagnostics['valid_class_draws'] == 10000
                    close(diagnostics['delta_mean'], result['itt_auc_mean']-item['designs']['D_dense']['itt_auc_mean'])
                    common = result['paired_delong_same_tested_patients']
                    assert common['valid_class_draws']+common['invalid_class_draws'] == common['attempted_draws'] == 10000
        selected = [s for s, item in block['by_study'].items() if item['non_saturated']]
        primary = block['non_saturated_primary']
        assert selected == primary['study_ids'] and len(selected) == primary['study_clusters']
        deltas[wells] = {}
        for design, expected in primary['paired_pooled_cluster_bootstrap'].items():
            weights = [block['by_study'][s]['favourable'] * (block['by_study'][s]['n']-block['by_study'][s]['favourable']) for s in selected]
            ds = [block['by_study'][s]['designs'][design]['itt_auc_mean'] -
                  block['by_study'][s]['designs']['D_dense']['itt_auc_mean'] for s in selected]
            delta = float(np.average(ds, weights=weights))
            close(delta, expected['delta_auc'])
            assert expected['ci95'][0] <= expected['ci95'][1]
            deltas[wells][design] = delta
        queue = block['multicentre_primary']
        assert set(queue['studies']) == set(cohort) and queue['budget_allocation_uses_outcomes'] is False
        for result in queue['whole_queue_design_costs'].values():
            assert result['mean_total_wells'] <= int(wells) and result.get('max_total_wells', 0) <= int(wells)
    for wells, expected in (('96', .0286), ('192', .0577), ('384', .0994)):
        assert round(deltas[wells]['D_sparse'], 4) == expected
    assert round(deltas['96']['D_single'], 4) == .1605
    return dict(status='passed', matched_patients=248, numeric_patients=243, study_clusters=8,
                complete_exposure_patients=185, complete_exposure_clusters=5, auc_estimates=estimates,
                loso_study_isolation=True, brier_decomposition_recomputed=True,
                monte_carlo_draws_per_released_summary=10000,
                monte_carlo_summary_deltas_reaggregated=deltas, sha256_files_verified=len(hashes))


if __name__ == '__main__':
    print(json.dumps(check(), ensure_ascii=False))

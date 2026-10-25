SKIP_TOKENS = ('S' + '132', 'S' + '312', '22014' + '23119', 'abo' + '2236')
"""Recompute acquisition totals, paired bootstrap and drift scenario summaries."""
import collections
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

HERE = Path(__file__).resolve().parent
ARTIFACT_HASHES = {
    'artifacts/final_v3_jci.json': 'a2ea69cf8a8488d9b7873394c9b181aced7b783766c70c6b8b292fce269d1e8d',
    'artifacts/final_v3_jci.rows.json': 'd4d31502bb9cc8cf689c4d093c17ee2c500f64fa67ef043f4d63cfd417ec9ddc',
    'artifacts/final_v3_jci_drift_sensitivity.json': 'c5a6dcc467c62163171becd7613972ed5679b747356d5d7940dcb7fccbadbd45',
}


def checked(name):
    p = HERE / name
    assert not any(t.casefold() in str(p.resolve()).casefold() for t in SKIP_TOKENS)
    return p


def sha(p):
    return hashlib.sha256(checked(p).read_bytes()).hexdigest()


def check():
    expected_hashes = ARTIFACT_HASHES
    if checked('receipt.json').is_file():
        receipt = json.loads(checked('receipt.json').read_text())
        assert all(receipt['files_sha256'][name] == digest for name, digest in expected_hashes.items())
    for name, expected in expected_hashes.items():
        assert sha(name) == expected, name
    f = json.loads(checked('artifacts/final_v3_jci.json').read_text())
    rows = json.loads(checked('artifacts/final_v3_jci.rows.json').read_text())
    drift = json.loads(checked('artifacts/final_v3_jci_drift_sensitivity.json').read_text())
    assert sha('artifacts/final_v3_jci.json') == drift['original_final_sha256']
    assert len(rows) == f['curves'] == 240
    assert sum(r['truth'] for r in rows) == f['actives'] == 237
    assert sum(r['w_FG'] for r in rows) == f['FG_wells'] == 7200
    for name in ('TW', 'TW_S', 'D1'):
        assert sum(r['w_' + name] for r in rows) == f['arms'][name]['wells']
        assert sum(r['miss_' + name] for r in rows) == f['arms'][name]['misses']
    for name in ('MODEL', 'MO'):
        w = sum(r['w_' + name] for r in rows)
        miss = sum(r['miss_' + name] for r in rows)
        assert w == f['arms'][name]['wells']
        assert miss == f['arms'][name]['misses']
        assert abs(1 - w / 7200 - f['arms'][name]['saving']) < 1e-14
        assert sum(r['wave1_' + name] for r in rows) == 2160
        assert sum(r['cert_rank_' + name] in ('in', 'out') for r in rows) == f['arms'][name]['ranking']['rank_certified']
        by_drug = collections.defaultdict(list)
        for r in rows:
            by_drug[r['drug']].append(r)
        hits = certified_correct = 0
        ar, ir = [], []
        for rr in by_drug.values():
            k = math.ceil(.2 * len(rr))
            a = {r['curve_id'] for r in sorted(rr, key=lambda r: r['auc_fg'])[:k]}
            b = {r['curve_id'] for r in sorted(rr, key=lambda r: r['auc_' + name])[:k]}
            hits += len(a & b)
            certified_correct += sum((r['cert_rank_' + name] == 'in' and r['curve_id'] in a) or
                                     (r['cert_rank_' + name] == 'out' and r['curve_id'] not in a) for r in rr)
            ar.append(float(spearmanr([r['auc_fg'] for r in rr], [r['auc_' + name] for r in rr]).statistic))
            ir.append(float(spearmanr([r['ic50_fg'] for r in rr], [r['ic50_' + name] for r in rr]).statistic))
        assert hits == f['arms'][name]['ranking']['topk_hits']
        assert certified_correct == f['arms'][name]['ranking']['rank_certified_correct']
        assert abs(float(np.mean(ar)) - f['arms'][name]['ranking']['spearman_mean']) < 1e-14
        assert abs(float(np.mean(ir)) - f['arms'][name]['ranking']['spearman_ic50_mean']) < 1e-14
    # Reconstruct the exact locked paired stratified cluster bootstrap.
    strata = collections.defaultdict(lambda: collections.defaultdict(list))
    for i, r in enumerate(rows):
        strata[r['stratum']][r['material'], r['batch']].append(i)
    rng = np.random.default_rng(55)
    ci = collections.defaultdict(list)
    fg = np.array([r['w_FG'] for r in rows])
    wm = np.array([r['w_MODEL'] for r in rows])
    wo = np.array([r['w_MO'] for r in rows])
    for _ in range(10000):
        ix = []
        for clusters in strata.values():
            keys = list(clusters)
            for j in rng.integers(0, len(keys), len(keys)):
                ix.extend(clusters[keys[j]])
        den = fg[ix].sum()
        ci['saving_MODEL'].append(1 - wm[ix].sum() / den)
        ci['saving_MO'].append(1 - wo[ix].sum() / den)
        ci['model_minus_mo'].append((wo[ix].sum() - wm[ix].sum()) / den)
    for k, values in ci.items():
        assert np.max(np.abs(np.quantile(values, [.025, .975]) - f['ci95'][k])) < 1e-14, k
    assert f['success'] == dict(model_vs_mo=True, total=True, miss=True, ranking=False, all=False)
    assert len(drift['scenarios']) == 3 * 77 * 4
    for name in ('MODEL', 'MO'):
        assert drift['self_checks'][name]['zero_drift_auc_max_abs'] == 0
        assert drift['self_checks'][name]['zero_drift_ic50_max_abs'] == 0
        assert drift['self_checks'][name]['unacquired_response_mutation_invariant']
    for e, modes in drift['summary'].items():
        for mode, s in modes.items():
            selected = [r for r in drift['scenarios'] if r['endpoint'] == e and r['mode'] == mode]
            assert len(selected) == 77
            assert {r['draw'] for r in selected} == set(range(77))
            for name in ('MODEL', 'MO'):
                valid = [r['arms'][name] for r in selected if r['arms'][name]['valid']]
                assert len(valid) == s['arms'][name]['valid_scenarios'] == 77
                bridge = f['arms'][name]['bridge_wells']
                extra = bridge if mode == 'two_control_affine_diagnostic' else 0
                assert all(r['wells'] == f['arms'][name]['wells'] + extra for r in valid)
                for key, stats in s['arms'][name]['metrics'].items():
                    a = [r[key] for r in valid]
                    assert abs(float(np.mean(a)) - stats['mean']) < 1e-12
                    assert np.max(np.abs(np.quantile(a, [.025, .975]) - stats['p025_p975'])) < 1e-12
    return dict(status='passed', curve_rows=240, active_curves=237, FG_wells=7200,
                independent_bootstrap_B=10000, bootstrap_seed=55,
                bootstrap_saving_and_net_CIs_exact=True,
                baseline_TopK_AUC_IC50_exact=True, sensitivity_scenarios=924,
                sensitivity_summary_and_cost_reconciliation=True,
                artifact_hashes_verified=len(expected_hashes))


if __name__ == '__main__':
    print(json.dumps(check(), ensure_ascii=False))

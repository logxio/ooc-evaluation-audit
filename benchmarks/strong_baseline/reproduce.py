#!/usr/bin/env python3
"""Offline recomputation from released predictions and published score subsets."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import resource
import sys
import time
import numpy as np

BASE = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_text())


def table(path):
    with path.open(newline='') as f:
        return list(csv.DictReader(f))


def paired(rows, tolerance=1e-12, replicates=10000):
    """Each row is an independent identity: (sort key, fold, K, comparator)."""
    rows = sorted(rows)
    a, b = np.array([[r[2], r[3]] for r in rows], dtype=np.float64).T
    d = a-b
    assert np.isfinite(d).all() and len({r[0] for r in rows}) == len(rows)
    rng = np.random.default_rng(0)
    draws = np.array([d[rng.integers(0, len(d), len(d))].mean() for _ in range(replicates)])
    folds = {str(f): float(np.mean([r[2]-r[3] for r in rows if r[1] == f]))
             for f in sorted({r[1] for r in rows})}
    return dict(n=len(rows), K_mae=float(a.mean()), comparator_mae=float(b.mean()),
                delta=float(d.mean()), ci95=np.percentile(draws, [2.5, 97.5]).tolist(),
                ci97_5=np.percentile(draws, [1.25, 98.75]).tolist(),
                relative_change_pct=float(100*d.mean()/b.mean()),
                wins=int((d < -tolerance).sum()), losses=int((d > tolerance).sum()),
                ties=int((np.abs(d) <= tolerance).sum()), fold_deltas=folds,
                fold_wins=sum(v < -tolerance for v in folds.values()),
                fold_losses=sum(v > tolerance for v in folds.values()),
                fold_ties=sum(abs(v) <= tolerance for v in folds.values()),
                bootstrap_replicates=replicates, bootstrap_seed=0)


def check_stats(actual, expected, n, delta, k, c, ci='ci95'):
    assert actual['n'] == expected[n]
    for a, b in [('delta', delta), ('K_mae', k), ('comparator_mae', c), ('ci95', ci)]:
        np.testing.assert_allclose(actual[a], expected[b], rtol=0, atol=1e-11,
                                   err_msg=f'Released result mismatch: {a}')


def nfa():
    rows = table(BASE/'nfa/per_chemical.csv')
    main = [(r['chemical'], int(r['fold']), float(r['K_linux_curve_mae']),
             float(r['C_published_curve_mae'])) for r in rows]
    result = dict(primary=paired(main, 0),
                  identity_sensitivity=paired([r for r in main if r[0] != 'Phenobarbital'], 0))
    stored = read(BASE/'nfa/result.json')
    for key in result:
        check_stats(result[key], stored[key], 'n_source_chemicals', 'mean_difference', 'K_mean', 'C_mean')
    replay = {}
    point_count = valid_count = 0
    for fold in range(1, 5):
        with np.load(BASE/f'nfa/fold{fold}.npz', allow_pickle=False) as z:
            chem, design, mask, truth = z['chemical'], z['design'], z['observed'], z['truth']
            predictions = {k:z[k] for k in ('K', 'C', 'interpolation')}
            assert all(np.isfinite(x).all() for x in predictions.values())
            assert (z['fold'] == fold).all()
            point_count += len(chem); valid_count += int(mask.sum())
            for name in np.unique(chem):
                values = []
                for d in sorted(np.unique(design[chem == name])):
                    sel = (chem == name) & (design == d)
                    values.append([float(np.abs(pred[sel]-truth[sel])[mask[sel]].mean())
                                   for pred in predictions.values()])
                assert len(values) == 5
                replay[str(name)] = np.mean(values, axis=0)
    gaps = []
    for r in rows:
        expected = [float(r[k]) for k in ('K_cached_curve_mae', 'C_replayed_curve_mae', 'interpolation_curve_mae')]
        # Saved arrays use float32; original reductions can use float64 predictions.
        gap = np.max(np.abs(replay[r['chemical']]-expected))
        assert gap < 1e-6, (r['chemical'], gap)
        gaps.append(float(gap))
    result['pointwise_verification'] = dict(concentration_rows=point_count, observed_output_cells=valid_count,
                                           max_replay_roundoff=max(gaps),
                                           main_estimate='Original published K and C score columns; pointwise replay retained separately.')
    return result


def source_means(x, y, mask):
    levels = np.unique(x); ix = np.searchsorted(levels, x)
    num = np.zeros((len(levels), *y.shape[1:])); den = np.zeros_like(num)
    np.add.at(num, ix, y*mask); np.add.at(den, ix, mask)
    return levels, np.where(den > 0, num/np.maximum(den, 1), 0).astype(np.float32), den > 0


def contexts(chemical, levels):
    rng = np.random.default_rng(int(hashlib.sha256(f'{chemical}|3'.encode()).hexdigest()[:8], 16))
    seen = set(); result = []
    for _ in range(20):
        lv = tuple(sorted(rng.choice(levels, size=3, replace=False).tolist()))
        if lv not in seen:
            seen.add(lv); result.append(np.array(lv, np.float32))
        if len(result) == 5:
            break
    return result


def external(screen, raw=None):
    base = BASE/'external'
    protocol = read(base/'protocol.json')
    meta = [m for m in read(base/'tasks.json') if m['screen'] == screen]
    stored = read(base/screen/'result.json')
    published = {r['chemical']:r for r in stored['records']}
    rows = []; observed = 0
    with np.load(base/'tasks.npz', allow_pickle=False) as source:
        for fold in range(5):
            path = raw/f'fold{fold}/predictions.npz' if raw else base/screen/f'fold{fold}.npz'
            with np.load(path, allow_pickle=False) as saved:
                for m in (m for m in meta if m['fold'] == fold):
                    key = m['key']
                    levels, mu, ok = source_means(source[key+'_logc'], source[key+'_y'], source[key+'_m'])
                    errors = []; subsets = {g:[] for g in ('hNP1', 'hN2')} if screen == 'harrill' else {}
                    for i, ctx in enumerate(contexts(m['chemical'], levels)):
                        prefix = f'{key}_design{i}_'
                        query, truth, mask = (saved[prefix+s] for s in ('query', 'truth', 'mask'))
                        held = ~np.isin(levels, ctx)
                        for a, b in [(saved[prefix+'context'], ctx), (query, levels[held]),
                                     (truth, mu[held]), (mask, ok[held])]:
                            assert np.array_equal(a, b), (screen, m['chemical'], i, 'input mismatch')
                        pred = [saved[prefix+s] for s in ('k', 'c', 'interp')]
                        assert all(np.isfinite(p).all() for p in pred)
                        errors.append([float(np.abs(p-truth)[mask].mean()) for p in pred])
                        observed += int(mask.sum())
                        for group in subsets:
                            columns = np.array([e.startswith(group+'_') for e in m['endpoints']])
                            sm = mask[:,:,columns]
                            if sm.any():
                                subsets[group].append([float(np.abs(p[:,:,columns]-truth[:,:,columns])[sm].mean()) for p in pred])
                    assert len(errors) == 5
                    values = np.mean(errors, axis=0)
                    if raw is None:
                        np.testing.assert_allclose(values, [published[m['chemical']][k] for k in ('k_mae','c_mae','interp_mae')], rtol=0, atol=1e-12)
                    rows.append(dict(chemical=m['chemical'], identity=m['identity'], fold=fold, values=values,
                                     subgroups={g:np.mean(v, axis=0) if v else None for g,v in subsets.items()}))
    excluded = {e['chemical'] for e in protocol['exclusions'] if e['screen'] == screen}
    clean = [r for r in rows if r['chemical'] not in excluded]
    def grouped(items, identity=True, subgroup=None):
        groups = {}
        for row in items:
            values = row['values'] if subgroup is None else row['subgroups'][subgroup]
            if values is None:
                continue
            key = row['identity'] if identity else row['chemical']
            groups.setdefault(key, []).append((row['fold'], values))
        return [(key, v[0][0] if len({r[0] for r in v}) == 1 else -1,
                 float(np.mean([r[1][0] for r in v])), float(np.mean([r[1][1] for r in v]))) for key,v in groups.items()]
    result = dict(primary=paired(grouped(clean)), all_original_labels=paired(grouped(rows, False)),
                  all_identity_clusters=paired(grouped(rows)), exclusions=sorted(excluded),
                  subgroups={g:paired(grouped(clean, subgroup=g)) for g in ('hNP1', 'hN2')} if screen == 'harrill' else {},
                  source_labels=len(rows), observed_targets_across_designs=observed,
                  folds={str(f):paired(grouped([r for r in clean if r['fold']==f])) for f in range(5)})
    if raw is None:
        for key in ('primary', 'all_original_labels', 'all_identity_clusters'):
            check_stats(result[key], stored[key], 'n_independent_units', 'delta', 'k_mae', 'c_mae')
        for group in result['subgroups']:
            check_stats(result['subgroups'][group], stored['subgroups'][group], 'n_independent_units', 'delta', 'k_mae', 'c_mae')
    return result


def ablation(raw=None):
    base = BASE/'ablation'; records = []; budgets = []
    for fold in range(1, 5):
        full = read((raw or base)/f'full_fold{fold}.json')
        five = read((raw or base)/f'fold{fold}.json')
        assert full['environment'] == five['environment']
        for key in ('training_rows', 'iterations', 'feature_width', 'row_iteration_budget'):
            assert full['timing'][key] == five['timing'][key]
        assert full['timing']['iterations'] == 600 and full['timing']['feature_width'] == 22
        budgets.append(dict(fold=fold, **{k:full['timing'][k] for k in ('training_rows', 'iterations', 'feature_width', 'row_iteration_budget')}))
        five_rows = {r['chemical']:r for r in five['rows']}
        assert set(five_rows) == {r['chemical'] for r in full['rows']}
        for row in full['rows']:
            control = five_rows[row['chemical']]
            assert len(row['contexts']) == len(control['contexts']) == 5
            for a,b in zip(row['contexts'],control['contexts']):
                assert a['context_log_concentration'] == b['context_log_concentration']
                assert a['target_log_concentration'] == b['target_log_concentration']
                assert a['n_valid_scalar_targets'] == b['n_valid_scalar_targets']
            a = float(np.mean([d['curve_mae'] for d in row['contexts']]))
            b = float(np.mean([d['curve_mae'] for d in control['contexts']]))
            assert abs(a-row['rerun_full_curve_mae']) < 1e-12 and abs(b-control['five_matched_curve_mae']) < 1e-12
            records.append((row['chemical'], fold, a, b))
    result = dict(primary=paired(records), budgets=budgets)
    if raw is None:
        check_stats(result['primary'], read(base/'result.json')['primary'], 'n_chemicals', 'mean_delta', 'full_curve_mae', 'five_matched_curve_mae')
    original = {r['chemical']:r for r in table(base/'source/published_full.csv') if r['method']=='anchorboost' and r['k']=='3'}
    control = {r['chemical']:r for r in table(base/'control_source/k3_no_anchor.csv') if r['method']=='anchorboost' and r['k']=='3'}
    result['residual_target_control'] = paired([(name, fold, float(original[name]['curve_mae']), float(control[name]['curve_mae'])) for name,fold,*_ in records])
    return result


def verify_files():
    manifest = read(BASE/'SHA256SUMS.json')
    for name, expected in manifest['files'].items():
        path = BASE/name
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == expected['sha256'] and path.stat().st_size == expected['bytes'], name
    return len(manifest['files'])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, default=Path('strong-baseline-recomputed.json'))
    p.add_argument('--probe', action='store_true', help='Verify checksums and bootstrap a small synthetic vector; no outcome selection.')
    p.add_argument('--acute-raw', type=Path); p.add_argument('--harrill-raw', type=Path); p.add_argument('--ablation-raw', type=Path)
    a = p.parse_args(); start = time.perf_counter()
    count = verify_files()
    result = dict(status='probe' if a.probe else 'complete', verified_files=count)
    if a.probe:
        paired([(str(i),i%2,i/10,(i+1)/10) for i in range(8)], replicates=20)
    else:
        result.update(nfa=nfa(), acute=external('acute', a.acute_raw), harrill=external('harrill', a.harrill_raw), ablation=ablation(a.ablation_raw))
    result['resources'] = dict(seconds=time.perf_counter()-start,
                               peak_rss_bytes=int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=='darwin' else 1024)),
                               python=sys.version.split()[0], numpy=np.__version__, paid_cost_usd=0)
    assert result['resources']['peak_rss_bytes'] < 4_000_000_000
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(json.dumps(dict(status=result['status'], verified_files=count, resources=result['resources']), indent=2))


if __name__ == '__main__':
    main()

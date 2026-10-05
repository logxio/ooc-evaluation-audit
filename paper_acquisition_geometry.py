#!/usr/bin/env python3
"""Post hoc highest-unobserved control from saved exhaustive acquisition branches.

Consumes complete original folds; never trains a model or evaluates a new forecast.
Writes separate artifacts and verifies unchanged source hashes at completion.
"""
import os
for _name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[_name] = '1'
import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import itertools
import json
import math
from pathlib import Path
import resource
import signal
import sys
import time
sys.dont_write_bytecode = True
import numpy as np

METHODS = ('interpolation', 'anchorboost_all', 'anchorboost_five', 'cnp')
CONTROLS = ('model_disagreement', 'uniform_random', 'fixed_maximin')
POLICIES = ('highest_unobserved',) + CONTROLS + ('none',)
METRICS = ('fixed_target_mae', 'measurement_only_mae', 'unrevealed_mae',
           'initial_wells', 'final_wells', 'full_wells', 'remaining_cells')
STRATA = ('all', 'top_dose_initially_measured=True', 'top_dose_initially_measured=False')


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def read_csv(path):
    with path.open(newline='') as f:
        return list(csv.DictReader(f))


def write_csv(path, rows):
    with path.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def dump(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n')


def paired(values):
    d = np.asarray(values, dtype=float)
    assert len(d) and np.isfinite(d).all()
    rng = np.random.default_rng(0)
    boot = np.mean(d[rng.integers(0, len(d), (10000, len(d)))], axis=1)
    wins, ties, losses = (int((d < -1e-12).sum()), int((np.abs(d) <= 1e-12).sum()),
                          int((d > 1e-12).sum()))
    n = wins + losses
    p = min(1., 2 * sum(math.comb(n, i) for i in range(min(wins, losses)+1)) / 2**n) if n else 1.
    ci = np.percentile(boot, [2.5, 97.5])
    return dict(n_drugs=len(d), mean_difference=float(d.mean()), ci95_low=float(ci[0]),
                ci95_high=float(ci[1]), highest_wins=wins, ties=ties,
                highest_losses=losses, sign_test_two_sided=p)


def member(row, stratum):
    return stratum == 'all' or stratum.endswith('=' + str(row['top_dose_initially_measured']))


def load_fold(source, fold, protocol, hashes):
    folder = source / f'fold{fold}'
    meta_path = folder / 'evaluation.json'
    meta = json.loads(meta_path.read_text())
    assert meta['status'] == 'complete' and not meta['probe']
    assert meta['protocol_sha256'] == hashes[source/'protocol.json']
    hashes[meta_path] = sha(meta_path)
    for name, digest in meta['output_sha256'].items():
        path = folder / name
        hashes[path] = sha(path)
        assert hashes[path] == digest, path
    choices = [json.loads(s) for s in (folder/'choices.jsonl').read_text().splitlines()]
    assert len(choices) == meta['n_designs'] == 5 * meta['n_chemicals']
    assert {c['chemical'] for c in choices} == set(protocol['splits'][str(fold)]['test'])
    counts = Counter(c['chemical'] for c in choices)
    assert set(counts.values()) == {5}
    raw = read_csv(folder/'branch_results.csv')
    branches = {(r['chemical'], int(r['design']), r['method'], int(r['branch'])): r for r in raw}
    assert len(branches) == len(raw) == sum(4*(1+c['n_candidates']) for c in choices)
    original = read_csv(folder/'design_results.csv')
    original = {(r['chemical'], int(r['design']), r['method'], r['policy']): r for r in original}
    assert len(original) == len(choices)*4*4
    rows, audit = [], []
    gap = 0.
    for c in choices:
        candidates = c['candidates']
        assert len(c['initial']) == 3 and len(set(c['initial'])) == 3
        assert len(candidates) == c['n_candidates'] and len(candidates) > 1
        assert candidates == sorted(set(candidates)) and not set(candidates) & set(c['initial'])
        highest = int(np.argmax(candidates))
        top_measured = max(c['initial']) > max(candidates)
        assert c['top_dose_initially_measured'] == top_measured
        assert c['choices']['uniform_random'] == list(range(len(candidates)))
        np.testing.assert_array_equal(c['random_weights'], np.full(len(candidates), 1/len(candidates)))
        choices_by_policy = {**c['choices'], 'highest_unobserved': highest, 'none': -1}
        audit.append(dict(chemical=c['chemical'], identity=c['identity'], fold=fold, design=c['design'],
            analysis_origin='post_hoc_control_added_after_original_results',
            rule='maximum original unobserved log10 concentration; response-free',
            initial=c['initial'], candidates=candidates, n_candidates=len(candidates),
            top_dose_initially_measured=top_measured, highest_unobserved=highest,
            selected_log10=candidates[highest], original_choices=c['choices'],
            original_choices_sha256=hashes[folder/'choices.jsonl'],
            same_as_disagreement=highest == c['choices']['model_disagreement'],
            same_as_maximin=highest == c['choices']['fixed_maximin'],
            random_expected_match=1/len(candidates)))
        for method in METHODS:
            all_branches = [branches[c['chemical'], c['design'], method, i] for i in range(-1,len(candidates))]
            assert len({r['valid_target_cells'] for r in all_branches}) == 1
            for i, r in enumerate(all_branches):
                assert int(r['fold']) == fold and r['identity'] == c['identity']
                assert r['top_dose_initially_measured'] == str(top_measured)
                assert int(r['n_levels']) == 3+len(candidates)
                if i:
                    assert float(r['selected_log10']) == candidates[i-1]
            for policy in POLICIES:
                indices = choices_by_policy[policy]
                indices = indices if isinstance(indices, list) else [indices]
                rs = [branches[c['chemical'], c['design'], method, i] for i in indices]
                row = dict(chemical=c['chemical'], identity=c['identity'], fold=fold, design=c['design'],
                    method=method, policy=policy, top_dose_initially_measured=top_measured,
                    n_candidates=len(candidates), n_levels=3+len(candidates),
                    initial_k=3, final_k=3 if policy=='none' else 4,
                    valid_target_cells=int(rs[0]['valid_target_cells']),
                    **{key: float(np.mean([float(r[key]) for r in rs])) for key in METRICS})
                assert all(np.isfinite(row[k]) for k in METRICS)
                if policy != 'highest_unobserved':
                    previous = original[c['chemical'], c['design'], method, policy]
                    gap = max(gap, *(abs(row[k]-float(previous[k])) for k in METRICS))
                rows.append(row)
    assert gap < 1e-12
    # Preserve and recheck highest's actual saved point forecasts, not new model output.
    with np.load(folder/'point_predictions.npz', allow_pickle=False) as archive:
        z = {key: archive[key] for key in archive.files}
    high_index = {(c['chemical'], c['design']): c['highest_unobserved'] for c in audit}
    keep = np.array([int(b) == high_index[str(c), int(d)] for c,d,b in
                     zip(z['chemical'], z['design'], z['branch'])])
    points = {k:v[keep] for k,v in z.items()}
    groups = defaultdict(list)
    for i, key in enumerate(zip(points['chemical'], points['design'], points['method'])):
        groups[key].append(i)
    point_gap = 0.
    assert len(groups) == len(choices)*4
    for (chem, design, method), ix in groups.items():
        branch = high_index[str(chem), int(design)]
        r = branches[str(chem), int(design), str(method), branch]
        mask = points['observed'][ix]
        truth, pred = points['truth'][ix], points['prediction'][ix]
        acquired = points['is_acquired'][ix]
        assert int(acquired.sum()) == 1 and acquired[branch]
        assert int(mask.sum()) == int(r['valid_target_cells'])
        np.testing.assert_array_equal(pred[acquired][mask[acquired]], truth[acquired][mask[acquired]])
        score = float(np.abs(pred-truth)[mask].mean())
        point_gap = max(point_gap, abs(score-float(r['fixed_target_mae'])))
    assert point_gap < 1e-6
    return rows, audit, points, meta['original_cnp_identity_overlap'], gap, point_gap


def summarize(rows, choices, excluded):
    drugs, differences, contrasts, overlaps, budgets = [], [], [], [], []
    populations = {'all_recorded': set()}
    if excluded:
        populations['common_identity_clean'] = set(excluded)
    for population, exclusions in populations.items():
        for stratum in STRATA:
            selected = [r for r in rows if r['chemical'] not in exclusions and member(r,stratum)]
            cs = [c for c in choices if c['chemical'] not in exclusions and member(c,stratum)]
            n_designs, n_drugs = len(cs), len({c['chemical'] for c in cs})
            grouped = defaultdict(list)
            for r in selected:
                grouped[r['chemical'],r['method'],r['policy']].append(r)
            lookup = {}
            for (chemical, method, policy), rs in sorted(grouped.items()):
                d = dict(population=population, stratum=stratum, chemical=chemical,
                         identity=rs[0]['identity'], fold=rs[0]['fold'], method=method,
                         policy=policy, n_designs=len(rs),
                         **{k:float(np.mean([r[k] for r in rs])) for k in METRICS})
                drugs.append(d)
                lookup[chemical,method,policy] = d
            chemicals = sorted({c['chemical'] for c in cs})
            for method in METHODS:
                for control in CONTROLS:
                    dd = []
                    for chemical in chemicals:
                        h, c = lookup[chemical,method,'highest_unobserved'], lookup[chemical,method,control]
                        total = h['fixed_target_mae'] - c['fixed_target_mae']
                        measurement = h['measurement_only_mae'] - c['measurement_only_mae']
                        d = dict(population=population, stratum=stratum, chemical=chemical,
                            fold=h['fold'], method=method, comparator=control, n_designs=h['n_designs'],
                            highest_mae=h['fixed_target_mae'], comparator_mae=c['fixed_target_mae'],
                            highest_minus_comparator=total, measurement_only_difference=measurement,
                            reconditioning_difference=total-measurement)
                        differences.append(d)
                        dd.append(d)
                    effect = dict(population=population, stratum=stratum, method=method, comparator=control,
                        n_designs=n_designs, highest_mae=float(np.mean([d['highest_mae'] for d in dd])),
                        comparator_mae=float(np.mean([d['comparator_mae'] for d in dd])),
                        **paired([d['highest_minus_comparator'] for d in dd]))
                    for component in ('measurement_only_difference','reconditioning_difference'):
                        st = paired([d[component] for d in dd])
                        effect.update({component+'_'+k:st[k] for k in ('mean_difference','ci95_low','ci95_high')})
                    contrasts.append(effect)
            for left,right in itertools.combinations(POLICIES[:-1],2):
                def idx(c,p):
                    return c['highest_unobserved'] if p=='highest_unobserved' else c['original_choices'][p]
                probabilities = [(1/c['n_candidates'] if 'uniform_random' in (left,right)
                                  else float(idx(c,left)==idx(c,right))) for c in cs]
                overlaps.append(dict(population=population,stratum=stratum,left=left,right=right,
                    n_drugs=n_drugs,n_designs=n_designs,matches_or_expected_matches=sum(probabilities),
                    overlap_fraction=float(np.mean(probabilities)),
                    type='exact_random_expectation' if 'uniform_random' in (left,right) else 'observed_choices'))
            for policy in POLICIES:
                rs = [r for r in selected if r['method']==METHODS[0] and r['policy']==policy]
                budgets.append(dict(population=population,stratum=stratum,policy=policy,n_drugs=n_drugs,
                    n_designs=n_designs,initial_concentrations=3*n_designs,
                    final_concentrations=(3 if policy=='none' else 4)*n_designs,
                    initial_wells=sum(r['initial_wells'] for r in rs),
                    final_wells=sum(r['final_wells'] for r in rs),full_wells=sum(r['full_wells'] for r in rs),
                    full_concentrations=sum(r['n_levels'] for r in rs)))
    return drugs, differences, contrasts, overlaps, budgets


def report(summary, contrasts, overlaps):
    lines = ['# Post hoc highest-unobserved geometry control', '',
        f"Completed folds: {summary['folds']}; {summary['n_drugs']} drugs / {summary['n_designs']} designs.", '',
        'This control was added after the original acquisition results. All forecasts, initial designs, ',
        'targets and update rules are reused from the frozen experiment. The rule selects the maximum ',
        'original unobserved log concentration. The two strata use only original concentration geometry.', '',
        'Differences are highest minus comparator; negative favors highest. Drug means average the ',
        'available designs within each stratum. Intervals are 10,000 paired drug bootstrap replicates ',
        '(seed 0); sign tests are exact and two-sided. The same drug can occur in both strata. ',
        'Intervals condition on fitted models; comparisons are exploratory without multiplicity correction.', '',
        ('The all-recorded CNP rows retain the original identity overlap. Use the common identity-clean '
         f"population for four-predictor inference. Excluded there: {summary['original_cnp_identity_exclusion']}."
         if summary['original_cnp_identity_exclusion'] else
         'All drugs in these folds are identity-clean for the four-predictor comparison.'), '']
    for population in sorted({r['population'] for r in contrasts}):
        for stratum in STRATA:
            rs = [r for r in contrasts if r['population']==population and r['stratum']==stratum]
            lines += [f'## {population} / {stratum}', '',
                f"{rs[0]['n_drugs']} drugs, {rs[0]['n_designs']} designs.", '',
                '| Predictor | Comparator | Highest MAE | Comparator MAE | Difference [95% CI] | Win/tie/loss | Sign p |',
                '|---|---|---:|---:|---|---|---:|']
            for r in rs:
                lines.append(f"| {r['method']} | {r['comparator']} | {r['highest_mae']:.6f} | "
                    f"{r['comparator_mae']:.6f} | {r['mean_difference']:+.6f} "
                    f"[{r['ci95_low']:+.6f}, {r['ci95_high']:+.6f}] | "
                    f"{r['highest_wins']}/{r['ties']}/{r['highest_losses']} | {r['sign_test_two_sided']:.6g} |")
            lines += ['', '| Choices | Matches / designs | Overlap |', '|---|---:|---:|']
            for r in overlaps:
                if r['population']==population and r['stratum']==stratum:
                    lines.append(f"| {r['left']} / {r['right']} | {r['matches_or_expected_matches']:.3f} / "
                        f"{r['n_designs']} | {100*r['overlap_fraction']:.2f}% |")
            lines.append('')
    lines += ['## Data and computation', '',
        'All policies add one concentration, including its recorded replicate wells, to initial K3. ',
        'The common target is all valid cells outside initial K3; the acquired cells have zero error. ',
        'Random is the exact uniform expectation over complete candidate branches. Measurements are ',
        'retrospective scenario counts; overlapping designs reuse recorded wells. Real wet-lab savings ',
        'remain a separate prospective question. Per-policy well budgets are in measurement_budgets.csv.', '',
        'drug_differences.csv preserves each signed paired effect. contrasts.csv also decomposes the ',
        'difference into measurement-only replacement and context reconditioning. Their sum equals ',
        'the total difference. This diagnostic describes forecast errors on this source.', '',
        'highest_point_predictions.npz copies the original saved highest branches, including true ',
        'responses, masks, forecasts and raw model outputs. choices.jsonl explicitly marks post hoc ',
        'selection; it makes no pre-reveal commitment claim for this newly added rule.', '',
        f"Candidate-count distribution: {summary['candidate_counts']}.",
        f"Extra training: 0; extra measurements: 0; elapsed {summary['seconds']:.3f}s; "
        f"peak RSS {summary['peak_rss_bytes']} bytes.", '']
    return '\n'.join(lines)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--folds', type=int, nargs='+', required=True)
    p.add_argument('--spec', type=Path, required=True)
    a = p.parse_args()
    signal.alarm(295)
    start = time.perf_counter()
    a.source, a.out = a.source.resolve(), a.out.resolve()
    assert a.out != a.source and a.out not in a.source.parents
    assert len(a.folds)==len(set(a.folds)) and set(a.folds)<=set(range(1,5))
    spec = json.loads(a.spec.read_text())
    hashes = {a.source/'protocol.json':sha(a.source/'protocol.json'), a.spec:sha(a.spec)}
    assert spec['original_protocol_sha256']==hashes[a.source/'protocol.json']
    protocol = json.loads((a.source/'protocol.json').read_text())
    assert protocol['context_k']==3 and protocol['final_k']==4
    # Preserve provenance and main-table immutability, including existing completion receipts.
    for name in ('summary.json','verification.json','completion.json','design_results.csv',
                 'drug_results.csv','choices.jsonl','first_fold_summary.json'):
        path=a.source/name
        if path.exists():
            hashes[path]=sha(path)
    rows, choices, point_parts, excluded = [], [], [], set()
    original_gap, point_gap = 0., 0.
    for fold in sorted(a.folds):
        r,c,z,e,g,pg = load_fold(a.source,fold,protocol,hashes)
        rows.extend(r); choices.extend(c); point_parts.append(z); excluded.update(e)
        original_gap=max(original_gap,g); point_gap=max(point_gap,pg)
    drugs,differences,contrasts,overlaps,budgets = summarize(rows,choices,excluded)
    a.out.mkdir(parents=True, exist_ok=True)
    for name,data in [('design_results',rows),('drug_results',drugs),('drug_differences',differences),
                      ('contrasts',contrasts),('selection_overlap',overlaps),('measurement_budgets',budgets)]:
        write_csv(a.out/(name+'.csv'),data)
    with (a.out/'choices.jsonl').open('w') as f:
        for c in choices:
            f.write(json.dumps(c,ensure_ascii=False,allow_nan=False)+'\n')
    np.savez_compressed(a.out/'highest_point_predictions.npz',
                        **{k:np.concatenate([z[k] for z in point_parts]) for k in point_parts[0]})
    assert all(sha(path)==digest for path,digest in hashes.items())
    peak = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=='darwin' else 1024))
    assert peak < 4_000_000_000
    summary=dict(schema='paper.acquisition.geometry.summary.v1',status='complete',
        created_utc=datetime.now(timezone.utc).isoformat(),analysis_origin=spec['origin'],
        folds=sorted(a.folds),n_drugs=len({c['chemical'] for c in choices}),n_designs=len(choices),
        original_cnp_identity_exclusion=sorted(excluded),candidate_counts=dict(Counter(c['n_candidates'] for c in choices)),
        contrasts=contrasts,selection_overlap=overlaps,measurement_budgets=budgets,
        seconds=time.perf_counter()-start,peak_rss_bytes=peak,extra_training_fits=0,
        extra_wet_measurements=0,original_policy_reconstruction_max_gap=original_gap,
        highest_point_reconstruction_max_gap=point_gap,source_hashes_unchanged=True,
        input_sha256={str(p):h for p,h in hashes.items()},code_sha256=sha(__file__),command=sys.argv,
        output_sha256={p.name:sha(p) for p in sorted(a.out.iterdir()) if p.suffix in ('.csv','.jsonl','.npz')})
    dump(a.out/'summary.json',summary)
    (a.out/'results.md').write_text(report(summary,contrasts,overlaps))
    print(json.dumps({k:v for k,v in summary.items() if k in ('status','folds','n_drugs','n_designs','seconds',
        'peak_rss_bytes','original_policy_reconstruction_max_gap','highest_point_reconstruction_max_gap',
        'source_hashes_unchanged')}))


if __name__=='__main__':
    main()

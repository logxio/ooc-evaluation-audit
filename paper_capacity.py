#!/usr/bin/env python3
"""Nested drug-held-out capacity selection on existing perfused-chip data.

This is a post-development retrospective re-evaluation. The candidate family
is frozen before running, and each outer drug is excluded from inner selection.
Use --freeze, --probe, --run, then --verify with the same --out directory.
"""
import os
for _key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS',
             'VECLIB_MAXIMUM_THREADS'):
    os.environ[_key] = '1'

import argparse
import csv
import hashlib
import importlib.util
import itertools
import json
import math
import resource
import signal
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import sklearn

ROOT = Path(__file__).resolve().parent.parent
EXP = ROOT / 'runs/chip-evidence-s1/expand'
MODEL = ROOT / 'release/benchmarks/ooc/raw/chip_forecast.py'
RULES = ['fixed50', 'adaptive10', 'fixed5', 'fixed2']
ALPHAS = [0.25, 0.5, 1.0]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def dump(path, value, exclusive=False):
    with path.open('x' if exclusive else 'w') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')


def csvout(path, rows):
    with path.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def rss():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == 'darwin' else 1024)


def load_cf():
    spec = importlib.util.spec_from_file_location('capacity_frozen_forecast', MODEL)
    cf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cf)
    cf.ND = cf.NF = cf.D = 1
    return cf


def candidates():
    # Ordering breaks numerical ties toward less residual correction, then the
    # conservative predeclared leaf rule. It never uses an outer score.
    return [dict(id='interpolation', rule='none', alpha=0.0)] + [
        dict(id=f'{rule}_a{alpha:g}', rule=rule, alpha=alpha)
        for alpha in ALPHAS for rule in RULES]


def freeze(out):
    old = json.loads((EXP / 'input_freeze.json').read_text())
    inputs = []
    for item in old['inputs'][:2]:
        p = EXP / item['path']
        assert sha(p) == item['sha256']
        inputs.append(dict(path=str(p.relative_to(ROOT)), sha256=sha(p)))
    cf = load_cf()
    p = dict(schema='paper.capacity.protocol.v1', frozen_at=now(),
        evidence_status='post-development retrospective re-evaluation for BOTH Yuan2025 and Ewart2022',
        decision='Does training-only nested selection of residual capacity improve sparse-dose prediction compared with fixed50 and interpolation?',
        prediction_before_run='Yuan selected MAE relative to interpolation: -10% to +10%; Ewart: -10% to +15%. All five endpoints reported without selecting by outer results.',
        source_protocol_sha256=old['protocol_sha256'], source_manifest_sha256=sha(EXP / 'input_freeze.json'),
        inputs=inputs, model_source_sha256=sha(MODEL), evaluator_sha256=sha(Path(__file__)),
        model_parameters=cf.MODEL, candidates=candidates(), primary_endpoints=old['primary_endpoints'],
        capacity_rules={'fixed50':50, 'fixed5':5, 'fixed2':2,
                        'adaptive10':'max(2, min(50, floor(training_target_rows / 10)))'},
        selection='For each outer drug, leave each remaining drug out internally; minimize equally weighted mean drug MAE over fixed contexts. Exact/numerical ties within 1e-12 use candidate order.',
        design='k=3; training enumerates all C(L,3) designs. Evaluation: original five seeded lowest-anchored Ewart designs, all three lowest-anchored Yuan designs.',
        preprocessing='Author units, positive doses, source concentration units preserved, within-dose means as original. No learned preprocessing from held-out drugs.',
        isolation='Selector accepts outer-training tasks only. Every inner analog/profile/model fit excludes inner validation and outer test. Prediction receives three-dose-only Task and query dose metadata. Selection saved before outer prediction; all outer predictions saved before outer scoring.',
        comparisons=['selected_minus_loglinear', 'selected_minus_fixed50', 'fixed50_minus_loglinear'],
        statistics='Drug-macro MAE; 10000 paired drug bootstrap draws, seed 0; exact sign-flip and Holm over five endpoints per contrast are descriptive because CV fits overlap and these data were used in development.',
        fit_budget='352 unique model fits at most with per-endpoint training-set cache; finite local run; 295-second alarm; 4 GB measured-RSS ceiling checked after every fit.',
        source_legacy_folds_sha256=sha(EXP / 'folds.csv'))
    dump(out / 'protocol.json', p, exclusive=True)
    print(json.dumps({'protocol_sha256':sha(out / 'protocol.json'), 'frozen_at':p['frozen_at']}))


def checked_protocol(out):
    p = json.loads((out / 'protocol.json').read_text())
    assert p['evaluator_sha256'] == sha(Path(__file__))
    assert p['model_source_sha256'] == sha(MODEL)
    assert p['source_manifest_sha256'] == sha(EXP / 'input_freeze.json')
    for item in p['inputs']:
        assert sha(ROOT / item['path']) == item['sha256']
    assert p['candidates'] == candidates()
    return p


def load_tasks(cf, p, cell):
    rr = []
    for item in p['inputs']:
        with (ROOT / item['path']).open() as f:
            rr += [r for r in csv.DictReader(f) if r['dataset'] == cell['dataset']
                   and r['endpoint'] == cell['endpoint'] and r['configuration'] == cell['configuration']
                   and r['time'] == cell['time']]
    tasks = []
    for drug in cell['drugs']:
        obs = [r for r in rr if r['compound'] == drug and r['value'] != '' and float(r['concentration']) > 0]
        # The primary normalized inputs have no donor mapping. Source row slots
        # remain observations; averaging matches the historical comparison.
        assert all(r['donor'] == '' for r in obs)
        c = np.array([float(r['concentration']) for r in obs])
        y = np.array([float(r['value']) for r in obs], np.float32)
        t = cf.Task(drug, len(tasks), cell['endpoint'], np.log10(c).astype(np.float32),
                    y[:, None, None], np.ones((len(y), 1, 1), bool))
        assert len(t.levels) >= 4
        tasks.append(t)
    return tasks, rr


def contexts(t, cell):
    tails = list(itertools.combinations(t.levels[1:].tolist(), 2))
    if cell['dataset'] == 'Ewart2022':
        seed = int(hashlib.sha256(f'ewart-transfer-v1|{cell["endpoint"]}|{t.chem}'.encode()).hexdigest()[:8], 16)
        tails = [tails[i] for i in np.random.default_rng(seed).permutation(len(tails))[:5]]
    return [np.array([t.levels[0], *tail], np.float32) for tail in tails]


def observed_task(cf, t, ctx):
    ic = np.isin(t.logc, ctx)
    return cf.Task(t.chem, t.fold, t.label, t.logc[ic].copy(), t.y[ic].copy(), t.m[ic].copy())


def row_count(train):
    return sum(math.comb(len(t.levels), 3) * (len(t.levels) - 3) for t in train)


def leaf_minimum(rule, rows):
    return max(2, min(50, rows // 10)) if rule == 'adaptive10' else int(rule[5:])


def leaf_stats(model):
    leaves = [int(np.sum(tree[0].nodes['is_leaf'])) for tree in model.model._predictors]
    return dict(training_rows=model.rows, trees=len(leaves), split_trees=sum(x > 1 for x in leaves),
                leaves_min=min(leaves), leaves_max=max(leaves), leaves_mean=float(np.mean(leaves)),
                leaves_total=sum(leaves), leaves_per_tree=leaves,
                initial_residual=float(model.model._baseline_prediction.ravel()[0]))


class Fits:
    def __init__(self, cf):
        self.cf, self.cache, self.audit = cf, {}, []

    def get(self, train, rule):
        key = (tuple(t.chem for t in train), rule)
        if key not in self.cache:
            params = dict(self.cf.MODEL)
            params['min_samples_leaf'] = leaf_minimum(rule, row_count(train))
            model = self.cf.AnchorBoost(train, 3, params)
            assert model.rows == row_count(train)
            assert rss() < 4_000_000_000
            self.cache[key] = model
            self.audit.append(dict(train_drugs=list(key[0]), rule=rule,
                                   min_samples_leaf=params['min_samples_leaf'], **leaf_stats(model)))
        return self.cache[key]


def predict_designs(cf, t, cell, models):
    """Only the observed three-dose Task reaches any predictor."""
    output = []
    for design, ctx in enumerate(contexts(t, cell)):
        q = t.levels[~np.isin(t.levels, ctx)]
        observed = observed_task(cf, t, ctx)
        ic = np.ones(len(observed.y), bool)
        base = cf.predict_interp(observed, ic, q).ravel()
        raw = {rule: m(observed, ic, q).ravel() for rule, m in models.items()}
        assert len(observed.levels) == 3
        for j, dose in enumerate(q):
            values = {'interpolation':float(base[j])}
            for cand in candidates()[1:]:
                if cand['rule'] in raw:
                    values[cand['id']] = float(base[j] + cand['alpha'] * (raw[cand['rule']][j] - base[j]))
            assert all(np.isfinite(v) for v in values.values())
            output.append(dict(design=design, context_log10='|'.join(map(str, ctx.tolist())),
                               query_log10=float(dose), values=values))
    return output


def losses(t, pp):
    dd = defaultdict(lambda: defaultdict(list))
    for row in pp:
        target = float(t.mu[np.flatnonzero(t.levels == row['query_log10'])[0], 0, 0])
        for cand, value in row['values'].items():
            dd[cand][row['design']].append(abs(value - target))
    return {c:float(np.mean([np.mean(v) for v in d.values()])) for c, d in dd.items()}


def select(cf, outer_train, cell, fits):
    """The outer test task is deliberately absent from this interface."""
    evidence = []
    for val in outer_train:
        train = [t for t in outer_train if t.chem != val.chem]
        models = {rule:fits.get(train, rule) for rule in RULES}
        ll = losses(val, predict_designs(cf, val, cell, models))
        evidence.append(dict(inner_validation_drug=val.chem, inner_training_drugs=[t.chem for t in train],
                             training_rows=row_count(train), candidate_drug_mae=ll))
    scores = [{**c, 'inner_mean_drug_mae':float(np.mean([e['candidate_drug_mae'][c['id']] for e in evidence]))}
              for c in candidates()]
    best = min(s['inner_mean_drug_mae'] for s in scores)
    winner = next(s for s in scores if s['inner_mean_drug_mae'] <= best + 1e-12)
    return winner, scores, evidence


def paired(a, b):
    d = np.asarray(a) - np.asarray(b)
    n = len(d)
    rng = np.random.default_rng(0)
    boot = d[rng.integers(0, n, (10000, n))].mean(1)
    flips = np.array(list(itertools.product([-1, 1], repeat=n))) @ d / n
    return dict(mean_difference=float(d.mean()), ci95=np.quantile(boot, [.025, .975]).tolist(),
                p_signflip=float(np.mean(np.abs(flips) >= abs(d.mean()) - 1e-12)),
                improved=int(sum(d < -1e-12)), equal=int(sum(abs(d) <= 1e-12)), worsened=int(sum(d > 1e-12)))


def probe(out):
    p = checked_protocol(out)
    start = time.monotonic()
    cf = load_cf()
    cell = p['primary_endpoints'][-1]
    tasks, _ = load_tasks(cf, p, cell)
    model = cf.AnchorBoost(tasks[:2], 3, {**cf.MODEL, 'min_samples_leaf':2})
    dump(out / 'probe.json', dict(seconds=time.monotonic()-start, peak_rss_bytes=rss(),
        input='two Yuan ALT training drugs; resource measurement only; no validation or test scoring',
        **leaf_stats(model)), exclusive=True)
    print(json.dumps({'seconds':time.monotonic()-start, 'peak_rss_bytes':rss(), 'rows':model.rows}))


def run(out):
    p = checked_protocol(out)
    assert (out / 'probe.json').exists()
    start = time.monotonic()
    cf = load_cf()
    folds, predictions, fits_all, selections, key_audit = [], [], [], [], []
    with (out / 'selection_before_test.jsonl').open('x') as journal:
        for cell in p['primary_endpoints']:
            tasks, source = load_tasks(cf, p, cell)
            key_audit.append(dict(dataset=cell['dataset'], endpoint=cell['endpoint'],
                n_source_rows=len(source), positive_numeric_rows=sum(r['value'] != '' and float(r['concentration']) > 0 for r in source),
                compound_keys=cell['drugs'], endpoint_key=True,
                donor_nonempty_rows=sum(bool(r.get('donor')) for r in source), batch_column_present='batch' in source[0],
                physical_chip_column_present='chip_id' in source[0], replicate_semantics='within-dose source row slot; pairing across doses is unestablished',
                concentration_units=sorted({r['concentration_unit'] for r in source}), time=cell['time'], configuration=cell['configuration']))
            fits = Fits(cf)
            for held in tasks:
                train = [t for t in tasks if t.chem != held.chem]
                winner, scores, evidence = select(cf, train, cell, fits)
                selection = dict(dataset=cell['dataset'], endpoint=cell['endpoint'], outer_test_drug=held.chem,
                    outer_training_drugs=[t.chem for t in train], selected=winner, candidates=scores,
                    inner_folds=evidence, selected_at=now(), protocol_sha256=sha(out / 'protocol.json'))
                journal.write(json.dumps(selection, allow_nan=False)+'\n')
                journal.flush()
                os.fsync(journal.fileno())
                selections.append(selection)
                models = {'fixed50':fits.get(train, 'fixed50')}
                if winner['rule'] != 'none':
                    models[winner['rule']] = fits.get(train, winner['rule'])
                pp = predict_designs(cf, held, cell, models)
                predicted_at = now()
                # A hidden-target perturbation checks that three-dose input construction
                # and prediction do not expose any unobserved response.
                ctx = contexts(held, cell)[0]
                poison = held.y.copy()
                poison[~np.isin(held.logc, ctx)] = 1e8
                poisoned = cf.Task(held.chem, held.fold, held.label, held.logc, poison, held.m)
                clean_context = observed_task(cf, held, ctx)
                poison_context = observed_task(cf, poisoned, ctx)
                assert np.array_equal(clean_context.y, poison_context.y)
                q = held.levels[~np.isin(held.levels, ctx)]
                for m in models.values():
                    assert np.array_equal(m(clean_context, np.ones(len(clean_context.y), bool), q),
                                          m(poison_context, np.ones(len(poison_context.y), bool), q))
                for row in pp:
                    common = dict(dataset=cell['dataset'], endpoint=cell['endpoint'], compound=held.chem,
                        design=row['design'], context_log10=row['context_log10'], query_log10=row['query_log10'], predicted_at=predicted_at)
                    for method, cid in [('selected', winner['id']), ('fixed50', 'fixed50_a1'), ('loglinear', 'interpolation')]:
                        predictions.append(dict(**common, method=method, candidate=cid, prediction=row['values'][cid]))
                fixed_stats = leaf_stats(models['fixed50'])
                selected_stats = leaf_stats(models[winner['rule']]) if winner['rule'] != 'none' else {}
                folds.append(dict(dataset=cell['dataset'], endpoint=cell['endpoint'], compound=held.chem,
                    n_train_drugs=len(train), training_rows=row_count(train), n_contexts=len(contexts(held, cell)),
                    selected_candidate=winner['id'], selected_rule=winner['rule'], selected_alpha=winner['alpha'],
                    selected_leaf_minimum=leaf_minimum(winner['rule'], row_count(train)) if winner['rule']!='none' else 0,
                    selected_mean_tree_leaves=selected_stats.get('leaves_mean', 0), selected_split_trees=selected_stats.get('split_trees', 0),
                    fixed50_mean_tree_leaves=fixed_stats['leaves_mean'], fixed50_split_trees=fixed_stats['split_trees'],
                    fixed50_initial_residual=fixed_stats['initial_residual']))
            fits_all += [dict(dataset=cell['dataset'], endpoint=cell['endpoint'], **r) for r in fits.audit]
            print(json.dumps({'prediction_complete':cell['dataset']+'/'+cell['endpoint'], 'outer_drugs':len(tasks), 'fits':len(fits.audit)}), flush=True)
    csvout(out / 'predictions_before_scoring.csv', predictions)
    prediction_sha = sha(out / 'predictions_before_scoring.csv')
    # All selectors and predictors are complete; only now create outer score tables.
    targets = {}
    for cell in p['primary_endpoints']:
        for t in load_tasks(cf, p, cell)[0]:
            for j, dose in enumerate(t.levels):
                targets[(cell['dataset'], cell['endpoint'], t.chem, float(dose))] = float(t.mu[j,0,0])
    errors = defaultdict(lambda: defaultdict(list))
    scored = []
    for r in predictions:
        key = (r['dataset'], r['endpoint'], r['compound'])
        target = targets[(*key, r['query_log10'])]
        error = abs(r['prediction']-target)
        errors[(*key, r['method'])][r['design']].append(error)
        scored.append(dict(**r, target=target, absolute_error=error))
    for fold in folds:
        key = (fold['dataset'], fold['endpoint'], fold['compound'])
        for method in ['selected','fixed50','loglinear']:
            fold[method+'_mae'] = float(np.mean([np.mean(e) for e in errors[(*key, method)].values()]))
    summaries = []
    for cell in p['primary_endpoints']:
        ff = [r for r in folds if r['dataset']==cell['dataset'] and r['endpoint']==cell['endpoint']]
        stats = {}
        for a, b in [('selected','loglinear'), ('selected','fixed50'), ('fixed50','loglinear')]:
            stats[a+'_minus_'+b] = paired([r[a+'_mae'] for r in ff], [r[b+'_mae'] for r in ff])
        summaries.append(dict(dataset=cell['dataset'], endpoint=cell['endpoint'], n_drugs=len(ff),
            mae={m:float(np.mean([r[m+'_mae'] for r in ff])) for m in ['selected','fixed50','loglinear']},
            comparisons=stats, selections=dict(Counter(r['selected_candidate'] for r in ff))))
    for contrast in summaries[0]['comparisons']:
        order = sorted(summaries, key=lambda s:s['comparisons'][contrast]['p_signflip'])
        prev = 0.0
        for rank, s in enumerate(order):
            prev = max(prev, min(1., (len(order)-rank)*s['comparisons'][contrast]['p_signflip']))
            s['comparisons'][contrast]['holm_p'] = prev
    csvout(out / 'outer_drugs.csv', folds)
    csvout(out / 'outer_predictions.csv', scored)
    dump(out / 'fit_audit.json', fits_all)
    dump(out / 'key_audit.json', key_audit)
    dump(out / 'summary.json', dict(status='complete', evidence_status=p['evidence_status'],
        protocol_sha256=sha(out/'protocol.json'), predictions_before_scoring_sha256=prediction_sha,
        outer_scoring_started_after_predictions=True, completed_at=now(), n_outer_drug_endpoints=len(folds),
        n_unique_drugs=len({r['compound'] for r in folds}), model_fits=len(fits_all),
        seconds=time.monotonic()-start, peak_rss_bytes=rss(), paid_usd=0,
        versions={'python':sys.version.split()[0], 'numpy':np.__version__, 'sklearn':sklearn.__version__},
        summary=summaries))
    assert rss() < 4_000_000_000
    print(json.dumps({'complete':True, 'seconds':time.monotonic()-start, 'peak_rss_bytes':rss(), 'model_fits':len(fits_all)}))


def verify(out):
    p = checked_protocol(out)
    summary = json.loads((out/'summary.json').read_text())
    pp = list(csv.DictReader((out/'outer_predictions.csv').open()))
    ff = list(csv.DictReader((out/'outer_drugs.csv').open()))
    legacy = list(csv.DictReader((EXP/'folds.csv').open()))
    assert sha(EXP/'folds.csv') == p['source_legacy_folds_sha256']
    assert len(ff)==27 and len({r['compound'] for r in ff})==11
    assert summary['predictions_before_scoring_sha256'] == sha(out/'predictions_before_scoring.csv')
    max_legacy = 0.0
    for f in ff:
        same = lambda r: all(r[k]==f[k] for k in ['dataset','endpoint','compound'])
        old = next(r for r in legacy if same(r))
        max_legacy = max(max_legacy, abs(float(f['fixed50_mae'])-float(old['frozen'])), abs(float(f['loglinear_mae'])-float(old['loglinear'])))
        for method in ['selected','fixed50','loglinear']:
            rows = [r for r in pp if same(r) and r['method']==method]
            dd = defaultdict(list)
            for r in rows:
                assert abs(abs(float(r['prediction'])-float(r['target']))-float(r['absolute_error']))<1e-12
                dd[r['design']].append(float(r['absolute_error']))
            value = np.mean([np.mean(e) for e in dd.values()])
            assert abs(value-float(f[method+'_mae']))<1e-12
    assert max_legacy < 1e-9, max_legacy
    sels = [json.loads(line) for line in (out/'selection_before_test.jsonl').read_text().splitlines()]
    for s in sels:
        assert s['outer_test_drug'] not in s['outer_training_drugs']
        for inner in s['inner_folds']:
            assert s['outer_test_drug'] not in inner['inner_training_drugs']+[inner['inner_validation_drug']]
            assert inner['inner_validation_drug'] not in inner['inner_training_drugs']
            assert set(inner['inner_training_drugs']+[inner['inner_validation_drug']])==set(s['outer_training_drugs'])
        for candidate in s['candidates']:
            mean = np.mean([r['candidate_drug_mae'][candidate['id']] for r in s['inner_folds']])
            assert abs(mean-candidate['inner_mean_drug_mae'])<1e-12
        best = min(c['inner_mean_drug_mae'] for c in s['candidates'])
        expected = next(c for c in s['candidates'] if c['inner_mean_drug_mae']<=best+1e-12)
        assert s['selected']==expected
        assert all(s['selected_at']<r['predicted_at'] for r in pp if r['dataset']==s['dataset'] and r['endpoint']==s['endpoint'] and r['compound']==s['outer_test_drug'])
    receipt = dict(status='pass', checked_at=now(), outer_folds=len(ff), candidates_per_fold=13,
        legacy_fixed50_and_interpolation_max_absolute_difference=max_legacy,
        nested_drug_disjointness=True, candidate_losses_recomputed=True,
        predictions_scored_independently=True, selections_before_predictions=True,
        hidden_target_perturbation_passed_during_run=True,
        files={name:sha(out/name) for name in ['protocol.json','summary.json','selection_before_test.jsonl','fit_audit.json','outer_drugs.csv','outer_predictions.csv','predictions_before_scoring.csv','key_audit.json']})
    dump(out/'verification.json', receipt)
    print(json.dumps(receipt))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    for flag in ['freeze','probe','run','verify']:
        group.add_argument('--'+flag, action='store_true')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    signal.alarm(295)
    for action in ['freeze','probe','run','verify']:
        if getattr(args, action):
            globals()[action](args.out)


if __name__ == '__main__':
    main()

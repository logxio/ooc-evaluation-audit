#!/usr/bin/env python3
"""Identity-disjoint, fixed-target K=3 -> K=4 retrospective acquisition replay.

Train two mixed-K AnchorBoost models at equal scalar-row and iteration budgets.
The all-design arm samples output rows across every possible design; the five-
design arm uses every output row of the five seeded contexts at each K. This is
a new budgeted acquisition experiment, distinct from the published K=3 ablation.
Evaluation uses real recorded responses. Choices are committed before reveal.
"""
import os
for _name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS',
              'VECLIB_MAXIMUM_THREADS', 'NUMEXPR_NUM_THREADS', 'NT_THREADS'):
    os.environ[_name] = '1'
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import importlib.util
import itertools
import json
import math
from pathlib import Path
import pickle
import platform
import resource
import signal
import sys
import time
from datetime import datetime, timezone
sys.dont_write_bytecode = True
import numpy as np
import sklearn
import chip_forecast as cf

POLICIES = ('fixed_maximin', 'uniform_random', 'model_disagreement')
METHODS = ('interpolation', 'anchorboost_all', 'anchorboost_five', 'cnp')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def seed(key):
    return int(hashlib.sha256(key.encode()).hexdigest()[:8], 16)


def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False) + '\n')


def table(path, rows):
    assert rows
    with path.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)


def read_table(path):
    with path.open(newline='') as f:
        return list(csv.DictReader(f))


def rss():
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == 'darwin' else 1024))


def observed(task, levels):
    sel = np.isin(task.logc, levels)
    # Predictor and selector only receive this physically restricted object.
    return cf.Task(task.chem, task.fold, 'unknown', task.logc[sel].copy(),
                   task.y[sel].copy(), task.m[sel].copy())


def identity_map(path):
    d = json.loads(path.read_text())
    return {r['chemical']: ident for ident, rows in d['groups'].items()
            for r in rows if r['screen'] == 'nfa'}


def split(tasks, identities, fold):
    test = [t for t in tasks if t.fold == fold]
    test_ids = {identities[t.chem] for t in test}
    original = [t for t in tasks if t.fold != fold]
    train = [t for t in original if identities[t.chem] not in test_ids]
    excluded = [t.chem for t in original if identities[t.chem] in test_ids]
    assert not ({identities[t.chem] for t in train} & test_ids)
    return train, test, excluded


def feature(model, task, query):
    mask = np.ones(len(task.logc), bool)
    base, x = cf.features(task, mask, query, model['analog'], model['profiles'])
    kcol = np.full((*x.shape[:-1], 1), len(task.levels))
    return base, np.concatenate([x, kcol], axis=-1)


def ab_predict(model, task, query):
    base, x = feature(model, task, query)
    return (base + model['estimator'].predict(x.reshape(-1, x.shape[-1])).reshape(len(query), cf.D)).reshape(len(query), cf.ND, cf.NF)


def slope_stat(task):
    good = task.ok[0] & task.ok[-1]
    return float(np.abs(task.mu[-1] - task.mu[0])[good].mean() / (task.levels[-1] - task.levels[0])) if good.any() else 0.0


def train_model(train, arm, iterations):
    start = time.perf_counter()
    model = dict(analog=cf.Analog(train), profiles=cf.Profiles(train))
    train_model_view = dict(model, analog=cf.Analog(train, exclude_self=True))
    budgets, slopes = [], []
    # Rows are matched separately for each chemical and each context size.
    for t in train:
        for k in (3, 4):
            five, full = cf.designs(t, k), cf.all_designs(t, k)
            budget = sum(int(t.ok[~np.isin(t.levels, c)].sum()) for c in five)
            budgets.append(dict(chemical=t.chem, k=k, rows=budget,
                                possible_designs=len(full), narrow_designs=len(five)))
        slopes += [slope_stat(observed(t, ctx)) for ctx in cf.designs(t, 3)]
    count = sum(b['rows'] for b in budgets)
    X, y = np.empty((count, 23)), np.empty(count)
    at = 0
    for t in train:
        for k in (3, 4):
            b = next(b for b in budgets if b['chemical'] == t.chem and b['k'] == k)
            contexts = cf.all_designs(t, k) if arm == 'all' else cf.designs(t, k)
            allocation = np.full(len(contexts), b['rows'] // len(contexts), dtype=int)
            rng = np.random.default_rng(seed(f'{t.chem}|{k}|acquisition-coverage'))
            allocation[rng.permutation(len(contexts))[:b['rows'] % len(contexts)]] += 1
            for i, ctx in enumerate(contexts):
                qmask = ~np.isin(t.levels, ctx)
                q, truth, valid = t.levels[qmask], t.mu[qmask], t.ok[qmask]
                base, f = feature(train_model_view, observed(t, ctx), q)
                keep = valid.reshape(-1)
                xf = f.reshape(-1, f.shape[-1])[keep]
                yf = (truth.reshape(len(q), cf.D) - base).reshape(-1)[keep]
                ix = rng.choice(len(yf), int(allocation[i]), replace=False) if arm == 'all' else np.arange(len(yf))
                X[at:at+len(ix)], y[at:at+len(ix)] = xf[ix], yf[ix]
                at += len(ix)
    assert at == count
    feature_seconds = time.perf_counter() - start
    model['estimator'] = cf.HistGradientBoostingRegressor(**dict(cf.MODEL, max_iter=iterations)).fit(X, y)
    model['slope_threshold'] = float(np.median(slopes))
    timing = dict(training_rows=count, iterations=int(model['estimator'].n_iter_),
                  row_iterations=count * int(model['estimator'].n_iter_), feature_width=23,
                  feature_seconds=feature_seconds, fit_seconds=time.perf_counter()-start-feature_seconds,
                  peak_rss_bytes=rss(), design_budgets=budgets,
                  represented_designs=sum(b['possible_designs' if arm == 'all' else 'narrow_designs'] for b in budgets))
    return model, timing


def select(model, obs, candidates):
    """Response-aware policy sees training-fitted model, observed rows and dose grid only."""
    p = ab_predict(model, obs, candidates)
    i = cf.predict_interp(obs, np.ones(len(obs.logc), bool), candidates)
    a = model['analog'].predict(obs, np.ones(len(obs.logc), bool), candidates)
    score = np.std(np.stack([p, i, a]), axis=0).mean(axis=(1, 2))
    distance = np.abs(candidates[:, None] - obs.levels[None, :]).min(1)
    return dict(fixed_maximin=int(np.argmax(distance)), model_disagreement=int(np.argmax(score))), score, distance


def load_cnp(root, fold):
    import torch
    torch.set_num_threads(1)
    sys.path.insert(0, str(root / 'src'))
    from neurotwin.models import cnp, trajectory
    models, config = cnp.load_fold_models(fold, 'cpu', root / 'data_bundle/models')
    assert len(models) == 3
    manifest = json.loads((root / 'data_bundle/manifest.json').read_text())
    hashes = {}
    for path in sorted((root / 'data_bundle/models').glob(f'cnp_fold{fold}_seed*.pt')):
        key = f'models/{path.name}'
        hashes[key] = sha(path)
        assert hashes[key] == manifest['files'][key]['sha256']
    def predict(obs, q):
        t = trajectory.ChemTask(obs.chem, obs.fold, obs.logc, obs.y, obs.m, np.full(len(obs.logc), ''))
        return np.mean([cnp.predict(m, t, np.ones(len(t.logc), bool), q, device='cpu')[0] for m in models], axis=0)
    return predict, dict(config=config, checkpoint_sha256=hashes, torch=torch.__version__)


def protocol(a):
    tasks = cf.load_tasks(a.data); identities = identity_map(a.identities)
    assert len(tasks) == 243 and len(identities) >= len(tasks)
    assert sha(a.data) == cf.FILES['data_bundle/nfa_tasks.npz']
    spec = dict(schema='paper.acquisition.v1', created_utc=datetime.now(timezone.utc).isoformat(),
                decision='Does response-aware acquisition improve on geometry/random, and does design coverage interact with that gain?',
                prediction='K4 reduces fixed-target MAE; disagreement-minus-random expected between -0.08 and +0.08; broad-minus-five expected between -0.05 and +0.03. All outcomes retained.',
                folds=[1, 2, 3, 4], test_n=194, context_k=3, final_k=4, contexts_per_chemical=5,
                source='EPA NFA, pinned NeuroChip Twin response bundle, historical static MEA data',
                status='Retrospective outer-fold replay on previously studied data, locally frozen protocol; not a new prospective dataset.',
                target='All concentration/output cells outside initial K3, fixed across predictors and policies. Acquired valid cells use measured means (zero error); other cells use recomputed predictions. Original masks retained.',
                secondary='MAE on remaining unrevealed cells; target membership depends on acquired dose.',
                update='All learned parameters fixed before test. Add measured fourth-dose wells to context and recompute every predictor. Both AB arms trained jointly on K3 and K4 with context count feature. No gradient update or fit on any held-out chemical.',
                training_budget='For every training chemical and k in {3,4}, row count equals all valid target cells of the five seeded contexts. Broad arm distributes exactly that row count across all contexts, sampling scalar rows without replacement inside each context; narrow arm uses all scalar rows of five contexts. Same 600 iterations, parameters, rows, feature width and seed. A40 full scalar enumeration is a separate historical static experiment.',
                model=dict(cf.MODEL, context_count_feature=True),
                policy='Fixed maximin log-dose distance; exact uniform random over candidates; mean output-wise std across broad AB, interpolation and training-only analog. Ties choose smallest dose. Same choices for all predictors.',
                failure_strata='Before test, training K3 contexts define median revealed end-to-end absolute slope. Apply this fixed threshold to test observed K3 only. Also report top-dose-in-context. No test-driven rule selection.',
                statistics='Mean designs within chemical; paired chemical percentile bootstrap, 10000 replicates seed0; exact two-sided sign test excluding absolute ties <=1e-12. Exploratory multiple contrasts, no multiplicity adjustment.',
                cnp='Original three published seeds, parameter-frozen context update. Full 194 rows retained; common 193-identity comparison excludes Phenobarbital, whose sodium form was in original CNP training. CNP not part of equal-AB-training-budget claim.',
                preprocessing='Public precomputed vehicle-normalized float16 bundle reused. Vehicle-derived normalization is not refitted here; no test drug responses used to fit new models or selectors.',
                measurement='One level reveals its existing replicate wells and 4x17 output panel. K3->K4 costs one additional concentration, not one scalar or one physical chip. Historical replay, realized wet-lab savings unmeasured.',
                input_sha256=dict(data=sha(a.data), identities=sha(a.identities), base_code=sha(Path(cf.__file__)), driver=sha(Path(__file__))),
                splits={})
    for fold in spec['folds']:
        train, test, excluded = split(tasks, identities, fold)
        spec['splits'][str(fold)] = dict(train=[t.chem for t in train], test=[t.chem for t in test],
                                       training_parent_exclusions=excluded,
                                       training_identities=sorted({identities[t.chem] for t in train}),
                                       test_identities=sorted({identities[t.chem] for t in test}))
    dump(a.out / 'protocol.json', spec)
    print(json.dumps(dict(status='frozen', protocol_sha256=sha(a.out/'protocol.json'), counts={f:len(v['test']) for f,v in spec['splits'].items()})))


def train(a):
    start = time.perf_counter()
    tasks = cf.load_tasks(a.data); identities = identity_map(a.identities)
    tr, te, excluded = split(tasks, identities, a.fold)
    if a.probe:
        tr = tr[:12]
    model, timing = train_model(tr, a.arm, 20 if a.probe else 600)
    folder = a.out / ('probe' if a.probe else f'fold{a.fold}')
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f'{a.arm}.pkl'
    with path.open('wb') as f:
        pickle.dump(model, f)
    timing.update(total_seconds=time.perf_counter()-start, peak_rss_bytes=rss())
    assert rss() < 4_000_000_000
    result = dict(status='complete', fold=a.fold, arm=a.arm, probe=a.probe,
                  train=[t.chem for t in tr], excluded=excluded, test=[t.chem for t in te],
                  slope_threshold=model['slope_threshold'], timing=timing,
                  protocol_sha256=sha(a.out/'protocol.json'), model_sha256=sha(path),
                  environment=dict(python=platform.python_version(), numpy=np.__version__, sklearn=sklearn.__version__))
    dump(folder/f'{a.arm}.json', result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('train','test','timing')} | {'timing':{k:v for k,v in timing.items() if k != 'design_budgets'}}, ensure_ascii=False), flush=True)


def evaluate(a):
    start = time.perf_counter()
    tasks = cf.load_tasks(a.data); identities = identity_map(a.identities)
    tr, test, excluded = split(tasks, identities, a.fold)
    folder = a.out / ('probe' if a.probe else f'fold{a.fold}')
    models, fitmeta = {}, {}
    for arm in ('all', 'five'):
        path = folder/f'{arm}.pkl'
        meta = json.loads((folder/f'{arm}.json').read_text())
        assert meta['model_sha256'] == sha(path)
        if not a.probe:
            assert meta['train'] == [t.chem for t in tr]
        with path.open('rb') as f:
            models[arm] = pickle.load(f)
        fitmeta[arm] = meta
    for key in ('training_rows','iterations','row_iterations','feature_width'):
        assert fitmeta['all']['timing'][key] == fitmeta['five']['timing'][key]
    cp, cmeta = load_cnp(a.cnp_root, a.fold)
    if a.probe:
        test = test[:2]
    branches, design_rows, points, audits = [], [], defaultdict(list), []
    overlap = Counter(); counts = Counter()
    with (folder/'choices.jsonl').open('w') as committed:
        for oracle in test:
            for di, ctx in enumerate(cf.designs(oracle, 3)):
                candidates = oracle.levels[~np.isin(oracle.levels, ctx)]
                obs = observed(oracle, ctx)
                choices, scores, distances = select(models['all'], obs, candidates)
                # Fixed selection is invariant to response values; adaptive selection's
                # complete inputs are recorded before oracle values are queried below.
                choices['uniform_random'] = list(range(len(candidates)))
                rec = dict(chemical=oracle.chem, identity=identities[oracle.chem], fold=a.fold, design=di,
                           phase='choices_committed_before_fourth_dose_reveal', initial=ctx.tolist(),
                           candidates=candidates.tolist(), n_candidates=len(candidates),
                           choices=choices, random_weights=[1/len(candidates)]*len(candidates),
                           disagreement_scores=scores.tolist(), maximin_scores=distances.tolist(),
                           observed_sha256=hashlib.sha256(obs.logc.tobytes()+obs.y.tobytes()+obs.m.tobytes()).hexdigest(),
                           initial_wells=len(obs.logc), training_model_sha256=fitmeta['all']['model_sha256'],
                           revealed_slope=slope_stat(obs), training_slope_threshold=models['all']['slope_threshold'],
                           slope_stratum='high' if slope_stat(obs)>models['all']['slope_threshold'] else 'low',
                           top_dose_initially_measured=bool(ctx[-1] == oracle.levels[-1]))
                committed.write(json.dumps(rec, ensure_ascii=False, allow_nan=False)+'\n')
                committed.flush(); os.fsync(committed.fileno())
                audits.append(rec)
                counts[len(candidates)] += 1
                overlap['fixed_equals_disagreement'] += choices['fixed_maximin']==choices['model_disagreement']
                overlap['disagreement_all_tied'] += bool(np.ptp(scores) <= 1e-12)
                # Only now access the oracle at the fixed evaluation target.
                sel = ~np.isin(oracle.levels, ctx)
                truth, valid = oracle.mu[sel].copy(), oracle.ok[sel].copy()
                assert len(candidates)>1 and valid.any()
                local, initial_prediction = {}, {}
                for bi in [-1] + list(range(len(candidates))):
                    added = None if bi == -1 else candidates[bi]
                    levels = ctx if added is None else np.sort(np.append(ctx, added))
                    current = observed(oracle, levels)
                    assert len(current.levels) == (3 if bi == -1 else 4)
                    pred = dict(interpolation=cf.predict_interp(current,np.ones(len(current.logc),bool),candidates),
                                anchorboost_all=ab_predict(models['all'],current,candidates),
                                anchorboost_five=ab_predict(models['five'],current,candidates),cnp=cp(current,candidates))
                    for method, raw in pred.items():
                        assert np.isfinite(raw).all()
                        if bi == -1:
                            initial_prediction[method] = raw.copy()
                        output = raw.copy()
                        measurement_only = initial_prediction[method].copy()
                        measured = np.zeros(len(candidates), bool)
                        if bi >= 0:
                            measured[bi] = True
                            output[bi][valid[bi]] = truth[bi][valid[bi]]
                            measurement_only[bi][valid[bi]] = truth[bi][valid[bi]]
                        residual_mask = valid & ~measured[:,None,None]
                        error = np.abs(output-truth)
                        mae = float(error[valid].mean())
                        remaining = float(error[residual_mask].mean())
                        row = dict(chemical=oracle.chem,identity=identities[oracle.chem],fold=a.fold,design=di,
                                   method=method,branch=bi,selected_log10='' if added is None else float(added),
                                   fixed_target_mae=mae,unrevealed_mae=remaining,valid_target_cells=int(valid.sum()),
                                   measurement_only_mae=float(np.abs(measurement_only-truth)[valid].mean()),
                                   remaining_cells=int(residual_mask.sum()),n_candidates=len(candidates),
                                   n_levels=len(oracle.levels),initial_wells=len(obs.logc),final_wells=len(current.logc),
                                   full_wells=len(oracle.logc),slope_stratum=rec['slope_stratum'],
                                   top_dose_initially_measured=rec['top_dose_initially_measured'])
                        branches.append(row); local[method,bi] = row
                        for qi,q in enumerate(candidates):
                            for key,value in dict(chemical=oracle.chem,fold=a.fold,design=di,method=method,
                                branch=bi,query_log10=q,is_acquired=measured[qi],truth=truth[qi].reshape(-1),
                                observed=valid[qi].reshape(-1),prediction=output[qi].reshape(-1),
                                raw_model_prediction=raw[qi].reshape(-1)).items():
                                points[key].append(value)
                for method in METHODS:
                    for policy in ('none',)+POLICIES:
                        indices = [-1] if policy=='none' else choices[policy]
                        if isinstance(indices,int):
                            indices = [indices]
                        rows = [local[method,i] for i in indices]
                        drow = {k:v for k,v in rows[0].items() if k not in ('branch','selected_log10')}
                        drow.update(policy=policy,
                            fixed_target_mae=float(np.mean([r['fixed_target_mae'] for r in rows])),
                            measurement_only_mae=float(np.mean([r['measurement_only_mae'] for r in rows])),
                            unrevealed_mae=float(np.mean([r['unrevealed_mae'] for r in rows])),
                            final_wells=float(np.mean([r['final_wells'] for r in rows])),
                            remaining_cells=float(np.mean([r['remaining_cells'] for r in rows])))
                        design_rows.append(drow)
    table(folder/'branch_results.csv', branches); table(folder/'design_results.csv',design_rows)
    np.savez_compressed(folder/'point_predictions.npz', **{k:np.asarray(v) for k,v in points.items()})
    result = dict(status='complete',fold=a.fold,probe=a.probe,n_chemicals=len(test),n_designs=len(audits),
                  candidate_counts=dict(counts),overlap=dict(overlap),n_concentration_prediction_rows=len(points['chemical']),
                  n_observed_output_predictions=int(np.asarray(points['observed']).sum()),
                  test=[t.chem for t in test],train=[t.chem for t in tr],training_excluded=excluded,
                  original_cnp_identity_overlap=[t.chem for t in test if any(identities[t.chem]==identities[r.chem] for r in tasks if r.fold!=a.fold)],
                  cnp=cmeta,parameter_update='Frozen weights; recondition on 4 observed levels.',
                  acquisition_parameter_updates=0,seconds=time.perf_counter()-start,peak_rss_bytes=rss(),
                  protocol_sha256=sha(a.out/'protocol.json'),
                  output_sha256={n:sha(folder/n) for n in ('choices.jsonl','branch_results.csv','design_results.csv','point_predictions.npz')})
    assert rss()<4_000_000_000
    dump(folder/'evaluation.json',result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('test','train','cnp','output_sha256')},ensure_ascii=False),flush=True)


def paired(values):
    d=np.asarray(values,dtype=float); assert len(d) and np.isfinite(d).all()
    rng=np.random.default_rng(0)
    boot=np.mean(d[rng.integers(0,len(d),(10000,len(d)))],axis=1)
    wins,losses,ties=int((d < -1e-12).sum()),int((d > 1e-12).sum()),int((np.abs(d)<=1e-12).sum())
    n=wins+losses
    p=min(1.0,2*sum(math.comb(n,i) for i in range(min(wins,losses)+1))/2**n) if n else 1.0
    return dict(n=len(d),mean_difference=float(d.mean()),ci95=np.percentile(boot,[2.5,97.5]).tolist(),
                wins=wins,ties=ties,losses=losses,sign_test_two_sided=p)


def summarize(a):
    rows=[]; meta=[]; budgets=[]
    for fold in (1,2,3,4):
        folder=a.out/f'fold{fold}'
        m=json.loads((folder/'evaluation.json').read_text()); assert m['status']=='complete' and not m['probe']
        meta.append(m); rows += read_table(folder/'design_results.csv')
        arms={arm:json.loads((folder/f'{arm}.json').read_text()) for arm in ('all','five')}
        for key in ('training_rows','iterations','row_iterations','feature_width'):
            assert arms['all']['timing'][key]==arms['five']['timing'][key]
        budgets.append(dict(fold=fold,arms={arm:v['timing'] for arm,v in arms.items()}))
    drug_rows=[]
    grouped=defaultdict(list)
    for r in rows:
        grouped[r['chemical'],r['method'],r['policy']].append(r)
    for (drug,method,policy),items in grouped.items():
        assert len(items)==5
        drug_rows.append(dict(chemical=drug,identity=items[0]['identity'],fold=int(items[0]['fold']),method=method,policy=policy,
            **{k:float(np.mean([float(r[k]) for r in items])) for k in ('fixed_target_mae','unrevealed_mae','measurement_only_mae','initial_wells','final_wells','full_wells')}))
    assert len({r['chemical'] for r in drug_rows})==194
    assert len({r['identity'] for r in drug_rows})==194
    table(a.out/'drug_results.csv',drug_rows);table(a.out/'design_results.csv',rows)
    with (a.out/'choices.jsonl').open('w') as f:
        for fold in (1,2,3,4):
            f.write((a.out/f'fold{fold}/choices.jsonl').read_text())
    def analyze(items, excluded=()):
        data=defaultdict(dict)
        for r in items:
            if r['chemical'] not in excluded:
                data[r['method'],r['policy']][r['chemical']]=float(r['fixed_target_mae'])
        means={f'{m}/{p}':float(np.mean(list(v.values()))) for (m,p),v in data.items()}
        contrasts={}
        def contrast(name, terms):
            keys=sorted(set.intersection(*(set(data[key]) for key,_ in terms)))
            contrasts[name]=paired([sum(weight*data[key][k] for key,weight in terms) for k in keys])
        for method in METHODS:
            for policy in POLICIES:
                contrast(f'{method}:{policy}-none',[((method,policy),1),((method,'none'),-1)])
            for control in ('fixed_maximin','uniform_random'):
                contrast(f'{method}:disagreement-{control}',[((method,'model_disagreement'),1),((method,control),-1)])
        for policy in ('none',)+POLICIES:
            for other in ('interpolation','anchorboost_five','cnp'):
                contrast(f'anchorboost_all-{other}:{policy}',[(('anchorboost_all',policy),1),((other,policy),-1)])
        for control in ('fixed_maximin','uniform_random'):
            contrast(f'coverage_x_acquisition:disagreement-{control}',[
                (('anchorboost_all','model_disagreement'),1),(('anchorboost_all',control),-1),
                (('anchorboost_five','model_disagreement'),-1),(('anchorboost_five',control),1)])
            contrast(f'predictor_x_acquisition:disagreement-{control}',[
                (('anchorboost_all','model_disagreement'),1),(('anchorboost_all',control),-1),
                (('interpolation','model_disagreement'),-1),(('interpolation',control),1)])
        return dict(n_chemicals=len(next(iter(data.values()))),means=means,contrasts=contrasts)
    contaminated=sorted(set(itertools.chain.from_iterable(m['original_cnp_identity_overlap'] for m in meta)))
    strata={}
    for key in ('slope_stratum','top_dose_initially_measured'):
        for value in sorted({r[key] for r in rows}):
            dg=defaultdict(list)
            for r in rows:
                if r[key]==value:
                    dg[r['chemical'],r['method'],r['policy']].append(float(r['fixed_target_mae']))
            subset=[dict(chemical=c,method=m,policy=p,fixed_target_mae=float(np.mean(v))) for (c,m,p),v in dg.items()]
            strata[f'{key}={value}']=analyze(subset,contaminated)
    result=dict(schema='paper.acquisition.summary.v1',status='complete',
                primary_194=analyze(drug_rows),common_identity_clean_193=analyze(drug_rows,contaminated),
                original_cnp_identity_exclusion=contaminated,
                by_fold={str(f):analyze([r for r in drug_rows if r['fold']==f],contaminated) for f in (1,2,3,4)},
                prespecified_strata=strata,
                budgets=budgets,evaluations=meta,
                runtime=dict(train_seconds=sum(b['arms'][arm]['total_seconds'] for b in budgets for arm in ('all','five')),
                    evaluation_seconds=sum(m['seconds'] for m in meta),
                    peak_rss_bytes=max([b['arms'][arm]['peak_rss_bytes'] for b in budgets for arm in ('all','five')]+[m['peak_rss_bytes'] for m in meta]),paid_cost_usd=0),
                candidate_counts=dict(sum((Counter({int(k):v for k,v in m['candidate_counts'].items()}) for m in meta),Counter())),
                overlap=dict(sum((Counter(m['overlap']) for m in meta),Counter())),
                protocol_sha256=sha(a.out/'protocol.json'),bootstrap_replicates=10000,bootstrap_seed=0,
                interpretation='194 identity-disjoint new AB/interpolation comparisons; use common193 for CNP inference. Fixed-target scores include measured fourth-dose cells. Retrospective, multiple exploratory contrasts, chemical bootstrap does not include model-retraining uncertainty.')
    dump(a.out/'summary.json',result)
    print(json.dumps({k:v for k,v in result.items() if k in ('status','runtime','candidate_counts','overlap')},indent=2))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=['protocol','train','evaluate','summarize'])
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--data',type=Path,required=True)
    p.add_argument('--identities',type=Path,required=True)
    p.add_argument('--cnp-root',type=Path)
    p.add_argument('--fold',type=int,choices=range(1,5),default=1)
    p.add_argument('--arm',choices=['all','five'],default='all')
    p.add_argument('--probe',action='store_true')
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    signal.alarm(295)
    if a.mode!='protocol':
        spec=json.loads((a.out/'protocol.json').read_text())
        assert spec['input_sha256']['data']==sha(a.data)
        assert spec['input_sha256']['identities']==sha(a.identities)
        assert spec['input_sha256']['base_code']==sha(Path(cf.__file__))
    globals()[a.mode](a)


if __name__=='__main__':
    main()

#!/usr/bin/env python3
"""Retrain either frozen ablation arm; both arms use the same interpreter."""
import os
for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ[name] = '1'
import argparse
import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import resource
import sys
import time
sys.dont_write_bytecode = True
import numpy as np
import sklearn
from ablation_core import fit_matched
BASE = Path(__file__).resolve().parent


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--fold', type=int, choices=range(1,5), required=True)
    p.add_argument('--arm', choices=['full','five'], required=True)
    p.add_argument('--probe', action='store_true')
    a = p.parse_args(); started = time.perf_counter()
    protocol = json.loads((BASE/'ablation/protocol.json').read_text())
    source = BASE/'ablation/source'
    for name, expected in protocol['input_sha256'].items():
        assert hashlib.sha256((source/name).read_bytes()).hexdigest() == expected, name
    spec = importlib.util.spec_from_file_location('frozen_anchorboost', source/'chip_forecast.py')
    cf = importlib.util.module_from_spec(spec); spec.loader.exec_module(cf)
    tasks = cf.load_tasks(source/'nfa_tasks.npz')
    train = [t for t in tasks if t.fold != a.fold]
    if a.probe:
        train = train[:12]
    iterations = 20 if a.probe else 600
    timing = {}
    if a.arm == 'five':
        predict, timing = fit_matched(cf, train, iterations)
    else:
        original = cf.HistGradientBoostingRegressor
        def measured(**params):
            model = original(**params); original_fit = model.fit
            def fit(x, y):
                start = time.perf_counter(); result = original_fit(x, y)
                timing.update(fit_seconds=time.perf_counter()-start, training_rows=len(y),
                              feature_width=x.shape[1], iterations=int(model.n_iter_),
                              row_iteration_budget=int(len(y)*model.n_iter_))
                return result
            model.fit = fit
            return model
        cf.HistGradientBoostingRegressor = measured
        start = time.perf_counter()
        predict = cf.AnchorBoost(train, 3, dict(cf.MODEL, max_iter=iterations))
        timing['feature_plus_fit_seconds'] = time.perf_counter()-start
        timing['feature_seconds'] = timing['feature_plus_fit_seconds']-timing['fit_seconds']
    rows = []; arrays = {}
    if not a.probe:
        original = json.loads((source/'published_full.json').read_text())
        assert timing['training_rows'] == original['timing'][f'k3_fold{a.fold}']['training_rows']
        for i,task in enumerate(t for t in tasks if t.fold == a.fold):
            contexts = []
            for di,ctx in enumerate(cf.designs(task,3)):
                ic = np.isin(task.logc,ctx); lv,mu,mask = cf.level_means(task,~ic)
                pred = predict(task,ic,lv); curve,well = cf.errors(pred,task,~ic)
                contexts.append(dict(context_log_concentration=ctx.tolist(),target_log_concentration=lv.tolist(),
                                     curve_mae=curve,well_mae=well,n_valid_scalar_targets=int(mask.sum())))
                for name,value in dict(truth=mu,mask=mask,prediction=pred,query=lv,context=ctx).items():
                    arrays[f't{i}_design{di}_{name}'] = value
            key = 'rerun_full_curve_mae' if a.arm == 'full' else 'five_matched_curve_mae'
            rows.append(dict(chemical=task.chem,fold=a.fold,label=task.label,contexts=contexts,
                             **{key:float(np.mean([r['curve_mae'] for r in contexts]))}))
    timing.update(total_seconds=time.perf_counter()-started,
                  peak_rss_bytes=int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=='darwin' else 1024)))
    assert timing['peak_rss_bytes'] < 4_000_000_000
    result = dict(status='complete',fold=a.fold,probe=a.probe,full_arm=a.arm=='full',
                  training_chemicals=len(train),test_n=len(rows),rows=rows,timing=timing,
                  environment=dict(python=platform.python_version(),numpy=np.__version__,sklearn=sklearn.__version__,platform=platform.platform()),
                  timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat())
    a.out.mkdir(parents=True,exist_ok=True)
    name = f'{a.arm}_probe' if a.probe else f'{"full_" if a.arm=="full" else ""}fold{a.fold}'
    (a.out/f'{name}.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    if arrays:
        np.savez_compressed(a.out/f'{name}_predictions.npz',**arrays)
    print(json.dumps({k:v for k,v in result.items() if k != 'rows'},indent=2))


if __name__ == '__main__':
    main()

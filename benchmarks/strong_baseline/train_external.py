#!/usr/bin/env python3
"""Run the frozen published conditional process and AnchorBoost on one screen."""
import os
os.environ.setdefault('OMP_NUM_THREADS', '2')
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
os.environ.setdefault('MKL_NUM_THREADS', '2')
os.environ.setdefault('NT_THREADS', '2')
import argparse
import csv
import datetime
import gzip
import hashlib
import json
import platform
import resource
import sys
import time
import traceback
from pathlib import Path
import numpy as np

sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(data, indent=2, allow_nan=False) + '\n')
    tmp.replace(path)


def setup(base, screen):
    protocol = json.loads((base / 'protocol.json').read_text())
    for name, digest in protocol['input_sha256'].items():
        assert sha(base / name) == digest, (name, 'checksum')
    sys.path.insert(0, str(base / 'source'))
    import chip_forecast as cf
    from published_c import cnp, trajectory
    meta = [m for m in json.loads((base / 'tasks.json').read_text()) if m['screen'] == screen]
    nf = len(meta[0]['endpoints'])
    cf.ND, cf.NF, cf.D = 1, nf, nf
    cnp.ND, cnp.NF, cnp.D_OUT = 1, nf, nf
    trajectory.ND, trajectory.NF = 1, nf
    kt, ct = {}, {}
    with np.load(base / 'tasks.npz', allow_pickle=False) as z:
        for m in meta:
            key = m['key']
            x,y,mask = z[key+'_logc'],z[key+'_y'],z[key+'_m']
            kt[m['chemical']] = cf.Task(m['chemical'],m['fold'],m['label'],x,y,mask)
            ct[m['chemical']] = trajectory.ChemTask(m['chemical'],m['fold'],x,y,mask,np.full(len(x),''),m['label'])
    assert cf.MODEL == protocol['k_config']
    return cf, cnp, meta, kt, ct, protocol


def environment():
    import sklearn, torch
    return dict(python=platform.python_version(),numpy=np.__version__,sklearn=sklearn.__version__,
                torch=torch.__version__,platform=platform.platform(),
                cuda=torch.version.cuda,gpu=torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
                omp_threads=os.environ['OMP_NUM_THREADS'],nt_threads=os.environ['NT_THREADS'])


def metrics():
    import torch
    return dict(peak_rss_bytes=int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform=='darwin' else 1024)),
                peak_cuda_bytes=torch.cuda.max_memory_allocated() if torch.cuda.is_available() else 0)


def probe(base, out, screen, device):
    import torch
    cf, cnp, meta, kt, ct, protocol = setup(base, screen)
    start = time.perf_counter()
    train = [t for t in ct.values() if t.fold != 0][:12]
    cfg = cnp.TrainConfig(**dict(protocol['c_config'],steps=20,seed=0))
    model = cnp.train_cnp(train,cfg,device=device,log_every=10)
    assert all(torch.isfinite(p).all() for p in model.parameters())
    n_seconds = time.perf_counter()-start
    kstart = time.perf_counter()
    kmodel = cf.AnchorBoost([t for t in kt.values() if t.fold != 0][:12],3,dict(cf.MODEL,max_iter=20))
    result = dict(status='complete',screen=screen,mode='resource probe; no test outcomes',
                  training_chemicals=12,c_steps=20,k_iterations=20,c_seconds=n_seconds,
                  k_seconds=time.perf_counter()-kstart,k_rows=kmodel.rows,environment=environment(),**metrics())
    write(out / f'{screen}_probe.json',result)
    print(json.dumps(result),flush=True)


def run_fold(base, out, screen, fold, device):
    import torch
    cf, cnp, meta, kt, ct, protocol = setup(base, screen)
    folder = out / f'fold{fold}'
    folder.mkdir(parents=True,exist_ok=True)
    protocol_hash, code_hash = sha(base/'protocol.json'),sha(Path(__file__))
    final = folder/'result.json'
    if final.exists():
        previous = json.loads(final.read_text())
        assert previous['protocol_sha256']==protocol_hash and previous['code_sha256']==code_hash
        if previous['status']=='complete':
            print(f'Reuse {screen} fold{fold}',flush=True)
            return
    start = time.perf_counter()
    train = [t for t in ct.values() if t.fold!=fold]
    test = [m for m in meta if m['fold']==fold]
    timing,models = {},[]
    for seed in protocol['c_seeds']:
        checkpoint = folder/f'c_seed{seed}.pt'
        cfg = cnp.TrainConfig(**dict(protocol['c_config'],seed=seed))
        fit_start=time.perf_counter()
        if checkpoint.exists():
            saved=torch.load(checkpoint,map_location=device,weights_only=False)
            assert saved['protocol_sha256']==protocol_hash
            model=cnp.NeuroTrajectoryCNP(use_interp=cfg.use_interp,n_freq=cfg.n_freq,use_attention=cfg.use_attention).to(device)
            model.load_state_dict(saved['state']);model.eval()
            timing[f'c_seed{seed}']=saved['seconds']
        else:
            print(f'{screen} fold{fold} C seed{seed} start',flush=True)
            model=cnp.train_cnp(train,cfg,device=device,log_every=400)
            assert all(torch.isfinite(p).all() for p in model.parameters()),'nonfinite model parameter'
            timing[f'c_seed{seed}']=time.perf_counter()-fit_start
            torch.save(dict(state=model.state_dict(),cfg=vars(cfg),protocol_sha256=protocol_hash,
                            seconds=timing[f'c_seed{seed}']),checkpoint)
        models.append(model)
    print(f'{screen} fold{fold} K start',flush=True)
    fit_start=time.perf_counter()
    kmodel=cf.AnchorBoost([t for t in kt.values() if t.fold!=fold],3)
    timing['k_fit_seconds']=time.perf_counter()-fit_start
    timing['k_training_rows']=kmodel.rows
    published={r['chemical']:float(r['curve_mae']) for r in csv.DictReader((base/f'baseline_{screen}.csv').open()) if r['method']=='anchorboost'}
    interp_published={r['chemical']:float(r['curve_mae']) for r in csv.DictReader((base/f'baseline_{screen}.csv').open()) if r['method']=='loglinear_interp'}
    points,arrays,records=[],{},[]
    for m in test:
        t=kt[m['chemical']];c_task=ct[t.chem]
        designs=[]
        for i,ctx in enumerate(cf.designs(t,3)):
            ic=np.isin(t.logc,ctx)
            query,truth,mask=cf.level_means(t,~ic)
            kp=kmodel(t,ic,query)
            cp=np.mean(np.stack([cnp.predict(model,c_task,ic,query,device=device)[0] for model in models]),axis=0)
            ip=cf.predict_interp(t,ic,query)
            assert np.isfinite(kp).all() and np.isfinite(cp).all()
            ident=f"{m['key']}_design{i}"
            for key,val in [('truth',truth),('mask',mask),('k',kp),('c',cp),('interp',ip),('query',query),('context',ctx)]:
                arrays[ident+'_'+key]=val
            errors={name:cf.errors(pred,t,~ic)[0] for name,pred in [('k',kp),('c',cp),('interp',ip)]}
            subgroup={}
            for prefix in ('hNP1','hN2') if screen=='harrill' else ():
                columns=np.array([n.startswith(prefix+'_') for n in m['endpoints']])
                mm=mask[:,:,columns]
                subgroup[prefix]={name:float(np.abs(pred[:,:,columns]-truth[:,:,columns])[mm].mean()) if mm.any() else None
                                  for name,pred in [('k',kp),('c',cp),('interp',ip)]}
            designs.append(dict(design=i,context_logc=ctx.tolist(),target_logc=query.tolist(),
                                n_valid_scalar_targets=int(mask.sum()),errors=errors,subgroups=subgroup))
            for q,logc in enumerate(query):
                for j,endpoint in enumerate(m['endpoints']):
                    observed=bool(mask[q,0,j])
                    points.append(dict(screen=screen,chemical=t.chem,identity=m['identity'],fold=fold,design=i,
                                       context_logc='|'.join(str(float(x)) for x in ctx),target_logc=float(logc),endpoint=endpoint,
                                       observed=observed,truth=float(truth[q,0,j]) if observed else '',
                                       prediction_k=float(kp[q,0,j]),prediction_c=float(cp[q,0,j]),prediction_interp=float(ip[q,0,j]),
                                       abs_error_k=float(abs(kp[q,0,j]-truth[q,0,j])) if observed else '',
                                       abs_error_c=float(abs(cp[q,0,j]-truth[q,0,j])) if observed else '',
                                       delta_abs_error=float(abs(kp[q,0,j]-truth[q,0,j])-abs(cp[q,0,j]-truth[q,0,j])) if observed else ''))
        record=dict(screen=screen,chemical=t.chem,identity=m['identity'],fold=fold,
                    n_wells=len(t.logc),n_concentrations=len(t.levels),designs=designs,
                    k_mae=float(np.mean([d['errors']['k'] for d in designs])),
                    c_mae=float(np.mean([d['errors']['c'] for d in designs])),
                    interp_mae=float(np.mean([d['errors']['interp'] for d in designs])),
                    k_published_mae=published[t.chem])
        assert abs(record['interp_mae']-interp_published[t.chem]) < 2e-6,('baseline mismatch',t.chem)
        record['delta']=record['k_mae']-record['c_mae']
        record['k_refit_minus_published']=record['k_mae']-record['k_published_mae']
        record['subgroups']={}
        for prefix in ('hNP1','hN2') if screen=='harrill' else ():
            record['subgroups'][prefix]={}
            for name in ('k','c','interp'):
                values=[d['subgroups'][prefix][name] for d in designs if d['subgroups'][prefix][name] is not None]
                record['subgroups'][prefix][name]=float(np.mean(values)) if values else None
        records.append(record)
    with gzip.open(folder/'predictions.csv.gz','wt',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(points[0]));w.writeheader();w.writerows(points)
    np.savez_compressed(folder/'predictions.npz',**arrays)
    result=dict(schema='strong-baseline.external.fold.v1',status='complete',screen=screen,fold=fold,
                protocol_sha256=protocol_hash,code_sha256=code_hash,training_labels=len(train),test_labels=len(test),
                n_prediction_scalar_rows=len(points),environment=environment(),timing=timing,
                total_seconds=time.perf_counter()-start,resources=metrics(),records=records)
    write(final,result)
    print(json.dumps(dict(screen=screen,fold=fold,status='complete',seconds=result['total_seconds'],resources=result['resources'])),flush=True)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--base',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--screen',choices=['acute','harrill'],required=True)
    p.add_argument('--folds',type=int,nargs='+',default=list(range(5)))
    p.add_argument('--device',default='cuda')
    p.add_argument('--probe',action='store_true')
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    if a.probe:
        probe(a.base,a.out,a.screen,a.device)
        return
    failures=[]
    for fold in a.folds:
        try:
            run_fold(a.base,a.out,a.screen,fold,a.device)
        except Exception as exc:
            failure=dict(status='failed',screen=a.screen,fold=fold,error=str(exc),traceback=traceback.format_exc(),
                         timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat())
            write(a.out/f'fold{fold}'/'failure.json',failure)
            print(json.dumps(failure),flush=True);failures.append(fold)
    write(a.out/'completion.json',dict(screen=a.screen,status='failed' if failures else 'complete',folds=a.folds,failed_folds=failures))
    if failures:
        raise SystemExit(1)


if __name__=='__main__':
    main()

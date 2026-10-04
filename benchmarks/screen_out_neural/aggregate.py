#!/usr/bin/env python3
"""Recompute curve errors, paired chemical intervals and every main table offline."""
import os
for _name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ[_name]='1'
import argparse,array,csv,gzip,hashlib,json,platform,resource,sys,time
from collections import defaultdict
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parent

def dump(path,value):
    path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def paired(rows,reference):
    groups=defaultdict(list)
    for r in rows:groups[r['identity']].append(r)
    keys=sorted(groups)
    a=np.array([np.mean([r['neural'] for r in groups[k]]) for k in keys])
    b=np.array([np.mean([r[reference] for r in groups[k]]) for k in keys])
    # Match the frozen estimator: difference within sample, then mean within chemical identity.
    d=np.array([np.mean([r['neural']-r[reference] for r in groups[k]]) for k in keys])
    rng=np.random.default_rng(0)
    boot=d[rng.integers(0,len(d),(4000,len(d)))].mean(1)
    return dict(n_drugs=len(d),neural=float(a.mean()),reference=float(b.mean()),mean_difference=float(d.mean()),
                ci95=np.quantile(boot,[.025,.975]).tolist(),
                ci_familywise_6=np.quantile(boot,[.05/12,1-.05/12]).tolist(),
                relative_change_pct=100*float(d.mean()/b.mean()) if b.mean() else None,
                drugs_improved=int((d<0).sum()))

def read_predictions(path,probe):
    designs={};meta={};seen=set();first=None;count=0
    with gzip.open(path,'rt',newline='') as f:
        for r in csv.DictReader(f):
            endpoint=r['endpoint'] if r['screen']=='ewart' else 'all'
            drug=(r['regime'],r['screen'],r['chemical'],endpoint)
            if first is None:first=drug
            if probe and drug!=first:break
            key=drug+(int(r['design']),)
            # Each exported row is one observed target dose x endpoint; mask exclusions are already explicit.
            cell=(key,r['query_log10'],r['endpoint'])
            if cell in seen:raise ValueError('Duplicate prediction cell: '+str(cell))
            seen.add(cell)
            meta.setdefault(drug,dict(regime=r['regime'],screen=r['screen'],chemical=r['chemical'],
                                      identity=r['identity'],fold=int(r['fold']),endpoint=endpoint))
            if meta[drug]['identity']!=r['identity']:raise ValueError('Chemical identity mismatch')
            designs.setdefault(key,array.array('f')).extend((float(r['target']),float(r['neural']),float(r['loglinear'])))
            count+=1
    drug_errors=defaultdict(list)
    for key,values in designs.items():
        v=np.frombuffer(values,dtype=np.float32).reshape(-1,3)
        if not np.isfinite(v).all():raise ValueError('Nonfinite prediction')
        # Original evaluation used float32 target/prediction subtraction and mean per design.
        drug_errors[key[:-1]].append((key[-1],float(np.abs(v[:,1]-v[:,0]).mean()),float(np.abs(v[:,2]-v[:,0]).mean())))
    rows=[]
    for key,values in drug_errors.items():
        values.sort()
        if [x[0] for x in values]!=list(range(5)):raise ValueError('Expected five original designs: '+str(key))
        r=meta[key].copy();r.update(neural=float(np.mean([x[1] for x in values])),
                                   loglinear_interp=float(np.mean([x[2] for x in values])))
        rows.append(r)
    return rows,count,len(designs)

def attach_comparators(rows,data):
    ab={}
    with (data/'comparator_errors.csv').open(newline='') as f:
        for r in csv.DictReader(f):ab[(r['screen'],r['chemical'],r['endpoint'])]=r
    np_errors={}
    with (data/'published_np.csv').open(newline='') as f:
        for r in csv.DictReader(f):
            if int(r['k'])==3 and r['method']=='neurotrajectory':np_errors[r['chemical']]=float(r['curve_mae'])
    for r in rows:
        source=ab[(r['screen'],r['chemical'],r['endpoint'])]
        if source['identity']!=r['identity'] or int(source['fold'])!=r['fold']:raise ValueError('Comparator pairing mismatch')
        r['anchorboost']=float(source['anchorboost'])
        if r['screen']=='nfa':r['published_np']=np_errors[r['chemical']]
    return rows

def summarize(rows):
    result={}
    for regime in sorted({r['regime'] for r in rows}):
        result[regime]={}
        for screen in ('nfa','acute','harrill','ewart'):
            rr=[r for r in rows if r['regime']==regime and r['screen']==screen]
            if not rr:continue
            result[regime][screen]={}
            for endpoint in sorted({r['endpoint'] for r in rr}):
                selected=[r for r in rr if r['endpoint']==endpoint]
                cell=dict(versus_anchorboost=paired(selected,'anchorboost'),versus_loglinear=paired(selected,'loglinear_interp'))
                if screen=='nfa':cell['versus_published_np']=paired(selected,'published_np')
                cell['np_scope']=('Frozen published NFA chemical errors, same k=3 designs; target-screen-trained reference.'
                                  if screen=='nfa' else 'Unavailable in the frozen experiment; no substituted neural-process values.')
                result[regime][screen][endpoint]=cell
    return result

def numeric_differences(got,expected,path=''):
    diffs=[]
    if isinstance(expected,dict):
        for k,v in expected.items():
            if k=='np_scope':continue
            if k not in got:raise ValueError('Missing field: '+path+'/'+k)
            diffs+=numeric_differences(got[k],v,path+'/'+k)
    elif isinstance(expected,list):
        if len(got)!=len(expected):raise ValueError('Length mismatch: '+path)
        for i,v in enumerate(expected):diffs+=numeric_differences(got[i],v,path+'/'+str(i))
    elif isinstance(expected,(float,int)):
        diffs.append((path,abs(float(got)-float(expected))))
    elif got!=expected:raise ValueError('Value mismatch: '+path)
    return diffs

def main():
    start=time.perf_counter()
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,default=ROOT/'recomputed')
    p.add_argument('--probe',action='store_true',help='Read one complete chemical/design group for a resource probe')
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((ROOT/'checksums.json').read_text())
    for name in ('predictions.csv.gz','comparator_errors.csv','published_np.csv','drug_results.json','summary.json'):
        if digest(ROOT/name)!=manifest[name]:raise ValueError('Input checksum mismatch: '+name)
    rows,ncells,ndesigns=read_predictions(ROOT/'predictions.csv.gz',a.probe)
    attach_comparators(rows,ROOT)
    frozen=json.loads((ROOT/'drug_results.json').read_text())
    key=lambda r:(r['regime'],r['screen'],r['chemical'],r['endpoint'])
    expected={key(r):r for r in frozen}
    drug_delta=max(abs(r[m]-expected[key(r)][m]) for r in rows for m in ('neural','loglinear_interp','anchorboost'))
    if drug_delta>2e-6:raise ValueError('Per-chemical reproduction mismatch: '+str(drug_delta))
    result=summarize(rows);table=[]
    for regime,screen_data in result.items():
        for screen,endpoints in screen_data.items():
            for endpoint,comparisons in endpoints.items():
                for comparison,v in comparisons.items():
                    if comparison=='np_scope':continue
                    table.append(dict(regime=regime,screen=screen,endpoint=endpoint,comparison=comparison,
                        n_drugs=v['n_drugs'],neural_mae=v['neural'],reference_mae=v['reference'],
                        difference=v['mean_difference'],ci95_low=v['ci95'][0],ci95_high=v['ci95'][1],
                        familywise_low=v['ci_familywise_6'][0],familywise_high=v['ci_familywise_6'][1],
                        relative_change_pct=v['relative_change_pct'],drugs_improved=v['drugs_improved']))
    max_delta=None
    if not a.probe:
        if len(rows)!=len(frozen) or {key(r) for r in rows}!=set(expected):raise ValueError('Evaluation sample mismatch')
        deltas=numeric_differences(result,json.loads((ROOT/'summary.json').read_text())['summary'])
        max_delta=max(d for _,d in deltas)
        if max_delta>2e-6:raise ValueError('Main table reproduction mismatch: '+str(sorted(deltas,key=lambda x:-x[1])[:3]))
    dump(a.out/'summary.json',dict(status='resource_probe' if a.probe else 'recomputed',summary=result))
    dump(a.out/'drug_results.json',rows)
    with (a.out/'main_table.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(table[0]));w.writeheader();w.writerows(table)
    md=['| regime | screen | endpoint | comparator | n | neural MAE | reference MAE | difference [95% CI] |',
        '|---|---|---|---|---:|---:|---:|---|']
    for r in table:
        md.append(f"| {r['regime']} | {r['screen']} | {r['endpoint']} | {r['comparison']} | {r['n_drugs']} | {r['neural_mae']:.6f} | {r['reference_mae']:.6f} | {r['difference']:+.6f} [{r['ci95_low']:+.6f}, {r['ci95_high']:+.6f}] |")
    (a.out/'main_table.md').write_text('\n'.join(md)+'\n')
    report=dict(status='passed',mode='probe' if a.probe else 'full',seconds=time.perf_counter()-start,
        peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=='darwin' else 1024),
        prediction_cells=ncells,design_groups=ndesigns,drug_endpoint_rows=len(rows),main_table_rows=len(table),
        bootstrap_resamples=4000,bootstrap_seed=0,max_drug_error_difference=drug_delta,max_main_table_difference=max_delta,
        environment=dict(python=platform.python_version(),numpy=np.__version__,system=platform.system(),machine=platform.machine()),
        error_inputs='Per-concentration target and neural/log-linear predictions; frozen per-drug AnchorBoost errors; published per-drug NFA NP errors.',
        frozen_summaries_usage='Comparison after recomputation only; no reported metric is read from a summary.')
    if report['peak_rss_bytes']>4_000_000_000:raise RuntimeError('Resource limit exceeded')
    dump(a.out/'resources.json',report);print(json.dumps(report),flush=True)
if __name__=='__main__':main()

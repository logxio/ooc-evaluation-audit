"""Small shared design-conditioned residual network, with frozen folds and drug-level inference."""
import os
for _k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS'):os.environ[_k]='1'
import argparse,csv,gzip,hashlib,itertools,json,math,resource,sys,time,traceback
from collections import defaultdict
from pathlib import Path
import numpy as np
import torch
from torch import nn
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'source'))
import chip_forecast as cf
import ewart_transfer as ew
SCREENS=('nfa','acute','harrill','ewart')
TERMS=('firing','burst','spike','interval','duration','count','number','neurite','viab','casp','albumin','alt','morph','prolif','intensity','percent','correlation','synchron')
SEED=1741; EPOCHS=2; BATCH=4096

def dump(p,obj):p.write_text(json.dumps(obj,indent=2,allow_nan=False)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dimensions(t):
    cf.ND,cf.NF=t.y.shape[1:];cf.D=cf.ND*cf.NF

def load():
    z=np.load(ROOT/'tasks.npz',allow_pickle=False);tasks=[]
    for m in json.loads((ROOT/'tasks.json').read_text()):
        k=m['key'];y=z[k+'_y'];cf.ND,cf.NF=y.shape[1:];cf.D=cf.ND*cf.NF
        t=cf.Task(m['chemical'],m['fold'],m['label'],z[k+'_logc'],y,z[k+'_m'])
        t.meta=m;t.identity=m['identity'];t.screen=m['screen'];tasks.append(t)
    return tasks

def contexts(t,train=False):
    if train:return cf.all_designs(t,3)
    if t.screen=='ewart':return ew.contexts(t,t.meta['endpoints'][0])
    return cf.designs(t,3)

def descriptor(t):
    rows=[]
    for e in t.meta['endpoints']:
        e=e.lower();rows.append([float(s in e) for s in TERMS]+[int(e.split(':')[0][3:])/12 if e.startswith('div') else 0.0])
    return np.array(rows,np.float32)

def inputs(t,ctx,q):
    """Reads the observed context only. Target masks/values enter solely the loss/evaluation."""
    dimensions(t)
    ic=np.isin(t.logc,ctx);lv,mu,ok=cf.level_means(t,ic)
    base=cf.interp_rows(lv,mu,ok,q).reshape(len(q),-1)
    y=mu.reshape(3,-1);m=ok.reshape(3,-1)
    # Deterministic per-context homogeneity transform, with no estimated dataset parameter.
    # The all-zero context uses 1 in its own declared endpoint units.
    amp=np.max(np.abs(y)*m,axis=0);amp=np.where(amp>1e-6,amp,1).astype(np.float32)
    Q,D=base.shape
    tok=np.zeros((Q,D,3,3),np.float32)
    tok[:,:,:,0]=(lv[None,None,:]-np.asarray(q)[:,None,None])/5
    tok[:,:,:,1]=(y/amp).T[None]
    tok[:,:,:,2]=m.T[None]
    c=np.zeros((Q,D,7+len(TERMS)+1),np.float32)
    c[:,:,0]=base/amp
    c[:,:,1]=np.asarray(q)[:,None]/5
    c[:,:,2]=(lv[-1]-lv[0])/5
    c[:,:,3]=np.maximum(np.asarray(q)-lv[-1],0)[:,None]/5
    c[:,:,4]=np.maximum(lv[0]-np.asarray(q),0)[:,None]/5
    c[:,:,5]=np.min(np.abs(np.asarray(q)[:,None]-lv[None,:]),axis=1)[:,None]/5
    c[:,:,6]=m.mean(0)[None]
    c[:,:,7:]=descriptor(t)[None]
    return np.concatenate([tok.reshape(Q*D,9),c.reshape(Q*D,-1)],1),base,amp

class Shared(nn.Module):
    def __init__(self):
        super().__init__()
        self.encoder=nn.Sequential(nn.Linear(3,48),nn.SiLU(),nn.Linear(48,48),nn.SiLU())
        self.head=nn.Sequential(nn.Linear(48+7+len(TERMS)+1,96),nn.SiLU(),nn.Linear(96,48),nn.SiLU(),nn.Linear(48,1))
        nn.init.zeros_(self.head[-1].weight);nn.init.zeros_(self.head[-1].bias)
    def forward(self,x):
        tokens=x[:,:9].reshape(-1,3,3);mask=tokens[:,:,2:3]
        pooled=(self.encoder(tokens)*mask).sum(1)/mask.sum(1).clamp_min(1)
        return self.head(torch.cat([pooled,x[:,9:]],1)).squeeze(1)

def dataset(train,probe=False):
    specs=[];n=0
    for t in train:
        for ctx in (contexts(t,True)[:2] if probe else contexts(t,True)):
            keep=~np.isin(t.levels,ctx);size=int(t.ok[keep].sum())
            specs.append((t,ctx,size));n+=size
            if probe and len(specs)>=8:break
        if probe and len(specs)>=8:break
    nf=9+7+len(TERMS)+1
    X=np.empty((n,nf),np.float32);Y=np.empty(n,np.float32);W=np.empty(n,np.float32)
    # Every supervised row is retained; loss gives each screen/chemical equal total mass.
    counts=defaultdict(int)
    for t,_,size in specs:counts[(t.screen,t.identity)]+=size
    screen_groups={s:len({i for ss,i in counts if ss==s}) for s in SCREENS}
    at=0
    for t,ctx,size in specs:
        dimensions(t);ic=np.isin(t.logc,ctx);q,mu,ok=cf.level_means(t,~ic)
        x,base,amp=inputs(t,ctx,q);mask=ok.ravel()
        X[at:at+size]=x[mask]
        Y[at:at+size]=((mu.reshape(len(q),-1)-base)/amp).ravel()[mask]
        W[at:at+size]=1/(counts[(t.screen,t.identity)]*screen_groups[t.screen])
        at+=size
    assert np.isfinite(X).all() and np.isfinite(Y).all() and at==n
    W*=len(W)/W.sum()
    return X,Y,W,len(specs)

def fit(train,device,out,probe=False):
    start=time.monotonic();torch.manual_seed(SEED);np.random.seed(SEED)
    X,Y,W,designs=dataset(train,probe)
    # The sole fitted response scaler is estimated strictly on these training targets.
    # Context amplitudes are inputs to the forward function, not a fit on a test curve.
    sy=max(float(np.average(np.abs(Y),weights=W)),1e-3)
    model=Shared().to(device);opt=torch.optim.AdamW(model.parameters(),lr=0.001,weight_decay=0.0001)
    rng=np.random.default_rng(SEED);losses=[]
    for epoch in range(1 if probe else EPOCHS):
        order=rng.permutation(len(Y));total=0
        model.train()
        for at in range(0,len(Y),64 if probe else BATCH):
            ix=order[at:at+(64 if probe else BATCH)]
            x=torch.from_numpy(X[ix]).to(device);y=torch.from_numpy(Y[ix]/sy).to(device);w=torch.from_numpy(W[ix]).to(device)
            opt.zero_grad(set_to_none=True);loss=(torch.abs(model(x)-y)*w).mean()
            loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),5);opt.step();total+=float(loss.detach())*len(ix)
            if probe:break
        losses.append(total/len(Y))
    report=dict(seconds=time.monotonic()-start,training_rows=len(Y),all_designs=designs,epochs=1 if probe else EPOCHS,
                train_target_scale=sy,parameters=sum(p.numel() for p in model.parameters()),losses=losses,
                train_identities=sorted({t.identity for t in train}),train_screens=sorted({t.screen for t in train}),
                peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=='darwin' else 1024),
                gpu_peak_allocated_bytes=torch.cuda.max_memory_allocated() if device=='cuda' else 0,
                gpu_peak_reserved_bytes=torch.cuda.max_memory_reserved() if device=='cuda' else 0)
    torch.save(dict(model=model.cpu().state_dict(),target_scale=sy,report=report),out.with_suffix('.pt'))
    model.to(device);model.eval();dump(out.with_suffix('.json'),report)
    del X,Y,W
    return model,sy,report

def predict(model,sy,t,ctx,q,device):
    x,base,amp=inputs(t,ctx,q)
    with torch.inference_mode():
        r=np.concatenate([model(torch.from_numpy(x[i:i+BATCH]).to(device)).cpu().numpy() for i in range(0,len(x),BATCH)])
    return (base+r.reshape(base.shape)*sy*amp).reshape(len(q),*t.y.shape[1:])

def pair(rows,reference='anchorboost'):
    # Repeated sample names/aliases are clustered at chemical identity, not counted as independent drugs.
    d=defaultdict(list);a=defaultdict(list);b=defaultdict(list)
    for r in rows:
        a[r['identity']].append(r['neural']);b[r['identity']].append(r[reference]);d[r['identity']].append(r['neural']-r[reference])
    x=np.array([np.mean(d[k]) for k in sorted(d)]);aa=np.array([np.mean(a[k]) for k in sorted(d)]);bb=np.array([np.mean(b[k]) for k in sorted(d)])
    rng=np.random.default_rng(0);boot=x[rng.integers(0,len(x),(4000,len(x)))].mean(1)
    return dict(n_drugs=len(x),neural=float(aa.mean()),reference=float(bb.mean()),mean_difference=float(x.mean()),
                ci95=np.quantile(boot,[.025,.975]).tolist(),ci_familywise_6=np.quantile(boot,[.05/12,1-.05/12]).tolist(),
                relative_change_pct=100*float(x.mean()/bb.mean()) if bb.mean() else None,drugs_improved=int((x<0).sum()))

def baseline_tables():
    tables={}
    for screen in SCREENS:
        rows=list(csv.DictReader((ROOT/f'baseline_{screen}.csv').open()));tab={}
        if screen=='ewart':
            for r in rows:
                if r['preparation']=='author_units':tab[(r['chemical'],r['endpoint'])]={m:float(r[m]) for m in ('anchorboost','loglinear_interp')}
        else:
            for r in rows:
                if int(r['k'])==3 and r['method'] in ('anchorboost','loglinear_interp'):
                    tab.setdefault((r['chemical'],'all'),{})[r['method']]=float(r['curve_mae'])
        tables[screen]=tab
    return tables

def baseline_for_test(tasks,test,tables,out):
    """Original within-screen AnchorBoost is a target-informed reference for screen-out neural transfer."""
    result={};audit=[]
    for screen in SCREENS:
        tests=[t for t in test if t.screen==screen]
        if not tests:continue
        if screen=='ewart':
            for t in tests:result[t.meta['key']]=tables[screen][(t.chem,t.meta['endpoints'][0])]
            continue
        held={t.identity for t in tests};fold=tests[0].fold
        original=[t for t in tasks if t.screen==screen and t.fold!=fold]
        train=[t for t in original if t.identity not in held]
        removed=[t.chem for t in original if t.identity in held]
        refit=bool(removed)
        if refit:
            dimensions(train[0]);model=cf.AnchorBoost(train,3)
        for t in tests:
            value=tables[screen][(t.chem,'all')].copy()
            if refit:
                errs=[]
                for ctx in contexts(t):
                    dimensions(t);ic=np.isin(t.logc,ctx);q=np.unique(t.logc[~ic]);errs.append(cf.errors(model(t,ic,q),t,~ic)[0])
                value['anchorboost']=float(np.mean(errs))
            result[t.meta['key']]=value
        audit.append(dict(screen=screen,refit_for_aliases=refit,removed=removed,training_drugs=len(train),fold=fold))
    dump(out/'baseline_audit.json',audit)
    return result

def eval_model(model,sy,tests,reference,device,regime,writer):
    rows=[]
    for t in tests:
        dimensions(t);acc=[];ll=[]
        for design,ctx in enumerate(contexts(t)):
            dimensions(t);ic=np.isin(t.logc,ctx);q,mu,ok=cf.level_means(t,~ic)
            pred=predict(model,sy,t,ctx,q,device);base=cf.predict_interp(t,ic,q)
            acc.append(cf.errors(pred,t,~ic)[0]);ll.append(cf.errors(base,t,~ic)[0])
            for qi,dose in enumerate(q):
                for j,endpoint in enumerate(t.meta['endpoints']):
                    if not ok.reshape(len(q),-1)[qi,j]:continue
                    writer.writerow(dict(regime=regime,screen=t.screen,chemical=t.chem,identity=t.identity,fold=t.fold,design=design,
                        context_log10='|'.join(map(str,ctx.tolist())),query_log10=float(dose),endpoint=endpoint,
                        target=float(mu.reshape(len(q),-1)[qi,j]),neural=float(pred.reshape(len(q),-1)[qi,j]),loglinear=float(base.reshape(len(q),-1)[qi,j])))
        ref=reference[t.meta['key']]
        assert abs(float(np.mean(ll))-ref['loglinear_interp'])<1e-4,(t.screen,t.chem,'baseline design/target mismatch',np.mean(ll),ref)
        rows.append(dict(regime=regime,screen=t.screen,chemical=t.chem,identity=t.identity,fold=t.fold,
            endpoint=t.meta['endpoints'][0] if t.screen=='ewart' else 'all',neural=float(np.mean(acc)),anchorboost=ref['anchorboost'],loglinear_interp=float(np.mean(ll))))
    return rows

def summarize(rows):
    out={};published=cf.published(ROOT/'published_np.csv')
    for regime in ('screen_out','within_screen'):
        out[regime]={}
        for screen in SCREENS:
            group=[r for r in rows if r['regime']==regime and r['screen']==screen]
            by={}
            for endpoint in sorted({r['endpoint'] for r in group}):
                rr=[r.copy() for r in group if r['endpoint']==endpoint]
                cell=dict(versus_anchorboost=pair(rr),versus_loglinear=pair(rr,'loglinear_interp'))
                if screen=='nfa':
                    for r in rr:r['published_np']=published[(3,'neurotrajectory')][r['chemical']]
                    cell['versus_published_np']=pair(rr,'published_np')
                    cell['np_scope']='Published per-chemical frozen errors; identical fold/designs/targets. The NP was trained within this target screen, not screen-out.'
                else:cell['np_scope']='not_available: no published neural-process predictions for this screen in the pinned source.'
                by[endpoint]=cell
            out[regime][screen]=by
    return out

def probe(tasks,out):
    train=[next(t for t in tasks if t.screen==s and t.fold not in (0,1)) for s in SCREENS]
    model,sy,report=fit(train,'cpu',out/'probe_model',True)
    # Poison all unobserved test readings. Inputs/predictions must remain byte-identical.
    t=next(t for t in tasks if t.screen=='nfa' and t.fold==1);ctx=contexts(t)[0];dimensions(t)
    q=t.levels[~np.isin(t.levels,ctx)];x,b,a=inputs(t,ctx,q)
    y=t.y.copy();y[~np.isin(t.logc,ctx)]=123456
    p=cf.Task(t.chem,t.fold,t.label,t.logc.copy(),y,t.m.copy());p.meta=t.meta;p.screen=t.screen;p.identity=t.identity
    x2,b2,a2=inputs(p,ctx,q)
    assert np.array_equal(x,x2) and np.array_equal(b,b2) and np.array_equal(a,a2)
    xx=torch.from_numpy(x[:32]);permuted=xx.clone();permuted[:,:9]=xx[:,:9].reshape(-1,3,3)[:,[2,0,1],:].reshape(-1,9)
    with torch.no_grad():delta=float((model(xx)-model(permuted)).abs().max())
    assert delta<1e-6
    tables=baseline_tables();parity={}
    for screen in SCREENS:
        tt=[t for t in tasks if t.screen==screen and (t.fold==1 or screen=='ewart')]
        diffs=[]
        for t in tt:
            errs=[]
            for ctx in contexts(t):
                dimensions(t);ic=np.isin(t.logc,ctx);q=np.unique(t.logc[~ic])
                errs.append(cf.errors(cf.predict_interp(t,ic,q),t,~ic)[0])
            key=(t.chem,t.meta['endpoints'][0] if screen=='ewart' else 'all')
            diffs.append(abs(float(np.mean(errs))-tables[screen][key]['loglinear_interp']))
        parity[screen]=dict(samples=len(tt),max_abs_error_difference=max(diffs))
        assert max(diffs)<1e-4,(screen,max(diffs))
    report.update(status='passed',target_poisoning_invariance=True,permutation_invariance_max_error=delta,
                  torch=torch.__version__,numpy=np.__version__,local_budget_bytes=4000000000,baseline_parity=parity)
    assert report['peak_rss_bytes']<4000000000
    dump(out/'probe.json',report);print(json.dumps(report),flush=True)

def run(tasks,out,device):
    start=time.monotonic()
    if device=='cuda' and not torch.cuda.is_available():raise RuntimeError('CUDA requested but unavailable')
    tests=[t for t in tasks if (t.screen!='ewart' and t.fold==1) or t.screen=='ewart']
    refs=baseline_for_test(tasks,tests,baseline_tables(),out)
    rows=[];fits={};splits={}
    fields=['regime','screen','chemical','identity','fold','design','context_log10','query_log10','endpoint','target','neural','loglinear']
    with gzip.open(out/'predictions.csv.gz','wt',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for screen in SCREENS:
            name='screen_out_'+screen
            excluded={t.identity for t in tasks if t.screen==screen}
            train=[t for t in tasks if t.screen!=screen and t.identity not in excluded]
            tt=[t for t in tests if t.screen==screen]
            assert not {t.identity for t in train}&excluded
            splits[name]=dict(train_keys=[t.meta['key'] for t in train],test_keys=[t.meta['key'] for t in tt],excluded_alias_identities=sorted(excluded))
            model,sy,rep=fit(train,device,out/name);fits[name]=rep
            rows+=eval_model(model,sy,tt,refs,device,'screen_out',writer);f.flush()
            dump(out/'partial_drug_results.json',rows);print(json.dumps(dict(completed=name,rows=len(rows),seconds=rep['seconds'])),flush=True)
            del model
        # One shared model for the existing fold 1 of all three large screens.
        tt=[t for t in tests if t.screen!='ewart'];excluded={t.identity for t in tt}
        train=[t for t in tasks if t.identity not in excluded and (t.screen=='ewart' or t.fold!=1)]
        assert not {t.identity for t in train}&excluded
        name='within_fold1';splits[name]=dict(train_keys=[t.meta['key'] for t in train],test_keys=[t.meta['key'] for t in tt],excluded_alias_identities=sorted(excluded))
        model,sy,rep=fit(train,device,out/name);fits[name]=rep
        rows+=eval_model(model,sy,tt,refs,device,'within_screen',writer);del model
        # Six leave-one-drug-out models share weights across all screens/endpoints in each fit.
        for identity in sorted({t.identity for t in tests if t.screen=='ewart'}):
            tt=[t for t in tests if t.screen=='ewart' and t.identity==identity]
            train=[t for t in tasks if t.identity!=identity]
            name='within_ewart_'+str(tt[0].fold)
            splits[name]=dict(train_keys=[t.meta['key'] for t in train],test_keys=[t.meta['key'] for t in tt],excluded_alias_identities=[identity])
            model,sy,rep=fit(train,device,out/name);fits[name]=rep
            rows+=eval_model(model,sy,tt,refs,device,'within_screen',writer);del model
            f.flush();dump(out/'partial_drug_results.json',rows)
            print(json.dumps(dict(completed=name,rows=len(rows),seconds=rep['seconds'])),flush=True)
    dump(out/'splits.json',splits);dump(out/'drug_results.json',rows)
    summary=summarize(rows)
    eligible=[]
    for screen,by in summary['screen_out'].items():
        for endpoint,c in by.items():
            p=c['versus_anchorboost']
            if p['n_drugs']>=12 and p['ci_familywise_6'][1]<0:eligible.append(dict(screen=screen,endpoint=endpoint,comparison=p))
    result=dict(status='complete',paid_usd=0,summary=summary,eligible_rental_signals=eligible,
                rental_recommendation_usd=0 if not eligible else None,
                reference_scope='AnchorBoost and published NP are original within-target-screen references on identical evaluation samples; they have more target-domain training information than screen-out neural.',
                small_experiment_scope='Existing fold 1 for NFA, acute and Harrill; all six Ewart leave-one-drug-out folds. Screen-out training excludes the entire held-out screen and every alias of any chemical in that screen.',
                normalization_scope='Fitted target scaler uses training rows only. Deterministic context amplitude reads only measured inputs. Immutable benchmark matrices retain the original published/legacy response-unit preparation; this does not audit upstream raw-data inductiveness.',
                source_hashes=json.loads((ROOT/'input_hashes.json').read_text()),protocol_sha256=sha(ROOT/'protocol.json'),code_sha256=sha(Path(__file__)),
                fits=fits,hours=(time.monotonic()-start)/3600,gpu_model=torch.cuda.get_device_name(0) if device=='cuda' else None,
                visible_gpu_count=torch.cuda.device_count(),used_gpu_indices=[0] if device=='cuda' else [],
                peak_gpu_allocated_bytes=torch.cuda.max_memory_allocated() if device=='cuda' else 0,
                peak_gpu_reserved_bytes=torch.cuda.max_memory_reserved() if device=='cuda' else 0,
                peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=='darwin' else 1024),
                environment=dict(python=sys.version.split()[0],torch=torch.__version__,numpy=np.__version__))
    dump(out/'summary.json',result)
    lines=['Completed fixed experiment.',f"Elapsed hours: {result['hours']:.6f}; device: {device}.",
           'AnchorBoost and published NP use target-screen training on identical evaluation samples.']
    for regime,by in summary.items():
        for screen,endpoints in by.items():
            for endpoint,c in endpoints.items():
                p=c['versus_anchorboost']
                lines.append(f"{regime}/{screen}/{endpoint}: n={p['n_drugs']}; neural={p['neural']:.6f}; "
                             f"AnchorBoost={p['reference']:.6f}; difference={p['mean_difference']:.6f}; 95% CI={p['ci95']}.")
    lines.append('Ewart author units are reported per endpoint. Published NP comparisons cover NFA only.')
    (out/'conclusion.md').write_text('\n\n'.join(lines)+'\n')
    print(json.dumps(dict(status='complete',hours=result['hours'],eligible_rental_signals=eligible)),flush=True)

def main():
    global RUN_OUT
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--probe',action='store_true')
    p.add_argument('--device',choices=('auto','cpu','cuda'),default='auto')
    p.add_argument('--out',type=Path,default=ROOT/'trained')
    a=p.parse_args();a.out.mkdir(exist_ok=True,parents=True)
    RUN_OUT=a.out
    torch.set_num_threads(1);tasks=load()
    if a.probe:probe(tasks,a.out)
    else:run(tasks,a.out,('cuda' if torch.cuda.is_available() else 'cpu') if a.device=='auto' else a.device)
if __name__=='__main__':
    try:main()
    except Exception:
        raw=traceback.format_exc()
        if 'RUN_OUT' in globals():
            (RUN_OUT/'failure_traceback.txt').write_text(raw)
            dump(RUN_OUT/'summary.json',dict(status='runtime_error',paid_usd=0,rental_recommendation_usd=0,error=raw,
                 partial_results_file='partial_drug_results.json',code_sha256=sha(Path(__file__))))
            (RUN_OUT/'conclusion.md').write_text('Runtime error. See failure_traceback.txt and partial_drug_results.json for completed evaluations.\n')
        traceback.print_exc();raise

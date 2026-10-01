#!/usr/bin/env python3
"""Compare browser calculations with the existing Python CLI and core functions.

python workbench/verify.py --out workbench/verification
Requires the repository's usual Python dependencies and Node.js.
"""
import argparse,csv,json,os,subprocess,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
CORE=HERE.parent
sys.path.insert(0,str(CORE))
from release_calibration import apply,measure
from matched_regimen import predict as matched_predict
from conditional_calibration import upper_bound

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--out',type=Path,required=True)
parser.add_argument('--node',default='node')
a=parser.parse_args();a.out.mkdir(parents=True,exist_ok=True)
started=time.perf_counter();checks=[];numeric=0
p=json.loads((HERE/'result.json').read_text())
cert=p['rule']['certificate']; rows=p['rows']
(a.out/'certificate.json').write_text(json.dumps(cert))
env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
def cli(csv_path,labelled,out_name):
 cmd=[sys.executable,str(CORE/'chip_release.py'),str(csv_path),'--a','readout1','--b','readout2','--certificate',str(a.out/'certificate.json'),'--out',str(a.out/(out_name+'.csv'))]
 if labelled:cmd+=['--outcome','response']
 raw=subprocess.check_output(cmd,env=env,text=True)
 (a.out/(out_name+'.json')).write_text(raw)
 return json.loads(raw)
def close(x,y,path='value'):
 global numeric
 if isinstance(y,bool) or y is None or isinstance(y,str):assert x==y,(path,x,y)
 elif isinstance(y,(int,float)):
  numeric+=1;assert x is not None and abs(x-y)<=1e-10*max(1,abs(y)),(path,x,y)
 elif isinstance(y,list):
  assert len(x)==len(y),(path,len(x),len(y))
  for i,(xx,yy) in enumerate(zip(x,y)):close(xx,yy,f'{path}[{i}]')
 elif isinstance(y,dict):
  for k,v in y.items():close(x[k],v,path+'.'+k)

def checked(name,fn):
 fn();checks.append(name)

before=cli(HERE/'examples/published_batch.csv',False,'cli_before')
after=cli(HERE/'examples/published_batch.csv',True,'cli_after')
matched_cmd=[sys.executable,str(CORE/'matched_regimen.py'),'--out',str(a.out/'matched.json'),'--freeze',str(a.out/'matched_frozen.json')]
subprocess.check_output(matched_cmd,env=env,text=True)
matched=json.loads((a.out/'matched.json').read_text())
matched_counts=matched['modes']['fixed_threshold']['test']
matched_counts['released_error_rate']=matched_counts['released_error']
matched_counts['loss']=(matched_counts['wrong_released']+p['cost']['retest']*matched_counts['retests'])/matched_counts['patients']
labelled=[dict(patient=r['patient'],x=[r['readout1'],r['readout2']],y=r['response']) for r in rows]
cases=apply(cert,labelled)
edge=[dict(patient='equal',x=cert['model']['cutoffs']),dict(patient='low',x=[-1e6,-1e6]),dict(patient='mixed',x=[-1e6,1e6]),dict(patient='high',x=[1e6,1e6])]
cp=[dict(n=n,e=e,alpha=alpha) for n,e in [(0,0),(17,2),(27,4),(43,1),(5,5),(29,0)] for alpha in [.1,.2]]
node_input=dict(packet=p,edges=edge,cp=cp)
(a.out/'node-input.json').write_text(json.dumps(node_input))
js=r'''
const fs=require('fs'),C=require(process.argv[1]+'/chain-engine.js'),S=require(process.argv[1]+'/stats.js'),E=require(process.argv[1]+'/engine.js');
const v=JSON.parse(fs.readFileSync(process.argv[2],'utf8')),p=C.validate(v.packet),rows=C.parse(E.toCSV(p.rows,['patient','readout1','readout2','baseline_readout','response']));
const pred=C.predict(p,rows),packet_pred=C.fromPacket(p),before=C.summary(p,rows,pred,false),after=C.summary(p,rows,pred,true);
const partial=rows.map((r,i)=>({...r,response:i%2?null:r.response}));
const missing=rows.slice(0,4).map((r,i)=>({...r,readout2:i%2?null:r.readout2,baseline_readout:null}));
const changed=structuredClone(p);changed.rule.certificate.margin=1;changed.version='replacement';
const invalid=['patient,readout1\na,2\na,3','patient,readout1\na,Infinity','patient,readout1,response\na,2,3'];
const invalid_results=invalid.map(text=>{try{C.parse(text);return false;}catch{return true;}});
const cp=v.cp.map(t=>S.budget(t.n,t.e,t.alpha));
console.log(JSON.stringify({pred,packet_pred,before,after,edges:E.predict(p.rule.certificate,v.edges),cp,partial:C.summary(p,partial,pred,true),missing:C.summary(p,missing,C.predict(p,missing),true),replacement:C.summary(changed,rows,C.predict(changed,rows),true),invalid_results,cost_changed:C.summary(p,rows,pred,true,.5),all_retest:C.summary(changed,rows,C.predict(changed,rows),false)}));
'''
raw=subprocess.check_output([a.node,'-e',js,str(HERE),str(a.out/'node-input.json')],text=True)
(a.out/'browser-engine.json').write_text(raw)
b=json.loads(raw)
checked('43 patient frozen calls and margins',lambda:close(b['pred']['cases'],cases))
checked('43 cached packet actions and baseline calls',lambda:close(b['pred']['cases'],p['cases']))
checked('page reads result-file predictions',lambda:close(b['packet_pred']['cases'],p['cases']))
checked('4 cutoff and extreme-value boundary cases',lambda:close(b['edges'],apply(cert,edge)))
fields=['patients','released','retests']
checked('pre-reveal CLI counts',lambda:close(b['before']['ours'],{k:before['summary'][k] for k in fields}))
fields+=['wrong_released','overall_wrong_release','released_error_rate','loss']
checked('post-reveal CLI counts and risks and loss',lambda:close(b['after']['ours'],{k:after['summary']['observed'][k] for k in fields}))
checked('cached expected method result',lambda:close(b['after']['ours'],{k:p['expected']['ours'][k] for k in fields}))
checked('matched-regimen CLI baseline result',lambda:close(b['after']['baseline'],{k:matched_counts[k] for k in fields}))
checked('cached expected baseline result',lambda:close(b['after']['baseline'],p['expected']['baseline']))
checked('both sample-need totals and upper endpoints',lambda:close(b['after']['plans'],p['expected']['plans']))
for i,t in enumerate(cp):
 total=max(t['n'],1)
 while upper_bound(t['e'],total,.05)>t['alpha']:total+=1
 checked(f"exact binomial plan n={t['n']} e={t['e']} alpha={t['alpha']}",lambda i=i,t=t,total=total:close(b['cp'][i],dict(n=t['n'],e=t['e'],alpha=t['alpha'],upper=upper_bound(t['e'],t['n'],.05),total=total,additional=total-t['n'])))
known=[r for i,r in enumerate(labelled) if i%2==0]
checked('partial outcomes use labelled denominators',lambda:close(b['partial']['ours'],{k:measure(cert,known)[k] for k in ['wrong_released','overall_wrong_release','released_error_rate','loss']}))
checked('cost change agrees with core measure',lambda:close(b['cost_changed']['ours']['loss'],measure(cert,labelled,.5)['loss']))
checked('before reveal retains unknown errors',lambda:close(b['before']['ours']['wrong_released'],None))
checked('missing second readout goes to retest',lambda:close(b['missing']['ours']['retests'],sum(1 for i,r in enumerate(rows[:4]) if i%2 or not cases[i]['released'])))
checked('replacement packet changes all actions',lambda:close(b['replacement']['ours']['released'],0))
checked('zero-release conditional risk is undefined',lambda:close(b['replacement']['ours']['released_error_rate'],None))
checked('invalid input is rejected',lambda:close(b['invalid_results'],[True,True,True]))
# Verify CLI patient CSV, not only aggregate JSON.
clirows=list(csv.DictReader((a.out/'cli_after.csv').open()))
for c,r in zip(b['pred']['cases'],clirows):
 expected='retest' if c['action']=='retest' else 'release: '+('sensitive' if c['action']=='1' else 'resistant')
 assert c['patient']==r['patient'] and expected==r['action']
checks.append('43 actions match actual CLI CSV export')
receipt=dict(status='passed',checks=len(checks),numeric_comparisons=numeric,patient_rows=43,boundary_rows=4,
             seconds=time.perf_counter()-started,items=checks,packet_version=p['version'],core_sha256=p['provenance'])
(a.out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt,indent=2))

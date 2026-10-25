SKIP_TOKENS = ('S' + '132', 'S' + '312', '22014' + '23119', 'abo' + '2236')
#!/usr/bin/env python3
"""Pre-adjudication paired reliability, paper-cluster CI; stdlib only."""
import argparse, collections, copy, hashlib, json, math, random
from pathlib import Path

FIELDS={'physical_model':'nominal','claimed_n':'interval','independent_human_donor_n':'interval','technical_pseudoreplication_ratio':'interval','raw_multidose_public_level':'nominal','clinical_attrition':'interval','treatment_timing_match':'nominal','positive_doses_ge5':'nominal','strict_clinical_eligible':'nominal'}
CORE_FIELDS=list(FIELDS)[:7]
# Exact aliases only. Static culture and organoid morphology are different facts.
PHYSICAL_ALIASES={'tumour':'tumor','non_tumour':'non_tumor','patient_direct':'direct_patient','direct-patient':'direct_patient','ipsc':'iPSC','IPSC':'iPSC','pdx':'PDX','in_vivo_animal':'in_vivo','line':'cell_line','2d':'2D','3d':'3D'}
def harmonize(records):
    out=copy.deepcopy(records)
    for r in out.values():
        d=r.get('fields',{}).get('physical_model',{})
        if d.get('status')=='observed' and isinstance(d.get('value'),list):
            d['value']=sorted(set(PHYSICAL_ALIASES.get(x,x) for x in d['value']))
    return out

def common_dimensions(records):
    """Explicitly separate projection sensitivity, never call it synonym mapping."""
    out=harmonize(records)
    keep={'human','mouse','rat','2D','3D','direct_patient','PDX','iPSC','cell_line','primary','tumor','non_tumor','chip','in_vivo'}
    for r in out.values():
        d=r.get('fields',{}).get('physical_model',{})
        if d.get('status')=='observed' and isinstance(d.get('value'),list):d['value']=sorted(x for x in d['value'] if x in keep)
    return out

def dual_analyze(a,b,meta,replicates=10000):
    return {'unharmonized':analyze(a,b,meta,replicates),
            'closed_vocabulary_normalized':analyze(harmonize(a),harmonize(b),meta,replicates),
            'common_dimensions_projection_sensitivity':analyze(common_dimensions(a),common_dimensions(b),meta,replicates),
            'normalization':{'physical_model_aliases':PHYSICAL_ALIASES,'set_order':'lexicographic, unique','numeric_values_changed':False,'statuses_changed':False,'organoid_static_equated':False,'projection_is_not_primary_normalization':True},
            'core_fields':CORE_FIELDS,'auxiliary_fields':list(FIELDS)[7:]}
def canonical(v):return json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':'))
def alpha(pairs, metric, weighted=False):
    if len(pairs)<2:return None
    ws=[p[2] if weighted else 1. for p in pairs];sw=sum(ws)
    if metric=='interval':
        obs=sum(w*(x-y)**2 for (x,y,_),w in zip(pairs,ws))/sw
        vals=[(v,w) for (x,y,_),w in zip(pairs,ws) for v in (x,y)]
        S=sum(w for _,w in vals);den=S*S-sum(w*w for _,w in vals)
        exp=2*(S*sum(w*v*v for v,w in vals)-sum(w*v for v,w in vals)**2)/den
    else:
        obs=sum(w*(x!=y) for (x,y,_),w in zip(pairs,ws))/sw
        counts=collections.defaultdict(float)
        for (x,y,_),w in zip(pairs,ws):counts[canonical(x)]+=w;counts[canonical(y)]+=w
        S=2*sw;den=S*S-2*sum(w*w for w in ws)
        exp=(S*S-sum(v*v for v in counts.values()))/den
    return 1-obs/exp if exp>1e-15 else None

def value(record,field):
    d=record.get('fields',{}).get(field,{})
    v=d.get('value')
    return v if d.get('status')=='observed' and v is not None else None
def valid(v,metric):
    if v is None:return False
    return not isinstance(v,bool) and isinstance(v,(int,float)) and math.isfinite(v) if metric=='interval' else True
def percentile(v,p):
    v=sorted(v);k=(len(v)-1)*p;a=int(k);return v[a]+(v[min(a+1,len(v)-1)]-v[a])*(k-a)
def analyze(a,b,meta,replicates=2000):
    common=sorted(set(a)&set(b));out={};rng=random.Random(20261024)
    strata=collections.defaultdict(list)
    formal=len(common)==len(meta)
    for sid in common:strata[meta[sid]['stratum'] if formal else 'pilot_papers'].append(sid)
    bootstrap=[[s for group in strata.values() for s in rng.choices(group,k=len(group))] for _ in range(replicates)]
    for field,metric in FIELDS.items():
        def pairs(ids):
            return [(value(a[s],field),value(b[s],field),meta[s]['inverse_probability_weight']) for s in ids if valid(value(a[s],field),metric) and valid(value(b[s],field),metric)]
        pp=pairs(common);aa=alpha(pp,metric)
        # A resampled duplicate of the only comparable paper does not create a
        # second independent paper. Undefined point estimates have no CI.
        boot=[x for ids in bootstrap if (x:=alpha(pairs(ids),metric)) is not None] if aa is not None else []
        status=lambda r:r.get('fields',{}).get(field,{}).get('status','missing_field')
        out[field]={'metric':metric,'comparable_papers':len(pp),'paired_papers':len(common),'alpha':aa,'alpha_95_cluster_bootstrap_ci':[percentile(boot,.025),percentile(boot,.975)] if boot else None,'undefined_reason':('fewer than two comparable papers' if len(pp)<2 else 'zero pooled variation') if aa is None else None,'valid_bootstrap_replicates':len(boot),'requested_bootstrap_replicates':replicates,'raw_agreement_comparable':sum(x==y for x,y,w in pp)/len(pp) if pp else None,'status_agreement_all_pairs':sum(status(a[s])==status(b[s]) for s in common)/len(common) if common else None,'status_alpha':alpha([(status(a[s]),status(b[s]),1) for s in common],'nominal'),'status_counts_A':dict(collections.Counter(status(a[s]) for s in common)),'status_counts_B':dict(collections.Counter(status(b[s]) for s in common)),'ipw_alpha_sensitivity':alpha(pp,metric,True),'key_field_threshold_met':aa>=.8 if aa is not None else None}
    return {'paired_papers':len(common),'fields':out,'seed':20261024,'bootstrap_unit':'paper, paired, within original sampling stratum' if formal else 'paper, paired, pilot-only calibration reliability; no field-population inference','singleton_sample_strata':[h for h,v in strata.items() if len(v)==1],'adjudication_used':False,'missing_numeric_zero_imputation':False}

def readrecords(p):
    out={}
    for f in sorted(p.glob('*.json')):
        r=json.loads(f.read_text())
        if 'sample_id' in r and 'fields' in r:
            if r['sample_id'] in out:raise ValueError('duplicate sample ID')
            out[r['sample_id']]=r
    return out
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('route_a',type=Path);ap.add_argument('route_b',type=Path);ap.add_argument('--sample',type=Path,default=Path(__file__).with_name('sample400.json'));ap.add_argument('--out',type=Path,required=True);ap.add_argument('--bootstrap',type=int,default=2000);ap.add_argument('--dual',action='store_true');args=ap.parse_args()
    m={p['sample_id']:p for p in json.loads(args.sample.read_text())};a=readrecords(args.route_a);b=readrecords(args.route_b)
    r=(dual_analyze if args.dual else analyze)(a,b,m,replicates=args.bootstrap);r.update(route_a_records=len(a),route_b_records=len(b),input_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for d in [args.route_a,args.route_b] for p in sorted(d.glob('*.json'))})
    args.out.write_text(json.dumps(r,ensure_ascii=False,indent=2,allow_nan=False)+'\n')

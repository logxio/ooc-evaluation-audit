#!/usr/bin/env python3
"""Recompute acquisition scores from saved point predictions and real responses."""
import os
for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ[name]='1'
import argparse
from collections import Counter,defaultdict
import json
from pathlib import Path
import sys
import time
sys.dont_write_bytecode=True
import numpy as np
import paper_acquisition as pa


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--data',type=Path,required=True)
    p.add_argument('--historical',type=Path,required=True)
    a=p.parse_args();start=time.perf_counter()
    tasks={t.chem:t for t in pa.cf.load_tasks(a.data)}
    summary=json.loads((a.out/'summary.json').read_text())
    protocol=json.loads((a.out/'protocol.json').read_text())
    assert pa.sha(a.data)==protocol['input_sha256']['data']
    assert pa.sha(Path(pa.__file__))==protocol['input_sha256']['driver']
    totals=Counter();max_score_gap=0.0;max_cnp_gap=0.0
    measurement=[];update=[]
    for fold in range(1,5):
        folder=a.out/f'fold{fold}'
        meta=json.loads((folder/'evaluation.json').read_text())
        assert meta['protocol_sha256']==summary['protocol_sha256']==pa.sha(a.out/'protocol.json')
        for file,digest in meta['output_sha256'].items():
            assert pa.sha(folder/file)==digest
        choices=[json.loads(line) for line in (folder/'choices.jsonl').read_text().splitlines()]
        ci={(c['chemical'],c['design']):c for c in choices}
        branch=pa.read_table(folder/'branch_results.csv')
        design=pa.read_table(folder/'design_results.csv')
        bi={(r['chemical'],int(r['design']),r['method'],int(r['branch'])):r for r in branch}
        di={(r['chemical'],int(r['design']),r['method'],r['policy']):r for r in design}
        with np.load(folder/'point_predictions.npz',allow_pickle=False) as archive:
            z={name:archive[name] for name in archive.files}
            groups=defaultdict(list)
            for i,key in enumerate(zip(z['chemical'],z['design'],z['method'],z['branch'])):
                groups[tuple(key)].append(i)
            initial={}
            for (chem,design_id,method,branch_id),indices in groups.items():
                ix=np.asarray(indices);t=tasks[str(chem)];choice=ci[str(chem),int(design_id)]
                q=z['query_log10'][ix];tix=np.searchsorted(t.levels,q)
                truth=z['truth'][ix];mask=z['observed'][ix];pred=z['prediction'][ix];raw=z['raw_model_prediction'][ix]
                np.testing.assert_array_equal(truth,t.mu[tix].reshape(len(q),68))
                np.testing.assert_array_equal(mask,t.ok[tix].reshape(len(q),68))
                np.testing.assert_array_equal(q,np.asarray(choice['candidates']))
                assert not set(q)&set(choice['initial'])
                acquired=z['is_acquired'][ix]
                assert int(acquired.sum())==(0 if branch_id==-1 else 1)
                if branch_id>=0:
                    assert q[acquired][0]==q[branch_id]
                    np.testing.assert_array_equal(pred[acquired][mask[acquired]],truth[acquired][mask[acquired]])
                np.testing.assert_array_equal(pred[~acquired],raw[~acquired])
                score=float(np.abs(pred-truth)[mask].mean())
                remaining=float(np.abs(pred-truth)[mask&~acquired[:,None]].mean())
                r=bi[str(chem),int(design_id),str(method),int(branch_id)]
                max_score_gap=max(max_score_gap,abs(score-float(r['fixed_target_mae'])),abs(remaining-float(r['unrevealed_mae'])))
                assert max_score_gap<1e-6
                if branch_id==-1:
                    initial[str(chem),int(design_id),str(method)]=raw.copy()
                stale=initial[str(chem),int(design_id),str(method)].copy()
                stale[acquired]=truth[acquired]
                stale_score=float(np.abs(stale-truth)[mask].mean())
                assert abs(stale_score-float(r['measurement_only_mae']))<1e-6
                totals['concentration_prediction_rows']+=len(q)
                totals['observed_scalar_predictions']+=int(mask.sum())
            # Original K3 CNP replay compares the very same real checkpoint means.
            with np.load(a.historical/f'fold{fold}.npz',allow_pickle=False) as historical:
                hz={name:historical[name] for name in historical.files}
                for choice in choices:
                    key=(choice['chemical'],choice['design'],'cnp',-1)
                    ix=groups[key]
                    select=(hz['chemical']==key[0])&(hz['design']==key[1])
                    old=hz['C'][select].reshape(len(ix),68)
                    np.testing.assert_array_equal(z['truth'][ix],hz['truth'][select].reshape(len(ix),68))
                    gap=float(np.max(np.abs(z['prediction'][ix]-old)))
                    max_cnp_gap=max(max_cnp_gap,gap)
                    assert gap<1e-5, (key,gap)
        for choice in choices:
            n=choice['n_candidates'];indices=choice['choices']
            fixed=int(np.argmax(choice['maximin_scores']));adaptive=int(np.argmax(choice['disagreement_scores']))
            assert fixed==indices['fixed_maximin'] and adaptive==indices['model_disagreement']
            assert indices['uniform_random']==list(range(n))
            assert sum(choice['random_weights'])==1 or abs(sum(choice['random_weights'])-1)<1e-14
            t=tasks[choice['chemical']];obs=pa.observed(t,np.array(choice['initial']))
            expected=__import__('hashlib').sha256(obs.logc.tobytes()+obs.y.tobytes()+obs.m.tobytes()).hexdigest()
            assert expected==choice['observed_sha256']
            for method in pa.METHODS:
                for policy in ('none',)+pa.POLICIES:
                    ix=[-1] if policy=='none' else indices[policy]
                    ix=ix if isinstance(ix,list) else [ix]
                    rs=[bi[t.chem,choice['design'],method,j] for j in ix]
                    row=di[t.chem,choice['design'],method,policy]
                    for field in ('fixed_target_mae','unrevealed_mae','measurement_only_mae','final_wells','remaining_cells'):
                        assert abs(np.mean([float(r[field]) for r in rs])-float(row[field]))<1e-12
                    if method=='interpolation':
                        measurement.append(dict(chemical=t.chem,fold=fold,design=choice['design'],policy=policy,
                            n_candidates=n,full_levels=len(t.levels),initial_levels=3,final_levels=3 if policy=='none' else 4,
                            initial_wells=float(row['initial_wells']),final_wells=float(row['final_wells']),full_wells=float(row['full_wells'])))
                    update.append(dict(chemical=t.chem,method=method,policy=policy,
                        delta=float(row['fixed_target_mae'])-float(row['measurement_only_mae'])))
        totals['choices']+=len(choices)
        totals['branches']+=len(branch)
    assert totals['choices']==970
    pa.table(a.out/'measurement_budget.csv',measurement)
    update_summary={}
    for method in pa.METHODS:
        for policy in pa.POLICIES:
            values=defaultdict(list)
            for r in update:
                if r['method']==method and r['policy']==policy and (method!='cnp' or r['chemical']!='Phenobarbital'):
                    values[r['chemical']].append(r['delta'])
            update_summary[f'{method}/{policy}']=pa.paired([np.mean(values[k]) for k in sorted(values)])
    measurements={}
    for policy in ('none',)+pa.POLICIES:
        rows=[r for r in measurement if r['policy']==policy]
        measurements[policy]=dict(designs=len(rows),concentration_measurements=sum(r['final_levels'] for r in rows),
            initial_well_measurements=sum(r['initial_wells'] for r in rows),
            final_well_measurements=sum(r['final_wells'] for r in rows),
            full_well_measurements=sum(r['full_wells'] for r in rows),
            full_concentration_measurements=sum(r['full_levels'] for r in rows),
            interpretation='Sum of 970 separate retrospective scenarios; repeated designs are not independent wet-lab runs.')
    result=dict(status='passed',counts=dict(totals),max_pointwise_score_recomputation_gap=max_score_gap,
                max_cnp_k3_checkpoint_replay_gap=max_cnp_gap,measurement_budgets=measurements,
                reconditioning_minus_measurement_only=update_summary,
                seconds=time.perf_counter()-start,peak_rss_bytes=pa.rss(),
                checked=['real source values and missingness','fixed common targets','selected measured cells',
                'raw model predictions retained','per-branch scores','exact random averaging',
                'response-free maximin and committed adaptive scores','observed-input hashes',
                'original K3 CNP checkpoint replay','equal training budgets','protocol and artifact hashes'])
    pa.dump(a.out/'verification.json',result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('measurement_budgets','reconditioning_minus_measurement_only')},indent=2))


if __name__=='__main__':
    main()

"""Replay the tool-agent archive offline: verify hashes, re-judge every saved contract, rebuild the ablation."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from .engine import evaluate
from .replay import replay as replay_legacy

HERE=Path(__file__).resolve().parent
STAGES=['single_pass','one_feedback','tool_loop']


def judge(contract,index,target,stored):
    # Frozen target with its published rounding. Checks that needed live state (uncertain figure labels,
    # Ewart's uncorrected-MOS rule) travel in the stored verdict, so a replay can confirm or withdraw a pass.
    reported=(contract.get('headline') or {}).get('reported');value=target['value']
    if isinstance(reported,(int,float)) and abs(reported-value)<=target['tolerance']:value=reported
    result=evaluate(contract,index,{'metric':target['metric'],'reported':value,'n':target['n'],'tolerance':target['tolerance']})
    return bool(result['matched'] and (stored or {}).get('matched'))


def cohort(config,name):
    # Development rounds read the frozen eight plus two controls; an external round reads the separately frozen scale-up cohort.
    if config['rounds'][name].get('cohort')=='external':
        external=config['external'];return external['eligible'],external['negative_controls'],external['targets']
    return config['eligible'],config['negative_controls'],config['targets']


def chain(folder,paper,config,gold,index,name):
    state=json.loads((folder/'state.json').read_text())
    if (folder/'visual.json').exists():index={**index,**{k:v['value'] for k,v in json.loads((folder/'visual.json').read_text()).items()}}
    calls=[json.loads(p.read_text()) for p in sorted(folder.glob('call*.receipt.json'))]
    reads=[json.loads(p.read_text()) for p in sorted(folder.glob('reader/*.receipt.json'))]
    tools=Counter(a['name'] for p in sorted(folder.glob('call*.tools.json')) for a in json.loads(p.read_text()))
    stages={}
    for stage in STAGES:
        checkpoint=state.get('checkpoints',{}).get(stage)
        if checkpoint is None:continue
        contract=checkpoint['contract'] if isinstance(checkpoint.get('contract'),dict) else {}
        fields=contract.get('fields') or {}
        correct=sum(isinstance(fields.get(k),dict) and fields[k].get('value') in v for k,v in gold['fields'].items())
        eligible,controls,targets=cohort(config,name)
        if paper in controls:passed=contract.get('status')=='no_headline' and not (contract.get('headline') or {}).get('records')
        else:passed=bool(contract) and judge(contract,index,targets[paper],checkpoint.get('evaluation'))
        stages[stage]={'passed':passed,'fields_correct':correct}
    usage=[r.get('usage',{}) for r in calls+reads]
    return {'done':state.get('done'),'stop_reason':state.get('stop_reason'),'model_calls':len(calls),'reader_calls':len(reads),
            'prompt_tokens':sum(u.get('prompt_tokens',0) for u in usage),
            'cached_tokens':sum(u.get('prompt_tokens_details',{}).get('cached_tokens',0) for u in usage),
            'completion_tokens':sum(u.get('completion_tokens',0) for u in usage),
            'estimated_cny':round(sum(r.get('estimated_cny',0) for r in calls+reads),4),
            'model_seconds':round(sum(r.get('seconds',0) for r in calls+reads),1),'tools':dict(tools),'stages':stages}


def replay_round(root,name,config,gold,audit):
    lanes={};eligible,controls,_=cohort(config,name)
    for lane in config['rounds'][name].get('lanes',['strong','weak']):
        papers={}
        for paper in eligible+controls:
            folder=root/name/lane/paper
            if not (folder/'state.json').exists():continue
            # Field gold exists for the development cohort only; external chains are read on the headline alone.
            papers[paper]=chain(folder,paper,config,gold.get(paper,{'fields':{}}),json.loads((root/'sources'/paper/'index.json').read_text()),name)
            verdict=audit.get(name,{}).get(lane,{}).get(paper)
            if verdict:papers[paper]['audit']=verdict['audited']
        table={}
        for stage in STAGES:
            measured=[p for p in eligible if stage in papers.get(p,{}).get('stages',{})]
            refused=[p for p in controls if stage in papers.get(p,{}).get('stages',{})]
            table[stage]={'eligible':len(eligible),'measured':len(measured),'passes':sum(papers[p]['stages'][stage]['passed'] for p in measured),
                          'fields_correct':sum(papers[p]['stages'][stage]['fields_correct'] for p in measured),'fields_total':0 if config['rounds'][name].get('cohort')=='external' else 10*len(measured),
                          'controls_measured':len(refused),'correct_refusals':sum(papers[p]['stages'][stage]['passed'] for p in refused)}
        passed=[p for p in eligible if papers.get(p,{}).get('stages',{}).get('tool_loop',{}).get('passed')]
        table['tool_loop']['audited_passes']=sum(papers[p].get('audit')=='pass' for p in passed)
        table['tool_loop']['unaudited_passes']=sum('audit' not in papers[p] for p in passed)
        lanes[lane]={'model':config['model_sets'][config['rounds'][name]['model_set']][lane]['model'],'ablation':table,'unfinished':[p for p in eligible if p in papers and not papers[p]['done']],
                     'totals':{k:round(sum(x[k] for x in papers.values()),4) for k in ['model_calls','reader_calls','prompt_tokens','cached_tokens','completion_tokens','estimated_cny','model_seconds']},
                     'papers':papers}
    return lanes


def replay(root):
    manifest=json.loads((root/'manifest.json').read_text())
    for relative,expected in manifest['files'].items():
        if hashlib.sha256((root/relative).read_bytes()).hexdigest()!=expected:raise ValueError('Archive hash mismatch: '+relative)
    config=json.loads((root/'experiment.json').read_text());gold=json.loads((HERE/'gold.json').read_text())
    audit=json.loads((root/'audit.json').read_text())
    fixture=json.loads((root/'functional_fixture.json').read_text());target=fixture['target']
    functional=evaluate(fixture['tools'][1]['output']['contract'],fixture['source_cells'],
                        {'metric':target['metric'],'reported':target['value'],'n':target['n'],'tolerance':target['tolerance']})
    if not functional['matched']:raise ValueError('Cached integration fixture did not reproduce its source calculation')
    rounds={path.name:replay_round(root,path.name,config,gold,audit) for path in sorted(root.glob('round*')) if path.is_dir()}
    final={}
    for name,spec in config['rounds'].items():
        # A round that reruns only some papers is read together with the round it carries the others from.
        if 'carried' not in spec or name not in rounds:continue
        for lane in spec.get('lanes',['strong','weak']):
            source={p:name if p in rounds[name][lane]['papers'] else spec['carried']['from'] for p in config['eligible']}
            chains={p:rounds[source[p]][lane]['papers'].get(p,{}) for p in config['eligible']}
            passed=[p for p,c in chains.items() if c.get('stages',{}).get('tool_loop',{}).get('passed')]
            controls=[rounds[name][lane]['papers'].get(p,{}).get('stages',{}).get('tool_loop',{}).get('passed') for p in config['negative_controls']]
            final[f'{name}/{lane}']={'eligible':len(config['eligible']),'judged_passes':len(passed),
                                     'audited_passes':sum(chains[p].get('audit')=='pass' for p in passed),
                                     'audited':sorted(p for p in passed if chains[p].get('audit')=='pass'),
                                     'correct_refusals':sum(bool(x) for x in controls),'controls':len(controls),'source_round':source}
    for name,spec in config['rounds'].items():
        # The external cohort is reported beside the development eight, by paper type, and never pooled with them.
        if spec.get('cohort')!='external' or name not in rounds:continue
        external=config['external']
        for lane in spec.get('lanes',['strong','weak']):
            chains=rounds[name][lane]['papers'];entry={'cohort':'external','by_type':{}}
            for kind in sorted(set(external['types'].values())):
                group=[p for p in external['eligible'] if external['types'][p]==kind]
                passed=[p for p in group if chains.get(p,{}).get('stages',{}).get('tool_loop',{}).get('passed')]
                entry['by_type'][kind]={'eligible':len(group),'judged_passes':len(passed),'audited_passes':sum(chains[p].get('audit')=='pass' for p in passed),
                                        'audited':sorted(p for p in passed if chains[p].get('audit')=='pass')}
            entry.update({k:sum(v[k] for v in entry['by_type'].values()) for k in ['eligible','judged_passes','audited_passes']})
            entry['audited']=sorted(p for v in entry['by_type'].values() for p in v['audited'])
            refusals=[chains.get(p,{}).get('stages',{}).get('tool_loop',{}).get('passed') for p in external['negative_controls']]
            entry.update(correct_refusals=sum(bool(x) for x in refusals),controls=len(refusals))
            final[f'{name}/{lane}']=entry
    errors=[{'file':str(p.relative_to(root)),'error':p.read_text().strip()} for p in sorted(root.rglob('*.error.txt'))]
    return {'rounds':rounds,'final':final,'audit_method':audit['method'],'blind_reader_probe':audit.get('blind_reader_probe'),'service_errors':errors,
            'functional_fixture':{'origin':fixture['origin'],'matched':functional['matched'],'n':functional['n'],'computed':functional['computed']},
            'archive_files':len(manifest['files'])}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--archive',type=Path,default=HERE/'agent_archive')
    p.add_argument('--out',type=Path,default=HERE/'agent_results.json');a=p.parse_args()
    result=replay(a.archive);a.out.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    legacy=replay_legacy();(a.out.parent/'results.json').write_text(json.dumps(legacy,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    summary={name:{lane:{'ablation':data['ablation'],'unfinished':data['unfinished'],'estimated_cny':data['totals']['estimated_cny']} for lane,data in lanes.items()}
             for name,lanes in result['rounds'].items()}
    print(json.dumps({'agent':summary,'final':{k:{x:v[x] for x in ['judged_passes','audited_passes','audited','correct_refusals']} for k,v in result['final'].items()},
                      'service_errors':len(result['service_errors']),'archive_files':result['archive_files'],
                      'legacy':{k:legacy[k] for k in ['single_pass','one_feedback','latest_development','free_local']}},ensure_ascii=False,indent=2,allow_nan=False))


if __name__=='__main__':main()

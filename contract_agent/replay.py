"""Reproduce every cached extraction score and source-bound numerical check offline."""
import argparse
import hashlib
import json
from pathlib import Path
import time

from .engine import evaluate, parse_reply, source_index

HERE=Path(__file__).resolve().parent


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replay(root=HERE):
    start=time.monotonic()
    manifest=json.loads((root/'manifest.json').read_text())
    for name,expected in manifest['files'].items():
        path=root/name
        if not path.is_file() or file_hash(path)!=expected:
            raise ValueError(f'Archive hash mismatch: {name}')
    gold=json.loads((root/'gold.json').read_text())
    papers=[]
    usage=[]
    for name in manifest['papers']:
        documents=json.loads((root/'data'/name/'documents.json').read_text())
        index=source_index(documents)
        entry={'paper':name,'rounds':[]}
        for path in sorted((root/'cache'/name).glob('round*.response.json')):
            prefix=path.name.removesuffix('.response.json')
            receipt=json.loads(path.with_name(prefix+'.receipt.json').read_text())
            if file_hash(path)!=receipt['response_sha256']:raise ValueError(f'Response changed: {name}/{prefix}')
            response=json.loads(path.read_text())
            contract=parse_reply(response['choices'][0]['message']['content'])
            target=gold[name].get('target')
            candidates=gold[name].get('targets',[])
            if candidates:
                matches=[x for x in candidates if (x['metric'],x['reported'])==(contract.get('headline',{}).get('metric'),contract.get('headline',{}).get('reported'))]
                target=matches[0] if matches else candidates[0]
            numerical=evaluate(contract,index,target)
            semantic=[]
            for rule in gold[name].get('semantic_exclusions',[]):
                if contract.get('headline',{}).get('threshold')==rule['threshold'] and rule['source_prefix'] in json.dumps(contract.get('headline',{}).get('records',[])):
                    semantic.append(rule['reason'])
            scores={k:contract.get('fields',{}).get(k,{}).get('value') in values for k,values in gold[name]['fields'].items()}
            entry['rounds'].append({'round':int(prefix[5:]),'fields_correct':sum(scores.values()),
                'fields_total':len(scores),'field_scores':scores,'numeric':numerical,
                'semantic_errors':semantic,'verified_numerical_contract':numerical['matched'] and not semantic,
                'all_fields_and_numeric_pass':numerical['matched'] and not semantic and all(scores.values()),
                'contract':contract,'usage':response.get('usage',{})})
            usage.append(response.get('usage',{}))
        if not entry['rounds']:raise ValueError(f'No cached extraction for {name}')
        free_path=root/'free_cache'/name/'round0.response.json'
        if not free_path.exists():raise ValueError(f'Missing free comparison: {name}')
        free_response=json.loads(free_path.read_text())
        try:free_contract=parse_reply(free_response['choices'][0]['message']['content'])
        except (ValueError,KeyError):free_contract={}
        entry['free_fields_correct']=sum(free_contract.get('fields',{}).get(k,{}).get('value') in values for k,values in gold[name]['fields'].items())
        try:
            entry['free_numeric']=evaluate(free_contract,index,gold[name].get('target'))
        except (ValueError,TypeError,KeyError) as exc:
            entry['free_numeric']={'matched':False,'errors':[str(exc)]}
        entry['free_usage']=free_response.get('usage',{})
        papers.append(entry)
    first=[p['rounds'][0] for p in papers]
    one_feedback=[p['rounds'][min(1,len(p['rounds'])-1)] for p in papers]
    last=[p['rounds'][-1] for p in papers]
    def summary(rows):
        return {'fields_correct':sum(r['fields_correct'] for r in rows),'fields_total':sum(r['fields_total'] for r in rows),
                'numeric_matches':sum(r['numeric']['matched'] for r in rows),
                'verified_numerical_contracts':sum(r['verified_numerical_contract'] for r in rows),
                'all_fields_and_numeric_pass':sum(r['all_fields_and_numeric_pass'] for r in rows),'papers':len(rows)}
    def cost(u):
        inputs=u.get('prompt_tokens',0);outputs=u.get('completion_tokens',0)
        cached=u.get('prompt_tokens_details',{}).get('cached_tokens',0)
        ir,orr=(2,8) if inputs<=256000 else (6,24)
        return ((inputs-cached)*ir+cached*ir*.2+outputs*orr)/1e6
    s={'single_pass':summary(first),'one_feedback':summary(one_feedback),'latest_development':summary(last),
       'free_local':{'fields_correct':sum(p['free_fields_correct'] for p in papers),'fields_total':sum(r['fields_total'] for r in first),
                     'numeric_matches':sum(p['free_numeric']['matched'] for p in papers),'papers':len(papers)},
       'usage':{'calls':len(usage),'prompt_tokens':sum(u.get('prompt_tokens',0) for u in usage),
                'completion_tokens':sum(u.get('completion_tokens',0) for u in usage),
                'list_price_estimate_cny':sum(cost(u) for u in usage),
                'cost_source':'https://help.aliyun.com/zh/model-studio/qwen3-7-plus',
                'billing_note':'Estimated for received successful responses only; one timed-out request has unknown usage; actual invoice not available.'},
       'runtime_seconds':time.monotonic()-start,'papers':papers}
    return s


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,default=HERE/'results.json')
    args=p.parse_args()
    result=replay()
    args.out.write_text(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='papers'},indent=2))


if __name__=='__main__':main()

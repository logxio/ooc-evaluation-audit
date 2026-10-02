"""Extract contracts live or replay hash-verified cached responses (the default)."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request

from .engine import evaluate, parse_reply, source_index

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n')


def request(messages, args, prefix):
    payload = {'model': args.model, 'messages': messages, 'temperature': 0,
               'max_tokens': args.max_tokens, 'response_format': {'type': 'json_object'}}
    if 'dashscope.' in args.base_url:
        payload['enable_thinking'] = False
    else:
        payload['chat_template_kwargs'] = {'enable_thinking': False}
    raw = json.dumps(payload, ensure_ascii=False).encode()
    paid_usage = []
    for receipt_path in args.cache.glob('*/round*.receipt.json'):
        paid_usage.append(json.loads(receipt_path.read_text()).get('usage', {}))
    spent_upper = sum((u.get('prompt_tokens', 0)*8 + u.get('completion_tokens', 0)*48)/1e6 for u in paid_usage)
    request_upper = (len(raw)*8 + 12000*48)/1e6
    if 'dashscope.' in args.base_url and spent_upper + request_upper > 50:
        raise ValueError(f'50 CNY ceiling: prior upper estimate {spent_upper:.3f}; request bound {request_upper:.3f}')
    prefix.parent.mkdir(parents=True, exist_ok=True)
    prefix.with_suffix('.request.json').write_bytes(raw)
    headers = {'Content-Type': 'application/json'}
    key = os.environ.get(args.key_env)
    if key: headers['Authorization'] = 'Bearer ' + key
    started = time.monotonic()
    try:
        with urllib.request.urlopen(urllib.request.Request(args.base_url.rstrip('/')+'/chat/completions', data=raw, headers=headers), timeout=args.timeout) as r:
            response = r.read()
    except urllib.error.HTTPError as exc:
        error = exc.read()
        prefix.with_suffix('.error.txt').write_bytes(error)
        raise RuntimeError(f'HTTP {exc.code}: {error.decode(errors="replace")}') from exc
    except (TimeoutError, urllib.error.URLError) as exc:
        prefix.with_suffix('.error.txt').write_text(f'{type(exc).__name__}: {exc}\n')
        raise
    prefix.with_suffix('.response.json').write_bytes(response)
    parsed = json.loads(response)
    dump(prefix.with_suffix('.receipt.json'), {'request_sha256':sha(prefix.with_suffix('.request.json')),
         'response_sha256':sha(prefix.with_suffix('.response.json')), 'seconds':time.monotonic()-started,
         'model':parsed.get('model'), 'usage':parsed.get('usage', {})})
    return parsed


def one(name, args):
    source = args.sources/name
    documents = json.loads((source/'documents.json').read_text())
    index = source_index(documents)
    gold_path = HERE/'gold.json'
    gold = json.loads(gold_path.read_text()).get(name, {}) if gold_path.exists() else {}
    prompt = (HERE/'prompt.txt').read_text()
    # Field gold is withheld. Frozen published numeric targets enter execution feedback.
    messages = [{'role':'system','content':prompt},
                {'role':'user','content':(source/'input.txt').read_text()}]
    outputs = []
    for turn in range(args.rounds+1):
        prefix = args.cache/name/f'round{turn}'
        response_path = prefix.with_suffix('.response.json')
        if response_path.exists():
            receipt = json.loads(prefix.with_suffix('.receipt.json').read_text())
            if sha(response_path) != receipt['response_sha256']:
                raise ValueError(f'Response hash mismatch for {name} round {turn}')
            request_path = prefix.with_suffix('.request.json')
            if request_path.exists() and sha(request_path) != receipt['request_sha256']:
                raise ValueError(f'Request hash mismatch for {name} round {turn}')
            if request_path.exists():
                messages = json.loads(request_path.read_text())['messages']
            response = json.loads(response_path.read_text())
        elif args.live:
            response = request(messages, args, prefix)
        else:
            break
        text = response['choices'][0]['message']['content']
        target = gold.get('target')
        try:
            contract = parse_reply(text)
            target = gold.get('target')
            if gold.get('targets'):
                selected = [t for t in gold['targets'] if t['metric'] == contract.get('headline',{}).get('metric') and t['reported'] == contract.get('headline',{}).get('reported')]
                target = selected[0] if selected else gold['targets'][0]
            numerical = evaluate(contract, index, target)
            numerical['semantic_errors'] = []
            for rule in gold.get('semantic_exclusions', []):
                if contract.get('headline',{}).get('threshold') == rule['threshold'] and rule['source_prefix'] in json.dumps(contract.get('headline',{}).get('records', [])):
                    numerical['semantic_errors'].append(rule['reason'])
            numerical['verified'] = numerical['matched'] and not numerical['semantic_errors']
        except (ValueError, KeyError, TypeError) as exc:
            contract = {}
            numerical = {'matched':False,'errors':[f'{type(exc).__name__}: {exc}']}
        field_scores = {}
        for field, accepted in gold.get('fields', {}).items():
            observed = contract.get('fields',{}).get(field,{}).get('value')
            field_scores[field] = {'observed':observed,'accepted':accepted, 'correct':observed in accepted}
        outputs.append({'turn':turn,'contract':contract,'numerical':numerical,
                        'fields':field_scores,'usage':response.get('usage',{})})
        dump(args.results/name/f'round{turn}.json', outputs[-1])
        print(json.dumps({'paper':name,'turn':turn,'matched':numerical['matched'],
                         'correct':sum(v['correct'] for v in field_scores.values()),
                         'fields':len(field_scores),'usage':response.get('usage',{}),
                         'errors':numerical['errors'][:4]}, ensure_ascii=False), flush=True)
        if numerical.get('verified', False):
            break
        messages.append({'role':'assistant','content':text})
        # The published numeric target is the judge, fixed before extraction.
        # Field gold and manual semantic corrections remain hidden from the model.
        try:
            feedback = evaluate(contract, index, target)
        except (ValueError, KeyError, TypeError) as exc:
            feedback = {'matched': False, 'errors': [f'Invalid contract: {exc}']}
        feedback.pop('rows', None)
        all_errors = feedback['errors']
        feedback['error_count'] = len(all_errors)
        feedback['errors'] = all_errors[:6] + all_errors[-2:] if len(all_errors)>8 else all_errors
        hint = ''
        if any('convert string to float' in e or 'Unmapped value' in e for e in all_errors):
            hint = (' A PDF reference reads the ENTIRE LINE, not a single cell. Add a regex with one capture group to isolate the actual score column and a separate regex for the truth column. '
                    'Synthetic example only: for a line "A17 0.25 PR", score={"ref":"line","regex":"^\\\\S+\\\\s+(\\\\S+)"}, truth={"ref":"line","regex":"(PR|PD)$","map":{"PR":1,"PD":0}}. Choose the columns from the real header. Use these keys inside each score/truth object. Never omit regex for a mixed text line.')
        messages.append({'role':'user','content':'Execution feedback:\n'+json.dumps(feedback, ensure_ascii=False)+'\nRe-read the supplied sources and return a complete corrected contract. Retain unresolved limitations. If numeric-only data cannot support a clinical headline, state the precise missing evidence.'+hint})
    return outputs


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--papers', nargs='+')
    p.add_argument('--sources',type=Path, default=HERE/'data')
    p.add_argument('--cache',type=Path, default=HERE/'cache')
    p.add_argument('--results',type=Path, default=HERE/'results')
    p.add_argument('--live',action='store_true')
    p.add_argument('--base-url',default='')
    p.add_argument('--model',default='')
    p.add_argument('--key-env',default='CONTRACT_MODEL_KEY')
    p.add_argument('--timeout',type=int,default=150)
    p.add_argument('--max-tokens',type=int,default=12000)
    p.add_argument('--rounds',type=int,default=1)
    args = p.parse_args(argv)
    if args.live and not (args.base_url and args.model): p.error('--live requires --base-url and --model')
    names = args.papers or sorted(x.name for x in args.sources.iterdir() if (x/'documents.json').exists())
    outputs = {name:one(name,args) for name in names}
    dump(args.results/'all.json',outputs)


if __name__ == '__main__': main()

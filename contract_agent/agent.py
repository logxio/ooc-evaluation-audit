"""Bounded multimodal tool loop, with single-pass and one-feedback checkpoints."""
import argparse
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import time
import urllib.error
import urllib.request

from .agent_tools import TOOLS,Workbench
from .engine import parse_reply

HERE=Path(__file__).resolve().parent


def dump(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def price(spec,inputs):
    # The first tier whose input bound covers the request's input length prices all of its tokens.
    return next(t for t in spec['price_cny_per_million'] if t['max_input_tokens'] is None or inputs<=t['max_input_tokens'])


def cost(spec,usage):
    inputs=usage.get('prompt_tokens',0);outputs=usage.get('completion_tokens',0)
    cached=(usage.get('prompt_tokens_details') or {}).get('cached_tokens',0);tier=price(spec,inputs)
    return ((inputs-cached)*tier['input']+cached*tier['cached_input']+outputs*tier['output'])/1e6


def budget(path,key,reserve=None,settle=None):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a+') as stream:
        fcntl.flock(stream,fcntl.LOCK_EX);stream.seek(0);raw=stream.read();data=json.loads(raw) if raw else {'ceiling':107.54,'entries':{}}
        if reserve is not None:
            used=sum(x.get('actual',x['reserve']) for x in data['entries'].values())
            if key in data['entries']:raise RuntimeError('This request already has a billing reservation; inspect its cache before retrying.')
            if used+reserve>data['ceiling']:raise RuntimeError(f'Budget limit: reserved/received {used:.3f}+request {reserve:.3f}>{data["ceiling"]}')
            data['entries'][key]={'reserve':reserve}
        if settle is not None:data['entries'][key]['actual']=settle
        stream.seek(0);stream.truncate();stream.write(json.dumps(data,indent=2));stream.flush();fcntl.flock(stream,fcntl.LOCK_UN)
    return data


def request(payload,args,folder,turn,name=None):
    folder.mkdir(parents=True,exist_ok=True)
    base=name or f'call{turn:02d}';prefix=folder/base
    attempt=0
    while prefix.with_suffix('.error.txt').exists():
        attempt+=1;prefix=folder/f'{base}_attempt{attempt}'
    request_path=prefix.with_suffix('.request.json');response_path=prefix.with_suffix('.response.json')
    raw=json.dumps(payload,ensure_ascii=False).encode()
    if response_path.exists():
        if request_path.read_bytes()!=raw:raise RuntimeError('Cached response belongs to a different request; preserve this run and use a new archive.')
        return json.loads(response_path.read_text())
    # Image input is bounded at 2400x2400. Reserve 16k tokens per image, plus two text bytes per token
    # (measured 2.6-2.9, the token_upper rule) and the lane's full output cap (thinking included).
    images=0;text_bytes=0
    for message in payload['messages']:
        content=message.get('content') or ''
        if isinstance(content,list):
            images+=sum(x.get('type')=='image_url' for x in content)
            text_bytes+=sum(len(x.get('text','').encode()) for x in content)
        else:text_bytes+=len(content.encode())
        text_bytes+=len(json.dumps(message.get('tool_calls',[])).encode())
    estimate=text_bytes//2+images*16384+4000;tier=price(args.spec,estimate)
    reserve=(estimate*tier['input']+args.spec['output_cap']*tier['output'])/1e6
    # Rounds share one ledger, so a key names its run folder; round-1 keys predate this prefix.
    key=f'{args.root.name}/{args.lane}/{args.paper}/{name or turn}/{attempt}'
    budget(args.budget,key,reserve=reserve)
    request_path.write_bytes(raw)
    headers={'Content-Type':'application/json','Authorization':'Bearer '+os.environ['CONTRACT_MODEL_KEY']}
    started=time.monotonic();content='';reasoning='';calls={};usage={};model=args.spec['model'];finish=None
    wall=args.request_wall_seconds
    def expired(signum,frame):raise TimeoutError(f'Request exceeded the {wall}-second wall limit')
    previous=signal.signal(signal.SIGALRM,expired);signal.setitimer(signal.ITIMER_REAL,wall)
    try:
        request=urllib.request.Request(args.base_url.rstrip('/')+'/chat/completions',data=raw,headers=headers)
        with urllib.request.urlopen(request,timeout=wall-10) as response,prefix.with_suffix('.response.sse').open('wb') as archive:
            for line in response:
                archive.write(line);archive.flush()
                if time.monotonic()-started>wall:raise TimeoutError(f'Request exceeded the {wall}-second wall limit')
                if not line.startswith(b'data:'):continue
                data=line[5:].strip()
                if data==b'[DONE]':break
                event=json.loads(data);model=event.get('model',model)
                if event.get('usage'):usage=event['usage']
                for choice in event.get('choices',[]):
                    delta=choice.get('delta',{});content+=delta.get('content') or '';reasoning+=delta.get('reasoning_content') or ''
                    finish=choice.get('finish_reason') or finish
                    for part in delta.get('tool_calls',[]):
                        i=part['index'];call=calls.setdefault(i,{'id':'','type':'function','function':{'name':'','arguments':''}})
                        if part.get('id'):call['id']=part['id']
                        f=part.get('function',{})
                        if f.get('name'):call['function']['name']+=f['name']
                        call['function']['arguments']+=f.get('arguments') or ''
    except Exception as exc:
        message=exc.read().decode(errors='replace') if isinstance(exc,urllib.error.HTTPError) else str(exc)
        prefix.with_suffix('.error.txt').write_text(f'{type(exc).__name__}: {message}\n');raise
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous)
    message={'role':'assistant','content':content}
    if calls:message['tool_calls']=[calls[i] for i in sorted(calls)]
    result={'model':model,'message':message,'reasoning_content':reasoning,'finish_reason':finish,'usage':usage}
    dump(response_path,result)
    receipt={'request_sha256':hashlib.sha256(raw).hexdigest(),'response_sha256':hashlib.sha256(response_path.read_bytes()).hexdigest(),
             'sse_sha256':hashlib.sha256(prefix.with_suffix('.response.sse').read_bytes()).hexdigest(),
             'usage':usage,'seconds':time.monotonic()-started,'model':model,'estimated_cny':cost(args.spec,usage)}
    dump(prefix.with_suffix('.receipt.json'),receipt)
    budget(args.budget,key,settle=receipt['estimated_cny'])
    return result


def token_upper(messages,output_cap):
    # Two bytes per token stays conservative against the 2.6-2.9 measured on these requests,
    # so the per-paper token cap binds near its stated value.
    size=0;images=0
    for message in messages:
        content=message.get('content') or ''
        if isinstance(content,list):
            images+=sum(p.get('type')=='image_url' for p in content);size+=sum(len(p.get('text','').encode()) for p in content)
        else:size+=len(content.encode())
        size+=len(json.dumps(message.get('tool_calls',[])).encode())
    return 4000+output_cap+images*16384+size//2


def packet(workbench,target):
    inventory=[{k:v for k,v in x.items() if k in ['file','caption','status','sheets','error','parse_error']} for x in workbench.files]
    terms=re.compile(r'clinical|patient|response|prediction|accuracy|specificity|sensitivity|cutoff|threshold|RECIST|FOLFOX|TRG|concord',re.I)
    paragraphs=sorted(workbench.article,key=lambda p:-len(terms.findall(p['text'])))
    selected=[];used=0
    for p in paragraphs:
        if used+len(p['text'])<=20000:selected.append(p);used+=len(p['text'])
    candidates=[]
    for file,sheets in workbench.tables.items():
        for sheet,data in sheets.items():
            rows=data.get('rows',[]);preview=json.dumps(rows[:12],ensure_ascii=False)
            rank=len(terms.findall(sheet+' '+preview))
            candidates.append((rank,file,sheet))
    tables=[];used=0
    for _,file,sheet in sorted(candidates,reverse=True):
        table=workbench.preview(file,sheet,1,8);size=len(json.dumps(table,ensure_ascii=False))
        if used+size<=22000:tables.append(table);used+=size
    return {'task_target':target,'negative_control_instruction':'When no global clinical/toxicity headline exists, return no_headline.',
            'files':inventory,'selected_article_paragraphs':selected,'table_previews':tables,
            'note':'Complete cells/tables/styles are available to generated Python. All previews were selected by fixed word matching, independent of outputs.'}


def feedback(result):
    if not result:return {'matched':False,'errors':['No contract was emitted']}
    compact={k:v for k,v in result.items() if k!='rows'}
    errors=compact.get('errors',[])
    if len(errors)>8:compact['error_count']=len(errors);compact['errors']=errors[:6]+errors[-2:]
    return compact


def execute_text(text,workbench,target):
    try:
        output=parse_reply(text)
        if 'python' in output:
            tool_result=workbench.python(output['python']);contract=tool_result.get('contract')
        else:contract=output.get('contract',output);tool_result={'contract':contract}
        evaluation=workbench.check(contract,target) if contract else {'matched':False,'errors':['Python produced no CONTRACT'],
                                                                   'execution':{k:v for k,v in tool_result.items() if k!='contract'}}
        return tool_result,contract,evaluation
    except Exception as exc:return {'error':f'{type(exc).__name__}: {exc}'},None,{'matched':False,'errors':[f'{type(exc).__name__}: {exc}']}


def step(args):
    step_started=time.monotonic()
    config=json.loads((HERE/'experiment_v2.json').read_text());external=config.get('external',{})
    # The development cohort and the external scale-up cohort are frozen separately; a paper key belongs to one of them.
    target={**config['targets'],**external.get('targets',{})}.get(args.paper)
    if args.paper not in config['eligible']+config['negative_controls']+external.get('eligible',[])+external.get('negative_controls',[]):
        raise ValueError('Paper is outside the frozen cohorts')
    # The frozen lane spec is the only source of model, provider request fields, output cap and price.
    spec=args.spec=config['model_sets'][args.model_set][args.lane];args.request_wall_seconds=config['request_wall_seconds'][args.model_set]
    args.max_model_calls=args.max_model_calls or config['max_model_calls_per_paper'];args.max_tool_calls=args.max_tool_calls or config['max_tool_calls_per_paper']
    folder=args.root/args.lane/args.paper;folder.mkdir(parents=True,exist_ok=True)

    def reader(png):
        # Same model and settings as the agent, but a fresh conversation that never sees the task or its target.
        payload={'model':spec['model'],'messages':[{'role':'system','content':(HERE/'reader_prompt.txt').read_text()},
                 {'role':'user','content':[{'type':'text','text':'Transcribe this source image as JSON.'},
                                           {'type':'image_url','image_url':{'url':'data:image/png;base64,'+base64.b64encode(png).decode()}}]}],
                 'stream':True,'stream_options':{'include_usage':True},'temperature':0,**spec['request']}
        # No JSON mode here: with an image attached it let seed-2.0-pro emit whitespace up to the output cap.
        name='read_'+hashlib.sha256(json.dumps(payload,ensure_ascii=False).encode()).hexdigest()[:16]
        result=request(payload,args,folder/'reader',0,name)
        state['tokens']+=result['usage'].get('total_tokens',0);state['reader_calls']=state.get('reader_calls',0)+1
        return parse_reply(result['message']['content'])

    workbench=Workbench(args.sources/args.paper,folder/'scratch',args.paper,reader)
    state_path=folder/'state.json'
    if state_path.exists():state=json.loads(state_path.read_text())
    else:
        state={'messages':[{'role':'system','content':(HERE/'agent_prompt.txt').read_text()},
                            {'role':'user','content':json.dumps(packet(workbench,target),ensure_ascii=False)}],
               'turn':0,'tool_count':0,'tokens':0,'checkpoints':{},'last_contract':None,'last_evaluation':None,'done':False}
    if state['done']:print(json.dumps({'paper':args.paper,'lane':args.lane,'done':True,'checkpoints':state['checkpoints']}));return
    if state['tokens']+token_upper(state['messages'],spec['output_cap'])>config['max_total_tokens_per_paper']:
        state['done']=True;state['stop_reason']='conservative_token_limit'
        for stage in ['single_pass','one_feedback','tool_loop']:
            state['checkpoints'].setdefault(stage,{'contract':state['last_contract'],'evaluation':state['last_evaluation'],'calls':state['turn'],'tokens':state['tokens']})
        dump(state_path,state);print(json.dumps({'paper':args.paper,'lane':args.lane,'done':True,'reason':state['stop_reason']}));return
    turn=state['turn'];payload={'model':spec['model'],'messages':state['messages'],'stream':True,'stream_options':{'include_usage':True},
                              'temperature':0,**spec['request']}
    if turn<2:payload['response_format']={'type':'json_object'}
    else:payload['tools']=TOOLS;payload['tool_choice']='auto';payload['parallel_tool_calls']=True
    response=request(payload,args,folder,turn);state['messages'].append(response['message'])
    state['tokens']+=response['usage'].get('total_tokens',response['usage'].get('prompt_tokens',0)+response['usage'].get('completion_tokens',0))
    actions=[];images=[]
    if turn<2 or not response['message'].get('tool_calls'):
        output,contract,evaluation=execute_text(response['message']['content'],workbench,target)
        dump(folder/f'call{turn:02d}.execution.json',output)
        actions.append({'name':'initial_code' if turn<2 else 'final_text','output':output})
        if contract:state['last_contract']=contract
        state['last_evaluation']=evaluation
        state['messages'].append({'role':'user','content':'Execution feedback: '+json.dumps(feedback(evaluation),ensure_ascii=False)+
                                  ('\nReturn one complete corrected Python program or contract.' if turn==0 else '\nUse the browsing, vision and Python tools to resolve source/column errors. Finish with a complete contract.')} )
    else:
        for call in response['message']['tool_calls']:
            name=call['function']['name']
            try:
                if time.monotonic()-step_started>config['step_wall_seconds'][args.model_set]:
                    raise RuntimeError('This step has reached its wall-time budget; continue the tool call next turn')
                if state['tool_count']>=args.max_tool_calls:
                    raise RuntimeError('The fixed tool-call budget is exhausted')
                state['tool_count']+=1
                arguments=json.loads(call['function']['arguments']);output,image=workbench.call(name,arguments)
                if output.get('contract'):
                    state['last_contract']=output['contract'];state['last_evaluation']=workbench.check(output['contract'],target)
                    output['execution_feedback']=feedback(state['last_evaluation'])
                if image:images.append(image)
            except Exception as exc:arguments=call['function'].get('arguments');output={'error':workbench.redact(f'{type(exc).__name__}: {exc}')};image=None
            actions.append({'name':name,'arguments':arguments,'output':output})
            # The verdict leads and the echoed contract stays in the action log, so truncation never hides feedback.
            shown={'execution_feedback':output['execution_feedback'],**{k:v for k,v in output.items() if k not in ['contract','execution_feedback']}} if 'execution_feedback' in output else output
            rendered=json.dumps(shown,ensure_ascii=False)
            if len(rendered)>32000:rendered=rendered[:32000]+'\n[Tool preview truncated at 32000 characters; request a narrower range.]'
            state['messages'].append({'role':'tool','tool_call_id':call['id'],'content':rendered})
        if images:
            state['messages'].append({'role':'user','content':[{'type':'text','text':'Images returned by your view_source and read_grid calls, in call order; read_grid images mark every sample point. Values you use as evidence must come from read_figure or read_grid.'}]+
                                     [{'type':'image_url','image_url':{'url':'data:image/png;base64,'+base64.b64encode(image).decode()}} for image in images]})
    dump(folder/f'call{turn:02d}.tools.json',actions)
    if turn==0:state['checkpoints']['single_pass']={'contract':state['last_contract'],'evaluation':state['last_evaluation'],'calls':1,'tokens':state['tokens']}
    if turn==1:state['checkpoints']['one_feedback']={'contract':state['last_contract'],'evaluation':state['last_evaluation'],'calls':2,'tokens':state['tokens']}
    state['turn']+=1
    passed=state['last_evaluation'] and (state['last_evaluation'].get('matched') or state['last_evaluation'].get('correct_refusal'))
    if passed or state['turn']>=args.max_model_calls or state['tool_count']>=args.max_tool_calls or state['tokens']>=config['max_total_tokens_per_paper']:
        state['done']=True
        state['stop_reason']='verified' if passed else 'budget_exhausted'
        for stage in ['one_feedback','tool_loop']:
            state['checkpoints'].setdefault(stage,{'contract':state['last_contract'],'evaluation':state['last_evaluation'],'calls':state['turn'],'tokens':state['tokens']})
    dump(state_path,state)
    print(json.dumps({'paper':args.paper,'lane':args.lane,'turn':state['turn'],'done':state['done'],'tokens':state['tokens'],
                      'tools':[a['name'] for a in actions],'evaluation':feedback(state['last_evaluation'])},ensure_ascii=False),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True);p.add_argument('--sources',type=Path,required=True)
    p.add_argument('--paper',required=True);p.add_argument('--lane',choices=['strong','weak'],required=True)
    p.add_argument('--base-url',required=True)
    p.add_argument('--model-set',default='qwen',help='Key of experiment_v2.json model_sets; it fixes model, request fields, output cap and price per lane')
    p.add_argument('--budget',type=Path,help='Shared CNY ledger; defaults to ROOT/budget.json')
    p.add_argument('--max-model-calls',type=int,help='Override of the frozen per-paper model-call cap for a declared round');p.add_argument('--max-tool-calls',type=int)
    args=p.parse_args();args.budget=args.budget or args.root/'budget.json'
    try:step(args)
    except urllib.error.HTTPError as exc:
        if exc.code==429 or exc.code>=500:raise SystemExit(75) from exc
        raise
    except (urllib.error.URLError,TimeoutError) as exc:raise SystemExit(75) from exc


if __name__=='__main__':main()

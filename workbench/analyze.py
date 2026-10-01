#!/usr/bin/env python3
"""Analyse anonymous six-task exports, keeping self-tests separate from researchers."""
import argparse
import json
import statistics
from pathlib import Path

ROOT=Path(__file__).resolve().parent
KEY=json.loads((ROOT/'study/answer_key.json').read_text())
TASKS={t['id']:t for t in KEY['tasks']}

def score(task, reference):
    actions=task['actions'];rows=reference['rows'];truth={r['patient']:r['response'] for r in reference['outcomes']}
    expected=[str(a['prediction']) if a['released'] else 'retest' for a in reference['reference']['actions']]
    if len(actions)!=len(rows) or any(a not in ('0','1','retest') for a in actions):
        raise ValueError('Action count or values differ from the task definition')
    n=len(rows);released=sum(a!='retest' for a in actions)
    wrong=sum(a!='retest' and int(a)!=truth[r['patient']] for a,r in zip(actions,rows))
    actual={'overall_percent':100*wrong/n,'conditional_percent':100*wrong/released if released else None,
            'loss':(wrong+task['cost']*(n-released))/n}
    calls=[a['calls'] for a in reference['reference']['actions']]
    baselines={'readout1':[a[0] for a in calls],'readout2':[a[1] for a in calls],
               'both_sensitive':[min(a) for a in calls],'either_sensitive':[max(a) for a in calls]}
    costs={k:sum(a!=truth[r['patient']] for a,r in zip(v,rows))/n for k,v in baselines.items()}
    costs['all_retest']=task['cost'];best=min(costs.values())
    checks={}
    for k,v in actual.items():
        a=task['answers'].get(k)
        checks[k]=(a is None if v is None else isinstance(a,(int,float)) and abs(a-v)<= (.015 if k.endswith('percent') else .00015))
    checks['best_baseline']=costs.get(task['answers'].get('best_baseline'),float('inf'))<=best+1e-12
    correct=sum(a==b for a,b in zip(actions,expected))
    return {'action_matches':correct,'patient_actions':n,'action_accuracy':correct/n,
            'summary_checks':checks,'task_correct':correct==n and all(checks.values()),
            'observed_wrong_releases':wrong,'normalized_cost':actual['loss']}

def analyse_record(record):
    if record.get('schema')!='workbench.record.v1':raise ValueError('Unsupported record schema')
    if record.get('model_sha256')!=KEY['model_sha256']:raise ValueError('Record uses a different frozen model')
    if record.get('app_version')!=KEY['version']:raise ValueError('Record uses a different task-pack version')
    if record.get('record_type') not in ('researcher','agent_self_test','facilitator_pilot','exploration'):raise ValueError('Unknown record type')
    events=record.get('events',[])
    if [e.get('seq') for e in events]!=list(range(1,len(events)+1)):raise ValueError('Event sequence is incomplete')
    if any(events[i]['elapsed_ms']>events[i+1]['elapsed_ms'] for i in range(len(events)-1)):raise ValueError('Event times go backwards')
    tasks=record.get('tasks',[]);ids=[t['task'] for t in tasks]
    if len(set(ids))!=len(ids):raise ValueError('Duplicate completed task')
    result={'participant':record.get('participant'),'session_id':record['session_id'],
            'record_type':record['record_type'],'complete':len(tasks)==6,'tasks':[],'pairs':[]}
    for t in tasks:
        if t['task'] not in TASKS:raise ValueError('Unknown task')
        if t['cost']!=.25:raise ValueError('Timed-study retest cost differs from the frozen protocol')
        if t['mode'] not in ('manual','tool') or t['active_ms']<0 or t['wall_ms']<t['active_ms']:raise ValueError('Invalid mode or timing')
        expected_step=record['schedule'][t['position']-1]
        if any(t[k]!=expected_step[k] for k in ('task','mode','pair')):raise ValueError('Task differs from assigned schedule')
        ev=events[t['start_event']-1:t['end_event']]
        if not ev or ev[0]['type']!='task_start' or ev[-1]['type']!='task_end':raise ValueError('Task lacks start/end events')
        if abs(ev[-1]['elapsed_ms']-ev[0]['elapsed_ms']-t['wall_ms'])>50:raise ValueError('Task wall time differs from its event log')
        locks=[e for e in ev if e['type']=='actions_locked'];reveals=[e for e in ev if e['type']=='outcomes_revealed']
        if len(locks)!=1 or len(reveals)!=1 or locks[0]['seq']>=reveals[0]['seq'] or locks[0]['actions']!=t['actions']:
            raise ValueError('Action lock and reveal sequence differs from the final task')
        if t['mode']=='manual' and any(e['type']=='prediction_run' for e in ev):raise ValueError('Manual task used automated recommendations')
        result['tasks'].append({**{k:t[k] for k in ('task','pair','mode','position','active_ms','wall_ms','paused_ms')},
                                **score(t,TASKS[t['task']]),'visibility_changes':sum(e['type']=='visibility_change' for e in ev)})
    for pair in (1,2,3):
        pairtasks=[t for t in result['tasks'] if t['pair']==pair]
        if len(pairtasks)!=2:continue
        modes={t['mode']:t for t in pairtasks}
        if set(modes)!={'manual','tool'}:raise ValueError('Matched pair requires one manual and one tool task')
        a,b=modes['manual'],modes['tool']
        result['pairs'].append({'pair':pair,'manual_task':a['task'],'tool_task':b['task'],
            'manual_active_s':a['active_ms']/1000,'tool_active_s':b['active_ms']/1000,
            'manual_minus_tool_s':(a['active_ms']-b['active_ms'])/1000,
            'manual_minus_tool_wall_s':(a['wall_ms']-b['wall_ms'])/1000,
            'both_correct':a['task_correct'] and b['task_correct'],
            'manual_action_accuracy':a['action_accuracy'],'tool_action_accuracy':b['action_accuracy']})
    diffs=[p['manual_minus_tool_s'] for p in result['pairs']]
    quality=[p['manual_minus_tool_s'] for p in result['pairs'] if p['both_correct']]
    result.update(mean_paired_difference_s=statistics.mean(diffs) if diffs else None,
                  median_paired_difference_s=statistics.median(diffs) if diffs else None,
                  correct_pair_count=len(quality),mean_correct_pair_difference_s=statistics.mean(quality) if quality else None,
                  active_total_s=sum(t['active_ms'] for t in tasks)/1000,
                  wall_total_s=sum(t['wall_ms'] for t in tasks)/1000)
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('records',nargs='+',type=Path);p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    sessions={};invalid=[]
    for path in args.records:
        try:
            record=json.loads(path.read_text());id=record['session_id']
            if id not in sessions or record.get('exported_at','')>sessions[id].get('exported_at',''):sessions[id]=record
        except (ValueError,KeyError) as e:invalid.append({'file':path.name,'error':str(e)})
    analysed=[]
    for record in sessions.values():
        try:analysed.append(analyse_record(record))
        except (ValueError,KeyError,TypeError) as e:invalid.append({'session_id':record.get('session_id'),'error':str(e)})
    human=[r for r in analysed if r['record_type']=='researcher' and r['complete']]
    codes=[r['participant'] for r in human]
    if len(codes)!=len(set(codes)):raise ValueError('Multiple complete researcher sessions share a participant code; select one export per participant')
    means=[r['mean_paired_difference_s'] for r in human]
    result={'schema':'workbench.paired-analysis.v1','effect_direction':'positive manual-minus-tool means faster with tool',
            'researcher_complete_n':len(human),'researcher_mean_of_person_means_s':statistics.mean(means) if means else None,
            'records':analysed,'invalid_records':invalid,
            'interpretation':'Descriptive matched-task workflow differences. Agent self-tests and facilitator pilots are kept outside researcher aggregates. Normalized decision costs are not monetary savings.'}
    args.out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'records':len(analysed),'researchers':len(human),'invalid':invalid,'out':args.out.name}))
    if invalid:raise SystemExit(1)
if __name__=='__main__':main()

#!/usr/bin/env python3
"""Turn the frozen 43-patient comparison into an inspectable batch action file.

Readout measurements and outcomes are published research data. Cost parameters
are user assumptions in units of one wrong call, not observed money or hours.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent

def build(packet, retest_cost, added_assay_cost):
    if retest_cost<0 or added_assay_cost<0:
        raise ValueError('Costs must be nonnegative')
    rows={r['patient']:r for r in packet['rows']}
    output=[]
    for c in packet['cases']:
        y=rows[c['patient']]['response']
        if y not in (0,1):
            raise ValueError('This retrospective action comparison requires all outcome values')
        main,old=c['action'],c['baseline_action']
        wrong=main!='retest' and int(main)!=y
        old_wrong=old!='retest' and int(old)!=y
        if old=='retest' and main!='retest':
            change='previous_retest_now_report'
        elif old_wrong and not wrong:
            change='previous_error_corrected'
        elif wrong and not old_wrong:
            change='new_error'
        else:
            change='unchanged'
        output.append(dict(patient=c['patient'],old_action=old,new_action=main,outcome=y,
                           change=change,wrong=wrong,old_wrong=old_wrong,
                           next_action='Review the discordant assay and endpoint before the next validation batch' if wrong else 'Retain the coded research report with its frozen rule and source'))
    n=len(output)
    categories={k:sum(c['change']==k for c in output) for k in sorted({c['change'] for c in output})}
    old_retest=sum(c['old_action']=='retest' for c in output)
    new_retest=sum(c['new_action']=='retest' for c in output)
    old_wrong=sum(c['old_wrong'] for c in output)
    new_wrong=sum(c['wrong'] for c in output)
    gross=old_wrong-new_wrong+retest_cost*(old_retest-new_retest)
    return dict(schema='patient.action.delta.v1',patients=n,categories=categories,
                old=dict(retests=old_retest,wrong=old_wrong),new=dict(retests=new_retest,wrong=new_wrong),
                costs=dict(unit='One wrong research call',retest_cost=retest_cost,
                           added_combined_assay_cost_per_patient=added_assay_cost,
                           gross_loss_reduction=gross,net_loss_reduction=gross-n*added_assay_cost,
                           added_assay_break_even_per_patient=gross/n,
                           formula='(old_wrong-new_wrong) + retest_cost*(old_retests-new_retests) - patients*added_assay_cost',
                           scope='Retrospective decision accounting; measurement, staff-time and treatment effects are unobserved'),
                actions=output)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--packet',type=Path,default=ROOT/'patient_workbench_result.json')
    p.add_argument('--retest-cost',type=float,default=.25)
    p.add_argument('--added-assay-cost',type=float,default=0)
    p.add_argument('--out',type=Path,default=ROOT/'patient_action_delta.json')
    a=p.parse_args();data=a.packet.read_bytes();result=build(json.loads(data),a.retest_cost,a.added_assay_cost)
    result['source_packet_sha256']=hashlib.sha256(data).hexdigest()
    a.out.write_text(json.dumps(result,indent=2)+'\n')
    with a.out.with_suffix('.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(result['actions'][0]));w.writeheader();w.writerows(result['actions'])
    print(json.dumps({k:result[k] for k in ['patients','categories','old','new','costs']},indent=2))

if __name__=='__main__':main()

#!/usr/bin/env python3
"""Build the static result packet by calling the repository's frozen core.

Run from the repository: python workbench/build_result.py
Only workbench files are written. No network or training is performed.
"""
import ast
import csv
import hashlib
import json
import sys
from pathlib import Path
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
CORE = HERE.parent
sys.path.insert(0, str(CORE))
from release_calibration import apply, measure
from matched_regimen import predict as matched_predict
from conditional_calibration import upper_bound

def literal(path, name):
    tree = ast.parse(path.read_text())
    return next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == name for t in n.targets))

def plan(n, e, alpha):
    total = max(n, 1)
    while upper_bound(e, total, .05) > alpha:
        total += 1
    return dict(n=n, e=e, alpha=alpha, upper=upper_bound(e,n,.05), total=total, additional=total-n)

def main():
    cert = json.loads((HERE/'study/certificate.json').read_text())
    frozen = json.loads((CORE/'matched_regimen_frozen.json').read_text())
    raw = literal(CORE/'blind2_predict.py', 'RECTAL')
    clinical = literal(CORE/'blind2_score.py', 'RECTAL_CLINICAL')
    # Exact test membership from the frozen matched-regimen replay.
    ids = [c['patient'] for c in frozen['test_predictions']]
    rows = []
    for ident in ids:
        i = int(ident.removeprefix('Patient'))
        rows.append(dict(patient=ident, readout1=raw[i][0], readout2=raw[i][1],
                         baseline_readout=raw[i][3], response=int(clinical[i][1].lower() in ('0','1','ccr','pcr'))))
    labelled = [dict(patient=r['patient'], x=[r['readout1'],r['readout2']],y=r['response']) for r in rows]
    predictions = apply(cert, labelled)
    cal = [dict(patient=p, x=[raw[int(p.removeprefix('Patient'))][0],raw[int(p.removeprefix('Patient'))][1]],
                y=int(clinical[int(p.removeprefix('Patient'))][1].lower() in ('0','1','ccr','pcr'))) for p in cert['calibration_ids']]
    cal_calls = apply(cert,cal)
    single_errors = [sum(c['calls'][j]!=r['y'] for c,r in zip(cal_calls,cal)) for j in (0,1)]
    best_single = min((0,1),key=lambda j:(single_errors[j],j))
    base = matched_predict(frozen['model'], [dict(patient=r['patient'],x=r['baseline_readout']) for r in rows])
    truth = {r['patient']:r['response'] for r in rows}
    ours = {k:v for k,v in measure(cert,labelled).items() if k!='rows'}
    errors = sum(c['prediction']!=truth[c['patient']] for c in base)
    baseline = dict(patients=len(rows), released=len(rows), retests=0, wrong_released=errors,
                    overall_wrong_release=errors/len(rows),released_error_rate=errors/len(rows),loss=errors/len(rows))
    cases = [dict(patient=a['patient'],calls=a['calls'],margin=a['margin'],action=str(a['prediction']) if a['released'] else 'retest',
                  baseline_action=str(b['prediction'])) for a,b in zip(predictions,base)]
    packet = dict(schema='workbench.result.v1', version='rectal-frozen-2026-10-02',
        study=dict(title='Rectal organoids · 2025',url='https://doi.org/10.1016/j.xcrm.2025.102397',
                   status='Retrospective replay of previously analysed public outcomes.',
                   input_note='Patient-derived rectal organoids; day-24/day-0 size ratios. Readout 1: irradiation; readout 2: 5-FU; baseline_readout: measured combined regimen. Clinical response: TRG 0/1 or cCR. Treatment mapping may include an additional partner drug.',
                   split=dict(training=len(cert['model']['training_ids']),calibration=len(cert['calibration_ids']),test=len(rows))),
        rule=dict(kind='two_readout_v2',name='Two-readout release rule',certificate=cert),
        baseline=dict(kind='fixed_single',name='Fixed threshold · combined regimen',field='baseline_readout',
                      cutoff=frozen['model']['cutoff'],model=frozen['model'],
                      selection='Strongest observed fixed single-readout comparator among these available study signals; identified in a previously analysed cohort. The threshold uses training patients only.',
                      fallback_field=f'readout{best_single+1}',fallback_cutoff=cert['model']['cutoffs'][best_single],
                      fallback_name=f'Fixed threshold · readout {best_single+1}',fallback_selection=f'Readout {best_single+1} selected on the original calibration sample: readout 1 has {single_errors[0]}/{len(cal)} errors; readout 2 has {single_errors[1]}/{len(cal)}. Test outcomes stay separate.'),
        cost=dict(retest=.25,wrong_release=1,unit='relative loss units'),
        rows=rows,cases=cases,expected=dict(ours=ours,baseline=baseline,
            plans=[plan(ours['released'],ours['wrong_released'],a) for a in (.1,.2)]),
        provenance={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in
                    [CORE/'release_calibration.py',CORE/'matched_regimen.py',CORE/'matched_regimen_frozen.json',CORE/'chip_release.py',CORE/'conditional_calibration.py']})
    (HERE/'result.json').write_text(json.dumps(packet,indent=2,allow_nan=False)+'\n')
    (HERE/'result.js').write_text('window.WORKBENCH_RESULT = '+json.dumps(packet,allow_nan=False)+';\n')
    with (HERE/'examples/published_batch.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    print(json.dumps({'patients':len(rows),'ours':ours,'baseline':baseline,'plans':packet['expected']['plans']}))

if __name__=='__main__':main()

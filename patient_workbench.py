#!/usr/bin/env python3
"""Export the measured combined-regimen signal as the primary workbench result.

The earlier paired-readout rule supplies the comparator. This adapter reuses
frozen models and predictions; it performs no training or threshold selection.
Run: python patient_workbench.py [--csv compatible_patient_table.csv]
Open patient_workbench_result.json with the workbench's updated-packet control.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

from matched_regimen import predict
from release_calibration import apply

ROOT = Path(__file__).resolve().parent


def metrics(rows, actions, cost):
    known = [(r, a) for r, a in zip(rows, actions) if r['response'] is not None]
    released = sum(a != 'retest' for a in actions)
    n = len(known)
    accepted = sum(a != 'retest' for _, a in known)
    wrong = sum(a != 'retest' and int(a) != r['response'] for r, a in known)
    return dict(patients=len(rows), released=released, retests=len(rows)-released,
                scored=n, scored_released=accepted, wrong_released=wrong if n else None,
                overall_wrong_release=wrong/n if n else None,
                released_error_rate=wrong/accepted if accepted else None,
                loss=(wrong+cost*(n-accepted))/n if n else None)


def build(rows, template, frozen):
    model = frozen['model']
    cert = template['rule']['certificate']
    cases = []
    for r in rows:
        measured = r['baseline_readout']
        main = predict(model, [dict(patient=r['patient'], x=measured)])[0] if measured is not None else None
        paired = apply(cert, [dict(patient=r['patient'], x=[r['readout1'], r['readout2']])])[0] if r['readout1'] is not None and r['readout2'] is not None else None
        action = str(main['prediction']) if main else 'retest'
        baseline = str(paired['prediction']) if paired and paired['released'] else 'retest'
        cases.append(dict(patient=r['patient'], calls=paired['calls'] if paired else [None, None],
                          margin=main['margin'] if main else None, action=action, baseline_action=baseline,
                          reason='Measured combined-regimen assay at its frozen training cutoff' if main else 'Combined-regimen measurement required'))
    packet = dict(schema='workbench.result.v1', version='combined-regimen-primary-v1',
                  study=template['study'], rows=rows, cases=cases,
                  rule=dict(kind='precomputed', name='Combined-regimen signal', model_sha256=model['model_sha256'],
                            description='One measured combined-regimen assay; sensitive at or below 0.31875. Frozen training cutoff. Improvement belongs to the signal; the fixed-threshold rule gives the same 43 releases and one error. The strongest-component equal-risk primary comparison failed.'),
                  baseline=dict(kind='precomputed', name='Earlier two-readout agreement',
                                field='readout1', cutoff=cert['model']['cutoffs'][0],
                                fallback_field='readout2', fallback_cutoff=cert['model']['cutoffs'][1],
                                fallback_name='Earlier two-readout agreement', fallback_selection='Saved paired-readout actions',
                                selection=f"Paired irradiation/5-FU calls at {cert['model']['cutoffs'][0]} / {cert['model']['cutoffs'][1]}, with frozen margin {cert['margin']}; disagreement goes to retest. Comparator actions are saved for every patient."),
                  cost=template['cost'])
    packet['expected'] = dict(ours=metrics(rows,[c['action'] for c in cases],packet['cost']['retest']),
                              baseline=metrics(rows,[c['baseline_action'] for c in cases],packet['cost']['retest']))
    packet['provenance'] = {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in
                            ['patient_workbench.py','matched_regimen.py','matched_regimen_frozen.json','release_calibration.py','workbench/result.json']}
    return packet


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--csv',type=Path)
    p.add_argument('--out',type=Path,default=ROOT/'patient_workbench_result.json')
    a=p.parse_args()
    template=json.loads((ROOT/'workbench/result.json').read_text())
    frozen=json.loads((ROOT/'matched_regimen_frozen.json').read_text())
    rows=template['rows']
    if a.csv:
        with a.csv.open(newline='') as f: raw=list(csv.DictReader(f))
        rows=[]; seen=set()
        for r in raw:
            ident=r.get('patient','')
            if not ident or ident in seen: raise ValueError('Each row needs a unique coded patient ID')
            seen.add(ident); row={'patient':ident}
            for key in ('readout1','readout2','baseline_readout','response'):
                v=r.get(key,''); value=float(v) if v is not None and v.strip() else None
                if value is not None and not math.isfinite(value): raise ValueError(f'{ident}: {key} must be finite')
                row[key]=value
            if row['response'] not in (None,0,1): raise ValueError(f'{ident}: response must be 0, 1 or empty')
            if row['readout1'] is None and row['readout2'] is None: raise ValueError(f'{ident}: provide a component readout for the workbench table')
            rows.append(row)
    packet=build(rows,template,frozen)
    if a.csv:packet['study']=dict(template['study'], title='Your compatible patient table',status='Frozen-rule predictions; outcomes supplied by the reader.',split=dict(template['study']['split'],test=len(rows)))
    a.out.write_text(json.dumps(packet,indent=2,allow_nan=False)+'\n')
    print(json.dumps(packet['expected'],indent=2))


if __name__=='__main__': main()

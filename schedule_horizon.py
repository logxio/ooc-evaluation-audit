#!/usr/bin/env python3
"""Reproduce schedule decision horizons from the paper's Figure 5a-b source XLSX."""
import argparse
import csv
import hashlib
import json
import math
import resource
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import openpyxl

SOURCE_SHA256 = '0717526b2857cd746f6a809d8becaafb648572696731ea2740a4e883391e5bea'
FAMILIES = ('FOLFIRINOX', 'FOLFIRI', 'FOLFOX', 'Gemcitabine + 5FU')
ARMS = ('4 hour', '72 hour', 'Temporal')
MARKERS = ('apoptosis', 'death')
MARKER_COLS = {'apoptosis': 3, 'death': 22}  # zero-indexed D:V and W:AO
TIMES = list(range(0, 73, 4))


def parse(source):
    ws = openpyxl.load_workbook(source, read_only=True, data_only=True)['Figure 5a-b']
    records = defaultdict(list)
    patient = None
    arm = None
    for line, row in enumerate(ws.values, 1):
        label = row[2] if len(row) > 2 else None
        if isinstance(label, str) and label.startswith('Patient '):
            patient = label.strip()
            arm = None
            continue
        if label == 'hours':
            for marker, start in MARKER_COLS.items():
                actual = [row[start+i] for i in range(19)]
                assert actual == TIMES, (marker, actual)
            continue
        if isinstance(label, str) and label.strip():
            arm = label.strip()
        if patient is None or arm is None:
            continue
        if not any(arm == f'{family} {schedule}' for family in FAMILIES for schedule in ARMS):
            continue
        for marker, start in MARKER_COLS.items():
            values = row[start:start+19]
            if len(values) != 19 or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in values):
                continue
            if values[0] <= 0:
                continue
            curve = np.asarray(values, dtype=float)/float(values[0])-1
            records[(patient, arm, marker)].append((line, curve))
    patients = sorted({key[0] for key in records})
    eligibility = {}
    mean_curves = {}
    for patient in patients:
        for family in FAMILIES:
            for schedule in ARMS:
                arm = f'{family} {schedule}'
                for marker in MARKERS:
                    rows = records.get((patient, arm, marker), [])
                    eligibility[f'{patient}|{arm}|{marker}'] = {'replicates': len(rows), 'source_rows': [r for r,_ in rows]}
                    if len(rows) >= 2:
                        mean_curves[(patient, arm, marker)] = np.mean([v for _,v in rows], axis=0)
    return patients, eligibility, mean_curves


def template_predict(held_patient, arm, marker, patients, curves):
    train = [curves[(p, arm, marker)] for p in patients if p != held_patient]
    assert len(train) == 2
    template = np.mean(train, axis=0)
    observed = curves[(held_patient, arm, marker)]
    denominator = float(np.dot(template[:7],template[:7]))
    scale = max(0., float(np.dot(template[:7], observed[:7])) / denominator) if denominator > 1e-8 else 0.
    return scale*float(template[-1])


def sign(x):
    return int(x > 0)-int(x < 0)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source', type=Path, required=True, help='Original article Source Data XLSX')
    ap.add_argument('--out', type=Path, default=Path('schedule_horizon.json'))
    args = ap.parse_args()
    source_hash = hashlib.sha256(args.source.read_bytes()).hexdigest()
    if source_hash != SOURCE_SHA256:
        raise ValueError(f'Unexpected source SHA256: {source_hash}')
    started = time.monotonic()
    patients, eligibility, curves = parse(args.source)
    cases = []
    for patient in patients:
        for family in FAMILIES:
            temporal = f'{family} Temporal'
            for schedule in ARMS[:2]:
                static = f'{family} {schedule}'
                for marker in MARKERS:
                    if not all((patient, arm, marker) in curves for arm in (temporal, static)):
                        continue
                    a, b = curves[(patient,temporal,marker)], curves[(patient,static,marker)]
                    truth = float(a[-1]-b[-1])
                    early = float(a[6]-b[6])
                    line = float(early + 6*((a[6]-a[4])-(b[6]-b[4])))
                    forecast = template_predict(patient,temporal,marker,patients,curves)-template_predict(patient,static,marker,patients,curves)
                    differences = [float(x-y) for x,y in zip(a,b)]
                    final_sign = sign(differences[-1])
                    stable_from = next(hour for i,hour in enumerate(TIMES[1:],1)
                                       if all(sign(x)==final_sign for x in differences[i:]))
                    cases.append({'patient':patient,'family':family,'static':schedule,'marker':marker,
                                  'truth_72h':truth,'early_24h':early,'baseline_persistence':early,
                                  'baseline_linear':line,'template':forecast,
                                  'reversal':sign(early)!=sign(truth),
                                  'stable_from_hour':stable_from,
                                  'hourly_effects_4h':differences,
                                  'template_direction_correct':sign(forecast)==sign(truth),
                                  'abs_errors':{k:abs(v-truth) for k,v in [('persistence',early),('linear',line),('template',forecast)]}})
    methods = ('persistence','linear','template')
    maes = {m:float(np.mean([c['abs_errors'][m] for c in cases])) for m in methods}
    stronger = min(('persistence','linear'),key=lambda m:maes[m])
    by_patient = {p:{m:float(np.mean([c['abs_errors'][m] for c in cases if c['patient']==p])) for m in methods} for p in patients}
    by_marker = {marker:{m:float(np.mean([c['abs_errors'][m] for c in cases if c['marker']==marker])) for m in methods} for marker in MARKERS}
    reversal = sum(c['reversal'] for c in cases)
    direction = sum(c['template_direction_correct'] for c in cases)
    gates = {'complete_pairs_ge_48':len(cases)>=48,
             'early_late_sign_reversals_ge_10':reversal>=10,
             'template_mae_improvement_ge_20pct':maes['template']<=0.8*maes[stronger],
             'improves_each_heldout_patient':all(by_patient[p]['template']<by_patient[p][stronger] for p in patients),
             'direction_accuracy_ge_75pct':direction/len(cases)>=.75 if cases else False}
    marker_counts = {m:{'pairs':sum(c['marker']==m for c in cases),
                        'reversals_24h_72h':sum(c['marker']==m and c['reversal'] for c in cases),
                        'stable_after_24h':sum(c['marker']==m and c['stable_from_hour']>24 for c in cases)} for m in MARKERS}
    pair_map = defaultdict(dict)
    for case in cases:
        pair_map[(case['patient'],case['family'],case['static'])][case['marker']] = case
    discordant_24h = sum(sign(v['apoptosis']['early_24h'])!=sign(v['death']['early_24h']) for v in pair_map.values())
    reversed_pair_count = sum(any(x['reversal'] for x in v.values()) for v in pair_map.values())
    discordant_and_reversed = sum(sign(v['apoptosis']['early_24h'])!=sign(v['death']['early_24h'])
                                  and any(x['reversal'] for x in v.values()) for v in pair_map.values())
    result = {'schema':'schedule.decision_horizon.v1',
              'source_url':'https://www.nature.com/articles/s41467-020-19058-4',
              'source_sha256':source_hash,
              'source_sheet':'Figure 5a-b','patients':patients,'families':FAMILIES,'markers':MARKERS,
              'normalization':'each replicate signal(t)/signal(0)-1, then average by patient/arm/marker',
              'unit':'patient x family x static comparator x marker; fluorescence replicates are not independent patients',
              'data_eligibility':eligibility,'cases':cases,
              'complete_pairs':len(cases),'reversal_count':reversal,
              'marker_counts':marker_counts,
              'two_marker_pairs':len(pair_map),
              'early_marker_discordant_pairs':discordant_24h,
              'pairs_with_either_marker_reversed':reversed_pair_count,
              'discordant_early_pairs_with_reversal':discordant_and_reversed,
              'template_direction_correct':direction,'direction_accuracy':direction/len(cases) if cases else None,
              'mae':maes,'stronger_baseline':stronger,'mae_by_patient':by_patient,'mae_by_marker':by_marker,
              'relative_mae_gain_vs_stronger':1-maes['template']/maes[stronger] if cases else None,
              'gates':gates,'passes_all':all(gates.values()),
              'elapsed_seconds':time.monotonic()-started,
              'maxrss_bytes_approx':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
              'limit':'Only three patients from one study; same original paper reported schedule endpoint effects; not independent laboratory or clinical outcome.'}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    with args.out.with_suffix('.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=('patient','family','static','marker','early_24h','truth_72h','reversal','stable_from_hour','template','baseline_persistence','baseline_linear'),lineterminator='\n')
        writer.writeheader()
        writer.writerows({k:c[k] for k in writer.fieldnames} for c in cases)
    print(json.dumps({k:result[k] for k in ('complete_pairs','reversal_count','direction_accuracy','mae','stronger_baseline','relative_mae_gain_vs_stronger','mae_by_patient','gates','passes_all','elapsed_seconds')},indent=2))

if __name__=='__main__':
    main()

#!/usr/bin/env python3
"""Audit a two-channel release-or-abstain rule on published chip responses."""

import argparse
import json
from pathlib import Path

from chip_clinic import (FIGURE_SHA256, FIGURE_URL, PATIENTS, SOURCE_SHA256,
                         SOURCE_URL, evaluate, read_chip, read_clinical, source_bytes)


ABSTAIN_COSTS = (0.10, 0.25, 0.50)


def one_condition(condition, chip, truth):
    vessel = [chip[p]['vessel'][condition] for p in PATIENTS]
    tumoroid = [chip[p]['tumoroid'][condition] for p in PATIENTS]
    mean = [(a+b)/2 for a,b in zip(vessel,tumoroid)]
    evaluations = {key: evaluate(truth, scores)
                   for key,scores in (('vessel',vessel),('tumoroid',tumoroid),('mean',mean))}
    vessel_calls = evaluations['vessel']['predictions']
    tumoroid_calls = evaluations['tumoroid']['predictions']
    mean_calls = evaluations['mean']['predictions']
    released = [a==b for a,b in zip(vessel_calls,tumoroid_calls)]
    n_release = sum(released)
    errors = sum(flag and call!=actual for flag,call,actual in zip(released,vessel_calls,truth))
    abstain = len(truth)-n_release
    mean_errors = sum(a!=b for a,b in zip(mean_calls,truth))
    vessel_errors = sum(a!=b for a,b in zip(vessel_calls,truth))
    tumoroid_errors = sum(a!=b for a,b in zip(tumoroid_calls,truth))
    by_truth = {}
    for name,label in (('sensitive',1),('resistant',0)):
        indices=[i for i,t in enumerate(truth) if t==label]
        by_truth[name]={'patients':len(indices),'released':sum(released[i] for i in indices),
                        'released_errors':sum(released[i] and vessel_calls[i]!=truth[i] for i in indices),
                        'abstained':sum(not released[i] for i in indices)}
    return {
        'condition':condition,'patients':len(truth),
        'released':n_release,'abstained':abstain,'release_coverage':round(n_release/len(truth),6),
        'released_correct':n_release-errors,'released_errors':errors,
        'released_accuracy':round((n_release-errors)/n_release,6) if n_release else None,
        'by_clinical_truth':by_truth,
        'mean_full_calls_correct':len(truth)-mean_errors,
        'vessel_full_calls_correct':len(truth)-vessel_errors,
        'tumoroid_full_calls_correct':len(truth)-tumoroid_errors,
        'abstained_mean_errors':sum(not released[i] and mean_calls[i]!=truth[i] for i in range(len(truth))),
        'abstained_vessel_errors':sum(not released[i] and vessel_calls[i]!=truth[i] for i in range(len(truth))),
        'abstained_tumoroid_errors':sum(not released[i] and tumoroid_calls[i]!=truth[i] for i in range(len(truth))),
        'cost_per_patient':{str(cost):round((errors+cost*abstain)/len(truth),6) for cost in ABSTAIN_COSTS},
        'mean_full_call_cost_per_patient':round(mean_errors/len(truth),6),
        'vessel_full_call_cost_per_patient':round(vessel_errors/len(truth),6),
        'gate_minus_vessel_cost_per_patient':{
            str(cost):round((errors+cost*abstain-vessel_errors)/len(truth),6)
            for cost in ABSTAIN_COSTS},
        'break_even_abstain_cost_vs_mean':round((mean_errors-errors)/abstain,6) if abstain else None,
    }, {'vessel_calls':vessel_calls,'tumoroid_calls':tumoroid_calls,'mean_calls':mean_calls,
        'released':released,'vessel_cutoffs':evaluations['vessel']['training_cutoffs'],
        'tumoroid_cutoffs':evaluations['tumoroid']['training_cutoffs']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-zip',type=Path)
    parser.add_argument('--figure',type=Path)
    parser.add_argument('--out',type=Path,help='Optional private patient-level audit JSON')
    args=parser.parse_args()
    chip=read_chip(source_bytes(args.source_zip,SOURCE_URL,SOURCE_SHA256))
    clinical=read_clinical(source_bytes(args.figure,FIGURE_URL,FIGURE_SHA256))
    truth=[clinical[p] for p in PATIENTS]
    conditions={};details={}
    for condition in ('optimized','original'):
        conditions[condition],details[condition]=one_condition(condition,chip,truth)
    result={
        'schema':'channel.consensus.release.v1',
        'source_article':'https://doi.org/10.1016/j.xcrm.2026.102873',
        'source_sha256':SOURCE_SHA256,'figure_sha256':FIGURE_SHA256,
        'n_patients':len(PATIENTS),'sensitive_patients':sum(truth),
        'abstain_costs':list(ABSTAIN_COSTS),'conditions':conditions,
        'limits':['Rule and cost values were chosen after earlier six-channel results were known; exploratory design, not independent validation.',
                  'All individual thresholds use only the other 21 patients; this does not remove design-level selection.',
                  'An abstention is neither a correct nor an incorrect clinical prediction; cost values are illustrative, not observed patient utilities.',
                  'The 22 patients are one publication and one treatment; technical repeats are averaged, not independent patients.'],
    }
    if args.out:
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_text(json.dumps({'summary':result,'patients':list(PATIENTS),
                                        'clinical_sensitive':truth,'details':details},indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()

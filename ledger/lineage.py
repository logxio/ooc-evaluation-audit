#!/usr/bin/env python3
"""Join browser exports, frozen patient rules and archived cross-platform folds."""
import csv
import hashlib
import json
import platform
import resource
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'ledger'
R=ROOT
INPUTS={}


def read(path):
    data=path.read_bytes()
    INPUTS[str(path.relative_to(ROOT))]=hashlib.sha256(data).hexdigest()
    return data.decode()


def obj(path):
    return json.loads(read(path))


def table(path):
    return list(csv.DictReader(read(path).splitlines()))


def save(name,value):
    (OUT/name).write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n')


def csvout(name,rows):
    with (OUT/name).open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)


def rank(ref,x):
    return (sum(v<x for v in ref)+.5*sum(v==x for v in ref))/len(ref)


def patient_lineage():
    old=obj(R/'workbench/result.json')
    new=obj(R/'patient_workbench_result.json')
    frozen=obj(R/'matched_regimen_frozen.json')
    receipt=obj(OUT/'browser/receipt.json')
    baseline={r['patient']:r for r in table(OUT/'browser/built_in_two_readout.csv')}
    combined={r['patient']:r for r in table(OUT/'browser/updated_combined_regimen.csv')}
    old_analysis=obj(OUT/'browser/built_in_two_readout.json')
    new_analysis=obj(OUT/'browser/updated_combined_regimen.json')
    original_export={r['patient']:r for r in table(ROOT/'ledger/reference/patient-actions.csv')}
    assert old['rows']==new['rows']
    assert sorted(baseline)==sorted(combined)==sorted(original_export)
    model=old['rule']['certificate']['model']; cert=old['rule']['certificate']
    primary=frozen['model']
    assert sorted(model['training_ids'])==sorted(primary['training_ids'])
    old_cases={r['patient']:r for r in old['cases']}
    new_cases={r['patient']:r for r in new['cases']}
    out=[]
    for row in old['rows']:
        patient=row['patient']; y=row['response']
        calls=[int(row['readout'+str(j+1)]<=model['cutoffs'][j]) for j in (0,1)]
        margin=min(abs(rank(model['reference'][j],row['readout'+str(j+1)])-
                       rank(model['reference'][j],model['cutoffs'][j])) for j in (0,1))
        action=str(calls[0]) if calls[0]==calls[1] and margin>cert['margin'] else 'retest'
        combined_margin=abs(rank(primary['reference'],row['baseline_readout'])-rank(primary['reference'],primary['cutoff']))
        direct=str(int(row['baseline_readout']<=primary['cutoff']))
        calibrated=direct if combined_margin>frozen['certificate']['overall_margin'] else 'retest'
        assert direct==calibrated  # overall margin -1 releases every available measured signal
        assert action==baseline[patient]['action']==old_cases[patient]['action']==original_export[patient]['action']
        assert direct==combined[patient]['action']==new_cases[patient]['action']==old_cases[patient]['baseline_action']
        assert action==new_cases[patient]['baseline_action']
        assert str(y)==baseline[patient]['response']==combined[patient]['response']==original_export[patient]['response']
        wrong=int(action!='retest' and int(action)!=y)
        newwrong=int(int(direct)!=y)
        assert baseline[patient]['wrong_release']==(str(wrong) if action!='retest' else '')
        assert combined[patient]['wrong_release']==str(newwrong)
        assert abs(margin-old_cases[patient]['margin'])<1e-14
        assert abs(combined_margin-new_cases[patient]['margin'])<1e-14
        delta=('retest_to_correct_report' if action=='retest' and not newwrong else
               'wrong_to_correct_report' if wrong and not newwrong else
               'new_wrong_report' if newwrong and not wrong else 'unchanged')
        out.append(dict(patient=patient,cohort='rectal_2025',outcome=y,
            outcome_definition='TRG_0_or_1_or_cCR_is_1',split='same_42_train_42_calibration_43_test',
            split_seed=frozen['seed'],irradiation_readout=row['readout1'],five_fu_readout=row['readout2'],
            combined_regimen_readout=row['baseline_readout'],
            built_in_packet_version=old['version'],built_in_rule='two_readout_agreement',
            irradiation_cutoff=model['cutoffs'][0],five_fu_cutoff=model['cutoffs'][1],
            built_in_rank_margin=margin,built_in_release_margin=cert['margin'],
            built_in_action=action,built_in_released=int(action!='retest'),built_in_wrong_release=wrong,
            built_in_model_sha256=model['model_sha256'],
            updated_packet_version=new['version'],updated_rule='single_measured_combined_regimen_fixed_cutoff',
            combined_cutoff=primary['cutoff'],combined_rank_margin=combined_margin,
            combined_crc_margin=frozen['certificate']['overall_margin'],combined_action=direct,
            combined_released=1,combined_wrong_release=newwrong,combined_model_sha256=primary['model_sha256'],
            identical_patient_input_and_outcome=1,identical_strategy=0,
            comparison_change=delta,browser_old_csv='browser/built_in_two_readout.csv',
            browser_new_csv='browser/updated_combined_regimen.csv'))
    csvout('lineage.csv',out)
    assert len(out)==43
    assert sum(r['built_in_released'] for r in out)==27 and sum(r['built_in_wrong_release'] for r in out)==4
    assert sum(r['combined_wrong_release'] for r in out)==1
    assert old_analysis['summary']['ours']['wrong_released']==4
    assert new_analysis['summary']['ours']['wrong_released']==1
    return dict(patients=43,input_rows_identical=True,training_ids_identical=True,
        original_browser_export_rows_matched=43,new_browser_exports_and_independent_formula_rows_matched=43,
        built_in=dict(released=27,retests=16,wrong=4,overall_error=4/43,conditional_error=4/27,
            wrong_ids=[r['patient'] for r in out if r['built_in_wrong_release']]),
        combined=dict(released=43,retests=0,wrong=1,overall_error=1/43,conditional_error=1/43,
            wrong_ids=[r['patient'] for r in out if r['combined_wrong_release']]),
        changes=dict(Counter(r['comparison_change'] for r in out)),
        execution=receipt,
        policy_relationship='different signals and release policies on the same test patients; old comparator becomes new primary; fixed combined cutoff and overall-CRC give identical calls',
        delivery_relationship='built-in packet uses saved two-readout cases; updated result control opens precomputed combined-regimen cases; CLI is needed for a new combined-regimen input table')


def paired(a,b):
    keys=sorted(a)
    d=np.array([a[k]-b[k] for k in keys])
    rng=np.random.default_rng(0)
    boot=np.array([d[rng.integers(0,len(d),len(d))].mean() for _ in range(4000)])
    return dict(mean=float(d.mean()),ci95=np.percentile(boot,[2.5,97.5]).tolist(),n=len(d),seed=0,resamples=4000)


def fold_lineage():
    public_rows=table(ROOT/'chip_forecast_result.csv')
    public={(r['chemical'],int(r['fold']),r['method']):float(r['curve_mae']) for r in public_rows if r['k']=='3'}
    comparator=table(R/'ledger/.cache/trajectory_cv_per_chemical.csv')
    # The comparator file's method identifier comes from its recorded rows.
    np_methods=sorted({r['method'] for r in comparator})
    neural={r['chemical']:float(r['curve_mae']) for r in comparator if r['k']=='3' and r['method']=='neurotrajectory'}
    if not neural:
        raise ValueError(f'Neural method lookup requires original identifier: {np_methods}')
    reference=obj(ROOT/'ledger/reference/training_summary.json')
    pub_receipt=obj(ROOT/'ledger/reference/public_notebook.json')
    source=ROOT/'chip_forecast.py'
    read(source)
    assert INPUTS[str(source.relative_to(ROOT))]==pub_receipt['code_sha256']
    assert hashlib.sha256((ROOT/'chip_forecast_result.csv').read_bytes()).hexdigest()==pub_receipt['result_sha256']['chip_forecast_result.csv']
    line=[]; chemical_rows=[]; linux_all={}; mixed_all={}
    for fold in (1,2,3,4):
        linux_path=ROOT/f'ledger/reference/linux/fold{fold}/k3_fold{fold}.csv'
        linux=table(linux_path)
        linux_meta=obj(linux_path.with_suffix('.json'))
        mac_path=ROOT/f'ledger/reference/macos/fold{fold}/k3_fold{fold}.csv'
        mac=table(mac_path) if fold in (1,2) else []
        mac_meta=obj(mac_path.with_suffix('.json')) if mac else None
        lm={(r['chemical'],r['method']):float(r['curve_mae']) for r in linux}
        mm={(r['chemical'],r['method']):float(r['curve_mae']) for r in mac}
        assert all(value==public[(c,fold,m)] for (c,m),value in lm.items())
        chems=sorted({r['chemical'] for r in linux})
        la={c:lm[(c,'anchorboost')] for c in chems}
        ma={c:mm[(c,'anchorboost')] for c in chems} if mac else {}
        nc={c:neural[c] for c in chems}
        linux_all.update(la); mixed_all.update(ma or la)
        lp=paired(la,nc); mp=paired(ma,nc) if mac else None
        line.append(dict(fold=fold,chemicals=len(chems),linux_anchorboost_mean=float(np.mean(list(la.values()))),
            public_linux_rerun_max_abs_diff=max(abs(v-public[(c,fold,m)]) for (c,m),v in lm.items()),
            macos_anchorboost_mean=float(np.mean(list(ma.values()))) if mac else '',
            macos_minus_linux_mean=float(np.mean([ma[c]-la[c] for c in chems])) if mac else '',
            macos_minus_linux_max_abs=max(abs(ma[c]-la[c]) for c in chems) if mac else '',
            macos_evidence='archived_retrain' if mac else 'fold_not_retrained_on_macos_in_archive',
            neural_mean=float(np.mean(list(nc.values()))),linux_vs_neural_mean=lp['mean'],
            linux_vs_neural_ci_low=lp['ci95'][0],linux_vs_neural_ci_high=lp['ci95'][1],
            macos_vs_neural_mean=mp['mean'] if mp else '',
            macos_vs_neural_ci_low=mp['ci95'][0] if mp else '',macos_vs_neural_ci_high=mp['ci95'][1] if mp else '',
            linux_seconds=linux_meta['timing'][f'k3_fold{fold}']['seconds'],
            macos_seconds=mac_meta['timing'][f'k3_fold{fold}']['seconds'] if mac else '',
            training_rows=linux_meta['timing'][f'k3_fold{fold}']['training_rows'],
            linux_source=str(linux_path.relative_to(ROOT)),macos_source=str(mac_path.relative_to(ROOT)) if mac else '',
            code_sha256=linux_meta['code_sha256']))
        for c in chems:
            chemical_rows.append(dict(chemical=c,fold=fold,linux_curve_mae=la[c],
                public_linux_curve_mae=public[(c,fold,'anchorboost')],
                macos_curve_mae=ma.get(c,''),mixed_curve_mae=mixed_all[c],neural_curve_mae=nc[c]))
    csvout('fold_results.csv',line); csvout('fold_chemicals.csv',chemical_rows)
    result=dict(linux_folds_1to4=paired(linux_all,neural),mixed_macos12_linux34=paired(mixed_all,neural),
        public_vs_private_rows_equal=194*4,
        new_training_runs=0,scope='archived Linux public rerun and Mac fold 1/2 retrains; summaries and paired bootstrap recomputed now')
    for label,original in [('linux_folds_1to4',reference['primary']['versus']['published_neural_process']),
                           ('mixed_macos12_linux34',reference['cross_platform']['mixed_macos12_linux34']['versus_neural_process'])]:
        assert round(result[label]['mean'],4)==original['mean_diff']
        assert [round(x,4) for x in result[label]['ci95']]==original['ci95']
    env=[dict(environment='registered_and_public_Linux_CPU',python='3.12; patch not recorded',numpy='2.5.3',
        sklearn='1.7.2',platform='Kaggle Linux CPU',model_seed=0,design_seed='sha256(chemical|k) first 8 hex digits',
        bootstrap_seed=0,folds='1;2;3;4',execution='archived training plus public rerun',
        source='ledger/reference/public_notebook.json; ledger/reference/linux/',
        environment_limit='numpy/sklearn pins retained; Python minor evidenced by log path; Python patch and BLAS/thread configuration absent'),
        dict(environment='archived_Mac_training',python='not recorded in run artifacts',numpy='not recorded in run artifacts',
        sklearn='not recorded in run artifacts',platform='macOS as recorded in ledger/reference/training_summary.json',model_seed=0,
        design_seed='sha256(chemical|k) first 8 hex digits',bootstrap_seed=0,folds='1;2',execution='archived retrains',
        source='ledger/reference/macos/; ledger/reference/training_summary.json',
        environment_limit='exact historical Python, package and BLAS/thread snapshot absent; model config and input/code hashes retained'),
        dict(environment='current_ledger_replay',python=platform.python_version(),numpy=np.__version__,sklearn='unused',
        platform=platform.platform(),model_seed='saved predictions',design_seed='sha256(chemical|3) first 8 hex digits',
        bootstrap_seed=0,folds='1;2;3;4',execution='fresh raw-data decision and archive-statistics replay; archived browser exports',
        source='ledger/summary.json; ledger/browser/receipt.json; ledger/lineage_summary.json',
        environment_limit='no new model training; does not reconstruct the absent historical Mac environment')]
    csvout('environments.csv',env)
    save('reference_environment.json',dict(environments=env,model=reference['runs'],
        artifact_tolerance=dict(public_linux_saved_rows=0.0,archived_summary_rounding=0.00005,
            numerical_tolerance_scope='precomparison arithmetic checks; cross-platform training differences reported without a pass threshold'),
        archived_environment_gap='historical Mac dependency snapshot and Linux patch/BLAS metadata were not recorded in available artifacts'))
    return result


def headlines(patient):
    s=obj(OUT/'summary.json'); w=s['wells']; a=s['risk']['anchorboost']; b=s['risk']['measured_only']
    rows=[]
    def add(display,metric,num,den,unit,platform_,stage,path):
        rows.append(dict(display=display,metric=metric,numerator=num,denominator=den,unit=unit,
            platform=platform_,stage=stage,source=path))
    mea='static_rat_cortical_MEA_48_well_plates'
    stage='retrospective_5_alternative_designs_per_heldout_chemical_folds1to4'
    add('56.6%','exposed_well_equivalent_savings',w['baseline_wells']-w['strategy_wells'],w['baseline_wells'],'well_equivalents',mea,stage,'ledger/wells.csv')
    add('53.3%','uniform_21_baseline_9_initial_counterfactual',10860,20370,'well_equivalents',mea,stage,'ledger/well_cost_decomposition.csv')
    add('8.1%','wrong_releases_all_designs',79,970,'designs',mea,stage,'ledger/risk.csv')
    add('8.7293%','wrong_releases_released_designs',79,905,'released_designs',mea,stage,'ledger/risk.csv')
    add('11.1111%','measured_only_wrong_releases_released_designs',79,711,'released_designs',mea,stage,'ledger/risk.csv')
    for display,metric,num,den,unit in [('970','evaluated_design_count',970,194,'five_designs_per_chemical'),
        ('194','heldout_chemical_count',194,243,'chemicals_in_folds1to4_vs_all_folds'),
        ('905','release_count',905,970,'designs'),('65','retest_count',65,970,'designs'),
        ('93.3%','forecast_release_coverage',905,970,'designs'),('73.3%','measured_only_release_coverage',711,970,'designs'),
        ('+20.0 pp','release_coverage_gain',905-711,970,'designs'),
        ('-4.4 pp','forced_full_coverage_error_difference',102-145,970,'designs')]:
        add(display,metric,num,den,unit,mea,stage,'ledger/risk.csv')
    add('10%','calibration_budget','calibration_wrong_releases+1','calibration_designs+1','smoothed_design_loss',mea,'per_test_fold_calibration','ledger/calibration.csv')
    add('964187','valid_evaluation_observation_count',964187,5637,'repeated_design_x_well_x_day_x_feature_values_per_distinct_well',mea,stage,'ledger/observation_map.csv.gz; ledger/well_records.csv')
    organoid='rectal_patient_derived_organoids_2025'
    add('43','browser_displayed_patients',43,127,'fixed_test_split_vs_training_calibration_test_pool',organoid,'retrospective_browser_built_in','ledger/lineage.csv')
    add('4','built_in_wrong_reported_calls_all_patients',4,43,'patients',organoid,'retrospective_browser_built_in','ledger/lineage.csv')
    add('14.8148%','built_in_conditional_error',4,27,'released_patients',organoid,'retrospective_browser_built_in','ledger/lineage.csv')
    add('1/43','combined_regimen_error_all_and_released',1,43,'patients',organoid,'retrospective_offline_and_browser_updated_packet','ledger/lineage.csv')
    csvout('headline_numbers.csv',rows)


def main():
    from sources import ensure_sources
    ensure_sources()
    start=time.monotonic()
    patient=patient_lineage(); folds=fold_lineage(); headlines(patient)
    save('lineage_summary.json',dict(patients=patient,folds=folds,inputs=INPUTS,
        execution=dict(python=sys.version,numpy=np.__version__,platform=platform.platform(),
            seconds=time.monotonic()-start,max_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == 'darwin' else 1024))))
    print(json.dumps(dict(patients={k:v for k,v in patient.items() if k!='execution'},folds=folds),indent=2))


if __name__=='__main__':
    main()

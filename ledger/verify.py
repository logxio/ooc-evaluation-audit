#!/usr/bin/env python3
"""Independently check the delivered CSV arithmetic, joins and pinned sources."""
import csv
import gzip
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
P=ROOT/'ledger'


def rows(name):
    with (P/name).open(newline='') as f:
        return list(csv.DictReader(f))


def main():
    wells=rows('wells.csv'); risk=rows('risk.csv'); lineage=rows('lineage.csv')
    summary=json.loads((P/'summary.json').read_text())
    archive=json.loads((ROOT/'chip_forecast_decision.json').read_text())
    assert len(wells)==len(risk)==970
    assert {r['design_id'] for r in wells}=={r['design_id'] for r in risk}
    assert len({r['design_id'] for r in risk})==970
    assert set(Counter(r['chemical'] for r in wells).values())=={5}
    assert len({r['chemical'] for r in wells})==194
    for r in wells:
        counts=[int(v) for v in r['replicates_by_concentration'].split(';')]
        selected=[int(v) for v in r['first_level_indices'].split(';')]
        assert len(counts)==int(r['concentration_count']) and len(selected)==3
        assert sum(counts)==int(r['baseline_wells'])
        assert sum(counts[j] for j in selected)==int(r['first_wells'])
        assert int(r['first_wells'])+int(r['extra_retest_wells'])==int(r['strategy_wells'])
        assert int(r['extra_retest_wells'])==(0 if int(r['released']) else int(r['baseline_wells'])-int(r['first_wells']))
    baseline=sum(int(r['baseline_wells']) for r in wells)
    strategy=sum(int(r['strategy_wells']) for r in wells)
    savings=1-strategy/baseline
    assert math.isclose(savings,summary['wells']['savings_fraction'],abs_tol=1e-15)
    assert round(savings,4)==archive['anchorboost']['wells_saved_fraction']
    assert strategy==archive['anchorboost']['wells_used'] and baseline==archive['anchorboost']['wells_full']
    rate_results={}
    for method in ('anchorboost','measured_only'):
        released=wrong=fullwrong=0
        for r in risk:
            pred=int(float(r[method+'_score'])<=float(r[method+'_cutoff']))
            passed=int(float(r[method+'_margin'])>float(r[method+'_release_threshold']))
            truth=int(r['complete_series_call']=='inactive')
            assert pred==int(r[method+'_prediction'])
            assert passed==int(r[method+'_released'])
            assert int(r[method+'_released_wrong'])==passed*int(pred!=truth)
            assert int(r[method+'_forced_full_coverage_wrong'])==int(pred!=truth)
            released+=passed; wrong+=passed*(pred!=truth); fullwrong+=pred!=truth
        assert released==archive[method]['released'] and wrong==archive[method]['wrong_released']
        assert fullwrong==archive[method]['full_coverage_errors']
        assert round(wrong/released,4)==archive[method]['released_error']
        rate_results[method]=dict(released=released,wrong=wrong,all_designs=wrong/970,
            conditional=wrong/released,forced_errors=fullwrong)
    for r in rows('calibration.csv'):
        assert (int(r['calibration_wrong_releases'])+1)/(int(r['calibration_designs'])+1)==float(r['smoothed_overall_risk'])
        assert float(r['smoothed_overall_risk'])<=float(r['alpha'])
    by_well={r['bundle_well_row']:r for r in rows('well_records.csv')}
    by_design={r['design_id']:r for r in wells}
    observations=Counter();unique=set()
    features=('firing_rate_mean','burst_rate','per_burst_interspike_interval','per_burst_spike_percent',
        'burst_duration_mean','interburst_interval_mean','active_electrodes_number','bursting_electrodes_number',
        'network_spike_number','network_spike_peak','spike_duration_mean','per_network_spike_spike_percent',
        'inter_network_spike_interval_mean','network_spike_duration_std','per_network_spike_spike_number_mean',
        'correlation_coefficient_mean','mutual_information_norm')
    with gzip.open(P/'observation_map.csv.gz','rt',newline='') as f:
        for r in csv.DictReader(f):
            physical=by_well[r['bundle_well_row']]; design=by_design[r['design_id']]
            assert physical['chemical']==design['chemical']
            day=(5,7,9,12).index(int(r['day'])); feature=features.index(r['feature'])
            assert int(physical['valid_day_feature_mask_hex'],16)&(1<<(17*day+feature))
            observations[r['design_id']]+=1
            unique.add((r['bundle_well_row'],r['day'],r['feature']))
    assert sum(observations.values())==964187
    assert all(observations[r['design_id']]==int(r['target_observations']) for r in wells)
    assert len(lineage)==43 and len({r['patient'] for r in lineage})==43
    assert sum(int(r['built_in_wrong_release']) for r in lineage)==4
    assert sum(int(r['combined_wrong_release']) for r in lineage)==1
    for record in summary['inputs']:
        assert hashlib.sha256((ROOT/record['path']).read_bytes()).hexdigest()==record['sha256'],record['path']
    ls=json.loads((P/'lineage_summary.json').read_text())
    for name,digest in ls['inputs'].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,name
    result=dict(status='passed',well_rows=970,risk_rows=970,patient_rows=43,baseline_wells=baseline,
        strategy_wells=strategy,savings=savings,risk=rate_results,observation_rows=964187,
        distinct_well_day_feature_observations=len(unique),distinct_well_rows=len(by_well),
        patient_built_in_error='4/43 overall; 4/27 conditional',patient_combined_error='1/43 for both',
        source_hashes_checked=len(summary['inputs'])+len(ls['inputs']),
        fresh_training_runs=0,external_network_requests=0)
    (P/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()

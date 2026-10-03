#!/usr/bin/env python3
"""Rebuild the Series 1 decision/well ledger from pinned task rows and saved forecasts.

No model training or writes outside ledger/. Uses numpy and
the published cutoff function (stdlib only); compares every exported action.
"""
import argparse
import csv
import gzip
import hashlib
import json
import platform
import resource
import sys
import time
import warnings
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'ledger'
RELEASE = ROOT
sys.dont_write_bytecode = True
sys.path.insert(0, str(RELEASE))
from release_calibration import cutoff

DATA = OUT / '.cache/nfa_tasks.npz'
DATA_SHA = 'e1f056ef33f568052fb8dfdba6e095f7b575c7f78d96768e34469918559008d2'
METHODS = ('anchorboost', 'measured_only')
DIVS = (5, 7, 9, 12)
FEATURES = ('firing_rate_mean', 'burst_rate', 'per_burst_interspike_interval',
            'per_burst_spike_percent', 'burst_duration_mean', 'interburst_interval_mean',
            'active_electrodes_number', 'bursting_electrodes_number', 'network_spike_number',
            'network_spike_peak', 'spike_duration_mean', 'per_network_spike_spike_percent',
            'inter_network_spike_interval_mean', 'network_spike_duration_std',
            'per_network_spike_spike_number_mean', 'correlation_coefficient_mean', 'mutual_information_norm')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def js(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n')


def csvout(path, rows):
    with path.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def joined(values):
    return ';'.join(str(v) for v in values)


def designs(chemical, levels):
    # Exact published RNG and ordering, necessary to join design 0..4.
    seed = int(hashlib.sha256(f'{chemical}|3'.encode()).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)
    out, seen = [], set()
    for _ in range(20):
        ctx = tuple(sorted(rng.choice(levels, size=3, replace=False).tolist()))
        if ctx not in seen:
            seen.add(ctx)
            out.append(np.array(ctx, np.float32))
        if len(out) == 5:
            break
    assert len(out) == 5
    return out


def reconstruct():
    assert sha(DATA) == DATA_SHA
    z = np.load(DATA, allow_pickle=False)
    pred = {}
    paths = [RELEASE / f'chip_forecast_runs/decision_fold{f}.npz' for f in range(5)]
    for f, path in enumerate(paths):
        with np.load(path, allow_pickle=False) as p:
            for c, d, level, value in zip(*(p[f'fold{f}_{s}'] for s in ('chem', 'design', 'level', 'pred'))):
                key = (str(c), int(d), int(level))
                assert key not in pred
                pred[key] = value.copy()
    rows, tasks = [], {}
    for i, chem in enumerate(z['chem']):
        chemical, fold = str(chem), int(z['fold'][i])
        a, b = map(int, z['offsets'][i:i+2])
        logc, y, mask = z['logc'][a:b], z['y'][a:b].astype(np.float32), z['m'][a:b]
        levels, counts = np.unique(logc, return_counts=True)
        li = np.searchsorted(levels, logc)
        numerator = np.zeros((len(levels), 4, 17))
        denominator = np.zeros_like(numerator)
        np.add.at(numerator, li, y * mask)
        np.add.at(denominator, li, mask)
        valid = denominator > 0
        mu = (numerator / np.maximum(denominator, 1)).astype(np.float32)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', RuntimeWarning)
            effect = np.nan_to_num(np.abs(np.nanmean(np.where(valid, mu, np.nan), axis=1)), nan=0.)
        tasks[chemical] = dict(fold=fold, a=a, b=b, levels=levels, counts=counts,
                               logc=logc, li=li, mask=mask, plates=z['plate'][a:b])
        for di, ctx in enumerate(designs(chemical, levels)):
            selected = np.searchsorted(levels, ctx)
            unmeasured = [j for j in range(len(levels)) if j not in selected]
            measured_score = float(effect[selected].max())
            forecast_score = max(float(np.abs(pred[(chemical, di, j)].reshape(4, 17).mean(0)).max())
                                 for j in unmeasured)
            rows.append(dict(design_id=f'{chemical}|{di}', chemical=chemical, fold=fold, design=di,
                             full_series_label=int(effect.max() < 3.),
                             full_series_activity=float(effect.max()),
                             anchorboost=max(measured_score, forecast_score), measured_only=measured_score,
                             levels=levels, measured_indices=selected,
                             counts=counts, first=int(counts[selected].sum()), full=b-a,
                             unmeasured_observations=int(mask[~np.isin(logc, ctx)].sum())))
    return rows, tasks, paths


def fit_rules(rows):
    calibration, frozen = [], {}
    for fold in (1, 2, 3, 4):
        other = [f for f in range(5) if f != fold]
        train = [r for r in rows if r['fold'] in other[:2]]
        cal = [r for r in rows if r['fold'] in other[2:]]
        test = [r for r in rows if r['fold'] == fold]
        for method in METHODS:
            values = [r[method] for r in train]
            cut = cutoff(values, [r['full_series_label'] for r in train])
            ref = np.sort(values)
            def rank(x):
                return float((np.searchsorted(ref, x, side='left') + np.searchsorted(ref, x, side='right')) / (2 * len(ref)))
            center = rank(cut)
            def calls(data):
                return [(int(r[method] <= cut), abs(rank(r[method])-center)) for r in data]
            calcases = calls(cal)
            margin = 1.
            for candidate in [-1.] + [i/100 for i in range(101)]:
                e = sum(m > candidate and p != r['full_series_label'] for (p, m), r in zip(calcases, cal))
                if (e+1)/(len(cal)+1) <= .1:
                    margin = candidate
                    break
            released = sum(m > margin for _, m in calcases)
            wrong = sum(m > margin and p != r['full_series_label'] for (p, m), r in zip(calcases, cal))
            for r, (p, m) in zip(test, calls(test)):
                r[method+'_prediction'] = p
                r[method+'_margin'] = m
                r[method+'_release'] = int(m > margin)
                r[method+'_wrong'] = int(p != r['full_series_label'])
                r[method+'_cutoff'] = cut
                r[method+'_release_margin'] = margin
            calibration.append(dict(test_fold=fold, method=method, training_folds=joined(other[:2]),
                calibration_folds=joined(other[2:]), training_designs=len(train),
                training_chemicals=len({r['chemical'] for r in train}), calibration_designs=len(cal),
                calibration_chemicals=len({r['chemical'] for r in cal}), cutoff=cut,
                release_margin=margin, calibration_releases=released, calibration_wrong_releases=wrong,
                smoothed_overall_risk=(wrong+1)/(len(cal)+1), alpha=.1,
                conditional_calibration_error=wrong/released if released else '',
                test_designs=len(test), test_releases=sum(r[method+'_release'] for r in test),
                test_wrong_releases=sum(r[method+'_release']*r[method+'_wrong'] for r in test)))
            frozen[f'{fold}/{method}'] = dict(cutoff=cut, reference=ref.tolist(), margin=margin,
                train_ids=[r['design_id'] for r in train], calibration_ids=[r['design_id'] for r in cal])
    return calibration, frozen


def cost_rows(held):
    out = []
    for r in held:
        n, selected, counts = len(r['levels']), r['measured_indices'], r['counts']
        release = r['anchorboost_release']
        # Every counterfactual design has weight one. Ratios of sums therefore
        # give larger full-series bundles more influence than smaller bundles.
        out.append(dict(design_id=r['design_id'], chemical=r['chemical'], fold=r['fold'], design=r['design'],
            concentration_count=n, concentration_log10_uM=joined(float(v) for v in r['levels']),
            replicates_by_concentration=joined(int(c) for c in counts), mean_replicates=r['full']/n,
            full_series_formula='sum(replicates_by_concentration) = concentration_count * mean_replicates',
            baseline_wells=r['full'], first_concentration_count=3,
            first_level_indices=joined(int(v) for v in selected), first_wells=r['first'],
            extra_retest_wells=0 if release else r['full']-r['first'],
            strategy_wells=r['first'] if release else r['full'],
            measured_only_strategy_wells=r['first'] if r['measured_only_release'] else r['full'],
            released=release, first_wells_reused=1, weight=1,
            design_status='one_of_five_retrospective_alternatives_per_chemical',
            qc_control_wells_included=0,
            qc_control_rule='retained_positive_concentration_task_rows_only; vehicle_normalization_source_excluded',
            excluded_items='vehicle/control_allocation; extra_QC; failed_or_missing_source_wells; physical_reruns; prospective_execution',
            missing_endpoint_rule='count_each_retained_well_once; mask_missing_day_feature_values_in_prediction_only',
            reference_baseline_wells=21, reference_first_wells=9,
            reference_strategy_wells=9 if release else 21,
            target_observations=r['unmeasured_observations']))
    return out


def risk_rows(held):
    out = []
    for r in held:
        row = dict(design_id=r['design_id'], chemical=r['chemical'], fold=r['fold'], design=r['design'],
            complete_series_call='inactive' if r['full_series_label'] else 'active',
            complete_series_activity=r['full_series_activity'], endpoint_threshold=3.,
            endpoint='max_abs_DIV_mean_over_features_and_concentrations',
            complete_measurement_reference_prediction=r['full_series_label'],
            complete_measurement_reference_error=0)
        for m in METHODS:
            row.update({m+'_score':r[m], m+'_cutoff':r[m+'_cutoff'], m+'_margin':r[m+'_margin'],
                m+'_release_threshold':r[m+'_release_margin'],
                m+'_action':'release' if r[m+'_release'] else 'complete_series',
                m+'_released':r[m+'_release'], m+'_prediction':r[m+'_prediction'],
                m+'_released_wrong':r[m+'_release']*r[m+'_wrong'],
                m+'_forced_full_coverage_wrong':r[m+'_wrong']})
        out.append(row)
    return out


def verify_actions(held):
    archived = {r['chemical']+'|'+r['design']:r for r in csv.DictReader((RELEASE/'chip_forecast_actions.csv').open())}
    assert set(archived) == {r['design_id'] for r in held}
    for r in held:
        a = archived[r['design_id']]
        assert int(a['wells_measured']) == r['first'] and int(a['wells_full']) == r['full']
        assert (a['action'] == 'report call') == bool(r['anchorboost_release'])
        assert (a['call'] == 'inactive') == bool(r['anchorboost_prediction'])
        assert (a['full_series_call'] == 'inactive') == bool(r['full_series_label'])
        assert a['measured_log10_uM'] == ';'.join(f'{r["levels"][j]:g}' for j in r['measured_indices'])
        assert float(a['forecast_score']) == round(r['anchorboost'],4)
        assert float(a['measured_only_score']) == round(r['measured_only'],4)
        assert float(a['margin']) == round(r['anchorboost_margin'],4)
        assert float(a['release_margin']) == r['anchorboost_release_margin']
        assert a['released_call_wrong'] == (str(r['anchorboost_wrong']) if r['anchorboost_release'] else '')
    return len(archived)


def bootstrap(held, n=4000):
    chems = sorted({r['chemical'] for r in held})
    sums = {c:np.zeros(9) for c in chems}
    for r in held:
        a, b = r['anchorboost_release'], r['measured_only_release']
        sums[r['chemical']] += (1,a,b,a*r['anchorboost_wrong'],b*r['measured_only_wrong'],
            r['anchorboost_wrong']-r['measured_only_wrong'], r['full'],
            r['first'] if a else r['full'], r['first'] if b else r['full'])
    arr = np.array(list(sums.values()))
    def stats(s):
        return np.array([(s[1]-s[2])/s[0], (s[3]-s[4])/s[0], s[3]/s[1], s[4]/s[2],
            s[5]/s[0], (s[8]-s[7])/s[6], 1-s[7]/s[8]])
    rng = np.random.default_rng(0)
    samples = np.array([stats(arr[rng.integers(0,len(arr),len(arr))].sum(0)) for _ in range(n)])
    names = ['release_coverage_difference','overall_wrong_release_difference',
        'anchorboost_conditional_error','measured_only_conditional_error',
        'forced_full_coverage_error_difference','savings_difference_vs_full_series',
        'strategy_savings_relative_to_measured_only']
    est = stats(arr.sum(0))
    return {name:dict(estimate=float(est[i]), ci95=np.percentile(samples[:,i],[2.5,97.5]).tolist(),
        one_sided_upper95=float(np.percentile(samples[:,i],95)), resamples=n, seed=0,
        unit='chemical_with_all_five_designs', inference='posthoc_percentile_bootstrap_at_fixed_rules')
        for i,name in enumerate(names)}


def summary(held, wells, cal):
    risk = {}
    for m in METHODS:
        released = sum(r[m+'_release'] for r in held)
        errors = sum(r[m+'_release']*r[m+'_wrong'] for r in held)
        fullerrors = sum(r[m+'_wrong'] for r in held)
        risk[m] = dict(designs=len(held), released=released, retests=len(held)-released,
            wrong_released=errors, release_coverage=released/len(held),
            errors_per_all_designs=errors/len(held), errors_per_released_designs=errors/released,
            forced_full_coverage_errors=fullerrors, forced_coverage=len(held),
            forced_errors_per_all_designs=fullerrors/len(held),
            forced_errors_per_released_designs=fullerrors/len(held))
    # Explicit sequential counterfactual decomposition: change the level count,
    # then mean replicate weights, then within-chemical replicate imbalance.
    L=np.array([r['concentration_count'] for r in wells],float)
    F=np.array([r['baseline_wells'] for r in wells],float)
    I=np.array([r['first_wells'] for r in wells],float)
    R=np.array([r['released'] for r in wells],float)
    scenarios=[('uniform_7_levels_3_replicates',np.full(len(wells),21.),np.full(len(wells),9.)),
        ('actual_level_count_3_replicates',L*3,np.full(len(wells),9.)),
        ('actual_mean_replicates_equal_within_chemical',F,3*F/L),
        ('actual_retained_wells_per_level',F,I)]
    waterfall=[]
    last=None
    for name,full,initial in scenarios:
        used=initial+(1-R)*(full-initial)
        s=1-used.sum()/full.sum()
        waterfall.append(dict(scenario=name,baseline_wells=float(full.sum()),strategy_wells=float(used.sum()),
            saving_rate=float(s),change_percentage_points=0. if last is None else float(100*(s-last))))
        last=s
    return dict(wells=dict(baseline_wells=int(F.sum()),first_wells=int(I.sum()),
        added_retest_wells=sum(r['extra_retest_wells'] for r in wells),
        strategy_wells=sum(r['strategy_wells'] for r in wells),
        savings_fraction=float(last), headline_rounded_percent=round(100*last,1),
        judge_model_savings_fraction=waterfall[0]['saving_rate'],
        difference_percentage_points=100*(last-waterfall[0]['saving_rate']),
        observed_unique_heldout_wells=int(F.sum()/5),
        concentration_count_chemical_distribution=dict(Counter(int(x) for x in L[::5])),
        interpretation='retrospective exposed-well equivalents, summed across five alternative designs per chemical; shared controls and prospective overhead excluded',
        decomposition_order='level count, mean replicate weighting, within-chemical replicate imbalance',
        decomposition_order_dependence='individual increments depend on this stated path; their total is invariant'),
        risk=risk, waterfall=waterfall, calibration=cal, intervals=bootstrap(held),
        risk_scope=dict(loss='1{released and predicted call differs from complete-series call}',
            calibration_rule='smallest grid margin with (wrong_calibration_releases+1)/(all_calibration_designs+1)<=0.10',
            conditional_rule='not used: the decision script selects overall_margin',
            grouping='five designs reuse each chemical; calibration designs are not independent biological samples',
            crossfit='each saved forecast excludes its own chemical fold; other-fold forecasts used for cutoff/calibration can have been trained on the current test fold',
            guarantee='reported 10% is the calibration budget; these replay counts and bootstrap intervals do not establish an independent prospective or conditional-risk guarantee'))


def observation_map(held, tasks):
    records=[]
    for chemical, t in tasks.items():
        if t['fold']==0:
            continue
        for j in range(t['b']-t['a']):
            records.append(dict(bundle_well_row=t['a']+j,chemical=chemical,fold=t['fold'],
                log10_uM=float(t['logc'][j]),plate_date=str(t['plates'][j]),
                valid_day_feature_mask_hex=hex(sum(int(v)<<k for k,v in enumerate(t['mask'][j].ravel()))),
                retained_observations=int(t['mask'][j].sum())))
    csvout(OUT/'well_records.csv',records)
    # A stable bundle row identifies a retained physical-well trajectory. The
    # bundle omits the original well coordinate; plate/date alone is not its ID.
    count=0
    with (OUT/'observation_map.csv.gz').open('wb') as raw:
        import io
        with gzip.GzipFile(fileobj=raw,mode='wb',mtime=0,filename='') as gz:
            with io.TextIOWrapper(gz,newline='') as f:
                w=csv.writer(f); w.writerow(['design_id','bundle_well_row','day','feature'])
                for r in held:
                    t=tasks[r['chemical']]
                    for j in np.where(~np.isin(t['li'],r['measured_indices']))[0]:
                        for day, feature in np.argwhere(t['mask'][j]):
                            w.writerow([r['design_id'],t['a']+int(j),DIVS[day],FEATURES[feature]])
                            count+=1
    assert count==sum(r['unmeasured_observations'] for r in held)==964187
    return dict(observations=count,unique_heldout_well_rows=len(records),chemicals=len(tasks)-49,
        mapping='observation_map.csv.gz joins well_records.csv on bundle_well_row',
        independence='the same physical well repeats across day, feature and alternative design; count chemicals for bootstrap',
        upstream_physical_key='chemical,spid,plate,date,well,concentration_uM; bundle retains plate|date and row order only')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--probe',action='store_true')
    args=p.parse_args(); started=time.monotonic()
    OUT.mkdir(exist_ok=True)
    from sources import ensure_sources
    ensure_sources()
    rows,tasks,paths=reconstruct()
    if args.probe:
        js(OUT/'probe.json',dict(chemicals=len(tasks),designs=len(rows),seconds=time.monotonic()-started,
            max_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == "darwin" else 1024),platform=platform.platform(),
            scope='load pinned data and forecasts, reconstruct scores; model training count 0'))
        print((OUT/'probe.json').read_text()); return
    cal,frozen=fit_rules(rows)
    held=[r for r in rows if r['fold'] in (1,2,3,4)]
    assert len(held)==970 and len({r['chemical'] for r in held})==194
    matches=verify_actions(held)
    wells=cost_rows(held)
    csvout(OUT/'wells.csv',wells)
    csvout(OUT/'risk.csv',risk_rows(held))
    csvout(OUT/'calibration.csv',cal)
    js(OUT/'frozen_rules.json',frozen)
    result=summary(held,wells,cal)
    csvout(OUT/'well_cost_decomposition.csv',result['waterfall'])
    result['observation_units']=observation_map(held,tasks)
    result['verification']=dict(archived_action_rows_matched=matches,
        decision_summary_matches={m:result['risk'][m]['wrong_released']==json.loads((RELEASE/'chip_forecast_decision.json').read_text())[m]['wrong_released'] for m in METHODS})
    assert all(result['verification']['decision_summary_matches'].values())
    inputs=[DATA,*paths,RELEASE/'chip_forecast.py',RELEASE/'chip_forecast_decision.py',
        RELEASE/'chip_forecast_actions.py',RELEASE/'chip_forecast_actions.csv',RELEASE/'chip_forecast_decision.json',
        RELEASE/'chip_forecast_decision_protocol.json',RELEASE/'release_calibration.py',RELEASE/'matched_regimen.py']
    result['inputs']=[dict(path=str(v.relative_to(ROOT)),sha256=sha(v)) for v in inputs]
    result['execution']=dict(python=sys.version,numpy=np.__version__,platform=platform.platform(),
        seconds=time.monotonic()-started,max_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == "darwin" else 1024),
        new_training_runs=0,paid_api_calls=0,source_sha256=sha(Path(__file__)))
    js(OUT/'summary.json',result)
    print(json.dumps({k:result[k] for k in ('wells','risk','verification','execution')},indent=2))


if __name__=='__main__':
    main()

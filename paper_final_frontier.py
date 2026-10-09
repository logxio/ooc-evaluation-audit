"""Recompute retrospective cost/error frontiers from frozen rank scores; no fitting."""
import sys
sys.dont_write_bytecode = True
from paper_final_common import *
import argparse
from types import SimpleNamespace
METHODS = ['anchorboost', 'measured_only', 'loglinear']
SCANS = ['common_margin', 'calibrated_offset']
TOL = 1e-12
def clean(x):
    if isinstance(x, dict):
        return {k: clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple, np.ndarray)):
        return [clean(v) for v in x]
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (float, np.floating)):
        return float(x) if np.isfinite(x) else None
    return x

def frontier_interval(values):
    valid = values[1:][np.isfinite(values[1:])]
    ci = np.quantile(valid, [0.025, 0.975]) if len(valid) else [np.nan, np.nan]
    return clean({'estimate': values[0], 'ci95': ci, 'bootstrap_defined': len(valid), 'bootstrap_total': len(values) - 1, 'interval_scope': 'pointwise' if len(valid) == len(values) - 1 else 'pointwise_conditional_on_feasibility'})

def flat(name, values):
    r = frontier_interval(values)
    return {name: r['estimate'], name + '_ci95_low': r['ci95'][0], name + '_ci95_high': r['ci95'][1], name + '_bootstrap_defined': r['bootstrap_defined']}

def ranges(rows, key):
    values = sorted((r['loss_cap'] for r in rows if r[key + '_ci95_low'] is not None and r[key + '_ci95_low'] > 0))
    result = []
    for value in values:
        if result and abs(value - result[-1][1] - 0.005) < TOL:
            result[-1][1] = value
        else:
            result.append([value, value])
    return result
mt=SimpleNamespace(interval=frontier_interval,flat=flat,ranges=ranges)
def scores(data, method, scan):
    D = data['D']
    m = np.array([num * (D // den) for num, den in (r[method + '_exact'] for r in data['rows'])], dtype=np.int64)
    if scan == 'calibrated_offset':
        lam = np.array([Fraction(repr(data['cal'][r['outer_fold']][method]['margin'])) for r in data['rows']])
        m = m - np.array([int(x * D) for x in lam], dtype=np.int64)
    return m

def thresholds(data, s, scan):
    D = data['D']
    s = s[~data['lane']]
    if scan == 'common_margin':
        extra = [D, -D] + [j * D // 100 for j in range(101)]
    else:
        extra = [0, int(s.min()) - D]
    return np.sort(np.unique(np.r_[s, np.array(extra, dtype=np.int64)]))[::-1]

def arrays_for(data, s, ts, err):
    """Thresholds x replicates arrays; row 0 of W1 is the point estimate. Loss kept as integer numerators."""
    ix, n = (data['ix'], data['n'])
    ng = len(n)
    W1 = np.vstack((np.ones(ng), data['W']))
    onehot = np.eye(ng)[ix]
    release = (s[None, :] > ts[:, None]) | data['lane'][None, :]
    gr = release.astype(float) @ onehot
    ge = (release & err).astype(float) @ onehot
    gw = np.where(release, data['meas'], data['full']) @ onehot
    L = math.lcm(*{int(v) for v in n})
    unit = (L / n)[None, :]
    loss_num = W1 @ (ge * unit).T
    assert np.all(loss_num == np.round(loss_num))
    return ({'loss_num': loss_num, 'wells': W1 @ gw.T, 'wrong_reports': W1 @ ge.T, 'reports': W1 @ gr.T}, L * ng)

def select(arr, scale, ts, D, constraint, cap):
    """Exact constrained optimum per replicate. cap: ('loss', Fraction) | ('loss_num', array) | ('wells', array) | ('wells_frac', Fraction, full)."""
    loss_num, wells = (arr['loss_num'], arr['wells'])
    if constraint == 'loss':
        q = cap
        valid = loss_num * q.denominator <= q.numerator * scale
    elif constraint == 'loss_num':
        valid = loss_num <= cap[:, None]
    elif constraint == 'wells':
        valid = wells <= cap[:, None]
    else:
        q, fullb = cap
        valid = wells * q.denominator <= q.numerator * fullb[:, None]
    if constraint in ('loss', 'loss_num'):
        objective = np.where(valid, wells, np.inf)
        optimum = objective.min(axis=1)
        tied = valid & (wells == optimum[:, None])
        choice = np.where(tied, loss_num, np.inf).argmin(axis=1)
    else:
        objective = np.where(valid, loss_num, np.inf)
        optimum = objective.min(axis=1)
        tied = valid & (loss_num == optimum[:, None])
        choice = np.where(tied, wells, np.inf).argmin(axis=1)
    feasible = valid.any(axis=1)
    rr = np.arange(len(choice))
    res = {'loss': np.where(feasible, loss_num[rr, choice] / scale, np.nan), 'wells': np.where(feasible, wells[rr, choice], np.nan), 'wrong_reports': np.where(feasible, arr['wrong_reports'][rr, choice], np.nan), 'reports': np.where(feasible, arr['reports'][rr, choice], np.nan), 'threshold': np.where(feasible, ts[choice] / D, np.nan)}
    return res

def matched(data, cache):
    p, D, ix, n = (data['p'], data['D'], data['ix'], data['n'])
    ng = len(n)
    W1 = np.vstack((np.ones(ng), data['W']))
    rows = data['rows']
    fullg = np.bincount(ix, weights=data['full'], minlength=ng)
    full_boot = W1 @ fullg
    L = math.lcm(*{int(v) for v in n})
    scale = L * ng
    abrep = np.array([r['anchorboost_release'] for r in rows])
    abwrong = abrep & np.array([r['anchorboost_call'] != r['truth'] for r in rows])
    abg = {'loss_num': np.bincount(ix, weights=abwrong, minlength=ng) * (L / n), 'wells': np.bincount(ix, weights=np.where(abrep, data['meas'], data['full']), minlength=ng), 'wrong_reports': np.bincount(ix, weights=abwrong, minlength=ng), 'reports': np.bincount(ix, weights=abrep, minlength=ng)}
    jg = [data['joint'][g] for g in data['groups']]
    assert all((float(j['designs']) == n[i] and float(j['wells_full']) == fullg[i] for i, j in enumerate(jg)))
    loopg = {'loss_num': np.array([float(j['wrong_reports']) for j in jg]) * (L / n), 'wells': np.array([float(j['wells_used']) for j in jg]), 'wrong_reports': np.array([float(j['wrong_reports']) for j in jg]), 'reports': np.array([float(j['reports']) for j in jg])}
    op = {k: W1 @ v for k, v in abg.items()}
    loop = {k: W1 @ v for k, v in loopg.items()}
    for x in (op, loop):
        x['loss'] = x['loss_num'] / scale
    caps = [Fraction(repr(c)) for c in p['frontier']['matched']['loss_caps']]
    grid = [Fraction(repr(q)) for q in p['frontier']['matched']['wells_fraction_grid']]
    budgets = [('fraction_grid', float(q), ('wells_frac', (q, full_boot))) for q in grid]
    budgets += [('anchor_working_point_budget', op['wells'][0] / 28080, ('wells', op['wells'])), ('loop_working_point_budget', loop['wells'][0] / 28080, ('wells', loop['wells']))]
    selected = {}
    for scan in SCANS:
        for method in METHODS:
            s, ts, err = cache[method, scan]
            arr, sc = arrays_for(data, s, ts, err)
            assert sc == scale
            selected[scan, method, 'loss'] = [select(arr, scale, ts, D, 'loss', c) for c in caps]
            selected[scan, method, 'wells'] = [select(arr, scale, ts, D, kind, cap) if kind == 'wells' else select(arr, scale, ts, D, 'wells_frac', cap) for _, _, (kind, cap) in budgets]
            selected[scan, method, 'loop_loss'] = select(arr, scale, ts, D, 'loss_num', loop['loss_num'])
    loss_rows, wells_rows = ([], [])
    loop_result = {'schema': 'paper.scale_A.matched.loop.v1', 'policy': 'model_disagreement', 'primary_bootstrap': 'seed0', 'variants': {}}
    summary = {'schema': 'paper.scale_A.matched.summary.v1', 'new_fits': 0, 'protocol_sha256': frozen_sha(FINAL / 'reporting/protocol.json'), 'primary_bootstrap': 'seed0', 'primary_scan': 'calibrated_offset', 'variants': {}, 'interpretation': 'Retrospective descriptive threshold scan on the test set; operating thresholds come from calibration data; grid points are not deployable test-selected thresholds.'}
    loop_result['variants']['seed0'] = {'operating_point': {k: mt.interval(v) for k, v in loop.items() if k != 'loss_num'}, 'scans': {}}
    sv = {'anchor_operating_point': {k: mt.interval(v) for k, v in op.items() if k != 'loss_num'}, 'anchor_operating_point_vs_frontier': {}, 'positive_savings_loss_grid_ranges': {}}
    for scan in SCANS:
        for j, cap in enumerate(caps):
            row = {'bootstrap': 'seed0', 'scan': scan, 'loss_cap': float(cap), 'bootstrap_total': 4000}
            for method in METHODS:
                for key, values in selected[scan, method, 'loss'][j].items():
                    if key == 'threshold':
                        row[method + '_threshold'] = values[0]
                    else:
                        row.update(mt.flat(method + '_' + key, values))
            ab = selected[scan, 'anchorboost', 'loss'][j]['wells']
            for base in METHODS[1:]:
                other = selected[scan, base, 'loss'][j]['wells']
                row.update(mt.flat('anchorboost_vs_' + base + '_savings_fraction', 1 - ab / other))
                row.update(mt.flat('anchorboost_vs_' + base + '_wells_saved', other - ab))
            loss_rows.append(row)
        for j, (kind, fraction, (ckind, cap)) in enumerate(budgets):
            bw = cap[1][0] * float(cap[0]) if ckind == 'wells_frac' else cap[0]
            row = {'bootstrap': 'seed0', 'scan': scan, 'budget_kind': kind, 'budget_fraction_full': fraction, 'budget_wells': bw, 'bootstrap_total': 4000}
            for method in METHODS:
                for key, values in selected[scan, method, 'wells'][j].items():
                    if key == 'threshold':
                        row[method + '_threshold'] = values[0]
                    else:
                        row.update(mt.flat(method + '_' + key, values))
            for base in METHODS[1:]:
                a, b = (selected[scan, 'anchorboost', 'wells'][j], selected[scan, base, 'wells'][j])
                for metric in ['loss', 'wrong_reports']:
                    row.update(mt.flat('anchorboost_minus_' + base + '_' + metric, a[metric] - b[metric]))
            row['interval_scope'] = 'pointwise' if row['anchorboost_loss_bootstrap_defined'] == 4000 else 'pointwise_conditional_on_feasibility'
            wells_rows.append(row)
        sv['anchor_operating_point_vs_frontier'][scan] = {}
        for base in METHODS:
            comp = selected[scan, base, 'wells'][-2]
            sv['anchor_operating_point_vs_frontier'][scan][base] = {'loss_difference': mt.interval(op['loss'] - comp['loss']), 'loss_reduction_pp': mt.interval(100 * (comp['loss'] - op['loss'])), 'wrong_reports_difference': mt.interval(op['wrong_reports'] - comp['wrong_reports']), 'comparator': {k: mt.interval(v) for k, v in comp.items() if k != 'threshold'}, 'comparator_threshold': comp['threshold'][0]}
        bybase = {}
        for base in METHODS:
            eqw, eql = (selected[scan, base, 'wells'][-1], selected[scan, base, 'loop_loss'])
            bybase[base] = {'equal_wells': {'loss_difference': mt.interval(loop['loss'] - eqw['loss']), 'wrong_reports_difference': mt.interval(loop['wrong_reports'] - eqw['wrong_reports']), 'comparator': {k: mt.interval(v) for k, v in eqw.items() if k != 'threshold'}, 'comparator_threshold': eqw['threshold'][0]}, 'equal_loss': {'savings_fraction': mt.interval(1 - loop['wells'] / eql['wells']), 'wells_saved': mt.interval(eql['wells'] - loop['wells']), 'comparator': {k: mt.interval(v) for k, v in eql.items() if k != 'threshold'}, 'comparator_threshold': eql['threshold'][0]}}
        loop_result['variants']['seed0']['scans'][scan] = bybase
        subset = [r for r in loss_rows if r['scan'] == scan]
        sv['positive_savings_loss_grid_ranges'][scan] = {b: mt.ranges(subset, 'anchorboost_vs_' + b + '_savings_fraction') for b in METHODS[1:]}
    sv['at_loss_cap_8pct'] = [r for r in loss_rows if abs(r['loss_cap'] - 0.08) < 1e-12]
    summary['variants']['seed0'] = sv
    summary['dimensions'] = {'matched_loss_rows': len(loss_rows), 'matched_wells_rows': len(wells_rows), 'identities': ng, 'designs': len(rows), 'bootstrap_variants': 1, 'replicates_per_variant': 4000}
    summary['infeasible_grid_rows'] = [dict(bootstrap='seed0', scan=r['scan'], fraction=r['budget_fraction_full'], defined=r['anchorboost_loss_bootstrap_defined'], total=4000) for r in wells_rows if r['anchorboost_loss_bootstrap_defined'] < 4000]
    return (loss_rows, wells_rows, loop_result, summary)

def inputs():
    rows = decision_rows('B')
    groups, W = bootstrap()
    ix = np.array([groups.index(r['drug_group']) for r in rows])
    n = np.bincount(ix).astype(float)
    D = math.lcm(100, *[r[m + '_exact'][1] for r in rows for m in METHODS])
    lambdas = load(FINAL / 'reporting/three_point_lambdas.json')['B']
    cal = {f: {m: dict(margin=lambdas[str(f)][m]['lambda']) for m in METHODS} for f in range(1,5)}
    joint = {r['drug_group']: r for r in rcsv(FINAL / 'loop/identity_totals.csv') if r['policy']=='model_disagreement'}
    return dict(p=load(FINAL/'reporting/protocol.json'),rows=rows,groups=groups,W=W,ix=ix,n=n,D=D,cal=cal,joint=joint,
        lane=np.array([r['measured_only']>=3 for r in rows]),
        full=np.array([r['wells_full'] for r in rows]),meas=np.array([r['wells_measured'] for r in rows]))

def run():
    for g in ['reporting','loop','frontier']:
        verify(g)
    data=inputs()
    cache={}
    for m in METHODS:
        for scan in SCANS:
            s=scores(data,m,scan)
            cache[m,scan]=(s,thresholds(data,s,scan),np.array([r[m+'_call']!=r['truth'] for r in data['rows']]))
    loss,wells,loop,summary=matched(data,cache)
    same(summary,load(FINAL/'frontier/summary.json'))
    same(loop,load(FINAL/'frontier/loop_vs_frontier.json'))
    # Every matched table row is reconstructed, including infeasible resamples.
    for values,name in [(loss,'matched_loss.csv'),(wells,'matched_wells.csv')]:
        saved=rcsv(FINAL/'frontier'/name)
        same(len(values),len(saved))
        for a,b in zip(values,saved):
            for k,v in a.items():
                if isinstance(v,(int,float)):
                    same(v,float(b[k]),name+'/'+k)
                elif v is not None:
                    same(v,b[k],name+'/'+k)
    return dict(summary=summary,loop=loop)

def entries(result):
    command='python paper_final_frontier.py summarize'
    out=numeric_entries(result['summary']['variants']['seed0']['anchor_operating_point_vs_frontier'],
        'frontier.anchor_budget', 'frontier','results/final/frontier/summary.json',command,
        '/variants/seed0/anchor_operating_point_vs_frontier')
    out+=numeric_entries(result['loop']['variants']['seed0'],'frontier.loop','frontier',
        'results/final/frontier/loop_vs_frontier.json',command,'/variants/seed0')
    for i,row in enumerate(result['summary']['variants']['seed0']['at_loss_cap_8pct']):
        for base in ['measured_only','loglinear']:
            key='anchorboost_vs_'+base+'_savings_fraction'
            out.append(dict(key='frontier.loss_cap_8pct.'+row['scan']+'.'+base+'.saving',
                value=row[key],ci95=[row[key+'_ci95_low'],row[key+'_ci95_high']],unit='fraction',group='frontier',
                source_file='results/final/frontier/summary.json',field='/variants/seed0/at_loss_cap_8pct/'+str(i)+'/'+key,
                ci95_fields=['/variants/seed0/at_loss_cap_8pct/'+str(i)+'/'+key+'_ci95_low',
                             '/variants/seed0/at_loss_cap_8pct/'+str(i)+'/'+key+'_ci95_high'],command=command))
    return out

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('command',choices=['summarize','verify'])
    ap.add_argument('--write',action='store_true')
    a=ap.parse_args()
    result=run()
    if a.write:
        write_json(FINAL/'frontier/recomputed.json',result)
        write_json(FINAL/'frontier/numbers.json',entries(result))
    print(json.dumps(result,indent=2))

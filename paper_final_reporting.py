"""Recompute the reporting table from saved decisions and frozen rank references."""
import sys
sys.dont_write_bytecode = True
from paper_final_common import *
import argparse
METHODS = ['anchorboost', 'measured_only', 'loglinear', 'observed_active_fallback']
ci = interval
def group_arrays(rows, groups):
    by = {g: [] for g in groups}
    for r in rows:
        by[r['drug_group']].append(r)
    out = {}
    for m in METHODS:
        rec = []
        for g in groups:
            part = by[g]
            rel = [r[m + '_release'] == 'True' for r in part]
            wrong = [r[m + '_call'] != r['truth'] for r in part]
            rec.append(dict(designs=len(part), reports=sum(rel), wrong_reports=sum((a and b for a, b in zip(rel, wrong))), full_coverage_errors=sum(wrong), wells_used=sum((int(r['wells_measured']) if a else int(r['wells_full']) for a, r in zip(rel, part))), wells_full=sum((int(r['wells_full']) for r in part))))
        arr = {k: np.array([x[k] for x in rec], float) for k in rec[0]}
        arr['release_rate'] = arr['reports'] / arr['designs']
        arr['drug_loss'] = arr['wrong_reports'] / arr['designs']
        arr['full_error_rate'] = arr['full_coverage_errors'] / arr['designs']
        out[m] = arr
    return out

def summarize(arr, W):
    n = len(next(iter(arr.values()))['designs'])
    methods = {}
    for m, v in arr.items():
        cell = {k: ci(v[k].sum(), W @ v[k]) for k in ['reports', 'wrong_reports', 'wells_used', 'wells_full', 'full_coverage_errors']}
        for k in ['release_rate', 'drug_loss', 'full_error_rate']:
            cell[k] = ci(v[k].mean(), W @ v[k] / n)
        cell['pooled_report_rate'] = ci(v['reports'].sum() / v['designs'].sum(), W @ v['reports'] / (W @ v['designs']))
        cell['conditional_error'] = ci(v['wrong_reports'].sum() / v['reports'].sum(), W @ v['wrong_reports'] / (W @ v['reports']))
        cell['savings_vs_full'] = ci(1 - v['wells_used'].sum() / v['wells_full'].sum(), 1 - W @ v['wells_used'] / (W @ v['wells_full']))
        methods[m] = cell
    paired = {}
    a = arr['anchorboost']
    for m in METHODS[1:]:
        c = arr[m]
        cell = {k: ci((a[k] - c[k]).mean(), W @ (a[k] - c[k]) / n) for k in ['release_rate', 'drug_loss', 'full_error_rate']}
        for k in ['reports', 'wrong_reports', 'wells_used', 'full_coverage_errors']:
            cell[k + '_count_difference'] = ci((a[k] - c[k]).sum(), W @ (a[k] - c[k]))
        cell['cost_savings'] = ci(1 - a['wells_used'].sum() / c['wells_used'].sum(), 1 - W @ a['wells_used'] / (W @ c['wells_used']))
        paired[m] = cell
    return (methods, paired)

def change(new, old, W):
    """Paired change of the AnchorBoost advantage, arm minus current manuscript, on the same identities."""
    n = len(new['anchorboost']['designs'])
    out = {}
    for m in ['measured_only', 'loglinear']:
        cell = {}
        for k in ['release_rate', 'drug_loss', 'full_error_rate']:
            d = new['anchorboost'][k] - new[m][k] - (old['anchorboost'][k] - old[m][k])
            cell[k + '_advantage_change'] = ci(d.mean(), W @ d / n)

        def saving(arr, w):
            return 1 - w @ arr['anchorboost']['wells_used'] / (w @ arr[m]['wells_used'])
        ones = np.ones(n)
        cell['cost_savings_change'] = ci(saving(new, ones) - saving(old, ones), saving(new, W) - saving(old, W))
        out[m] = cell
    for m in METHODS:
        out['counts_' + m] = {k: ci((new[m][k] - old[m][k]).sum(), W @ (new[m][k] - old[m][k])) for k in ['reports', 'wrong_reports', 'wells_used']}
    return out

def csv_types(rows):
    return [{k: str(v) for k, v in r.items()} for r in rows]

def recompute(lane=True):
    groups, W = bootstrap()
    out = {}
    for arm in ['B', 'A']:
        rows = decision_rows(arm, lane)
        arrays = group_arrays(csv_types(rows), groups)
        methods, paired = summarize(arrays, W)
        folds = {}
        for f in range(1, 5):
            rr = [r for r in rows if r['outer_fold'] == f]
            gg = sorted({r['drug_group'] for r in rr})
            aa = group_arrays(csv_types(rr), gg)
            folds[str(f)] = {m: float(v['drug_loss'].mean()) for m, v in aa.items()}
        out[arm] = dict(methods=methods, paired=paired, fold_loss=folds,
                       worst_fold_loss=max(x['anchorboost'] for x in folds.values()))
    return out

def run():
    verify('reporting')
    result = recompute()
    saved = load(FINAL / 'reporting/headline.json')
    for arm, values in result.items():
        same({k: values[k] for k in ['methods', 'paired']}, saved['arms'][arm])
        # Independent saved figure tables also preserve each public decision.
        rr = rcsv(FINAL / 'reporting' / arm / 'design_outcomes.csv')
        same(len(rr), 965)
        for m in METHODS[:3]:
            same(sum(int(x[m + '_report']) for x in rr), values['methods'][m]['reports']['estimate'])
            same(sum(int(x[m + '_wrong_report']) for x in rr), values['methods'][m]['wrong_reports']['estimate'])
            same(sum(int(x[m + '_wells']) for x in rr), values['methods'][m]['wells_used']['estimate'])
    return result

def entries(result):
    out = []
    command = 'python paper_final_reporting.py summarize'
    for arm, values in result.items():
        for part in ['methods', 'paired']:
            out += numeric_entries(values[part], 'reporting.' + arm + '.' + part, 'reporting',
                'results/final/reporting/headline.json', command, '/arms/' + arm + '/' + part)
        for part in ['fold_loss', 'worst_fold_loss']:
            out += numeric_entries(values[part], 'reporting.' + arm + '.' + part, 'reporting',
                'results/final/reporting/recomputed.json', command, '/' + arm + '/' + part)
    rows = rcsv(FINAL / 'reporting/B/design_outcomes.csv')
    population = dict(designs=len(rows), identity_groups=len({r['drug_group'] for r in rows}),
                      substances=len({r['chemical'] for r in rows}))
    for k, v in population.items():
        out.append(dict(key='reporting.' + k, value=v, unit='count', group='reporting',
            source_file='results/final/reporting/population.json', field='/' + k,
            command=command))
    return out

if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('command', choices=['summarize', 'verify'])
    ap.add_argument('--write', action='store_true', help='write recomputed numeric tables')
    args = ap.parse_args()
    result = run()
    if args.write:
        write_json(FINAL / 'reporting/recomputed.json', result)
        rows = rcsv(FINAL / 'reporting/B/design_outcomes.csv')
        write_json(FINAL / 'reporting/population.json', dict(designs=len(rows),
            identity_groups=len({r['drug_group'] for r in rows}), substances=len({r['chemical'] for r in rows})))
        write_json(FINAL / 'reporting/numbers.json', entries(result))
    print(json.dumps(result, indent=2))

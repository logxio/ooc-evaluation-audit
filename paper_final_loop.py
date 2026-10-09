"""Recompute closed-loop counts, costs and paired intervals from frozen decisions."""
import sys
sys.dont_write_bytecode = True
from paper_final_common import *
from collections import defaultdict
import argparse

def count_matrix(names):
    groups, W = bootstrap()
    if names != groups:
        raise AssertionError('Identity order differs from frozen bootstrap')
    return W
POLICIES = ['model_disagreement', 'highest_unmeasured', 'fixed_maximin', 'uniform_random']

CLASSICAL = ['gp_ivr', 'hill_var', 'gp_var']

RULES = POLICIES + CLASSICAL

BASELINES = ['nested_measured_only', 'nested_anchorboost']

METRICS = ['reports', 'wrong_reports', 'stage1_reports', 'stage2_reports', 'completed', 'wells_initial', 'wells_added', 'wells_completion', 'wells_used', 'wells_full']

def aggregate(rows, policies):
    by = defaultdict(list)
    for r in rows:
        by[r['drug_group'], r['policy']].append(r)
    groups = []
    for (group, policy), rr in sorted(by.items()):
        cell = dict(drug_group=group, outer_fold=rr[0]['outer_fold'], policy=policy, substances=len({r['chemical'] for r in rr}), designs=len(rr))
        for k in METRICS:
            cell[k] = sum((r[k] for r in rr))
        cell['report_rate'] = cell['reports'] / len(rr)
        cell['wrong_report_loss'] = cell['wrong_reports'] / len(rr)
        groups.append(cell)
    summary = {}
    for policy in policies:
        gg = [g for g in groups if g['policy'] == policy]
        x = {k: sum((g[k] for g in gg)) for k in METRICS}
        x['designs'] = sum((g['designs'] for g in gg))
        x['identity_groups'] = len(gg)
        x['group_mean_report_rate'] = float(np.mean([g['report_rate'] for g in gg]))
        x['group_mean_wrong_report_loss'] = float(np.mean([g['wrong_report_loss'] for g in gg]))
        x['error_among_reports'] = x['wrong_reports'] / x['reports'] if x['reports'] else None
        x['savings_vs_full'] = 1 - x['wells_used'] / x['wells_full']
        summary[policy] = x
    return (groups, summary)

def bootstraps(groups):
    names = sorted({r['drug_group'] for r in groups})
    W = count_matrix(names)
    n = len(names)
    lookup = {(r['drug_group'], r['policy']): r for r in groups}
    keys = ['reports', 'wrong_reports', 'report_rate', 'wrong_report_loss', 'wells_used']
    vals = {p: np.array([[lookup[g, p][k] for k in keys] for g in names], dtype=float) for p in RULES + BASELINES}

    def cell(point, arr):
        return {'estimate': float(point), 'ci95': np.quantile(arr, [0.025, 0.975]).tolist()}
    pairs = [(p, b) for p in POLICIES for b in BASELINES] + [(p, b) for i, p in enumerate(POLICIES) for b in POLICIES[i + 1:]]
    pairs += [(c, 'model_disagreement') for c in CLASSICAL] + [(c, b) for c in CLASSICAL for b in BASELINES]
    contrasts = {}
    for p, b in pairs:
        d = vals[p] - vals[b]
        out = {}
        for j, k in enumerate(keys):
            out[k + '_identity_mean_difference'] = cell(d[:, j].mean(), W @ d[:, j] / n)
            if k in ['reports', 'wrong_reports', 'wells_used']:
                out[k + '_total_difference'] = cell(d[:, j].sum(), W @ d[:, j])
        wp, wb = (vals[p][:, -1], vals[b][:, -1])
        out['relative_well_saving'] = cell(1 - wp.sum() / wb.sum(), 1 - W @ wp / (W @ wb))
        contrasts[p + '__minus__' + b] = out
    intervals = {p: {'group_wrong_report_loss': cell(v[:, 3].mean(), W @ v[:, 3] / n), 'group_report_rate': cell(v[:, 2].mean(), W @ v[:, 2] / n), 'reports': cell(v[:, 0].sum(), W @ v[:, 0]), 'wrong_reports': cell(v[:, 1].sum(), W @ v[:, 1]), 'wells_used': cell(v[:, 4].sum(), W @ v[:, 4])} for p, v in vals.items()}
    return (contrasts, intervals)

def typed(rows):
    return [{k: (float(v) if k in METRICS or k in ['weight', 'call3', 'call4', 'truth', 'outer_fold'] else v)
             for k, v in r.items()} for r in rows]

def run():
    verify('reporting')
    verify('loop')
    rows = typed(rcsv(FINAL / 'loop/design_decisions.csv'))
    groups, methods = aggregate(rows, RULES + BASELINES)
    contrasts, intervals = bootstraps(groups)
    result = dict(methods=methods, paired_contrasts=contrasts, identity_bootstrap_intervals=intervals)
    saved = load(FINAL / 'loop/summary.json')
    same(result, saved)
    same(frozen_sha(FINAL / 'reporting/protocol.json'), saved['protocol_sha256'])
    branch = typed(rcsv(FINAL / 'loop/branch_decisions.csv'))
    # Rebuild the published design totals from selected or weighted saved branches.
    by = defaultdict(list)
    for r in branch:
        by[r['policy'], r['chemical'], r['design']].append(r)
    for r in rows:
        if r['policy'] not in RULES:
            continue
        bs = by[r['policy'], r['chemical'], r['design']]
        same(sum(x['weight'] for x in bs), 1)
        for k in METRICS:
            same(sum(x['weight'] * x[k] for x in bs), r[k], k)
    transition = {}
    for p in RULES:
        bs = [r for r in branch if r['policy'] == p and not r['stage1_reports']]
        val = lambda predicate: sum(r['weight'] for r in bs if predicate(r))
        transition[p] = dict(
            continued=val(lambda r: True),
            wrong_to_right=val(lambda r: r['call3'] != r['truth'] and r['call4'] == r['truth']),
            right_to_wrong=val(lambda r: r['call3'] == r['truth'] and r['call4'] != r['truth']),
            right_to_wrong_completed=val(lambda r: r['call3'] == r['truth'] and r['call4'] != r['truth'] and r['completed']),
            stage2_reports=val(lambda r: r['stage2_reports']),
            stage2_wrong=val(lambda r: r['stage2_reports'] and r['wrong_reports']))
    result['transitions'] = transition
    return result

def entries(result):
    out=[]
    cmd='python paper_final_loop.py summarize'
    for part in ['methods','paired_contrasts','identity_bootstrap_intervals']:
        out += numeric_entries(result[part], 'loop.'+part, 'loop', 'results/final/loop/summary.json', cmd, '/'+part)
    out += numeric_entries(result['transitions'], 'loop.transitions', 'loop',
                           'results/final/loop/recomputed.json', cmd, '/transitions')
    return out

if __name__ == '__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('command', choices=['summarize','verify'])
    ap.add_argument('--write',action='store_true')
    args=ap.parse_args()
    result=run()
    if args.write:
        write_json(FINAL/'loop/recomputed.json',result)
        write_json(FINAL/'loop/numbers.json',entries(result))
    print(json.dumps(result,indent=2))

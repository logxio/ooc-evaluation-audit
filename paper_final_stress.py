#!/usr/bin/env python3
"""Aggregate the saved stress ladder; no predictions, noise, or calibration reruns."""
import sys
sys.dont_write_bytecode = True
import argparse
import json
from statistics import median
from paper_final_heldout import verify, load, csv_rows, compare, numbers_for

def summarize():
    base, manifest = verify('stress')
    ladder = csv_rows(base / 'three_point/ladder.csv')
    curve = csv_rows(base / 'three_point/curve.csv')
    checked = 0
    for row in ladder:
        if row['population'] != 'pooled_primary':
            continue
        fold = [r for r in ladder if r['population'] == 'primary' and all(r[k] == row[k] for k in ('ladder','level','seed'))]
        for key in ('reports','wrong','fn','fp','wells_used','wells_full','designs','groups'):
            compare(sum(float(r[key]) for r in fold), float(row[key]), 'three_point/' + key)
        for key in ('wrong_loss','report_rate','fn_loss','fp_loss'):
            compare(sum(float(r[key])*float(r['groups']) for r in fold)/float(row['groups']), float(row[key]), 'three_point/' + key)
        compare(float(row['wrong']) / float(row['reports']), float(row['error_among_reports']))
        checked += 1
    for row in curve:
        selected = [r for r in ladder if r['population'] == 'pooled_primary' and r['ladder'] == row['ladder'] and r['level'] == row['x']]
        key = row['readout']
        if selected and key in selected[0] and all(r[key] for r in selected):
            values = [float(r[key]) for r in selected]
            compare(median(values),float(row['median']), 'curve/' + key)
            compare(min(values),float(row['seed_min']), 'curve/min/' + key)
            compare(max(values),float(row['seed_max']), 'curve/max/' + key)
    noise = [r for r in curve if r['ladder'] == 'noise']
    levels = sorted({float(r['x']) for r in noise})
    table = {}
    for level in levels:
        table[str(level)] = {r['readout']:float(r['median']) for r in noise if float(r['x']) == level}
    headline = {'wells_share_zero_noise':table['0.0']['wells_ratio'], 'wells_share_max_noise':table['8.0']['wells_ratio'], 'largest_noise_level_median_wrong_loss':max(v['wrong_loss'] for v in table.values()), 'largest_noise_level_median_error_among_reports':max(v['error_among_reports'] for v in table.values())}
    compare(headline, load(base / 'headline.json')['values'], 'headline')
    source = load(base / 'three_point/summary.json')
    compare(headline['wells_share_zero_noise'],source['reading']['sentence_1']['wells_ratio_median_by_s']['0'])
    compare(headline['wells_share_max_noise'],source['reading']['sentence_1']['wells_ratio_s8']['median'])
    joint = csv_rows(base / 'joint/ladder.csv')
    joint_checked = 0
    for row in joint:
        if row['population'] != 'pooled':
            continue
        fold = [r for r in joint if r['population'] == 'fold' and all(r[k] == row[k] for k in ('arm','rule','variant','policy','s','seed'))]
        if not fold:
            continue
        for key in ('reports','wrong','fn','fp','wells_used','wells_full','designs','groups'):
            compare(sum(float(r[key]) for r in fold),float(row[key]),'joint/' + key)
        for key in ('wrong_loss','report_rate'):
            compare(sum(float(r[key])*float(r['groups']) for r in fold)/float(row['groups']),float(row[key]),'joint/' + key)
        joint_checked += 1
    entries = numbers_for('stress')
    return {'group':'stress','input_files_verified':len(manifest['sha256']),'number_entries_verified':len(entries),'three_point_pooled_rungs_recomputed':checked,'joint_pooled_rungs_recomputed':joint_checked,'headline':headline,'noise_level_medians':table,'confidence_intervals':'Saved identity-bootstrap intervals are hash verified; per-identity noisy decisions were not exported, so this command recomputes fold pooling and seed medians, not their confidence intervals.','monotone_wells':source['reading']['sentence_1']['monotone_non_decreasing'],'decreasing_steps':source['reading']['sentence_1']['decreases']}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['summarize','verify'])
    parser.add_argument('--numbers',action='store_true')
    args = parser.parse_args()
    result = summarize()
    print(json.dumps(numbers_for('stress') if args.numbers else result,indent=2,allow_nan=False))
if __name__ == '__main__':
    main()

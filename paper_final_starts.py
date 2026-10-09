#!/usr/bin/env python3
"""Recompute start stratification, selected starts, and all 35-start ceiling tables."""
import sys
sys.dont_write_bytecode = True
import argparse
import json
from paper_final_heldout import verify, module, load, compare, numbers_for

def summarize():
    base, manifest = verify('starts')
    statistics = module(base / 'statistics.py')
    source = load(base / 'summary.json')
    recommendation = load(base / 'recommended.json')
    rows = [r for fold in range(1, 5) for r in load(base / f'fold{fold}/test_scored.json.gz')]
    random = [r for r in rows if r['arm'] == 'random']
    q1, table = statistics.q1_block(random, [])
    compare(q1['population'], source['q1']['population'], 'q1/population')
    compare(q1['three_point'], source['q1']['three_point'], 'q1/three_point')
    seven = [r for r in rows if r['arm'] == 'family' and r['n_levels'] == 7]
    ceiling = statistics.ceiling(seven, 'single|seven|{m}')
    compare(ceiling, source['ceiling'], 'ceiling')
    boot = statistics.Boot({r['drug_group'] for r in seven})
    recommended = {}
    for method in statistics.METHODS:
        chosen = {fold: recommendation['by_fold'][str(fold)]['seven'][method]['recommended']['design'] for fold in range(1, 5)}
        selected = [r for r in seven if r['design'] == chosen[r['outer_fold']]]
        values = statistics.three_point(boot, selected, method, [r['release']['single|seven|' + method] for r in selected])
        cell = statistics.cell_summary(boot, values)
        compare(cell, source['q2']['cells']['seven']['recommended|' + method], 'recommended/' + method)
        recommended[method] = cell
    entries = numbers_for('starts')
    return {'group':'starts', 'input_files_verified':len(manifest['sha256']), 'number_entries_verified':len(entries), 'frozen_scored_rows':len(rows), 'bootstrap_replicates':4000, 'three_point_stratification':q1['three_point'], 'recommended_seven_concentration':recommended, 'ceiling_rank_classes':ceiling['rank_classes'], 'ceiling_pooled':ceiling['pooled'], 'additional_saved_statistics':'Additional cell and asymmetric results are retained with source hashes; only the explicitly listed tables are recomputed in this command.'}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['summarize', 'verify'])
    parser.add_argument('--numbers', action='store_true')
    args = parser.parse_args()
    result = summarize()
    print(json.dumps(numbers_for('starts') if args.numbers else result, indent=2, allow_nan=False))
if __name__ == '__main__':
    main()

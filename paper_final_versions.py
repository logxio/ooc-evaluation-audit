"""Compare the original, common-scale, and observed-active reporting definitions."""
import sys
sys.dont_write_bytecode = True
from paper_final_common import *
from paper_final_reporting import group_arrays, summarize, recompute
import argparse

def run():
    verify('reporting')
    verify('versions')
    groups, W = bootstrap()
    rows = [r for r in rcsv(FINAL / 'versions/original_design_decisions.csv') if r['outer_fold'] in ['1','2','3','4']]
    old_methods, old_pairs = summarize(group_arrays(rows, groups), W)
    old = dict(methods=old_methods, paired=old_pairs)
    no_lane = recompute(lane=False)['B']
    lane = recompute(lane=True)['B']
    saved = load(FINAL / 'versions/headline.json')
    same(old, saved['current_manuscript'])
    same({k:no_lane[k] for k in ['methods','paired']}, saved['arms']['B'])
    same({k:lane[k] for k in ['methods','paired']}, load(FINAL/'reporting/headline.json')['arms']['B'])
    result = {}
    for name, block in [('original',old),('common_scale_without_direct_reporting',no_lane),('common_scale_with_direct_reporting',lane)]:
        result[name] = dict(anchorboost_reports=block['methods']['anchorboost']['reports'],
            measured_only_reports=block['methods']['measured_only']['reports'],
            anchorboost_wrong=block['methods']['anchorboost']['wrong_reports'],
            measured_only_wrong=block['methods']['measured_only']['wrong_reports'],
            anchorboost_wells=block['methods']['anchorboost']['wells_used'],
            measured_only_wells=block['methods']['measured_only']['wells_used'],
            well_saving=block['paired']['measured_only']['cost_savings'])
    return result

def entries(result):
    return numeric_entries(result,'versions','versions','results/final/versions/recomputed.json',
                           'python paper_final_versions.py summarize')

if __name__ == '__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('command',choices=['summarize','verify'])
    ap.add_argument('--write',action='store_true')
    a=ap.parse_args()
    result=run()
    if a.write:
        write_json(FINAL/'versions/recomputed.json',result)
        write_json(FINAL/'versions/numbers.json',entries(result))
    print(json.dumps(result,indent=2))

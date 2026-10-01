#!/usr/bin/env python3
"""One declared calibration-budget sensitivity; outcomes were previously seen."""
import argparse
import hashlib
import json
import tempfile
from pathlib import Path
import calibration_replay as replay


def expanded(name, rows):
    ranked = sorted(rows, key=lambda r: hashlib.sha256((replay.SEED + '|' + name + '|' + r['patient']).encode()).hexdigest())
    n = len(rows)
    train, cal = n//5, 3*n//5
    return ranked[:train], ranked[train:train+cal], ranked[train+cal:]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--third-xlsx',type=Path)
    p.add_argument('--out',type=Path,default=Path('calibration_budget.json'))
    a=p.parse_args()
    replay.split=expanded
    with tempfile.TemporaryDirectory() as tmp:
        result={name:replay.run_source(name,rows,Path(tmp)/name) for name,rows in replay.sources(a.third_xlsx).items()}
    payload={'status':'retrospective sensitivity, not a replacement for the primary split',
             'split':'floor(n/5) training, floor(3n/5) calibration, remainder test; same hash seed',
             'pooling':'sources are kept separate because pooled mixture control would not guarantee each source',
             'sources':result}
    a.out.write_text(json.dumps(payload,indent=2)+'\n')
    print(json.dumps({k:{'split':s['split'],'levels':[{'alpha':v['alpha'],**v['test']} for v in s['levels']]} for k,s in result.items()},indent=2))


if __name__=='__main__':main()

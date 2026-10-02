"""Deterministic evidence retrieval for a small, free local model."""
import argparse
import json
from pathlib import Path
import re

WORDS = re.compile(r'\b(clinical|patient|response|accuracy|sensitivity|specificity|auc|cutoff|threshold|youden|validation|training|recist|outcome|pfs|trg)\b', re.I)


def compact(documents, limit=24000):
    paragraphs = [line for doc in documents for line in doc['narrative'] if not line.startswith('article:title')]
    ranked = sorted(enumerate(paragraphs), key=lambda item:(-len(WORDS.findall(item[1])),item[0]))
    narrative = []
    used = 0
    for _, line in ranked:
        if used + len(line) <= limit * .65:
            narrative.append(line)
            used += len(line)
    groups = {}
    for doc in documents:
        for ref, value in doc['cells'].items():
            groups.setdefault(ref.rsplit('/',1)[0], {})[ref] = value
    scored = sorted(groups.items(), key=lambda item:(-sum(len(WORDS.findall(str(v))) for v in item[1].values()) / max(1,len(item[1])**.5),item[0]))
    cells = {}
    for _, values in scored:
        for ref, value in values.items():
            size = len(ref)+len(str(value))+5
            if used+size <= limit:
                cells[ref]=value
                used+=size
    result={'name':'retrieved', 'sha256':None,'narrative':narrative,'cells':cells,'license_text':'See paper provenance.'}
    return [result]


def main():
    from .ingest import render
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('sources', type=Path)
    p.add_argument('output', type=Path)
    args=p.parse_args()
    for path in args.sources.glob('*/documents.json'):
        selected=compact(json.loads(path.read_text()))
        folder=args.output/path.parent.name
        folder.mkdir(parents=True,exist_ok=True)
        # Keep the full source index for replay, but send only retrieved context.
        (folder/'documents.json').write_bytes(path.read_bytes())
        (folder/'input.txt').write_text('\n\n'.join(render(d) for d in selected))


if __name__=='__main__': main()

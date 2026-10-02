"""Download the cited originals locally and reproduce the evidence index."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request
from zipfile import ZipFile

from .ingest import normalize, render

HERE=Path(__file__).resolve().parent


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',required=True,type=Path)
    parser.add_argument('--papers',nargs='+')
    args=parser.parse_args()
    names=args.papers or json.loads((HERE/'manifest.json').read_text())['papers']
    for name in names:
        provenance=json.loads((HERE/'data'/name/'provenance.json').read_text())
        folder=args.out/name;folder.mkdir(parents=True,exist_ok=True)
        documents=[]
        for source in provenance['sources']:
            path=folder/source['file']
            if not path.exists():
                request=urllib.request.Request(source['url'],headers={'User-Agent':'Contract-research/1.0'})
                with urllib.request.urlopen(request,timeout=90) as response:
                    path.write_bytes(response.read())
            actual=hashlib.sha256(path.read_bytes()).hexdigest()
            if actual!=source['sha256']:
                raise ValueError(f'Original changed: {name}/{path.name}: expected {source["sha256"]}; got {actual}')
            if path.suffix=='.zip':
                with ZipFile(path) as archive:
                    # This source-data workbook is the one used in the pilot.
                    output=folder/'supp.xlsx'
                    output.write_bytes(archive.read('Source data/Source data figure 5.xlsx'))
                documents.append(normalize(output,'supp'))
            else:
                documents.append(normalize(path,path.stem))
        (folder/'documents.json').write_text(json.dumps(documents,ensure_ascii=False,indent=2)+'\n')
        (folder/'input.txt').write_text('\n\n'.join(render(d) for d in documents))
        print(json.dumps({'paper':name,'source_files':len(provenance['sources'])}))


if __name__=='__main__':main()

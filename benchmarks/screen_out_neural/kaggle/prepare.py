#!/usr/bin/env python3
"""Prepare a public CPU reproduction notebook for an immutable public Git commit."""
import argparse
import hashlib
import json
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPOSITORY = 'logxio/ooc-evaluation-audit'
DIRECTORY = 'benchmarks/screen_out_neural'
KERNEL = 'loxigicck/screen-out-neural-cpu-reproduction'

INTRO = '''# Shared design-conditioned neural transfer: CPU reproduction

This notebook downloads the public benchmark archive at a fixed Git commit,
verifies SHA-256 hashes, and recomputes all 26 main-table rows and paired chemical
confidence intervals from 271,766 exported prediction cells. It uses CPU only.
Frozen AnchorBoost and published neural-process per-chemical errors supply the
reference comparisons. Full training inputs and all 11 checkpoints are downloaded
from the same public repository; execution consists of aggregation.

Screen-out excludes the whole test screen and chemical aliases from training.
Within-screen uses the original fold-1 tests for NFA/acute/Harrill and six Ewart
leave-one-drug-out fits. The reference models use within-screen training.
Published neural-process comparisons cover NFA. Ewart endpoints retain separate
author units. All negative results are included.

Code and the attributed NeuroChip Twin comparator are MIT; Ewart data are CC BY 4.0.
The downloaded SOURCES.md documents EPA source access and dataset-license scope.
The original private training notebook remains experimental provenance:
https://www.kaggle.com/code/loxigicck/shared-design-screen-transfer-s1-1004
'''

DOWNLOAD = '''from pathlib import Path, PurePosixPath
from concurrent.futures import ThreadPoolExecutor
import hashlib, json, os, re, resource, sys, time, urllib.request

started = time.perf_counter()
if not isinstance(SOURCE_COMMIT, str) or not re.fullmatch(r"[0-9a-f]{40}", SOURCE_COMMIT):
    raise ValueError("Prepare this notebook with a complete public Git commit first.")
if not isinstance(MANIFEST_SHA256, str) or not re.fullmatch(r"[0-9a-f]{64}", MANIFEST_SHA256):
    raise ValueError("The source manifest SHA-256 must be pinned before execution.")
base = f"https://raw.githubusercontent.com/{REPOSITORY}/{SOURCE_COMMIT}/{DIRECTORY}/"
bundle = Path.cwd() / "screen_out_neural"
bundle.mkdir(exist_ok=True)
with urllib.request.urlopen(base + "checksums.json", timeout=60) as response:
    manifest_bytes = response.read(1_000_001)
if len(manifest_bytes) > 1_000_000:
    raise ValueError("Source manifest exceeds the expected size.")
if hashlib.sha256(manifest_bytes).hexdigest() != MANIFEST_SHA256:
    raise ValueError("Source manifest SHA-256 mismatch.")
manifest = json.loads(manifest_bytes)
required = {"aggregate.py", "predictions.csv.gz", "comparator_errors.csv", "published_np.csv",
            "drug_results.json", "summary.json", "tasks.npz", "tasks.json", "identities.json",
            "protocol.json", "run_experiment.py", "SOURCES.md", "LICENSE"}
if not required.issubset(manifest):
    raise ValueError("The public archive is missing required reproduction inputs.")
if len([n for n in manifest if n.startswith("models/") and n.endswith(".pt")]) != 11:
    raise ValueError("Expected all 11 frozen model checkpoints.")
for name, expected in manifest.items():
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\\\" in name or not path.parts:
        raise ValueError("Invalid relative archive path.")
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ValueError("Invalid file digest.")

def download(item):
    name, expected = item
    target = bundle / name
    target.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    count = 0
    with urllib.request.urlopen(base + name, timeout=60) as response, target.open("wb") as output:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            count += len(chunk)
            if count > 64 * 1024 * 1024:
                raise ValueError("Source file exceeds the expected size: " + name)
            digest.update(chunk)
            output.write(chunk)
    if digest.hexdigest() != expected:
        raise ValueError("Source SHA-256 mismatch: " + name)
    return count

with ThreadPoolExecutor(max_workers=4) as pool:
    file_bytes = list(pool.map(download, sorted(manifest.items())))
(bundle / "checksums.json").write_bytes(manifest_bytes)
download_report = dict(source_commit=SOURCE_COMMIT, source_repository=REPOSITORY,
    manifest_sha256=MANIFEST_SHA256, verified_files=len(file_bytes),
    downloaded_bytes=sum(file_bytes) + len(manifest_bytes), seconds=time.perf_counter() - started)
print(json.dumps(download_report, indent=2))
'''

AGGREGATE = '''import subprocess
os.environ["CUDA_VISIBLE_DEVICES"] = ""
output = Path.cwd() / "recomputed"
subprocess.run([sys.executable, str(bundle / "aggregate.py"), "--out", str(output)], check=True)
report = json.loads((output / "resources.json").read_text())
assert report["status"] == "passed"
assert report["prediction_cells"] == 271766
assert report["drug_endpoint_rows"] == 326 and report["main_table_rows"] == 26
assert report["max_main_table_difference"] <= 2e-6
assert report["max_drug_error_difference"] <= 2e-6
rss_factor = 1 if sys.platform == "darwin" else 1024
notebook_peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * rss_factor
assert notebook_peak <= 4_000_000_000 and report["peak_rss_bytes"] <= 4_000_000_000
receipt = dict(status="complete", execution="CPU aggregation", retraining=False,
    notebook_url="https://www.kaggle.com/code/loxigicck/screen-out-neural-cpu-reproduction",
    source=download_report, aggregate=report, elapsed_seconds=time.perf_counter()-started,
    notebook_peak_rss_bytes=notebook_peak, gpu_used=False, paid_usd=0)
(output / "reproduction_receipt.json").write_text(json.dumps(receipt, indent=2) + "\\n")
print((output / "main_table.md").read_text())
print(json.dumps(receipt, indent=2))
'''


def cell(kind, text, identifier):
    result = dict(cell_type=kind, id=identifier, metadata={}, source=text.splitlines(keepends=True))
    if kind == 'code':
        result.update(execution_count=None, outputs=[])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commit', help='40-character commit already accessible on public GitHub')
    args = parser.parse_args()
    manifest_sha = None
    if args.commit:
        if not re.fullmatch(r'[0-9a-f]{40}', args.commit):
            parser.error('--commit requires a full lowercase Git commit')
        url = f'https://raw.githubusercontent.com/{REPOSITORY}/{args.commit}/{DIRECTORY}/checksums.json'
        with urllib.request.urlopen(url, timeout=60) as response:
            content = response.read(1_000_001)
        if len(content) > 1_000_000:
            raise ValueError('Manifest exceeds the expected size')
        manifest = json.loads(content)
        assert 'aggregate.py' in manifest and 'predictions.csv.gz' in manifest
        manifest_sha = hashlib.sha256(content).hexdigest()
    config = f'REPOSITORY = {REPOSITORY!r}\nDIRECTORY = {DIRECTORY!r}\nSOURCE_COMMIT = {args.commit!r}\nMANIFEST_SHA256 = {manifest_sha!r}\n'
    notebook = dict(nbformat=4, nbformat_minor=5,
        metadata=dict(kernelspec=dict(name='python3', display_name='Python 3', language='python'),
                      language_info=dict(name='python')),
        cells=[cell('markdown', INTRO, 'scope'), cell('code', config, 'source'),
               cell('code', DOWNLOAD, 'download'), cell('code', AGGREGATE, 'aggregate')])
    metadata = dict(id=KERNEL, title='Screen Out Neural CPU Reproduction',
        code_file='cpu_reproduction.ipynb', language='python', kernel_type='notebook',
        is_private=False, enable_gpu=False, enable_tpu=False, enable_internet=True, dataset_sources=[],
        competition_sources=[], kernel_sources=[], model_sources=[])
    for name, value in [('cpu_reproduction.ipynb', notebook), ('kernel-metadata.json', metadata)]:
        (ROOT / name).write_text(json.dumps(value, indent=2) + '\n')
    print(json.dumps(dict(status='prepared' if args.commit else 'awaiting_public_commit',
        source_commit=args.commit, manifest_sha256=manifest_sha, kernel_id=KERNEL)))


if __name__ == '__main__':
    main()

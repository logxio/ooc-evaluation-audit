#!/usr/bin/env python3
"""Execute the public notebook against local copies of the public input files."""
import contextlib
import hashlib
import io
import json
import os
import resource
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    started = time.perf_counter()
    notebook = json.loads((ROOT / 'kaggle/cpu_reproduction.ipynb').read_text())
    metadata = json.loads((ROOT / 'kaggle/kernel-metadata.json').read_text())
    assert metadata['is_private'] is False and metadata['enable_gpu'] is False
    assert metadata['enable_internet'] is True
    assert metadata['dataset_sources'] == metadata['kernel_sources'] == metadata['model_sources'] == []
    namespace = {}
    code = {c['id']: ''.join(c['source']) for c in notebook['cells'] if c['cell_type'] == 'code'}
    for name, value in code.items():
        compile(value, name, 'exec')
    exec(code['source'], namespace)
    # The fixture tests the download and hash-check code without claiming public accessibility.
    namespace['SOURCE_COMMIT'] = '0' * 40
    namespace['MANIFEST_SHA256'] = hashlib.sha256((ROOT / 'checksums.json').read_bytes()).hexdigest()
    prefix = f"https://raw.githubusercontent.com/{namespace['REPOSITORY']}/{namespace['SOURCE_COMMIT']}/{namespace['DIRECTORY']}/"
    requested = set()

    def fixture_open(url, timeout=60):
        assert url.startswith(prefix), url
        name = url[len(prefix):]
        assert not name.startswith('/') and '..' not in Path(name).parts
        requested.add(name)
        return (ROOT / name).open('rb')

    original_open = urllib.request.urlopen
    original_cwd = Path.cwd()
    try:
        urllib.request.urlopen = fixture_open
        with tempfile.TemporaryDirectory(prefix='.notebook-check-', dir=ROOT) as folder:
            os.chdir(folder)
            with contextlib.redirect_stdout(io.StringIO()):
                exec(code['download'], namespace)
                exec(code['aggregate'], namespace)
            result = namespace['report']
            assert len(requested) == len(json.loads((ROOT / 'checksums.json').read_text())) + 1
    finally:
        urllib.request.urlopen = original_open
        os.chdir(original_cwd)
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == 'darwin' else 1024)
    report = dict(status='passed',mode='local-file fixture; public GitHub and Kaggle pending',
        notebook_cells_executed=len(code),verified_download_requests=len(requested),
        seconds=time.perf_counter()-started,notebook_peak_rss_bytes=rss,aggregate=result,
        cpu_only=True,retraining=False,private_data_dependencies=[],
        scientific_scope='Fixed 26 comparisons, 326 drug-endpoint rows, same paired intervals and negative results')
    output = ROOT / 'validation/kaggle_preparation.json'
    output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report),flush=True)


if __name__ == '__main__':
    main()

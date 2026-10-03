"""Fetch the two public, checksum-pinned reference files into ledger/.cache/."""
import hashlib
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = 'https://raw.githubusercontent.com/Agnuxo1/neurochip-twin/f9848800dfab66a8bc005e6b3087153eeaabe9ac/'
FILES = {
    'data_bundle/nfa_tasks.npz': 'e1f056ef33f568052fb8dfdba6e095f7b575c7f78d96768e34469918559008d2',
    'results/trajectory_cv_per_chemical.csv': '0d013127aef781ca5e1de04088532e2e19223364173a198e0686941c04f93abc',
}


def ensure_sources():
    cache = Path(__file__).resolve().parent / '.cache'
    cache.mkdir(exist_ok=True)
    for name, expected in FILES.items():
        path = cache / Path(name).name
        if not path.exists():
            try:
                with urllib.request.urlopen(BASE + name, timeout=30) as response:
                    data = response.read(16 * 1024 * 1024 + 1)
            except urllib.error.HTTPError as exc:
                if exc.code in (408, 429, 500, 502, 503, 504):
                    print(str(exc), file=sys.stderr)
                    raise SystemExit(75) from exc
                raise
            except (urllib.error.URLError, TimeoutError) as exc:
                print(str(exc), file=sys.stderr)
                raise SystemExit(75) from exc
            if hashlib.sha256(data).hexdigest() != expected:
                raise ValueError(f'{name}: downloaded source checksum differs')
            path.write_bytes(data)
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f'{name}: cached source checksum differs')


if __name__ == '__main__':
    ensure_sources()

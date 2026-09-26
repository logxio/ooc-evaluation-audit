#!/usr/bin/env python3
"""Create a private Kaggle CPU job from the single public baseline source.

The generated payload lives in .cache and is never part of the public repo.
"""
from pathlib import Path
import argparse
import json

ROOT = Path(__file__).resolve().parent
JOB = ROOT / ".cache" / "kaggle_f1"
SOURCE = ROOT / "ooc_qc.py"
TAIL = 'if __name__ == "__main__":\n    main()'
RUNNER = '''
from argparse import Namespace as _Namespace
from contextlib import redirect_stdout as _redirect_stdout
from io import StringIO as _StringIO

print("F1 image baseline: source", DATASET_URL, flush=True)
CACHE = Path("/kaggle/working/.cache")
_table = CACHE / "OOC_datasheet.xlsx"
_zip = CACHE / "OOC_image_dataset.zip"
_features = CACHE / "image_features.jsonl"
read_table(_table)
_retry = 0
while not _zip.exists() or _zip.stat().st_size < IMAGE_SIZE:
    _before = _zip.stat().st_size if _zip.exists() else 0
    try:
        command_download_images(_Namespace(zip=_zip, seconds=200))
        _after = _zip.stat().st_size
        _retry = 0 if _after > _before else _retry + 1
    except Exception as exc:
        _retry += 1
        print("download retry", _retry, repr(exc), flush=True)
    if _retry >= 8:
        raise RuntimeError("Zenodo download did not make progress after 8 attempts")
command_verify_images(_Namespace(zip=_zip))
while len(read_feature_cache(_features)) < 3072:
    command_extract_images(_Namespace(table=_table, zip=_zip, features=_features, count=256))
_buffer = _StringIO()
with _redirect_stdout(_buffer):
    command_metadata(_Namespace(table=_table))
Path("/kaggle/working/f1_metadata_result.json").write_text(_buffer.getvalue())
_buffer = _StringIO()
with _redirect_stdout(_buffer):
    command_image_evaluate(_Namespace(table=_table, features=_features))
Path("/kaggle/working/f1_image_result.json").write_text(_buffer.getvalue())
print("F1_IMAGE_RESULT_START")
print(_buffer.getvalue())
print("F1_IMAGE_RESULT_END")
'''


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner", required=True, help="your Kaggle username")
    args = parser.parse_args()
    source = SOURCE.read_text()
    if not source.rstrip().endswith(TAIL):
        raise RuntimeError("baseline entry point changed; inspect generator")
    payload = source.rsplit(TAIL, 1)[0] + RUNNER
    JOB.mkdir(parents=True, exist_ok=True)
    (JOB / "ooc_f1.py").write_text(payload)
    metadata = {
        "id": f"{args.owner}/ooc-quality-f1-private",
        "title": "OoC Quality F1 Private",
        "code_file": "ooc_f1.py",
        "language": "python",
        "kernel_type": "script",
        "is_private": "true",
        "enable_gpu": "false",
        "enable_internet": "true",
        "dataset_sources": [],
        "competition_sources": [],
        "kernel_sources": [],
        "model_sources": [],
    }
    (JOB / "kernel-metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(JOB)


if __name__ == "__main__":
    main()

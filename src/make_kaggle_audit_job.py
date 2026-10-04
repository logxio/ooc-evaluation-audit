#!/usr/bin/env python3
"""Package a private, clean Kaggle CPU verification of the public audit command."""
from __future__ import annotations

import argparse
import base64
from io import BytesIO
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
JOB = ROOT / ".cache" / "kaggle_f9"
SOURCES = ("run_full_audit.py", "ooc_qc.py", "f2_rf.py", "source_split_audit.py",
           "f4_paired.py", "audit_report.py", "evaluation_audit.py",
           "frozen_reference.json", "requirements.txt")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner", required=True, help="your Kaggle username")
    args = parser.parse_args()
    archive = BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for name in SOURCES:
            bundle.write(ROOT / name, name)
    payload = base64.b85encode(archive.getvalue()).decode("ascii")
    runner = f'''#!/usr/bin/env python3
"""Private clean-run verifier; generated from the public repository."""
import base64
from pathlib import Path
import subprocess
import sys
from io import BytesIO
import shutil
import zipfile

source = Path("/kaggle/temp/ooc_audit_source")
source.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(BytesIO(base64.b85decode({payload!r}))) as bundle:
    bundle.extractall(source)
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r",
                str(source / "requirements.txt")], check=True)
cache = Path("/kaggle/temp/ooc_audit_cache")
try:
    subprocess.run([sys.executable, str(source / "run_full_audit.py"),
                    "--cache", str(cache),
                    "--output", "/kaggle/working/audit_report",
                    "--time-budget", "0"], check=True)
finally:
    results = Path("/kaggle/working/model_results")
    results.mkdir(exist_ok=True)
    for name in ("f1_metadata_result.json", "f1_image_result.json",
                 "f2_rf_result.json", "f3_source_result.json", "f4_paired_result.json"):
        if (cache / name).exists():
            shutil.copy2(cache / name, results / name)
'''
    JOB.mkdir(parents=True, exist_ok=True)
    (JOB / "run_kaggle_audit.py").write_text(runner)
    metadata = {
        "id": f"{args.owner}/ooc-image-audit-f9-private",
        "title": "OoC Image Audit F9 Private",
        "code_file": "run_kaggle_audit.py",
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

#!/usr/bin/env python3
"""Rebuild all three tables: python ledger/run.py (NumPy required)."""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS'):
    os.environ[name] = '1'
for script in ('recompute.py', 'lineage.py', 'verify.py'):
    result = subprocess.run([sys.executable, '-B', str(ROOT / 'ledger' / script)], cwd=ROOT)
    if result.returncode:
        raise SystemExit(result.returncode)

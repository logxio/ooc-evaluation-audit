#!/usr/bin/env python3
"""Train one LPM seed and predict one held-out fold and k."""

import argparse
import os
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
os.environ.setdefault("S5_KIT", str(HERE / "kit"))
os.environ.setdefault("S5_HERE", str(HERE / "vendor/lpm"))
sys.path.insert(0, str(HERE / "vendor/lpm"))
import common  # noqa: E402
import lpm_run as lpm  # noqa: E402


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--fold", type=int, required=True)
    p.add_argument("--k", type=int, required=True)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--device", default="cpu")
    a = p.parse_args()
    out = HERE / "vendor/lpm/preds/lpm_seeds" / f"f{a.fold}_k{a.k}_s{a.seed}.npz"
    if out.exists():
        with np.load(out) as data:
            if f"k{a.k}" in data.files:
                return
    kit, wells = common.load_kit(), lpm.load_wells()
    model, vocabulary, _ = lpm.train_model(kit, wells, a.fold, "lincs", "date", "lookup", a.seed, a.device)
    predictions, _ = lpm.evaluate(kit, wells, model, vocabulary, a.fold, a.k, a.device,
                                  ["opt0.1@200"], a.seed)
    tasks, count = common.load_tasks(a.k, [a.fold])
    result = common.to_query_array(tasks, predictions["opt0.1@200"], count)
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out, **{f"k{a.k}": result})
    print(f"LPM seed {a.seed}, fold {a.fold}, k={a.k}: {len(tasks)} designs")


if __name__ == "__main__":
    main()

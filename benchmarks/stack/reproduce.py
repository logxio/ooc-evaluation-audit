#!/usr/bin/env python3
"""Rebuild the four held-out AnchorBoost team scores from frozen member cells."""

import argparse
import csv
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
RELEASE = HERE.parents[1]


def cohort_rows():
    with (HERE / "cohort.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 194
    assert {int(row["fold"]) for row in rows} == {1, 2, 3, 4}
    assert len({row["identity_group"] for row in rows}) == 189
    return rows


def predict(k, selection):
    with np.load(HERE / f"members_k{k}.npz", allow_pickle=False) as data:
        cells = {name: data[name] for name in data.files}
    n = len(cells["truth"])
    assert all(len(value) == n for value in cells.values())
    rows = cohort_rows()
    chemical = cells["chemical_index"].astype(np.int64)
    design = cells["design"].astype(np.int64)
    assert chemical.min() >= 0 and chemical.max() < 194
    assert design.min() == 0 and design.max() == 4
    weights = np.array([selection["k"][str(k)][row["fold"]]["weights"]["T"] for row in rows])
    w = weights[chemical]
    lpm = "lpm20" if k <= 2 else "lpm10"
    prediction = w * cells["tabpfn2"] + (1 - w) * cells[lpm]
    if k >= 3:
        prediction += cells["stack_correction"]
    assert np.isfinite(prediction).all() and np.isfinite(cells["truth"]).all()
    group = 5 * chemical + design
    counts = np.bincount(group, minlength=194 * 5)
    assert (counts > 0).all(), "Each reported chemical needs five designs"
    errors = np.abs(prediction - cells["truth"])
    per_design = np.bincount(group, weights=errors, minlength=194 * 5) / counts
    return per_design.reshape(194, 5).mean(axis=1)


def compare(rows, path):
    with path.open(newline="") as handle:
        reference = {r["chemical"]: r for r in csv.DictReader(handle)}
    assert len(reference) == len(rows)
    gaps = []
    for row in rows:
        original = reference[row["chemical"]]
        assert all(original[field] == row[field] for field in ("chemical", "identity_group", "fold", "k", "method"))
        gaps.append(abs(float(original["mae"]) - float(row["mae"])))
    gap = max(gaps)
    assert gap <= 1e-9, f"{path.name}: maximum per-chemical difference {gap:.12g}"
    return gap


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=HERE / "output")
    parser.add_argument("--reference", type=Path, default=RELEASE / "results/final/baselines")
    args = parser.parse_args()
    selection = json.loads((HERE / "selection.json").read_text())
    cohort = cohort_rows()
    args.out.mkdir(parents=True, exist_ok=True)
    for k in (1, 2, 3, 4):
        errors = predict(k, selection)
        rows = [dict(chemical=c["chemical"], identity_group=c["identity_group"], fold=c["fold"],
                     k=str(k), method="anchorboost_team", mae=str(float(error)))
                for c, error in zip(cohort, errors)]
        target = args.out / f"anchorboost_team_k{k}.csv"
        with target.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["chemical", "identity_group", "fold", "k", "method", "mae"])
            writer.writeheader()
            writer.writerows(rows)
        gap = compare(rows, args.reference / target.name)
        print(f"k={k}: 194 chemicals, 189 identity groups, MAE={errors.mean():.9f}, "
              f"maximum per-chemical difference={gap:.3g}; {target}")


if __name__ == "__main__":
    main()

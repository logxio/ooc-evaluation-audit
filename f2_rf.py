#!/usr/bin/env python3
"""F2: one preregistered random forest on the frozen F1 image feature cache.

No image ZIP is needed if the 3,072-row JSONL feature cache is available.
The 64-row probe measures resources only; it reports no validation/test score.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import resource
import sys
import time

os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"

import numpy as np
from sklearn import __version__ as sklearn_version
from sklearn.ensemble import RandomForestClassifier

from ooc_qc import (CACHE, DATASET_URL, IMAGE_FEATURE_NAMES, IMAGE_MD5,
                    TABLE_SHA256, metrics, prefix_bootstrap_interval,
                    read_feature_cache, read_table, split_rows, split_summary)


PARAMETERS = {
    "n_estimators": 300,
    "min_samples_leaf": 8,
    "max_features": "sqrt",
    "class_weight": "balanced_subsample",
    "random_state": 26,
}
F1_TEST = {
    "balanced_accuracy": 0.6088356973995273,
    "bad_recall": 0.8027777777777778,
    "good_false_positive_rate": 220 / 376,
    "confusion": [[156, 220], [71, 289]],
}


def load_parts(table: Path, features: Path):
    parts = split_rows(read_table(table))
    cache = read_feature_cache(features)
    expected = {row["id"] for rows in parts.values() for row in rows}
    if set(cache) != expected:
        raise ValueError(f"feature IDs differ from datasheet: {len(cache)} cached, {len(expected)} expected")
    if not all(np.all(np.isfinite(vector)) for vector in cache.values()):
        raise ValueError("nonfinite image feature")
    x = {split: np.asarray([cache[row["id"]] for row in rows], dtype=np.float64)
         for split, rows in parts.items()}
    y = {split: np.asarray([row["label"] == 2 for row in rows], dtype=np.int64)
         for split, rows in parts.items()}
    if any(matrix.shape != (len(parts[split]), len(IMAGE_FEATURE_NAMES))
           for split, matrix in x.items()):
        raise ValueError("feature matrix shape mismatch")
    return parts, x, y


def forest() -> RandomForestClassifier:
    return RandomForestClassifier(**PARAMETERS)


def peak_rss_mb() -> float:
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak / (1024 * 1024) if sys.platform == "darwin" else peak / 1024


def probe(x: dict, y: dict) -> dict:
    start = time.perf_counter()
    # Same 300-tree specification, training rows only, with no metric or threshold.
    forest().fit(x["train"][:64], y["train"][:64])
    return {"kind": "resource_probe_only", "train_rows": 64,
            "feature_count": len(IMAGE_FEATURE_NAMES), "trees": 300,
            "fit_seconds": time.perf_counter() - start, "peak_rss_mb": peak_rss_mb()}


def select_f2_threshold(y: np.ndarray, probability: np.ndarray) -> tuple[float, dict, dict]:
    unique = sorted(set(map(float, probability)))
    candidates = sorted(set([0.0, 0.5, 1.0, *unique,
                             *((a + b) / 2 for a, b in zip(unique, unique[1:]))]))
    scored = [(threshold, metrics(y, probability >= threshold)) for threshold in candidates]
    first = [(t, m) for t, m in scored
             if m["bad_recall"] >= 0.60 and m["good_recall"] >= 0.55]
    second = [(t, m) for t, m in scored if m["bad_recall"] >= 0.60]
    pool = first or second or scored
    tier = ("both_recall_constraints" if first else
            "bad_recall_constraint" if second else "unconstrained")
    # Fixed before fit: maximum BA; on ties closest to 0.5; then higher threshold.
    threshold, result = max(pool, key=lambda item: (
        item[1]["balanced_accuracy"], -abs(item[0] - 0.5), item[0]))
    return threshold, result, {"tier": tier, "candidate_count": len(candidates),
                               "eligible_count": len(pool),
                               "tie_rule": "maximum BA; closest to 0.5; higher threshold"}


def detailed_metrics(rows: list[dict], y: np.ndarray, prediction: np.ndarray) -> dict:
    overall = metrics(y, prediction)
    overall["good_false_positive_rate"] = (
        overall["confusion"]["good_as_bad"] / overall["good_n"] if overall["good_n"] else None)
    per_cell = {}
    for cell in sorted({row["cell_type"] for row in rows}):
        mask = np.asarray([row["cell_type"] == cell for row in rows])
        entry = metrics(y[mask], prediction[mask])
        entry["good_false_positive_rate"] = (
            entry["confusion"]["good_as_bad"] / entry["good_n"] if entry["good_n"] else None)
        per_cell[cell] = entry
    return {"overall": overall, "by_cell": per_cell,
            "prefix_groups": len({row["id"][:6] for row in rows})}


def evaluate(parts: dict, x: dict, y: dict) -> dict:
    start = time.perf_counter()
    model = forest()
    model.fit(x["train"], y["train"])
    fit_seconds = time.perf_counter() - start
    if list(model.classes_) != [0, 1]:
        raise ValueError("unexpected class order")
    val_probability = model.predict_proba(x["val"])[:, 1]
    threshold, _, selection = select_f2_threshold(y["val"], val_probability)
    val_prediction = val_probability >= threshold
    test_probability = model.predict_proba(x["test"])[:, 1]
    test_prediction = test_probability >= threshold
    val = detailed_metrics(parts["val"], y["val"], val_prediction)
    test = detailed_metrics(parts["test"], y["test"], test_prediction)
    test_overall = test["overall"]
    f1 = F1_TEST
    result = {
        "phase": "F2_adaptive_after_F1_test",
        "source": DATASET_URL,
        "datasheet_sha256": TABLE_SHA256,
        "image_zip_md5_expected": IMAGE_MD5,
        "feature_names": list(IMAGE_FEATURE_NAMES),
        "feature_count": len(IMAGE_FEATURE_NAMES),
        "split": split_summary(parts),
        "model": "sklearn.ensemble.RandomForestClassifier",
        "sklearn_version": sklearn_version,
        "model_parameters": PARAMETERS,
        "other_parameters": "scikit-learn defaults",
        "preprocessing": "none; raw frozen F1 image features",
        "selection": selection,
        "threshold": threshold,
        "validation": val,
        "test": test,
        "test_ba_prefix_bootstrap_95pct": prefix_bootstrap_interval(
            parts["test"], y["test"], test_prediction),
        "f1_image_test_reference": f1,
        "f1_to_f2_test_change": {
            "balanced_accuracy": test_overall["balanced_accuracy"] - f1["balanced_accuracy"],
            "bad_recall": test_overall["bad_recall"] - f1["bad_recall"],
            "good_false_positive_rate": test_overall["good_false_positive_rate"] - f1["good_false_positive_rate"],
            "good_false_positives": test_overall["confusion"]["good_as_bad"] - 220,
        },
        "pass_conditions": {
            "test_balanced_accuracy_ge_0.65": test_overall["balanced_accuracy"] >= 0.65,
            "test_bad_recall_ge_0.60": test_overall["bad_recall"] >= 0.60,
            "test_good_false_positive_rate_le_0.45": test_overall["good_false_positive_rate"] <= 0.45,
        },
        "fit_seconds": fit_seconds,
        "total_seconds": time.perf_counter() - start,
        "peak_rss_mb": peak_rss_mb(),
    }
    result["passes_all"] = all(result["pass_conditions"].values())
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["probe", "evaluate"])
    parser.add_argument("--table", type=Path, default=CACHE / "OOC_datasheet.xlsx")
    parser.add_argument("--features", type=Path, default=CACHE / "image_features.jsonl")
    args = parser.parse_args()
    parts, x, y = load_parts(args.table, args.features)
    if args.command == "probe":
        result = probe(x, y)
    else:
        result = evaluate(parts, x, y)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

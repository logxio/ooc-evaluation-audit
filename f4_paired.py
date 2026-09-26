#!/usr/bin/env python3
"""Compare the frozen F2 and F3 forests on their shared test images."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time

import numpy as np

from f2_rf import (PARAMETERS, detailed_metrics, forest, peak_rss_mb,
                   select_f2_threshold, sklearn_version)
from ooc_qc import (CACHE, IMAGE_FEATURE_NAMES, confusion,
                    prefix_bootstrap_interval, read_feature_cache, read_table,
                    split_rows, split_summary)
from source_split_audit import load_mapping


def load_data(args: argparse.Namespace) -> tuple[dict, dict, dict]:
    rows = read_table(args.table)
    group_parts = split_rows(rows)
    source_parts, overlap = load_mapping(args.mapping, args.table)
    features = read_feature_cache(args.features)
    ids = {row["id"] for row in rows}
    if set(features) != ids:
        raise ValueError("frozen feature IDs differ from the 3,072 datasheet IDs")
    if any(len(vector) != len(IMAGE_FEATURE_NAMES)
           or not np.isfinite(vector).all() for vector in features.values()):
        raise ValueError("invalid frozen 29D image features")
    return group_parts, source_parts, {"features": features, "overlap": overlap}


def fit_split(parts: dict, features: dict) -> dict:
    x = {name: np.asarray([features[row["id"]] for row in rows], dtype=np.float64)
         for name, rows in parts.items()}
    y = {name: np.asarray([row["label"] == 2 for row in rows], dtype=np.int64)
         for name, rows in parts.items()}
    model = forest()
    model.fit(x["train"], y["train"])
    if list(model.classes_) != [0, 1]:
        raise ValueError("unexpected class order")
    val_probability = model.predict_proba(x["val"])[:, 1]
    threshold, _, selection = select_f2_threshold(y["val"], val_probability)
    val_prediction = val_probability >= threshold
    test_prediction = model.predict_proba(x["test"])[:, 1] >= threshold
    return {
        "model": model,
        "threshold": threshold,
        "selection": selection,
        "validation": detailed_metrics(parts["val"], y["val"], val_prediction),
        "test": detailed_metrics(parts["test"], y["test"], test_prediction),
        "test_bootstrap": prefix_bootstrap_interval(parts["test"], y["test"],
                                                    test_prediction),
        "test_prediction_by_id": {row["id"]: bool(pred)
                                  for row, pred in zip(parts["test"], test_prediction)},
    }


def checked_fields(actual: dict, expected: dict, prefix: str = "") -> list[str]:
    """List every matching leaf, raising on the first missing or different field."""
    if set(actual) != set(expected):
        raise ValueError(f"field set differs at {prefix or '<root>'}: "
                         f"actual={sorted(actual)} expected={sorted(expected)}")
    matched = []
    for key in sorted(expected):
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(expected[key], dict):
            if not isinstance(actual[key], dict):
                raise ValueError(f"{path} is no longer an object")
            matched.extend(checked_fields(actual[key], expected[key], path))
        elif actual[key] != expected[key]:
            raise ValueError(f"{path} differs: {actual[key]!r} != {expected[key]!r}")
        else:
            matched.append(path)
    return matched


def reproduce(parts: dict, fitted: dict, reference_path: Path) -> dict:
    reference = json.loads(reference_path.read_text())
    actual = {
        "split": split_summary(parts),
        "model_parameters": PARAMETERS,
        "sklearn_version": sklearn_version,
        "feature_names": list(IMAGE_FEATURE_NAMES),
        "feature_count": len(IMAGE_FEATURE_NAMES),
        "selection": fitted["selection"],
        "threshold": fitted["threshold"],
        "validation": fitted["validation"],
        "test": fitted["test"],
        "test_ba_prefix_bootstrap_95pct": fitted["test_bootstrap"],
    }
    checked = checked_fields(actual, {key: reference[key] for key in actual})
    return {"matches_reference": True, "checked_leaf_fields": len(checked),
            "test_leaf_fields": sum(path.startswith("test.") for path in checked),
            "reference_sha256": hashlib.sha256(reference_path.read_bytes()).hexdigest()}


def paired_bootstrap(rows: list[dict], truth: np.ndarray,
                     source_prediction: np.ndarray,
                     group_prediction: np.ndarray, draws: int = 2000) -> dict:
    prefixes = sorted({row["id"][:6] for row in rows})
    source_cm = []
    group_cm = []
    keys = ("good_as_good", "good_as_bad", "bad_as_good", "bad_as_bad")
    for prefix in prefixes:
        selected = np.asarray([row["id"][:6] == prefix for row in rows])
        source = confusion(truth[selected], source_prediction[selected])
        group = confusion(truth[selected], group_prediction[selected])
        source_cm.append([source[key] for key in keys])
        group_cm.append([group[key] for key in keys])
    source_cm = np.asarray(source_cm, dtype=np.int64)
    group_cm = np.asarray(group_cm, dtype=np.int64)
    rng = np.random.default_rng(26)
    differences = []
    for _ in range(draws):
        chosen = rng.integers(0, len(prefixes), size=len(prefixes))
        sgg, sgb, sbg, sbb = source_cm[chosen].sum(axis=0)
        ggg, ggb, gbg, gbb = group_cm[chosen].sum(axis=0)
        if sgg + sgb and sbg + sbb:
            source_ba = (sgg / (sgg + sgb) + sbb / (sbg + sbb)) / 2
            group_ba = (ggg / (ggg + ggb) + gbb / (gbg + gbb)) / 2
            differences.append(source_ba - group_ba)
    if not differences:
        raise ValueError("no bootstrap draw contained both labels")
    low, high = np.quantile(differences, [0.025, 0.975])
    return {"low": float(low), "high": float(high),
            "valid_draws": len(differences), "draws": draws,
            "group_count": len(prefixes), "seed": 26,
            "method": "paired prefix-group percentile bootstrap; each draw uses the same prefixes for both models"}


def transition_counts(truth: np.ndarray, source_prediction: np.ndarray,
                      group_prediction: np.ndarray) -> dict:
    source_correct = source_prediction == truth
    group_correct = group_prediction == truth
    return {
        "both_correct": int(np.sum(source_correct & group_correct)),
        "source_only_correct": int(np.sum(source_correct & ~group_correct)),
        "group_only_correct": int(np.sum(~source_correct & group_correct)),
        "both_wrong": int(np.sum(~source_correct & ~group_correct)),
    }


def evaluate(args: argparse.Namespace, group_parts: dict, source_parts: dict,
             data: dict) -> dict:
    started = time.perf_counter()
    features = data["features"]
    group = fit_split(group_parts, features)
    source = fit_split(source_parts, features)
    reproduction = {
        "F2": reproduce(group_parts, group, args.f2_result),
        "F3": reproduce(source_parts, source, args.f3_result),
    }
    common_ids = sorted(set(group["test_prediction_by_id"])
                        & set(source["test_prediction_by_id"]))
    by_id = {row["id"]: row for row in group_parts["test"]}
    common_rows = [by_id[image_id] for image_id in common_ids]
    truth = np.asarray([row["label"] == 2 for row in common_rows], dtype=np.int64)
    source_prediction = np.asarray([source["test_prediction_by_id"][image_id]
                                    for image_id in common_ids], dtype=np.int64)
    group_prediction = np.asarray([group["test_prediction_by_id"][image_id]
                                   for image_id in common_ids], dtype=np.int64)
    counts = (len(common_ids), int(np.sum(truth == 0)), int(np.sum(truth == 1)),
              len({image_id[:6] for image_id in common_ids}))
    if counts != (151, 68, 83, 14):
        raise ValueError(f"unexpected shared test image counts: {counts}")
    source_common = detailed_metrics(common_rows, truth, source_prediction)
    group_common = detailed_metrics(common_rows, truth, group_prediction)
    difference = (source_common["overall"]["balanced_accuracy"]
                  - group_common["overall"]["balanced_accuracy"])
    interval = paired_bootstrap(common_rows, truth, source_prediction,
                                group_prediction)
    return {
        "phase": "F4_paired_shared_test_diagnostic",
        "feature_cache_sha256": hashlib.sha256(args.features.read_bytes()).hexdigest(),
        "mapping_sha256": hashlib.sha256(args.mapping.read_bytes()).hexdigest(),
        "common_test": {"n": counts[0], "good": counts[1], "bad": counts[2],
                        "prefix_groups": counts[3]},
        "models": {
            "F2_prefix_split": {"threshold": group["threshold"],
                                "full_test": group["test"], "common_test": group_common},
            "F3_source_split": {"threshold": source["threshold"],
                                "full_test": source["test"], "common_test": source_common},
        },
        "paired_common_test": {
            "source_minus_prefix_balanced_accuracy": difference,
            "correctness_transition": {
                "all": transition_counts(truth, source_prediction, group_prediction),
                "good": transition_counts(truth[truth == 0],
                                          source_prediction[truth == 0],
                                          group_prediction[truth == 0]),
                "bad": transition_counts(truth[truth == 1],
                                         source_prediction[truth == 1],
                                         group_prediction[truth == 1]),
            },
            "source_minus_prefix_ba_bootstrap_95pct": interval,
            "preregistered_screen": {"difference_ge_0.08": difference >= 0.08,
                                     "interval_low_gt_0": interval["low"] > 0,
                                     "passes_both": difference >= 0.08 and interval["low"] > 0},
        },
        "full_test_reproduction": reproduction,
        "interpretation": "Same test images remove test-composition differences; training rows and validation thresholds still differ. This is not a causal estimate of prefix overlap or proof of chip leakage. Both full test scores were viewed before F4.",
        "elapsed_seconds": time.perf_counter() - started,
        "peak_rss_mb": peak_rss_mb(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["probe", "evaluate"])
    parser.add_argument("--table", type=Path, default=CACHE / "OOC_datasheet.xlsx")
    parser.add_argument("--mapping", type=Path, default=CACHE / "source_split.json")
    parser.add_argument("--features", type=Path, default=CACHE / "image_features.jsonl")
    parser.add_argument("--f2-result", type=Path, default=CACHE / "f2_rf_result.json")
    parser.add_argument("--f3-result", type=Path, default=CACHE / "f3_source_result.json")
    args = parser.parse_args()
    group_parts, source_parts, data = load_data(args)
    if args.command == "probe":
        started = time.perf_counter()
        features = data["features"]
        for parts in (group_parts, source_parts):
            rows = parts["train"][:64]
            x = np.asarray([features[row["id"]] for row in rows], dtype=np.float64)
            y = np.asarray([row["label"] == 2 for row in rows], dtype=np.int64)
            forest().fit(x, y)
        result = {"kind": "resource_probe_only", "train_rows_per_model": 64,
                  "trees_per_model": PARAMETERS["n_estimators"],
                  "elapsed_seconds": time.perf_counter() - started,
                  "peak_rss_mb": peak_rss_mb()}
    else:
        result = evaluate(args, group_parts, source_parts, data)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

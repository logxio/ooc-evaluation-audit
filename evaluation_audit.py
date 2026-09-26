"""Audit two sets of per-sample evaluation records.

Each record has id, group, label (0 good, 1 bad), split (train/val/test),
prediction (0/1 on test, null elsewhere), and optional subgroup. One record
per sample per evaluation is required.
"""
from __future__ import annotations

from collections import Counter

import numpy as np


SPLITS = {"train", "val", "test"}


def validate(records: list[dict], name: str) -> dict[str, dict]:
    by_id = {}
    for row in records:
        sample_id = row.get("id")
        if not isinstance(sample_id, str) or not sample_id:
            raise ValueError(f"{name}: every sample needs a nonempty id")
        if sample_id in by_id:
            raise ValueError(f"{name}: duplicate id {sample_id}")
        if not isinstance(row.get("group"), str) or not row["group"]:
            raise ValueError(f"{name}: missing group for {sample_id}")
        if row.get("label") not in (0, 1) or isinstance(row.get("label"), bool):
            raise ValueError(f"{name}: label must be 0 or 1 for {sample_id}")
        if row.get("split") not in SPLITS:
            raise ValueError(f"{name}: invalid split for {sample_id}")
        prediction = row.get("prediction")
        if row["split"] == "test":
            if prediction not in (0, 1) or isinstance(prediction, bool):
                raise ValueError(f"{name}: test prediction must be 0 or 1 for {sample_id}")
        elif prediction is not None:
            raise ValueError(f"{name}: prediction is only accepted on test for {sample_id}")
        by_id[sample_id] = row
    if not by_id:
        raise ValueError(f"{name}: no records")
    return by_id


def score(rows: list[dict]) -> dict:
    cm = [[0, 0], [0, 0]]
    for row in rows:
        cm[row["label"]][row["prediction"]] += 1
    good = sum(cm[0])
    bad = sum(cm[1])
    return {
        "n": good + bad,
        "good": good,
        "bad": bad,
        "confusion": cm,
        "good_recall": cm[0][0] / good if good else None,
        "bad_recall": cm[1][1] / bad if bad else None,
        "good_false_positives": cm[0][1],
        "good_false_positive_rate": cm[0][1] / good if good else None,
        "balanced_accuracy": (cm[0][0] / good + cm[1][1] / bad) / 2 if good and bad else None,
    }


def paired_interval(left: list[dict], right: list[dict], draws: int = 2000,
                    seed: int = 26) -> dict:
    groups = sorted({row["group"] for row in left})
    left_cm = np.zeros((len(groups), 4), dtype=np.int64)
    right_cm = np.zeros_like(left_cm)
    index = {group: i for i, group in enumerate(groups)}
    for side, matrix in ((left, left_cm), (right, right_cm)):
        for row in side:
            matrix[index[row["group"]], row["label"] * 2 + row["prediction"]] += 1
    rng = np.random.default_rng(seed)
    differences = []
    for _ in range(draws):
        chosen = rng.integers(0, len(groups), size=len(groups))
        a, b = left_cm[chosen].sum(axis=0), right_cm[chosen].sum(axis=0)
        good, bad = a[0] + a[1], a[2] + a[3]
        if good and bad:
            differences.append((a[0] / good + a[3] / bad - b[0] / good - b[3] / bad) / 2)
    if not differences:
        return {"low": None, "high": None, "valid_draws": 0, "draws": draws,
                "group_count": len(groups), "seed": seed,
                "method": "paired group percentile bootstrap"}
    low, high = np.quantile(differences, [0.025, 0.975])
    return {"low": float(low), "high": float(high),
            "valid_draws": len(differences), "draws": draws,
            "group_count": len(groups), "seed": seed,
            "method": "paired group percentile bootstrap"}


def audit(left_records: list[dict], right_records: list[dict],
          left_name: str = "source", right_name: str = "grouped") -> dict:
    left = validate(left_records, left_name)
    right = validate(right_records, right_name)
    for sample_id in left.keys() & right.keys():
        if left[sample_id]["label"] != right[sample_id]["label"]:
            raise ValueError(f"label conflict for id {sample_id}")
        if left[sample_id]["group"] != right[sample_id]["group"]:
            raise ValueError(f"group conflict for id {sample_id}")
    names = ((left_name, left), (right_name, right))
    evaluations = {}
    for name, records in names:
        train_groups = {row["group"] for row in records.values() if row["split"] == "train"}
        test = [row for row in records.values() if row["split"] == "test"]
        test_groups = {row["group"] for row in test}
        evaluations[name] = {
            "split_counts": {split: dict(Counter(row["label"] for row in records.values()
                                                       if row["split"] == split)) for split in ("train", "val", "test")},
            "test": score(test),
            "test_groups": len(test_groups),
            "test_groups_also_in_train": len(test_groups & train_groups),
        }
    common_ids = sorted({key for key, row in left.items() if row["split"] == "test"}
                        & {key for key, row in right.items() if row["split"] == "test"})
    a = [left[key] for key in common_ids]
    b = [right[key] for key in common_ids]
    a_score, b_score = score(a), score(b)
    transitions = {"both_correct": 0, "source_only_correct": 0,
                   "grouped_only_correct": 0, "both_wrong": 0}
    for ar, br in zip(a, b):
        ac, bc = ar["prediction"] == ar["label"], br["prediction"] == br["label"]
        key = ("both_correct" if ac and bc else "source_only_correct" if ac else
               "grouped_only_correct" if bc else "both_wrong")
        transitions[key] += 1
    interval = paired_interval(a, b) if common_ids else None
    return {
        "evaluations": evaluations,
        "full_test_ba_difference": (evaluations[left_name]["test"]["balanced_accuracy"] -
                                    evaluations[right_name]["test"]["balanced_accuracy"]
                                    if all(evaluations[name]["test"]["balanced_accuracy"] is not None
                                           for name, _ in names) else None),
        "common_test": {"n": len(common_ids), "groups": len({row["group"] for row in a}),
                        left_name: a_score, right_name: b_score,
                        "balanced_accuracy_difference": (a_score["balanced_accuracy"] - b_score["balanced_accuracy"]
                                                         if a_score["balanced_accuracy"] is not None
                                                         and b_score["balanced_accuracy"] is not None else None),
                        "transitions": transitions, "paired_interval_95pct": interval},
        "test_set_difference": {"source_only": sum(row["split"] == "test" for row in left.values()) - len(common_ids),
                                "grouped_only": sum(row["split"] == "test" for row in right.values()) - len(common_ids)},
    }

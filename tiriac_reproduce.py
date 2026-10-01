#!/usr/bin/env python3
"""Reproduce the frozen Tiriac experiment on a free CPU, using standard Python.

Run: python tiriac_reproduce.py
Downloads the original CC BY 4.0 S1/S4 tables and S6 figure, verifies their
hashes, rebuilds predictions without outcomes, and then scores the fixed
clinical endpoint. --cache-dir reuses hash-verified original source files.
"""

import argparse
import copy
import json
from pathlib import Path
import resource
import sys
import tempfile
import time

from fetch_tiriac_readouts import (
    fetch_sources, readouts, sha256, split_readouts, write_csv,
)
from tiriac_blind import freeze, load


HERE = Path(__file__).resolve().parent
FROZEN_SHA256 = "1da509ad8f9cb5de6fa8af79038f6b424a8191c4855bc2f4278adcacd9cb0e95"
METHODS = ("agreement", "fixed_anchor", "mean_rank", "margin_gt_one_sixth")


def without_generation_time(value):
    result = copy.deepcopy(value)
    result.pop("created_utc", None)
    return result


def score_group(rows, method):
    eligible = [row for row in rows if row["outcome"] is not None]
    released = [row for row in eligible if row[method]["released"]]
    wrong = [row["pdo"] for row in released if row[method]["prediction"] != row["outcome"]]
    n, k, errors = len(eligible), len(released), len(wrong)
    return {
        "n_total": len(rows), "n_endpoint_evaluable": n,
        "endpoint_unknown": len(rows) - n, "released": k, "retested": n - k,
        "errors": errors, "correct": k - errors,
        "coverage": k / n if n else None,
        "released_accuracy": 1 - errors / k if k else None,
        "released_error_rate": errors / k if k else None,
        "overall_wrong_release_rate": errors / n if n else None,
        "released_ids": [row["pdo"] for row in released], "wrong_ids": wrong,
        "empirical_error_at_most_10_percent": bool(k) and errors / k <= 0.1,
        "single_rule_one_sided_95_percent_binomial_upper_if_zero_errors":
            1 - 0.05 ** (1 / k) if k and not errors else None,
        "risk_certificate": False,
    }


def score(frozen, outcomes):
    if outcomes["freeze"]["sha256"] != FROZEN_SHA256:
        raise ValueError("Clinical outcomes refer to a different prediction freeze")
    threshold = outcomes["interpretation"]["threshold_days"]
    if threshold != 6 * 30.4375:
        raise ValueError("Clinical endpoint differs from the frozen six-month rule")
    cases = {case["pdo"]: case for case in frozen["cases"]}
    observations = outcomes["rows"]
    if len(observations) != len(cases) or {r["pdo_id"] for r in observations} != set(cases):
        raise ValueError("Clinical outcomes do not match the frozen nine PDOs")
    rows = []
    for observed in observations:
        case = cases[observed["pdo_id"]]
        if observed["patient_id"] != case["patient"]:
            raise ValueError("Clinical patient mapping differs from the freeze")
        if observed["reported_regimen"] != case["reported_regimen"]:
            raise ValueError("Clinical regimen differs from the frozen reported components")
        if observed["time_days_lower"] >= threshold:
            label = 1
        elif observed["progression_event"] and observed["time_days_upper"] < threshold:
            label = 0
        else:
            label = None
        if label != observed["outcome_6_months"]:
            raise ValueError("Derived binary label disagrees with the endpoint rule")
        prediction = case["subsets"][case["reported_regimen"]]
        rows.append({
            "pdo": case["pdo"], "patient": case["patient"], "outcome": label,
            "agreement": {"released": prediction["agreement_released"],
                          "prediction": prediction["agreement_prediction"]},
            "fixed_anchor": {"released": True,
                             "prediction": prediction["fixed_anchor_prediction"]},
            "mean_rank": {"released": True,
                          "prediction": prediction["mean_rank_prediction"]},
            "margin_gt_one_sixth": {"released": prediction["mean_rank_margin"] > 1 / 6,
                                    "prediction": prediction["mean_rank_prediction"]},
        })
    primary_ids = set(frozen["primary"]["pdo_ids"])
    groups = {
        "all_9": rows,
        "primary_7": [row for row in rows if row["pdo"] in primary_ids],
        "strict_6": [row for row in rows if row["pdo"] in primary_ids - {"hF28"}],
    }
    metrics = {name: {method: score_group(group, method) for method in METHODS}
               for name, group in groups.items()}
    actual = metrics["primary_7"]["agreement"]
    forecast = frozen["primary"]["forecast"]
    primary = metrics["primary_7"]
    strict = metrics["strict_6"]
    return {
        "schema": "tiriac.reproduced-score.v1",
        "attribution": outcomes["attribution"],
        "source_doi": frozen["source_doi"],
        "freeze_sha256": FROZEN_SHA256,
        "reproduction": {"frozen_model_and_all_279_predictions_identical": True,
                         "only_ignored_field": "created_utc",
                         "outcomes_loaded_after_prediction_comparison": True,
                         "model_sha256": frozen["model"]["model_sha256"],
                         "input_sha256": frozen["input_sha256"]},
        "blinding_scope": outcomes["freeze"]["scope"],
        "endpoint": outcomes["interpretation"],
        "metrics": metrics,
        "forecast_vs_actual": {
            "forecast": forecast, "actual_released": actual["released"],
            "actual_retests": actual["retested"],
            "actual_released_accuracy": actual["released_accuracy"],
            "release_count_error": actual["released"] - forecast["released"],
            "retest_count_error": actual["retested"] - forecast["retests"],
            "accuracy_actual_minus_forecast": actual["released_accuracy"] - forecast["released_accuracy"],
            "actual_correct": actual["correct"],
            "correct_actual_minus_forecast": actual["correct"] - forecast["expected_correct"],
        },
        "method_gain": {
            "primary_mean_rank_vs_fixed_anchor_same_coverage": {
                "coverage_each": primary["mean_rank"]["coverage"],
                "error_reduction": primary["fixed_anchor"]["errors"] - primary["mean_rank"]["errors"],
                "accuracy_gain": primary["mean_rank"]["released_accuracy"] - primary["fixed_anchor"]["released_accuracy"],
            },
            "primary_mean_rank_vs_agreement_same_observed_zero_error": {
                "additional_releases": primary["mean_rank"]["released"] - primary["agreement"]["released"],
                "coverage_gain": primary["mean_rank"]["coverage"] - primary["agreement"]["coverage"],
            },
            "primary_margin_vs_agreement_same_observed_zero_error": {
                "additional_releases": primary["margin_gt_one_sixth"]["released"] - primary["agreement"]["released"],
                "coverage_gain": primary["margin_gt_one_sixth"]["coverage"] - primary["agreement"]["coverage"],
            },
            "strict_mean_rank_vs_agreement_same_observed_zero_error": {
                "additional_releases": strict["mean_rank"]["released"] - strict["agreement"]["released"],
                "coverage_gain": strict["mean_rank"]["coverage"] - strict["agreement"]["coverage"],
            },
            "interpretation": "All methods and subgroups were frozen. Equal observed error does not establish equal guaranteed population risk. Full-nine sensitivity retains the hF50 error.",
        },
        "high_confidence_conditional_risk_10_percent": {
            "calibration_outcome_patients_before_freeze": 0,
            "certified_releases": 0, "certified_coverage": 0,
            "retests_all_9": 9, "retests_primary_7": 7, "retests_strict_6": 6,
            "reason": frozen["primary"]["risk_10_percent"],
            "distinction": "Seven correct primary predictions provide an observed result. Under an iid Bernoulli model, the single fixed-rule 95% upper error bound for 0/7 is 34.82%, so these data do not certify a 10% population conditional error bound.",
        },
    }


def reproduce(cache, outcomes_path):
    original_path = HERE / "tiriac_frozen_predictions.json"
    if sha256(original_path) != FROZEN_SHA256:
        raise ValueError("The original public prediction freeze has changed")
    original = json.loads(original_path.read_text())
    paths, source_receipts = fetch_sources(cache, include_figure=True)
    all_rows = readouts(paths)
    reference, clinical = split_readouts(all_rows)
    with tempfile.TemporaryDirectory(prefix="tiriac-inputs-") as temporary:
        reference_path = Path(temporary) / "reference.csv"
        clinical_path = Path(temporary) / "clinical.csv"
        write_csv(reference_path, reference)
        write_csv(clinical_path, clinical)
        # Reload the CSV representation used by the original public freeze.
        rebuilt = freeze(load(reference_path), load(clinical_path))
        rebuilt["input_sha256"] = {"reference": sha256(reference_path),
                                   "clinical_readouts": sha256(clinical_path)}
    if without_generation_time(rebuilt) != without_generation_time(original):
        raise ValueError("Rebuilt predictions differ from the public freeze")
    # Clinical endpoint data enter only after every frozen prediction matches.
    outcomes = json.loads(outcomes_path.read_text())
    if outcomes["source"]["supplement_sha256"] != source_receipts["s6"]["sha256"]:
        raise ValueError("Clinical interpretation refers to a different source figure")
    result = score(rebuilt, outcomes)
    result["source_sha256"] = {key: value["sha256"] for key, value in source_receipts.items()}
    result["outcomes_sha256"] = sha256(outcomes_path)
    counts = {"all_pdo_rows": len(all_rows), "clinical_patients": len(clinical),
              "reference_pdo_rows": len(reference),
              "reference_patients": len({row["patient_id"] for row in reference})}
    return result, source_receipts, counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path,
                        help="Optional cache of hash-verified original sources")
    parser.add_argument("--out", type=Path, default=Path("tiriac_score.json"))
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    start = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="tiriac-sources-") as temporary:
        result, sources, counts = reproduce(args.cache_dir or Path(temporary),
                                            HERE / "tiriac_outcomes.json")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak_bytes = peak if sys.platform == "darwin" else peak * 1024
    receipt = {"schema": "tiriac.reproduction-receipt.v1", "status": "complete",
               "elapsed_seconds": round(time.monotonic() - start, 4),
               "peak_rss_bytes": peak_bytes, "counts": counts,
               "score_sha256": sha256(args.out), "sources": sources,
               "freeze_matches": result["reproduction"],
               "primary": result["metrics"]["primary_7"],
               "conditional_certified_coverage": 0}
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(receipt, indent=2, allow_nan=False) + "\n")
    print(json.dumps(receipt, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()

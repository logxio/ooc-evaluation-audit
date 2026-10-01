#!/usr/bin/env python3
"""A fixed-budget chemical release feasibility experiment on EPA source data.

Install rdata, pandas, numpy, scipy and scikit-learn. Input is the unmodified
EPA Rdata file, fetched by default. No competitor data bundle is read.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import resource
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd
import rdata
from scipy.stats import beta

FEATURES = ["meanfiringrate", "burst.per.min", "mean.isis", "per.spikes.in.burst",
            "mean.dur", "mean.IBIs", "nAE", "nABE", "ns.n", "ns.peak.m",
            "ns.durn.m", "ns.percent.of.spikes.in.ns", "ns.mean.insis",
            "ns.durn.sd", "ns.mean.spikes.in.ns", "r", "mi"]
DAYS = [5, 7, 9, 12]
BATCH = ["apid.short", "date", "DIV"]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def exact_interval(errors, n):
    return [float(beta.ppf(.025, errors, n-errors+1)) if errors else 0.0,
            float(beta.ppf(.975, errors+1, n-errors)) if errors < n else 1.0] if n else None


def summarize(rows, key):
    selected = [r for r in rows if r[key + "_release"]]
    errors = sum(r[key + "_prediction"] != r["reference_active"] for r in selected)
    return {"n": len(rows), "released": len(selected), "retest": len(rows)-len(selected),
            "wrong_releases": errors, "coverage": len(selected)/len(rows),
            "overall_wrong_release_fraction": errors/len(rows),
            "conditional_wrong_release_fraction": errors/len(selected) if selected else None,
            "overall_risk_ci95": exact_interval(errors, len(rows)),
            "conditional_risk_ci95": exact_interval(errors, len(selected))}


def select_cutoff(train_scores, calibration_scores, calibration_errors):
    candidates = sorted(set([-1.0, float("inf")] +
                            list(np.quantile(train_scores, np.linspace(0, 1, 51)))))
    for cutoff in candidates:
        selected = calibration_scores >= cutoff
        corrected = (int(calibration_errors[selected].sum()) + 1)/(len(selected) + 1)
        if corrected <= .1:
            return float(cutoff), {"released": int(selected.sum()),
                                  "errors": int(calibration_errors[selected].sum()),
                                  "corrected_overall_risk": corrected}
    return float("inf"), {"released": 0, "errors": 0,
                            "corrected_overall_risk": 1/(len(calibration_scores)+1)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--out", type=Path, default=Path("epa_release_result.json"))
    args = parser.parse_args()
    started = time.monotonic()
    protocol_path = Path(__file__).with_name("epa_release_protocol.json")
    protocol_bytes = protocol_path.read_bytes()
    protocol = json.loads(protocol_bytes)
    raw = args.input.read_bytes() if args.input else urllib.request.urlopen(
        protocol["source_url"], timeout=60).read()
    if sha(raw) != protocol["source_sha256"]:
        raise ValueError("EPA raw-data SHA256 mismatch")
    # rdata accepts a binary stream, avoiding a separate transformed data bundle.
    import io
    frame = rdata.read_rda(io.BytesIO(raw))["rval.dat"].copy()
    frame.columns = [str(c) for c in frame.columns]
    # R NA_real_ has a signaling-NaN payload. Canonicalize missing readouts
    # before arithmetic; masks below continue to retain missingness.
    raw_values = frame[FEATURES].to_numpy(float)
    frame[FEATURES] = np.where(np.isfinite(raw_values), raw_values, np.nan)
    for c in frame.select_dtypes(include="category").columns:
        frame[c] = frame[c].astype(object)
    frame["chemical"] = frame.treatment.map(lambda x: " ".join(str(x).casefold().split()))
    if set(frame.units) != {"uM"} or set(frame.DIV) != set(DAYS):
        raise ValueError("EPA concentration units or DIV schema changed")
    exposed = frame[frame.dose > 0]
    eligible = [name for name, part in exposed.groupby("chemical", sort=True)
                if part.dose.nunique() >= 3 and set(part.DIV) == set(DAYS)]
    names = sorted(eligible, key=lambda x: sha(("epa-release-20261002-v1|" + x).encode()))
    n = len(names)//3
    stage = {name: ("train" if i < n else "calibrate" if i < 2*n else "test")
             for i, name in enumerate(names)}
    frame["stage"] = frame.chemical.map(stage)
    train_plates = set(frame.loc[frame.stage == "train", "apid.short"])
    controls = frame[frame.dose == 0].drop_duplicates(BATCH + ["well"])
    train_controls = controls[controls["apid.short"].isin(train_plates)]
    if train_controls.empty:
        raise ValueError("Training chemicals have no associated vehicle controls")
    transform = {}
    for feature in FEATURES:
        positive = train_controls.loc[(train_controls.DIV == 12) &
                                      (train_controls[feature] > 0), feature]
        scale = float(positive.median()/4) if len(positive) else 1.0
        train_control_g = train_controls[BATCH].copy()
        train_control_g["g"] = np.arcsinh(train_controls[feature].to_numpy(float)/scale)
        within = train_control_g.groupby(BATCH)["g"].agg(
            lambda a: 1.4826 * np.nanmedian(np.abs(a - np.nanmedian(a)))
            if a.notna().sum() >= 3 else np.nan)
        per_day = {day: max(float(within.xs(day, level="DIV").median()), .05)
                   for day in DAYS}
        for day in DAYS:
            if not np.isfinite(per_day[day]):
                per_day[day] = 1.0
        transform[feature] = {"asinh_scale": scale, "vehicle_robust_sd_by_day": per_day}
        current_controls = controls[BATCH].copy()
        current_controls["g"] = np.arcsinh(controls[feature].to_numpy(float)/scale)
        medians = current_controls.groupby(BATCH)["g"].median()
        center = pd.MultiIndex.from_frame(frame[BATCH]).map(medians).to_numpy(float)
        standardized = (np.arcsinh(frame[feature].to_numpy(float)/scale)-center)
        standardized /= frame.DIV.map(per_day).to_numpy(float)
        frame["z_" + feature] = np.clip(standardized, -10, 10)

    zcols = ["z_" + f for f in FEATURES]
    records, features = [], {}
    for name, part in frame[frame.dose > 0].groupby("chemical", sort=True):
        if name not in stage:
            continue
        levels = sorted(float(v) for v in part.dose.unique())
        if len(levels) < 3:
            continue
        cube = (part.groupby(["dose", "DIV"])[zcols].mean()
                .reindex(pd.MultiIndex.from_product([levels, DAYS], names=["dose", "DIV"]))
                .to_numpy(float).reshape(len(levels), len(DAYS), len(FEATURES)))
        observed = np.isfinite(cube)
        value = np.nan_to_num(cube, nan=0.0)
        selected = [0, (len(levels)-1)//2, len(levels)-1]
        developmental = value.mean(axis=1)
        full_effect = float(np.max(np.abs(developmental)))
        sparse_effect = float(np.max(np.abs(developmental[selected])))
        margin = abs(sparse_effect-3)
        records.append({"chemical": name, "stage": stage[name],
                        "source_files": sorted(str(v) for v in part.srcf.unique()),
                        "plates": sorted(str(v) for v in part["apid.short"].unique()),
                        "concentrations": levels, "selected_concentrations": [levels[i] for i in selected],
                        "reference_active": bool(full_effect >= 3),
                        "sparse_max_effect": sparse_effect,
                        "baseline_prediction": bool(sparse_effect >= 3),
                        "baseline_score": margin, "baseline_release": True,
                        "naive_prediction": bool(sparse_effect >= 3), "naive_release": True})
        features[name] = np.r_[value[selected].ravel(), observed[selected].ravel().astype(float),
                               np.log10(np.array(levels)[selected]), margin]

    train = [r for r in records if r["stage"] == "train"]
    calibration = [r for r in records if r["stage"] == "calibrate"]
    test = [r for r in records if r["stage"] == "test"]
    cutoff, calibration_detail = select_cutoff(
        [r["baseline_score"] for r in train], np.array([r["baseline_score"] for r in calibration]),
        np.array([r["baseline_prediction"] != r["reference_active"] for r in calibration]))
    for r in records:
        r["baseline_release"] = bool(r["baseline_score"] >= cutoff)
    result = {"schema": "epa-release-result-v1", "protocol_sha256": sha(protocol_bytes),
              "source_url": protocol["source_url"], "source_sha256": sha(raw),
              "source_bytes": len(raw), "source_rows": len(frame), "independent_chemicals": len(records),
              "split_counts": {s: sum(r["stage"] == s for r in records) for s in ("train", "calibrate", "test")},
              "endpoint": protocol["reference"], "transform": transform,
              "transform_sha256": sha(json.dumps(transform, sort_keys=True).encode()),
              "baseline_cutoff": cutoff if np.isfinite(cutoff) else "all_retest",
              "baseline_calibration": calibration_detail,
              "naive": summarize(test, "naive"), "strong_baseline": summarize(test, "baseline"),
              "batch_overlap": {}, "candidate_trained": False}
    for left, right in [("train", "calibrate"), ("train", "test"), ("calibrate", "test")]:
        a = {p for r in records if r["stage"] == left for p in r["plates"]}
        b = {p for r in records if r["stage"] == right for p in r["plates"]}
        result["batch_overlap"][left + "_" + right] = len(a & b)
    baseline = result["strong_baseline"]
    if baseline["coverage"] == 1 and baseline["overall_wrong_release_fraction"] <= .1:
        result.update({"decision": "stop_coverage_ceiling", "pass": False,
                       "maximum_attainable_coverage_gain": 0.0,
                       "reason": "The risk-qualified fixed baseline already releases every held-out chemical. No candidate can have a positive release-coverage difference on this endpoint and budget.",
                       "paired_gain_ci95": None,
                       "ablations": "Not run: the prespecified minimum-probe stop rule was reached."})
    else:
        from sklearn.ensemble import RandomForestClassifier
        model = RandomForestClassifier(n_estimators=200, min_samples_leaf=5, max_features="sqrt",
                                       random_state=20261002, n_jobs=1)
        model.fit([features[r["chemical"]] for r in train], [r["reference_active"] for r in train])
        probabilities = model.predict_proba([features[r["chemical"]] for r in records])
        for row, prob in zip(records, probabilities):
            row["method_prediction"] = bool(model.classes_[np.argmax(prob)])
            row["method_score"] = float(np.max(prob))
        method_cutoff, method_cal = select_cutoff(
            [r["method_score"] for r in train], np.array([r["method_score"] for r in calibration]),
            np.array([r["method_prediction"] != r["reference_active"] for r in calibration]))
        for r in records:
            r["method_release"] = bool(r["method_score"] >= method_cutoff)
        delta = np.array([int(r["method_release"])-int(r["baseline_release"]) for r in test])
        rng = np.random.default_rng(20261002)
        boot = np.mean(delta[rng.integers(0, len(test), size=(10000, len(test)))], axis=1)
        ci = [float(v) for v in np.quantile(boot, [.025, .975])]
        method = summarize(test, "method")
        passed = (ci[0] > 0 and method["overall_wrong_release_fraction"] <= .1 and
                  baseline["overall_wrong_release_fraction"] <= .1)
        result.update({"candidate_trained": True, "method": method, "method_calibration": method_cal,
                       "method_cutoff": method_cutoff if np.isfinite(method_cutoff) else "all_retest",
                       "coverage_gain": float(delta.mean()), "paired_gain_ci95": ci,
                       "pass": passed, "decision": "advance_to_ablations" if passed else "stop_failed_gain"})
    result["rows"] = records
    peak_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    result["runtime"] = {"seconds": time.monotonic()-started,
                         "peak_rss_bytes": peak_rss if sys.platform == "darwin" else peak_rss * 1024}
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False)+"\n")
    print(json.dumps({k: v for k, v in result.items() if k not in ("rows", "transform")}, indent=2))


if __name__ == "__main__":
    main()

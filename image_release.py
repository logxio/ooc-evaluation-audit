#!/usr/bin/env python3
"""Group-held-out image quality release using an independently trained error score.

The error score and the entire acceptance family are fixed from training groups.
CRC controls expected equal-group wrong-release loss under exchangeable groups;
it is not a conditional error-rate or a per-batch confidence guarantee.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import resource
import sys
import time

for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[name] = "1"

import numpy as np
import sklearn
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor

from ooc_qc import IMAGE_FEATURE_NAMES, read_feature_cache, read_table

ROOT = Path(__file__).resolve().parent
DEFAULT_PROTOCOL = ROOT / "image_release_protocol.json"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def rss():
    x = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(x if sys.platform == "darwin" else x * 1024)


def ordered_groups(groups, salt):
    return sorted(set(groups), key=lambda v: hashlib.sha256((salt + v).encode()).hexdigest())


def forest(protocol):
    return RandomForestClassifier(**protocol["classifier"])


def error_model(protocol):
    return RandomForestRegressor(**protocol["error_regressor"])


def score_features(model, x, groups):
    p = model.predict_proba(x)[:, 1]
    trees = np.asarray([tree.predict_proba(x)[:, 1] for tree in model.estimators_])
    conf = np.maximum(p, 1 - p)
    group_stats = np.zeros((len(x), 2))
    for group in sorted(set(groups)):
        mask = groups == group
        group_stats[mask] = [float(np.mean(conf[mask])), float(np.std(conf[mask]))]
    return np.column_stack((x, p, conf, np.std(trees, axis=0), group_stats)), p


def load(protocol, table, features):
    if sha(table) != protocol["datasheet_sha256"]:
        raise ValueError("datasheet SHA differs from the frozen protocol")
    source_rows = read_table(table)
    cache = read_feature_cache(features)
    if set(cache) != {r["id"] for r in source_rows}:
        raise ValueError("feature IDs differ from the datasheet")
    # Current public image extraction already rounds each feature to 12 decimals.
    # Normalize older caches in memory with that same rule, without replacing them.
    # Datasheet order and standard JSON serialization reproduce the frozen byte hash.
    cache = {key: [round(float(value), 12) for value in vector]
             for key, vector in cache.items()}
    canonical = "".join(json.dumps({"id": row["id"], "features": cache[row["id"]]}) + "\n"
                        for row in source_rows).encode()
    if hashlib.sha256(canonical).hexdigest() != protocol["feature_cache_sha256"]:
        raise ValueError("12-decimal canonical feature SHA differs from the frozen protocol")
    rows = sorted(source_rows, key=lambda r: r["id"])
    x = np.asarray([cache[r["id"]] for r in rows])
    y = np.asarray([int(r["label"] == 2) for r in rows])
    groups = np.asarray([r["id"][:6] for r in rows])
    stages = {name: np.isin(groups, members) for name, members in protocol["groups"].items()}
    if not np.all(sum(stages.values()) == 1):
        raise ValueError("each row must occur in exactly one split")
    return rows, x, y, groups, stages


def fit_score(protocol, x, y, groups):
    order = ordered_groups(groups, protocol["oof_salt"])
    folds = {group: i % protocol["oof_folds"] for i, group in enumerate(order)}
    oof = np.zeros((len(x), x.shape[1] + 5))
    oof_p = np.zeros(len(x))
    for fold in range(protocol["oof_folds"]):
        mask = np.asarray([folds[g] == fold for g in groups])
        base = forest(protocol).fit(x[~mask], y[~mask])
        oof[mask], oof_p[mask] = score_features(base, x[mask], groups[mask])
    errors = ((oof_p >= .5) != y).astype(int)
    # Equal total training weight per acquisition group, fixed before calibration.
    counts = Counter(groups)
    weights = np.asarray([1 / counts[g] for g in groups])
    model = error_model(protocol).fit(oof, errors, sample_weight=weights)
    base = forest(protocol).fit(x, y)
    return base, model, {"groups": order, "fold_by_group": folds,
                         "oof_errors": int(sum(errors)), "oof_rows": len(y)}


def choose(scores, wrong, groups, grid, risk, kind):
    unique = sorted(set(groups))
    losses = []
    for threshold in grid:
        accepted = scores <= threshold
        if kind == "group_crc":
            values = [float(np.mean((accepted & wrong)[groups == g])) for g in unique]
            loss = (sum(values) + 1) / (len(unique) + 1)
        elif kind == "image_crc":
            loss = (int(np.sum(accepted & wrong)) + 1) / (len(wrong) + 1)
        elif kind == "naive_empirical":
            loss = float(np.mean(accepted & wrong))
        else:
            raise ValueError(kind)
        losses.append(float(loss))
    eligible = [i for i, value in enumerate(losses) if value <= risk + 1e-14]
    selected = max(eligible) if eligible else None
    return {"threshold": grid[selected] if selected is not None else -1.0,
            "calibration_loss": losses[selected] if selected is not None else None,
            "kind": kind, "calibration_groups": len(unique),
            "calibration_images": len(wrong), "loss_by_fixed_grid": losses}


def metrics(accepted, wrong, groups):
    n = len(wrong)
    a, e = int(sum(accepted)), int(sum(accepted & wrong))
    by_group = []
    for group in sorted(set(groups)):
        mask = groups == group
        by_group.append({"group": group, "images": int(sum(mask)),
                         "accepted": int(sum(accepted[mask])),
                         "wrong_release": int(sum((accepted & wrong)[mask]))})
    return {"images": n, "groups": len(by_group), "accepted": a,
            "retest": n - a, "wrong_release": e, "coverage": a / n,
            "wrong_release_risk": e / n, "conditional_error": e / a if a else None,
            "equal_group_coverage": float(np.mean([r["accepted"] / r["images"] for r in by_group])),
            "equal_group_wrong_release_risk": float(np.mean([r["wrong_release"] / r["images"] for r in by_group])),
            "by_group": by_group}


def interval(values):
    return list(map(float, np.quantile(values, [.025, .975])))


def bootstrap(protocol, methods):
    names = list(methods)
    matrix = np.asarray([[[g["images"], g["accepted"], g["wrong_release"]]
                           for g in methods[name]["test"]["by_group"]] for name in names])
    rng = np.random.default_rng(protocol["bootstrap_seed"])
    chosen = rng.integers(0, matrix.shape[1], size=(protocol["bootstrap_resamples"], matrix.shape[1]))
    sums = matrix[:, chosen, :].sum(axis=2)
    cover = sums[:, :, 1] / sums[:, :, 0]
    risk = sums[:, :, 2] / sums[:, :, 0]
    eqcover = (matrix[:, chosen, 1] / matrix[:, chosen, 0]).mean(axis=2)
    eqrisk = (matrix[:, chosen, 2] / matrix[:, chosen, 0]).mean(axis=2)
    out = {name: {"coverage_95pct": interval(cover[i]), "risk_95pct": interval(risk[i]),
                  "equal_group_coverage_95pct": interval(eqcover[i]),
                  "equal_group_risk_95pct": interval(eqrisk[i])} for i, name in enumerate(names)}
    proposed = names.index("trained_group_crc")
    comparisons = {}
    for i, name in enumerate(names):
        if i == proposed:
            continue
        observed = methods["trained_group_crc"]["test"]["coverage"] - methods[name]["test"]["coverage"]
        ci = interval(cover[proposed] - cover[i])
        both_risk = all(methods[n]["test"]["wrong_release_risk"] <= protocol["alpha"]
                        for n in (name, "trained_group_crc"))
        comparisons[name] = {"coverage_gain": observed, "coverage_gain_95pct": ci,
                             "equal_group_coverage_gain_95pct": interval(eqcover[proposed] - eqcover[i]),
                             "both_observed_image_risks_le_alpha": both_risk,
                             "passes": bool(both_risk and ci[0] > 0)}
    return {"unit": "acquisition-prefix groups, paired; biological independence unverified",
            "resamples": protocol["bootstrap_resamples"], "seed": protocol["bootstrap_seed"],
            "method_intervals": out, "proposed_minus_comparator": comparisons}


def evaluate(args, protocol):
    started = time.perf_counter()
    rows, x, y, groups, stages = load(protocol, args.table, args.features)
    train, cal, test = (stages[k] for k in ("train", "calibration", "test"))
    base, scorer, fit = fit_score(protocol, x[train], y[train], groups[train])
    score_x, probabilities = score_features(base, x, groups)
    independent = scorer.predict(score_x)
    naive = 1 - np.maximum(probabilities, 1 - probabilities)
    wrong = (probabilities >= .5) != y
    scores = {"trained_group_crc": independent, "probability_group_crc": naive,
              "probability_naive_threshold": naive, "trained_image_crc": independent}
    kinds = {"trained_group_crc": "group_crc", "probability_group_crc": "group_crc",
             "probability_naive_threshold": "naive_empirical", "trained_image_crc": "image_crc"}
    # Explicitly invalid diagnostic: train the scoring function on calibration errors.
    # The same calibration labels then choose a threshold; exchangeability proof fails.
    if args.ablations:
        leaky = error_model(protocol).fit(score_x[cal], wrong[cal].astype(int))
        scores["calibration_fitted_score_invalid"] = leaky.predict(score_x)
        kinds["calibration_fitted_score_invalid"] = "group_crc"
    frozen = {"protocol_sha256": sha(args.protocol), "fit": fit,
              "classifier_predictions_train": probabilities[train].tolist(),
              "thresholds": {}}
    for name, values in scores.items():
        frozen["thresholds"][name] = choose(values[cal], wrong[cal], groups[cal],
                                              protocol["threshold_grid"], protocol["alpha"], kinds[name])
    # Persist thresholds and all test predictions before producing test label metrics.
    frozen["test_predictions"] = [{"id": rows[i]["id"], "predicted_bad": bool(probabilities[i] >= .5),
                                   "p_bad": float(probabilities[i]),
                                   "scores": {name: float(values[i]) for name, values in scores.items()}}
                                  for i in np.flatnonzero(test)]
    dump(args.freeze, frozen)
    methods = {}
    for name, values in scores.items():
        accepted = values <= frozen["thresholds"][name]["threshold"]
        methods[name] = {"selection": frozen["thresholds"][name],
                         "calibration": metrics(accepted[cal], wrong[cal], groups[cal]),
                         "test": metrics(accepted[test], wrong[test], groups[test])}
    result = {"experiment": "F92", "protocol_sha256": sha(args.protocol), "frozen_predictions_sha256": sha(args.freeze),
              "code_sha256": sha(__file__), "sklearn": sklearn.__version__, "numpy": np.__version__,
              "feature_input_sha256": sha(args.features),
              "feature_normalization": "Round to12decimal places in memory; serialize in original datasheet order; verify frozen canonical SHA256 before fitting.",
              "source": protocol["source"], "source_hashes": {k: protocol[k] for k in
              ("datasheet_sha256", "feature_cache_sha256", "image_zip_md5")},
              "split": {k: {"images": int(sum(v)), "groups": len(set(groups[v]))} for k, v in stages.items()},
              "methods": methods, "bootstrap": bootstrap(protocol, methods),
              "test_predictions": [{"id": rows[i]["id"], "group": str(groups[i]), "true_bad": bool(y[i]),
                  "predicted_bad": bool(probabilities[i] >= .5), "p_bad": float(probabilities[i]),
                  "scores": {name: float(values[i]) for name, values in scores.items()},
                  "accepted": {name: bool(values[i] <= methods[name]["selection"]["threshold"]) for name, values in scores.items()}}
                  for i in np.flatnonzero(test)],
              "limitations": protocol["limitations"], "seconds": time.perf_counter() - started, "peak_rss_bytes": rss()}
    result["passes_prespecified_gate"] = bool(result["bootstrap"]["proposed_minus_comparator"]["probability_group_crc"]["passes"]
                                               and result["bootstrap"]["proposed_minus_comparator"]["probability_naive_threshold"]["passes"])
    dump(args.out, result)
    print(json.dumps({"result": str(args.out), "split": result["split"],
                      "methods": {k: {j: v["test"][j] for j in ("accepted", "wrong_release", "coverage", "wrong_release_risk")} for k, v in methods.items()},
                      "comparisons": result["bootstrap"]["proposed_minus_comparator"],
                      "passes": result["passes_prespecified_gate"], "seconds": result["seconds"], "peak_rss_bytes": rss()}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["probe", "evaluate"])
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--table", type=Path, default=ROOT / ".cache/OOC_datasheet.xlsx")
    parser.add_argument("--features", type=Path, default=ROOT / ".cache/image_features.jsonl",
                        help="Public run_full_audit.py output; older unrounded caches are normalized and hash-verified in memory")
    parser.add_argument("--freeze", type=Path, default=ROOT / ".cache/image_release_frozen.json")
    parser.add_argument("--out", type=Path, default=ROOT / "image_release_result.json")
    parser.add_argument("--ablations", action="store_true")
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    if args.command == "probe":
        started = time.perf_counter()
        _, x, y, _, stages = load(protocol, args.table, args.features)
        forest(protocol).fit(x[stages["train"]][:64], y[stages["train"]][:64])
        print(json.dumps({"kind": "64-training-image resource probe, no test metrics",
                          "seconds": time.perf_counter() - started, "peak_rss_bytes": rss()}))
    else:
        evaluate(args, protocol)


if __name__ == "__main__":
    main()

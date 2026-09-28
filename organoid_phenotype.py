#!/usr/bin/env python3
"""Reproduce a source and biological-sample audit of neural organoid phenotypes.

Run on a free Kaggle Linux CPU with Python 3.12: python organoid_phenotype.py
The source is HNOCA v1. Its 3,000-gene panel and coarse labels were made with
the shared atlas, including the external study. This tests acquisition-source
transfer under that shared representation; it is not independent blind labeling.
HNOCA v1 data: CC BY 4.0 (https://zenodo.org/records/15004818). Code: MIT.
NumPy, SciPy, scikit-learn, and h5py: BSD-3-Clause; Requests: Apache-2.0.
"""
import argparse
import csv
import hashlib
from html import escape
import json
import os
import random
import resource
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

import h5py
import numpy as np
import requests
from scipy import sparse
from sklearn.linear_model import SGDClassifier
from sklearn.metrics import confusion_matrix, f1_score, precision_recall_fscore_support
from sklearn.model_selection import GroupShuffleSplit, train_test_split

URL = "https://zenodo.org/api/records/15004818/files/hnoca_minimal_for_mapping.h5ad/content"
SIZE = 2_880_860_613
MD5 = "078675d6108e93cebc99676b6b0626aa"
SOURCES = ("Velasco, 2019", "Bhaduri, 2020")
LABELS = ("NPC", "Neuron", "Glioblast")
SEED = 26
BLOCK_ROWS = 4096
START = time.monotonic()


def rss():
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)


def stage(name, **extra):
    rec = {"stage": name, "seconds": round(time.monotonic() - START, 3), "maxrss_bytes": rss(), **extra}
    print("ORGANOID_STAGE " + json.dumps(rec, ensure_ascii=False), flush=True)
    return rec


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for part in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def download(path):
    md5 = hashlib.md5()
    n = 0
    with requests.get(URL, stream=True, timeout=(30, 180), headers={"User-Agent": "organoid-phenotype-audit/1"}) as r:
        r.raise_for_status()
        with open(path, "wb") as f:
            for chunk in r.iter_content(chunk_size=4 * 1024 * 1024):
                if chunk:
                    f.write(chunk)
                    md5.update(chunk)
                    n += len(chunk)
    if n != SIZE or md5.hexdigest() != MD5:
        raise RuntimeError(f"original mismatch: bytes={n}, md5={md5.hexdigest()}")
    return {"bytes": n, "md5": md5.hexdigest(), "verified": True}


def verify_source(path):
    digest = hashlib.md5()
    size = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    if size != SIZE or digest.hexdigest() != MD5:
        raise RuntimeError(f"original mismatch: bytes={size}, md5={digest.hexdigest()}")
    return {"bytes": size, "md5": digest.hexdigest(), "verified": True}


def decode(a):
    return [v.decode() if isinstance(v, bytes) else str(v) for v in a]


def meta(h):
    obs = h["obs"]
    pc = decode(obs["publication"]["categories"][:])
    lc = decode(obs["annot_level_1"]["categories"][:])
    gc = decode(obs["bio_sample"]["categories"][:])
    p = obs["publication"]["codes"][:]
    y = obs["annot_level_1"]["codes"][:]
    g = obs["bio_sample"]["codes"][:]
    return p, y, g, pc, lc, gc


def choose_rows(p, y, pc, lc):
    selected = []
    counts = {}
    for source in SOURCES:
        counts[source] = {}
        for label in LABELS:
            rows = np.flatnonzero((p == pc.index(source)) & (y == lc.index(label)))
            counts[source][label] = int(len(rows))
            selected.extend(rows.tolist())
    return np.array(sorted(selected), dtype=np.int64), counts


def extract(h, rows):
    x = h["X"]
    if tuple(x.attrs["shape"]) != (1_770_578, 3000):
        raise RuntimeError(f"X shape changed: {x.attrs['shape']}")
    indptr = x["indptr"][:]
    matrices = []
    n = len(indptr) - 1
    pos = 0
    for a in range(0, n, BLOCK_ROWS):
        b = min(n, a + BLOCK_ROWS)
        lo = pos
        while pos < len(rows) and rows[pos] < b:
            pos += 1
        if pos == lo:
            continue
        v0, v1 = int(indptr[a]), int(indptr[b])
        data = x["data"][v0:v1]
        indices = x["indices"][v0:v1]
        block = sparse.csr_matrix((data, indices, indptr[a:b + 1].astype(np.int64) - v0), shape=(b-a, 3000))
        matrices.append(block[rows[lo:pos] - a])
    if pos != len(rows):
        raise RuntimeError(f"extracted {pos}, expected {len(rows)}")
    out = sparse.vstack(matrices, format="csr").astype(np.float32)
    if out.shape != (len(rows), 3000):
        raise RuntimeError(f"extraction shape {out.shape}")
    return out


def transform(x):
    x = x.copy()
    totals = np.asarray(x.sum(axis=1)).ravel()
    if np.any(totals <= 0):
        raise RuntimeError(f"zero panel counts: {(totals <= 0).sum()}")
    if np.any(x.data < 0) or not np.allclose(x.data, np.round(x.data), atol=1e-6):
        raise RuntimeError("X is not nonnegative count-like data")
    scale = (1e4 / totals).astype(np.float32)
    x.data *= np.repeat(scale, np.diff(x.indptr))
    np.log1p(x.data, out=x.data)
    return x


def model():
    return SGDClassifier(loss="log_loss", penalty="l2", alpha=1e-4, max_iter=30,
                         tol=1e-3, class_weight="balanced", average=True,
                         random_state=SEED, n_jobs=1)


def nearest_centroid(train_x, train_y, test_x):
    # Cosine to class mean; all means learned on Velasco training only.
    centroids = np.vstack([np.asarray(train_x[train_y == i].mean(axis=0)).ravel() for i in range(3)])
    centroids /= np.maximum(np.linalg.norm(centroids, axis=1, keepdims=True), 1e-12)
    return np.asarray(test_x @ centroids.T).argmax(axis=1).astype(np.int8)


def source_centroid_distance(train_x, train_y, target_x):
    """Distance to the nearest Velasco class mean in cosine space."""
    centroids = np.vstack([np.asarray(train_x[train_y == i].mean(axis=0)).ravel() for i in range(3)])
    centroids /= np.maximum(np.linalg.norm(centroids, axis=1, keepdims=True), 1e-12)

    def distance(x):
        norms = np.sqrt(np.asarray(x.multiply(x).sum(axis=1)).ravel())
        if np.any(norms <= 0):
            raise RuntimeError("zero transformed row norm")
        cosine = np.asarray(x @ centroids.T) / norms[:, None]
        return 1 - cosine.max(axis=1)

    threshold = float(np.quantile(distance(train_x), .95))
    return threshold, distance(target_x)


def metrics(y_true, y_pred):
    cm = confusion_matrix(y_true, y_pred, labels=np.arange(3))
    pr, re, f1, support = precision_recall_fscore_support(y_true, y_pred, labels=np.arange(3), zero_division=0)
    return {"n": int(len(y_true)), "macro_f1": float(f1.mean()), "confusion": cm.tolist(),
            "per_class": {LABELS[i]: {"precision": float(pr[i]), "recall": float(re[i]),
                                      "f1": float(f1[i]), "support": int(support[i])} for i in range(3)}}


def split_metrics(x, y, g, kind):
    ix = np.arange(len(y))
    if kind == "group":
        tr, va = next(GroupShuffleSplit(n_splits=1, test_size=.2, random_state=SEED).split(ix, y, g))
    else:
        tr, va = train_test_split(ix, test_size=.2, random_state=SEED, stratify=y)
    clf = model().fit(x[tr], y[tr])
    pred = clf.predict(x[va])
    return {"training_cells": int(len(tr)), "validation_cells": int(len(va)),
            "training_groups": int(len(np.unique(g[tr]))), "validation_groups": int(len(np.unique(g[va]))),
            "group_overlap": int(len(set(g[tr]) & set(g[va]))),
            "train_per_class": np.bincount(y[tr], minlength=3).tolist(),
            "validation_per_class": np.bincount(y[va], minlength=3).tolist(),
            "validation_group_codes": np.unique(g[va]).tolist(), "metrics": metrics(y[va], pred)}


def macro_cm(cm):
    tp = np.diag(cm).astype(float)
    support = cm.sum(axis=1).astype(float)
    predicted = cm.sum(axis=0).astype(float)
    f1 = 2 * tp / np.maximum(support + predicted, 1)
    return float(f1.mean())


def bootstrap(y, pmain, pmajor, pcentroid, groups):
    keys = np.unique(groups)
    arrays = []
    for pred in (pmain, pmajor, pcentroid):
        arrays.append(np.stack([confusion_matrix(y[groups == g], pred[groups == g], labels=np.arange(3)) for g in keys]))
    base_scores = [metrics(y, p)["macro_f1"] for p in (pmajor, pcentroid)]
    best_index = int(np.argmax(base_scores)) + 1
    rng = np.random.default_rng(SEED)
    scores, diffs = [], []
    valid = 0
    for _ in range(2000):
        draw = rng.integers(0, len(keys), size=len(keys))
        cm = arrays[0][draw].sum(axis=0)
        if np.any(cm.sum(axis=1) == 0):
            continue
        s = macro_cm(cm)
        b = macro_cm(arrays[best_index][draw].sum(axis=0))
        scores.append(s)
        diffs.append(s - b)
        valid += 1
    return {"groups": int(len(keys)), "draws": 2000, "effective_draws": valid,
            "macro_f1_ci95": np.quantile(scores, [.025, .975]).tolist() if valid else None,
            "best_baseline": ("majority", "nearest_centroid")[best_index - 1],
            "best_baseline_macro_f1": float(base_scores[best_index - 1]),
            "paired_difference": float(metrics(y, pmain)["macro_f1"] - base_scores[best_index - 1]),
            "paired_difference_ci95": np.quantile(diffs, [.025, .975]).tolist() if valid else None}


def score_only_review(scores, group_codes, group_names):
    """Rank sample keys using model scores and sample keys only."""
    groups = {}
    for values, code in zip(scores, group_codes):
        ordered = sorted(float(value) for value in values)
        margin = ordered[2] - ordered[1]
        if margin < 0:
            raise RuntimeError("negative decision-score margin")
        key = group_names[int(code)]
        group = groups.setdefault(key, [0, 0.0])
        group[0] += 1
        group[1] += 1 / (1 + margin)
    records = [{"group": key, "n": count, "uncertainty": total / count}
               for key, (count, total) in groups.items()]
    ranked = sorted(records, key=lambda row: (-row["uncertainty"], row["group"]))
    queue = [{"rank": rank, **row} for rank, row in enumerate(ranked, 1)]
    return records, {"cells": int(len(scores)), "groups": len(records),
                     "uncertainty": "mean(1/(1+top1_minus_top2_decision_score))",
                     "ranking": queue}


def ranks(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    out = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i + 1
        while j < len(order) and values[order[j]] == values[order[i]]:
            j += 1
        rank = (i + j - 1) / 2 + 1
        for k in range(i, j):
            out[order[k]] = rank
        i = j
    return out


def spearman(a, b):
    ra, rb = ranks(a), ranks(b)
    ma, mb = sum(ra) / len(ra), sum(rb) / len(rb)
    da = sum((x - ma) ** 2 for x in ra)
    db = sum((x - mb) ** 2 for x in rb)
    return sum((x - ma) * (y - mb) for x, y in zip(ra, rb)) / (da * db) ** .5 if da and db else None


def percentile(values, p):
    x = sorted(values)
    z = (len(x) - 1) * p
    i = int(z)
    return x[i] + (x[min(i + 1, len(x) - 1)] - x[i]) * (z - i)


def review_lift_permutation(ranked, by_key, denominator):
    """Shuffle the 34 observed key error rates under no score-error association."""
    rates = [by_key[row["group"]]["error_rate"] for row in ranked]
    observed = (sum(rates[:8]) / 8) / denominator
    rng = random.Random(SEED)
    draws = 10_000
    greater_or_equal = 0
    for _ in range(draws):
        shuffled = rates.copy()
        rng.shuffle(shuffled)
        if (sum(shuffled[:8]) / 8) / denominator >= observed - 1e-12:
            greater_or_equal += 1
    return {"draws": draws, "seed": SEED, "at_least_observed": greater_or_equal,
            "p_one_sided_plus_one": (greater_or_equal + 1) / (draws + 1)}


def review_validation(score_records, ranked, y_true, y_pred, group_codes, group_names):
    """Use atlas labels only after the score-only order has been frozen."""
    errors = {row["group"]: 0 for row in score_records}
    for truth, prediction, code in zip(y_true, y_pred, group_codes):
        errors[group_names[int(code)]] += int(truth != prediction)
    records = [{**row, "errors": errors[row["group"]],
                "error_rate": errors[row["group"]] / row["n"]} for row in score_records]
    by_key = {row["group"]: row for row in records}
    uncertainty = [row["uncertainty"] for row in records]
    error = [row["error_rate"] for row in records]
    rho = spearman(uncertainty, error)
    rng = random.Random(SEED)
    draws = []
    for _ in range(2000):
        sampled = [records[rng.randrange(len(records))] for _ in records]
        value = spearman([row["uncertainty"] for row in sampled],
                         [row["error_rate"] for row in sampled])
        if value is not None:
            draws.append(value)
    top = [by_key[row["group"]] for row in ranked[:8]]
    ratio = (sum(row["error_rate"] for row in top) / 8) / (sum(error) / len(error))
    permutation = review_lift_permutation(ranked, by_key, sum(error) / len(error))
    low, high = percentile(draws, .025), percentile(draws, .975)
    return {"label_source": "HNOCA shared-atlas annot_level_1",
            "rho": rho, "rho_ci95": [low, high], "draws": 2000,
            "valid_draws": len(draws), "top8_error_rate_ratio_to_all_groups": ratio,
            "top8_lift_permutation": permutation,
            "top8": top, "group_errors": {row["group"]: {"n": row["n"],
                             "errors": row["errors"], "error_rate": row["error_rate"]} for row in records},
            "gate": bool(rho >= .35 and low > 0 and ratio >= 1.3)}


def write_review_csv(path, ranking):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=("rank", "bio_sample", "cells", "mean_score_uncertainty"))
        writer.writeheader()
        for row in ranking:
            writer.writerow({"rank": row["rank"], "bio_sample": row["group"],
                             "cells": row["n"], "mean_score_uncertainty": row["uncertainty"]})


def unfiltered_review(scores, label_codes, group_codes, label_names, group_names):
    """Freeze an all-row score queue, then check it against atlas labels."""
    if scores.shape != (len(label_codes), 3) or len(group_codes) != len(label_codes):
        raise RuntimeError("unfiltered score and metadata shapes differ")
    records, queue = score_only_review(scores, group_codes, group_names)
    truth = np.full(len(label_codes), 3, dtype=np.int8)
    for i, label in enumerate(LABELS):
        truth[label_codes == label_names.index(label)] = i
    prediction = np.argmax(scores, axis=1).astype(np.int8)
    check = review_validation(records, queue["ranking"], truth, prediction,
                              group_codes, group_names)
    outside = truth == 3
    wrong_inside = (truth != 3) & (truth != prediction)
    per_key = {}
    for row in queue["ranking"]:
        mask = group_codes == group_names.index(row["group"])
        per_key[row["group"]] = {
            "cells": int(mask.sum()),
            "outside_three_class_endpoint": int(outside[mask].sum()),
            "wrong_within_three_class_endpoint": int(wrong_inside[mask].sum()),
            "review_finding_rate": float((outside[mask] | wrong_inside[mask]).mean()),
        }
    return {
        "cohort": "all Bhaduri rows, selected by publication only",
        "score_queue": queue,
        "retrospective_check": check,
        "three_class_endpoint_coverage": {
            "all_rows": int(len(truth)),
            "inside_endpoint": int((~outside).sum()),
            "outside_endpoint": int(outside.sum()),
            "inside_fraction": float((~outside).mean()),
            "wrong_inside_endpoint": int(wrong_inside.sum()),
            "review_findings": int((outside | wrong_inside).sum()),
        },
        "group_findings": per_key,
    }


def distance_review(source_threshold, target_distances, group_codes, group_names,
                    score_queue, label_codes, label_names, full_scores):
    """Freeze source-distance and equal-rank queues before checking Bhaduri labels."""
    if len(target_distances) != len(group_codes):
        raise RuntimeError("target distances and group codes differ")
    records = []
    for code in np.unique(group_codes):
        mask = group_codes == code
        records.append({"group": group_names[int(code)], "n": int(mask.sum()),
                        "uncertainty": float(np.mean(target_distances[mask] > source_threshold))})
    distance_ranked = [{"rank": i, **row} for i, row in enumerate(
        sorted(records, key=lambda row: (-row["uncertainty"], row["group"])), 1)]
    old_ranks = {row["group"]: row["rank"] for row in score_queue["ranking"]}
    distance_ranks = {row["group"]: row["rank"] for row in distance_ranked}
    combined = [{"group": row["group"], "n": row["n"],
                 "uncertainty": -(old_ranks[row["group"]] + distance_ranks[row["group"]])}
                for row in records]
    combined_ranked = [{"rank": i, **row} for i, row in enumerate(
        sorted(combined, key=lambda row: (-row["uncertainty"], row["group"])), 1)]
    truth = np.full(len(label_codes), 3, dtype=np.int8)
    for i, label in enumerate(LABELS):
        truth[label_codes == label_names.index(label)] = i
    prediction = np.argmax(full_scores, axis=1).astype(np.int8)
    outside = (truth == 3).astype(np.int8)
    outside_check = review_validation(records, distance_ranked, outside,
                                      np.zeros(len(outside), dtype=np.int8),
                                      group_codes, group_names)
    combined_check = review_validation(combined, combined_ranked, truth, prediction,
                                       group_codes, group_names)
    return {"distance": "1 - max cosine to three Velasco training-class means",
            "source_distance_p95": source_threshold,
            "distance_queue": distance_ranked,
            "distance_outside_endpoint_check": outside_check,
            "combined_order": "ascending sum of old-margin and source-distance group ranks; group-name tie break",
            "combined_queue": combined_ranked,
            "combined_total_findings_check": combined_check}


def group_diagnostics(per_group):
    records = []
    for key, group in per_group.items():
        cm = group["confusion"]
        n = group["cells"]
        gap = [(group["pred"][i] - group["true"][i]) * 100 / n for i in range(3)]
        records.append({"bio_sample": key, "cells": n, "true": group["true"],
                        "pred": group["pred"], "confusion": cm,
                        "macro_f1": group["macro_f1"],
                        "pred_minus_true_percentage_points": gap,
                        "glioblast_false_positives": cm[0][2] + cm[1][2],
                        "glioblast_false_negatives": cm[2][0] + cm[2][1]})
    return sorted(records, key=lambda row: (-row["glioblast_false_positives"], row["bio_sample"]))


def write_group_csv(path, groups):
    fields = ["bio_sample", "cells", "true_NPC", "true_Neuron", "true_Glioblast",
              "pred_NPC", "pred_Neuron", "pred_Glioblast", "glioblast_false_positives",
              "glioblast_false_negatives", "glioblast_gap_pp", "macro_f1",
              "confusion_true_rows_pred_columns"]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for group in groups:
            writer.writerow({"bio_sample": group["bio_sample"], "cells": group["cells"],
                             **{f"true_{label}": group["true"][i] for i, label in enumerate(LABELS)},
                             **{f"pred_{label}": group["pred"][i] for i, label in enumerate(LABELS)},
                             "glioblast_false_positives": group["glioblast_false_positives"],
                             "glioblast_false_negatives": group["glioblast_false_negatives"],
                             "glioblast_gap_pp": group["pred_minus_true_percentage_points"][2],
                             "macro_f1": group["macro_f1"],
                             "confusion_true_rows_pred_columns": json.dumps(group["confusion"], separators=(",", ":"))})


def html_report(result):
    """Render solely from the JSON that was written by this run."""
    external = result["external"]
    main = external["main"]
    boot = external["bootstrap"]
    groups = external["group_diagnostics"]
    review = external["score_only_review"]
    review_check = external["review_validation"]
    cm = main["confusion"]
    fp = cm[0][2] + cm[1][2]
    glioblast = main["per_class"]["Glioblast"]
    glioblast_large_groups = sum(group["true"][2] >= 100 for group in groups)
    top = groups[:8]
    review_rows = "".join(
        f"<tr><td>{row['rank']}</td><th scope='row'><details>"
        f"<summary>{escape(row['group'].rsplit(')_', 1)[-1].lstrip('; '))}</summary>"
        f"<code>{escape(row['group'])}</code></details></th><td>{row['n']:,}</td>"
        f"<td>{row['uncertainty']:.6f}</td></tr>" for row in review["ranking"][:8])
    group_rows = "".join(
        f"<tr><th scope='row'><details><summary>{escape(g['bio_sample'].rsplit(')_', 1)[-1].lstrip('; '))}</summary>"
        f"<code>{escape(g['bio_sample'])}</code></details></th><td>{g['cells']:,}</td>"
        f"<td>{g['true'][2]:,} / {g['pred'][2]:,}</td>"
        f"<td>{g['glioblast_false_positives']:,}</td>"
        f"<td>{g['pred_minus_true_percentage_points'][2]:+.2f}</td></tr>" for g in top)
    class_rows = "".join(
        f"<tr><th scope='row'>{label}</th><td>{main['per_class'][label]['support']:,}</td>"
        f"<td>{main['per_class'][label]['precision']:.3f}</td>"
        f"<td>{main['per_class'][label]['recall']:.3f}</td>"
        f"<td>{main['per_class'][label]['f1']:.3f}</td></tr>" for label in LABELS)
    matrix_rows = "".join(
        f"<tr><th scope='row'>{label}</th>" + "".join(f"<td>{v:,}</td>" for v in cm[i]) + "</tr>"
        for i, label in enumerate(LABELS))
    source_counts = result["data"]["actual_cells"]
    source_groups = result["data"]["actual_groups"]
    random_val = result["random_validation"]
    group_val = result["group_validation"]
    rows = (
        ("Velasco random cell holdout", random_val["training_cells"], random_val["training_groups"],
         random_val["validation_cells"], random_val["validation_groups"], random_val["metrics"]["macro_f1"]),
        ("Velasco biological-sample holdout", group_val["training_cells"], group_val["training_groups"],
         group_val["validation_cells"], group_val["validation_groups"], group_val["metrics"]["macro_f1"]),
        ("Bhaduri collection source", source_counts[SOURCES[0]], source_groups[SOURCES[0]],
         source_counts[SOURCES[1]], source_groups[SOURCES[1]], main["macro_f1"]),
    )
    split_rows = "".join(f"<tr><th scope='row'>{name}</th><td>{train:,} / {tg}</td>"
                         f"<td>{test:,} / {vg}</td><td>{score:.4f}</td></tr>"
                         for name, train, tg, test, vg, score in rows)
    author_section = ""
    unfiltered_section = ""
    if "unfiltered_review" in external:
        full = external["unfiltered_review"]
        coverage = full["three_class_endpoint_coverage"]
        checked = full["retrospective_check"]
        full_rows = "".join(
            f"<tr><td>{row['rank']}</td><th scope='row'><details>"
            f"<summary>{escape(row['group'].rsplit(')_', 1)[-1].lstrip('; '))}</summary>"
            f"<code>{escape(row['group'])}</code></details></th><td>{row['n']:,}</td>"
            f"<td>{row['uncertainty']:.6f}</td>"
            f"<td>{full['group_findings'][row['group']]['review_finding_rate']:.3f}</td></tr>"
            for row in full["score_queue"]["ranking"][:8])
        unfiltered_section = (
            "<h2>Which Bhaduri samples would you review first?</h2>"
            f"<p>All {coverage['all_rows']:,} cells enter by study name; no cell label selects a row "
            "or orders a sample key. The last column checks that order afterward "
            "against HNOCA atlas labels: it counts cells outside the three trained classes and "
            "cells misclassified within them.</p>"
            "<div class='scroll'><table><thead><tr><th>Rank</th><th>Sample key</th>"
            "<th>Cells</th><th>Score uncertainty</th><th>Findings after label check</th>"
            f"</tr></thead><tbody>{full_rows}</tbody></table></div>"
            f"<p>{coverage['inside_endpoint']:,} cells have one of the three trained atlas labels; "
            f"{coverage['outside_endpoint']:,} lie outside that endpoint. The score queue reaches "
            f"{checked['top8_error_rate_ratio_to_all_groups']:.3f} times the mean finding rate "
            f"in its first eight of {full['score_queue']['groups']} sample keys, compared with "
            "random key order. This is a retrospective check under the shared atlas, not a "
            "calibrated unknown-class detector. "
            "<a href='unfiltered_review_queue.csv'>Download the score-only queue</a>; "
            "<a href='unfiltered_review.json'>see every post-label finding</a>.</p>")
    if "original_author_sensitivity" in external:
        author = external["original_author_sensitivity"]
        a = author["results"]
        n = author["eligibility"]
        author_section = (
            "<h2>Original-author annotation sensitivity</h2>"
            f"<p>Within the HNOCA-selected cohort, {n['retained']:,} cells across "
            f"{n['retained_bio_sample_keys']} keys had unambiguous Bhaduri author labels of "
            "Neuron or Radial Glia. The fixed model reached binary macro-F1 "
            f"{a['model']['macro_f1']:.4f} (key-bootstrap 95% interval "
            f"{a['model']['group_ci95'][0]:.4f}–{a['model']['group_ci95'][1]:.4f}); "
            f"the prespecified nearest-centroid baseline reached {a['nearest_centroid']['macro_f1']:.4f}. "
            f"The paired model-minus-centroid difference was "
            f"{a['nearest_centroid']['paired_model_advantage']:+.4f} "
            f"({a['nearest_centroid']['paired_advantage_ci95'][0]:+.4f} to "
            f"{a['nearest_centroid']['paired_advantage_ci95'][1]:+.4f}). "
            "The baseline order reverses under this annotation source, so this result does not "
            "establish a new model advantage. These author labels come from the same Bhaduri "
            "acquisition source via the <a href='https://zenodo.org/records/14161275'>"
            "CC BY cleaned HNOCA archive</a> and may have informed atlas harmonization; this is neither "
            "independently blind nor an unselected cohort. Full counts, exclusions, and "
            "confusion matrices are in <a href='author_label_sensitivity.json'>JSON</a>.</p>")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Phenotype Transfer Map</title>
<style>
:root{{color-scheme:light;font-family:system-ui,-apple-system,sans-serif;color:#1e2926;background:#f5f7f3}}
body{{max-width:1100px;margin:0 auto;padding:clamp(20px,5vw,60px);line-height:1.5}}
h1{{font-size:clamp(2rem,4vw,3.5rem);line-height:1.1;letter-spacing:-.035em;max-width:18ch}}
h2{{margin-top:40px}}p{{max-width:78ch}}.lede{{font-size:1.2rem}}.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin:24px 0}}
.card{{background:#fff;border:1px solid #d7dfd8;padding:18px}}.card strong{{display:block;font-size:2rem}}.card span{{color:#42574b}}
.note{{background:#e9eee8;border-left:4px solid #325c43;padding:12px 18px}}table{{border-collapse:collapse;width:100%;background:white;font-variant-numeric:tabular-nums}}
th,td{{padding:10px;border-bottom:1px solid #d7dfd8;text-align:left;vertical-align:top}}thead{{background:#e9eee8}}.scroll{{overflow-x:auto}}
code{{overflow-wrap:anywhere}}summary{{cursor:pointer;color:#24563b}}
a{{color:#24563b}}footer{{margin-top:48px;color:#42574b;font-size:.9rem}}
</style></head><body><main>
<h1>Phenotype Transfer Map</h1>
<p class="lede">The Velasco-trained three-class model reached {main['macro_f1']:.4f} macro-F1 on {main['n']:,} Bhaduri cells (34-key 95% interval {boot['macro_f1_ci95'][0]:.4f}–{boot['macro_f1_ci95'][1]:.4f}). This map pairs that cross-source result with score-based sample review priorities and a separate known-label error audit.</p>
{unfiltered_section}
<p class="note">In the selected-cohort analysis below, HNOCA labels selected NPC, Neuron, and Glioblast cells before ranking. Within that selected cohort, group order uses model scores and <code>bio_sample</code> keys only. This is not an end-to-end test on wholly unannotated input. HNOCA's shared 3,000-gene panel includes the external study. The score is unitless and uncalibrated, not an error probability. The keys identify biological samples, not verified physical organoids.</p>
<h2>Score-only group order within the selected cohort</h2>
<div class="scroll"><table><thead><tr><th>Rank</th><th>Sample key</th><th>Cells</th><th>Mean score uncertainty</th></tr></thead><tbody>{review_rows}</tbody></table></div>
<p>Open a sample name for its exact key. <a href="review_queue.csv">All {review['groups']} score-only ranks</a> omit labels and errors; the upstream three-class cell selection used HNOCA labels.</p>
<h2>How this order associated with atlas errors</h2>
<p>On these {review['groups']} Bhaduri sample keys, the score-only order and HNOCA consensus-label error rates had Spearman rho {review_check['rho']:.3f}; the 2,000-draw group bootstrap 95% interval was {review_check['rho_ci95'][0]:.3f}–{review_check['rho_ci95'][1]:.3f}. The top eight ranked groups had {review_check['top8_error_rate_ratio_to_all_groups']:.3f} times the equal-weight mean error rate across all groups. In {review_check['top8_lift_permutation']['draws']:,} shuffles of the 34 observed group error rates, {review_check['top8_lift_permutation']['at_least_observed']} reached this fixed-top-eight ratio (one-sided plus-one p={review_check['top8_lift_permutation']['p_one_sided_plus_one']:.5f}). Labels selected the three-class cells and measured errors afterward, while the ordering formula used scores alone. This is an exploratory check on shared-atlas labels, not independent blind validation.</p>
<h2>Known-label evaluation</h2>
<div class="cards"><div class="card"><strong>{main['macro_f1']:.4f}</strong><span>Bhaduri macro-F1, {main['n']:,} cells across {boot['groups']} sample keys</span></div>
<div class="card"><strong>{glioblast['precision']:.3f}</strong><span>Glioblast cell-label precision; {fp:,} false positives, no tumor diagnosis</span></div>
<div class="card"><strong>+{boot['paired_difference']:.4f}</strong><span>macro-F1 above the Velasco nearest-centroid baseline on the same cells</span></div>
<div class="card"><strong>{glioblast_large_groups}/{boot['groups']}</strong><span>sample keys with at least 100 atlas-labeled Glioblast cells</span></div></div>
<p class="note">This is a Velasco-to-Bhaduri collection-source test under HNOCA's shared 3,000-gene panel and atlas labels. Bhaduri contributed to that panel and common annotation. Biological sample keys are not verified physical organoid IDs.</p>
<h2>Known-label audit: Glioblast false positives</h2>
<div class="scroll"><table><thead><tr><th>Sample key</th><th>Three-class cells</th><th>True / predicted Glioblast</th><th>False positives</th><th>Prediction minus atlas, points</th></tr></thead><tbody>{group_rows}</tbody></table></div>
<p>This second list uses known HNOCA labels and belongs to retrospective error audit. Open a sample name for its exact <code>bio_sample</code> key. <a href="groups.csv">All 34 labeled audit rows</a> include each group's 3×3 confusion matrix; <a href="audit.json">JSON</a> has both complete lists and evaluation details.</p>
<h2>External study and uncertainty</h2>
<p>Macro-F1 {main['macro_f1']:.6f}; 95% biological-sample bootstrap interval {boot['macro_f1_ci95'][0]:.6f}–{boot['macro_f1_ci95'][1]:.6f} ({boot['effective_draws']:,}/{boot['draws']:,} valid draws). The paired advantage over {escape(boot['best_baseline'].replace('_',' '))} is {boot['paired_difference']:+.6f}, interval {boot['paired_difference_ci95'][0]:+.6f} to {boot['paired_difference_ci95'][1]:+.6f}. The majority and nearest-centroid baselines score {external['majority']['macro_f1']:.6f} and {external['nearest_centroid']['macro_f1']:.6f} on these same cells. The better baseline was selected using the Bhaduri labels, so its paired interval is conditional on that choice.</p>
<div class="scroll"><table><thead><tr><th>Class</th><th>True cells</th><th>Precision</th><th>Recall</th><th>F1</th></tr></thead><tbody>{class_rows}</tbody></table></div>
<h2>Where cells went</h2><p>True class by row, predicted class by column.</p>
<div class="scroll"><table><thead><tr><th>True / predicted</th><th>NPC</th><th>Neuron</th><th>Glioblast</th></tr></thead><tbody>{matrix_rows}</tbody></table></div>
<h2>What each test measured</h2>
<div class="scroll"><table><thead><tr><th>Evaluation</th><th>Train cells / keys</th><th>Test cells / keys</th><th>Macro-F1</th></tr></thead><tbody>{split_rows}</tbody></table></div>
<p>The two Velasco validation fits and the full-source external fit use the same fixed model specification. Their test rows differ, so their score gaps describe different evaluation protocols and do not isolate a cause. The three-class endpoint was chosen after inspecting Bhaduri class counts. Bhaduri labels also scored the external test and compared the two prespecified baselines; they did not fit the classifier or tune its settings. The shared atlas selected the gene panel across studies.</p>
<p>The atlas panel and labels are shared across studies. Predictions are a review queue, not independent composition truth, a clinical diagnosis, or a drug-toxicity readout. Astrocyte is outside this three-class score; its sample denominators are in the JSON.</p>
{author_section}
<footer>HNOCA v1 source: <a href="https://zenodo.org/records/15004818">Zenodo record 15004818</a>, CC BY 4.0. Original size {result['data']['bytes']:,} bytes; MD5 {result['data']['md5']}. Code: MIT. Python dependencies: NumPy, SciPy, scikit-learn, h5py (BSD-3-Clause), Requests (Apache-2.0). All figures on this page come from this run's <a href="audit.json">audit.json</a>.</footer>
</main></body></html>"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("organoid_audit"),
                        help="Visible HTML, JSON, labeled group CSV, and score-only queue CSV (default: ./organoid_audit)")
    parser.add_argument("--input", type=Path, help="Previously downloaded HNOCA v1 H5AD; verified before use")
    parser.add_argument("--author-label-sensitivity", action="store_true",
                        help="Also compare Neuron versus Radial Glia against preserved Bhaduri author labels")
    parser.add_argument("--unfiltered-review", action="store_true",
                        help="Order all Bhaduri sample keys before using atlas labels to check review findings")
    parser.add_argument("--distance-review", action="store_true",
                        help="Add source-only centroid distance and an equal-rank all-row review queue")
    args = parser.parse_args()
    if args.distance_review and not args.unfiltered_review:
        parser.error("--distance-review requires --unfiltered-review")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output_dir / "audit.json"
    source_hash = sha256(__file__)
    stage("start", source_sha256=source_hash)
    with tempfile.TemporaryDirectory(prefix="hnoca-source-", dir=args.output_dir) as temporary:
        source_path = args.input if args.input else Path(temporary) / "hnoca_minimal_for_mapping.h5ad"
        original = verify_source(source_path) if args.input else download(source_path)
        stage("original_verified", **original)
        with h5py.File(source_path, "r") as h:
            p, yraw, graw, pc, lc, gc = meta(h)
            rows, all_counts = choose_rows(p, yraw, pc, lc)
            y = np.array([LABELS.index(lc[v]) for v in yraw[rows]], dtype=np.int8)
            source = np.array([SOURCES.index(pc[v]) for v in p[rows]], dtype=np.int8)
            test_global_rows = rows[source == 1]
            if args.unfiltered_review:
                full_test_rows = np.flatnonzero(p == pc.index(SOURCES[1]))
                extra_test_rows = np.setdiff1d(full_test_rows, test_global_rows, assume_unique=True)
                full_test_label_codes = yraw[full_test_rows]
                full_test_group_codes = graw[full_test_rows]
                x_extra = extract(h, extra_test_rows)
                stage("unfiltered_rows_extracted", all_rows=int(len(full_test_rows)),
                      additional_rows=int(len(extra_test_rows)))
            g = graw[rows]
            if len(set(g[source == 0]) & set(g[source == 1])):
                raise RuntimeError("source group key overlap")
            stage("metadata", cells=int(len(rows)), source_class_counts=all_counts)
            x = extract(h, rows)
            x_info = {"shape": list(x.shape), "nnz": int(x.nnz), "dtype": str(x.dtype),
                      "nonzero_fraction": float(x.nnz / (x.shape[0] * x.shape[1])),
                      "value_min": float(x.data.min()), "value_max": float(x.data.max())}
            stage("matrix_extracted", **x_info)
            astro = {}
            for src in SOURCES:
                source_mask = p == pc.index(src)
                astro_mask = source_mask & (yraw == lc.index("Astrocyte"))
                c = Counter(graw[astro_mask].tolist())
                astro[src] = {"cells": int(astro_mask.sum()), "groups": len(c),
                              "groups_at_least_100": int(sum(v >= 100 for v in c.values())),
                              "group_counts": {gc[k]: int(v) for k, v in c.items()}}
    x = transform(x)
    if args.unfiltered_review:
        x_extra = transform(x_extra)
    stage("transformed", cells=x.shape[0], nnz=int(x.nnz))
    dev = source == 0
    test = source == 1
    xd, yd, gd = x[dev], y[dev], g[dev]
    xt, yt, gt = x[test], y[test], g[test]
    random_val = split_metrics(xd, yd, gd, "random")
    stage("random_validation_complete", macro_f1=random_val["metrics"]["macro_f1"])
    group_val = split_metrics(xd, yd, gd, "group")
    stage("group_validation_complete", macro_f1=group_val["metrics"]["macro_f1"])
    clf = model().fit(xd, yd)
    pred = clf.predict(xt)
    scores = clf.decision_function(xt)
    score_records, review_queue = score_only_review(scores, gt, gc)
    unfiltered_result = None
    distance_result = None
    if args.unfiltered_review:
        full_scores = np.empty((len(full_test_rows), 3), dtype=scores.dtype)
        selected_positions = np.searchsorted(full_test_rows, test_global_rows)
        extra_positions = np.searchsorted(full_test_rows, extra_test_rows)
        if not np.array_equal(full_test_rows[selected_positions], test_global_rows):
            raise RuntimeError("selected rows missing from full Bhaduri cohort")
        if not np.array_equal(full_test_rows[extra_positions], extra_test_rows):
            raise RuntimeError("additional rows missing from full Bhaduri cohort")
        full_scores[selected_positions] = scores
        full_scores[extra_positions] = clf.decision_function(x_extra)
        unfiltered_result = unfiltered_review(full_scores, full_test_label_codes,
                                               full_test_group_codes, lc, gc)
        stage("unfiltered_review_complete", **unfiltered_result["three_class_endpoint_coverage"],
              rho=unfiltered_result["retrospective_check"]["rho"])
        if args.distance_review:
            threshold, selected_distances = source_centroid_distance(xd, yd, xt)
            _, extra_distances = source_centroid_distance(xd, yd, x_extra)
            full_distances = np.empty(len(full_test_rows), dtype=selected_distances.dtype)
            full_distances[selected_positions] = selected_distances
            full_distances[extra_positions] = extra_distances
            distance_result = distance_review(threshold, full_distances, full_test_group_codes,
                                              gc, unfiltered_result["score_queue"],
                                              full_test_label_codes, lc, full_scores)
            stage("distance_review_complete", source_distance_p95=threshold,
                  outside_lift=distance_result["distance_outside_endpoint_check"]["top8_error_rate_ratio_to_all_groups"],
                  combined_lift=distance_result["combined_total_findings_check"]["top8_error_rate_ratio_to_all_groups"])
    stage("score_only_review_complete", groups=review_queue["groups"])
    majority_class = int(np.bincount(yd, minlength=3).argmax())
    pmajor = np.full(len(yt), majority_class, dtype=np.int8)
    pcentroid = nearest_centroid(xd, yd, xt)
    author_result = None
    if args.author_label_sensitivity:
        from original_author_labels import evaluate
        author_result = evaluate(test_global_rows, pred, pmajor, pcentroid, gt, macro_cm, gc)
        (args.output_dir / "author_label_sensitivity.json").write_text(
            json.dumps(author_result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        stage("author_label_sensitivity_complete", retained=author_result["eligibility"]["retained"],
              macro_f1=author_result["results"]["model"]["macro_f1"])
    stage("full_source_model_and_baselines_complete")
    per_group = {}
    for code in np.unique(gt):
        mask = gt == code
        per_group[gc[code]] = {"cells": int(mask.sum()), "true": np.bincount(yt[mask], minlength=3).tolist(),
                               "pred": np.bincount(pred[mask], minlength=3).tolist(),
                               "confusion": confusion_matrix(yt[mask], pred[mask], labels=np.arange(3)).tolist(),
                               "macro_f1": metrics(yt[mask], pred[mask])["macro_f1"]}
    result = {"source_sha256": source_hash,
              "data": {"url": URL, **original, "panel_genes": 3000, "source_class_counts": all_counts,
                       "actual_cells": {SOURCES[i]: int((source == i).sum()) for i in range(2)},
                       "actual_groups": {SOURCES[i]: int(len(np.unique(g[source == i]))) for i in range(2)},
                       "astrocyte_descriptive": astro, "x": x_info},
              "method": {"labels": LABELS, "seed": SEED, "scale_total": 10000, "transform": "log1p(panel_count * 10000 / panel_row_sum)",
                         "model": "SGDClassifier(log_loss,l2,alpha=1e-4,max_iter=30,tol=1e-3,class_weight=balanced,average=True,random_state=26)",
                         "nearest_centroid": "cosine to Velasco class mean of transformed rows"},
              "random_validation": random_val, "group_validation": group_val,
              "external": {"groups": per_group, "main": metrics(yt, pred), "majority": metrics(yt, pmajor),
                           "nearest_centroid": metrics(yt, pcentroid), "majority_class": LABELS[majority_class]}}
    result["external"]["group_diagnostics"] = group_diagnostics(per_group)
    result["external"]["bootstrap"] = bootstrap(yt, pred, pmajor, pcentroid, gt)
    result["external"]["score_only_review"] = review_queue
    result["external"]["review_validation"] = review_validation(
        score_records, review_queue["ranking"], yt, pred, gt, gc)
    if author_result is not None:
        result["external"]["original_author_sensitivity"] = author_result
    if unfiltered_result is not None:
        result["external"]["unfiltered_review"] = unfiltered_result
        (args.output_dir / "unfiltered_review.json").write_text(
            json.dumps(unfiltered_result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_review_csv(args.output_dir / "unfiltered_review_queue.csv",
                         unfiltered_result["score_queue"]["ranking"])
    if distance_result is not None:
        result["external"]["distance_review"] = distance_result
        (args.output_dir / "distance_review.json").write_text(
            json.dumps(distance_result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    stage("bootstrap_complete", **{k: result["external"]["bootstrap"][k] for k in ("effective_draws", "macro_f1_ci95", "paired_difference_ci95")})
    result["runtime"] = {"seconds": round(time.monotonic() - START, 3), "maxrss_bytes": rss(),
                         "exit_code": 0, "cpu_count": os.cpu_count(),
                         "versions": {"python": sys.version.split()[0], "numpy": np.__version__,
                                      "scipy": __import__("scipy").__version__,
                                      "sklearn": __import__("sklearn").__version__, "h5py": h5py.__version__}}
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    loaded = json.loads(output_path.read_text(encoding="utf-8"))
    html_path = args.output_dir / "audit.html"
    csv_path = args.output_dir / "groups.csv"
    review_path = args.output_dir / "review_queue.csv"
    html_path.write_text(html_report(loaded), encoding="utf-8")
    write_group_csv(csv_path, loaded["external"]["group_diagnostics"])
    write_review_csv(review_path, loaded["external"]["score_only_review"]["ranking"])
    stage("done", result_sha256=sha256(output_path), html_sha256=sha256(html_path),
          groups_sha256=sha256(csv_path), review_sha256=sha256(review_path),
          output_dir=str(args.output_dir))


if __name__ == "__main__":
    main()

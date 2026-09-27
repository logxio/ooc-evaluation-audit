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
    cm = main["confusion"]
    fp = cm[0][2] + cm[1][2]
    glioblast = main["per_class"]["Glioblast"]
    glioblast_large_groups = sum(group["true"][2] >= 100 for group in groups)
    top = groups[:5]
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
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Neural organoid phenotype audit</title>
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
<h1>Find organoid samples to review.</h1>
<p class="lede">Compare predicted NPC, Neuron, and Glioblast composition with atlas labels by biological sample key. Start with samples that have the most Glioblast false positives; check marker genes and original annotations before using their composition estimates.</p>
<div class="cards"><div class="card"><strong>{main['macro_f1']:.4f}</strong><span>Bhaduri macro-F1, {main['n']:,} cells across {boot['groups']} sample keys</span></div>
<div class="card"><strong>{glioblast['precision']:.3f}</strong><span>Glioblast precision; {fp:,} false positives</span></div>
<div class="card"><strong>+{boot['paired_difference']:.4f}</strong><span>macro-F1 above the Velasco nearest-centroid baseline on the same cells</span></div>
<div class="card"><strong>{glioblast_large_groups}/{boot['groups']}</strong><span>sample keys with at least 100 atlas-labeled Glioblast cells</span></div></div>
<p class="note">This is a Velasco-to-Bhaduri collection-source test under HNOCA's shared 3,000-gene panel and atlas labels. Bhaduri contributed to that panel and common annotation. Biological sample keys are not verified physical organoid IDs.</p>
<h2>Samples with the most Glioblast false positives</h2>
<div class="scroll"><table><thead><tr><th>Sample key</th><th>Three-class cells</th><th>True / predicted Glioblast</th><th>False positives</th><th>Prediction minus atlas, points</th></tr></thead><tbody>{group_rows}</tbody></table></div>
<p>Open a sample name for its exact <code>bio_sample</code> key. <a href="groups.csv">All 34 sample rows</a> include each group's 3×3 confusion matrix; <a href="audit.json">JSON</a> has the same counts and full evaluation details.</p>
<h2>External study and uncertainty</h2>
<p>Macro-F1 {main['macro_f1']:.6f}; 95% biological-sample bootstrap interval {boot['macro_f1_ci95'][0]:.6f}–{boot['macro_f1_ci95'][1]:.6f} ({boot['effective_draws']:,}/{boot['draws']:,} valid draws). The paired advantage over {escape(boot['best_baseline'].replace('_',' '))} is {boot['paired_difference']:+.6f}, interval {boot['paired_difference_ci95'][0]:+.6f} to {boot['paired_difference_ci95'][1]:+.6f}. The majority and nearest-centroid baselines score {external['majority']['macro_f1']:.6f} and {external['nearest_centroid']['macro_f1']:.6f} on these same cells. The better baseline was selected using the Bhaduri labels, so its paired interval is conditional on that choice.</p>
<div class="scroll"><table><thead><tr><th>Class</th><th>True cells</th><th>Precision</th><th>Recall</th><th>F1</th></tr></thead><tbody>{class_rows}</tbody></table></div>
<h2>Where cells went</h2><p>True class by row, predicted class by column.</p>
<div class="scroll"><table><thead><tr><th>True / predicted</th><th>NPC</th><th>Neuron</th><th>Glioblast</th></tr></thead><tbody>{matrix_rows}</tbody></table></div>
<h2>What each test measured</h2>
<div class="scroll"><table><thead><tr><th>Evaluation</th><th>Train cells / keys</th><th>Test cells / keys</th><th>Macro-F1</th></tr></thead><tbody>{split_rows}</tbody></table></div>
<p>The two Velasco validation fits and the full-source external fit use the same fixed model specification. Their test rows differ, so their score gaps describe different evaluation protocols and do not isolate a cause. Bhaduri labels were used to score the external test and compare the two prespecified baselines; they were not used to fit the classifier, choose genes, or tune its settings.</p>
<p>The atlas panel and labels are shared across studies. Predictions are a review queue, not independent composition truth, a clinical diagnosis, or a drug-toxicity readout. Astrocyte is outside this three-class score; its sample denominators are in the JSON.</p>
<footer>HNOCA v1 source: <a href="https://zenodo.org/records/15004818">Zenodo record 15004818</a>, CC BY 4.0. Original size {result['data']['bytes']:,} bytes; MD5 {result['data']['md5']}. Code: MIT. Python dependencies: NumPy, SciPy, scikit-learn, h5py (BSD-3-Clause), Requests (Apache-2.0). All figures on this page come from this run's <a href="audit.json">audit.json</a>.</footer>
</main></body></html>"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("organoid_audit"),
                        help="Visible HTML, JSON, and group CSV output (default: ./organoid_audit)")
    parser.add_argument("--input", type=Path, help="Previously downloaded HNOCA v1 H5AD; verified before use")
    args = parser.parse_args()
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
    majority_class = int(np.bincount(yd, minlength=3).argmax())
    pmajor = np.full(len(yt), majority_class, dtype=np.int8)
    pcentroid = nearest_centroid(xd, yd, xt)
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
    html_path.write_text(html_report(loaded), encoding="utf-8")
    write_group_csv(csv_path, loaded["external"]["group_diagnostics"])
    stage("done", result_sha256=sha256(output_path), html_sha256=sha256(html_path),
          groups_sha256=sha256(csv_path), output_dir=str(args.output_dir))


if __name__ == "__main__":
    main()

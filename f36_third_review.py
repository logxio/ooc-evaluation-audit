#!/usr/bin/env python3
"""Frozen-model, score-only review-order replay on metadata-selected Uzquiano.

The cohort is HNOCA-label-selected; findings later reuse HNOCA labels. This
does not measure independent expert review or prospective unfiltered intake.
"""

import argparse
import hashlib
import json
import random
import tempfile
from pathlib import Path

import h5py
import numpy as np
from sklearn.metrics import confusion_matrix

import f32_third_source as third
import organoid_phenotype as base

SEED = 360928
RANDOM_DRAWS = 10000


def allocate(queue, groups, budget):
    chosen, cells, findings = [], 0, 0
    for key in queue:
        row = groups[key]
        if cells + row["cells"] <= budget:
            chosen.append(key)
            cells += row["cells"]
            findings += row["label_disagreements"]
    return chosen, cells, findings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("f36_third_review"))
    parser.add_argument("--input", type=Path)
    parser.add_argument("--f32-reference", type=Path, default=Path("third_source_reference.json"))
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    reference = json.loads(args.f32_reference.read_text())
    with tempfile.TemporaryDirectory(prefix="f36-hnoca-", dir=args.output_dir) as tmp:
        source_path = args.input or Path(tmp) / "hnoca_minimal_for_mapping.h5ad"
        original = base.verify_source(source_path) if args.input else base.download(source_path)
        with h5py.File(source_path, "r") as h:
            p, y, g, pc, lc, gc = base.meta(h)
            chosen, candidates = third.choose_third(p, y, g, pc, lc)
            assert chosen == reference["selection"]["chosen"]
            assert candidates == reference["selection"]["candidates"]
            wanted = np.isin(p, [pc.index(base.SOURCES[0]), pc.index(chosen["publication"])]) & np.isin(y, [lc.index(x) for x in base.LABELS])
            rows = np.flatnonzero(wanted)
            raw = base.extract(h, rows)
            ysel = np.array([base.LABELS.index(lc[z]) for z in y[rows]], dtype=np.int8)
            is_source = p[rows] == pc.index(base.SOURCES[0])
            gsel = g[rows]
    x = base.transform(raw)
    xd, xt = x[is_source], x[~is_source]
    yd, yt = ysel[is_source], ysel[~is_source]
    gt = gsel[~is_source]
    assert len(yd) == reference["training_rows"] == 135053
    assert len(yt) == reference["test_rows"] == 236453
    assert hashlib.sha256(rows[is_source].astype('<i8').tobytes()).hexdigest() == reference["training_row_index_sha256"]
    clf = base.model().fit(xd, yd)
    pred = clf.predict(xt)
    scores = np.asarray(clf.decision_function(xt))
    assert scores.shape == (len(yt), 3)
    top_two = np.partition(scores, -2, axis=1)[:, -2:]
    margin_uncertainty = 1.0 / (1.0 + top_two[:, 1] - top_two[:, 0])
    _, centroid_distance = base.source_centroid_distance(xd, yd, xt)
    assert np.isfinite(margin_uncertainty).all() and np.isfinite(centroid_distance).all()
    ref_groups = {r["group"]: r for r in reference["per_group"]}
    groups = {}
    for code in np.unique(gt):
        mask = gt == code
        key = gc[code]
        cm = confusion_matrix(yt[mask], pred[mask], labels=np.arange(3)).tolist()
        assert cm == ref_groups[key]["model_confusion"]
        n = int(mask.sum())
        groups[key] = {
            "cells": n,
            "label_disagreements": n - sum(cm[i][i] for i in range(3)),
            "mean_margin_uncertainty": float(margin_uncertainty[mask].mean()),
            "mean_centroid_distance": float(centroid_distance[mask].mean()),
            "model_confusion": cm,
        }
    assert len(groups) == reference["test_groups"] == 47
    total_cells = sum(r["cells"] for r in groups.values())
    total_errors = sum(r["label_disagreements"] for r in groups.values())
    assert total_cells == 236453
    budget = total_cells // 5
    queues = {
        "margin_uncertainty": sorted(groups, key=lambda k: (-groups[k]["mean_margin_uncertainty"], k)),
        "centroid_distance": sorted(groups, key=lambda k: (-groups[k]["mean_centroid_distance"], k)),
    }
    rng = random.Random(SEED)
    random_counts = []
    random_yields = []
    keys = list(groups)
    for _ in range(RANDOM_DRAWS):
        rng.shuffle(keys)
        _, used, found = allocate(keys, groups, budget)
        random_counts.append(found)
        random_yields.append(found / used)
    random_counts.sort()
    random_yields.sort()
    quantile = lambda values, p: values[int((len(values) - 1) * p)]
    results = {}
    rates = {k: v["label_disagreements"] / v["cells"] for k, v in groups.items()}
    all_equal_key_rate = sum(rates.values()) / len(rates)
    for name, queue in queues.items():
        selected, used, found = allocate(queue, groups, budget)
        results[name] = {
            "ranked_keys": queue,
            "selected_keys": selected,
            "reviewed_cells": used,
            "found": found,
            "missed": total_errors - found,
            "finding_share": found / total_errors,
            "findings_per_reviewed_cell": found / used,
            "yield_lift_over_all_cells": (found / used) / (total_errors / total_cells),
            "random_fraction_at_least_found": sum(x >= found for x in random_counts) / RANDOM_DRAWS,
            "random_fraction_at_least_yield": sum(x >= found / used for x in random_yields) / RANDOM_DRAWS,
            "top8_equal_key_error_rate_lift": (sum(rates[k] for k in queue[:8]) / 8) / all_equal_key_rate,
        }
    output = {
        "schema": "pazhou.f36.third_source_review.v1",
        "source": {"url": base.URL, **original},
        "selection": reference["selection"],
        "training_publication": reference["training_publication"],
        "training_rows": len(yd),
        "test_publication": chosen["publication"],
        "test_rows": total_cells,
        "test_groups": len(groups),
        "total_label_disagreements": total_errors,
        "budget_cells": budget,
        "score_definition": "margin=1/(1+top-two SGD decision-score gap), averaged per bio_sample; comparator=mean cosine distance to nearest source-trained class centroid",
        "allocation": "whole bio_sample keys in score order; accept any key fitting floor(test rows/5), skip otherwise",
        "random_seed": SEED,
        "random_draws": RANDOM_DRAWS,
        "random_count_95_range": [quantile(random_counts, .025), quantile(random_counts, .975)],
        "random_yield_95_range": [quantile(random_yields, .025), quantile(random_yields, .975)],
        "queues": results,
        "per_group": groups,
        "limits": "HNOCA labels selected the three-class cohort and define later disagreements. This is another acquisition publication but shares HNOCA labels and panel; no independent expert labels, complete unfiltered intake, measured labor or prospective use.",
    }
    (args.output_dir / "review.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({name: {k: row[k] for k in ("reviewed_cells", "found", "missed", "random_fraction_at_least_found", "top8_equal_key_error_rate_lift")} for name, row in results.items()}, indent=2))


if __name__ == "__main__":
    main()

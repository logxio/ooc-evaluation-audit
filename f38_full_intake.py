#!/usr/bin/env python3
"""Replay frozen score orders on every cell in the selected third publication.

The publication is fixed by the F32 metadata rule. HNOCA labels are used only
after ranking to count outside-endpoint cells and three-class disagreements.
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


SEED = 380928
RANDOM_DRAWS = 10000


def allocate(order, groups, budget):
    chosen = []
    cells = within = outside = 0
    for key in order:
        row = groups[key]
        if cells + row["cells"] <= budget:
            chosen.append(key)
            cells += row["cells"]
            within += row["within_error"]
            outside += row["outside_endpoint"]
    return chosen, cells, within, outside


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("f38_full_intake"))
    parser.add_argument("--input", type=Path)
    parser.add_argument("--f32-reference", type=Path, default=Path("third_source_reference.json"))
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    reference = json.loads(args.f32_reference.read_text())
    with tempfile.TemporaryDirectory(prefix="f38-hnoca-", dir=args.output_dir) as tmp:
        source_path = args.input or Path(tmp) / "hnoca_minimal_for_mapping.h5ad"
        original = base.verify_source(source_path) if args.input else base.download(source_path)
        with h5py.File(source_path, "r") as h:
            p, y, g, pc, lc, gc = base.meta(h)
            chosen, candidates = third.choose_third(p, y, g, pc, lc)
            assert chosen == reference["selection"]["chosen"]
            assert candidates == reference["selection"]["candidates"]
            source_code = pc.index(base.SOURCES[0])
            target_code = pc.index(chosen["publication"])
            label_codes = [lc.index(label) for label in base.LABELS]
            wanted = ((p == source_code) & np.isin(y, label_codes)) | (p == target_code)
            rows = np.flatnonzero(wanted)
            raw = base.extract(h, rows)
            is_source = p[rows] == source_code
            ycodes = y[rows]
            group_codes = g[rows]
    labels = np.full(len(rows), -1, dtype=np.int8)
    for i, code in enumerate(label_codes):
        labels[ycodes == code] = i
    assert int(is_source.sum()) == reference["training_rows"] == 135053
    assert hashlib.sha256(rows[is_source].astype("<i8").tobytes()).hexdigest() == reference["training_row_index_sha256"]
    x = base.transform(raw)
    xd, xt = x[is_source], x[~is_source]
    yd, yt = labels[is_source], labels[~is_source]
    gt = group_codes[~is_source]
    assert np.all(yd >= 0)
    clf = base.model().fit(xd, yd)
    pred = clf.predict(xt)
    scores = np.asarray(clf.decision_function(xt))
    assert scores.shape == (len(yt), 3)
    top_two = np.partition(scores, -2, axis=1)[:, -2:]
    margin = 1.0 / (1.0 + top_two[:, 1] - top_two[:, 0])
    _, distance = base.source_centroid_distance(xd, yd, xt)
    assert np.isfinite(margin).all() and np.isfinite(distance).all()
    ref_groups = {row["group"]: row for row in reference["per_group"]}
    groups = {}
    for code in np.unique(gt):
        mask = gt == code
        key = gc[code]
        included = mask & (yt >= 0)
        matrix = confusion_matrix(yt[included], pred[included], labels=np.arange(3)).tolist()
        if key in ref_groups:
            assert matrix == ref_groups[key]["model_confusion"]
        else:
            assert int(included.sum()) == 0
        groups[key] = {
            "cells": int(mask.sum()),
            "selected_three_class_cells": int(included.sum()),
            "within_error": int(np.count_nonzero(included & (pred != yt))),
            "outside_endpoint": int(np.count_nonzero(mask & (yt < 0))),
            "mean_margin_uncertainty": float(margin[mask].mean()),
            "mean_centroid_distance": float(distance[mask].mean()),
            "selected_confusion": matrix,
        }
    assert sum(row["selected_three_class_cells"] for row in groups.values()) == reference["test_rows"] == 236453
    assert set(ref_groups) <= set(groups)
    total_cells = len(yt)
    total_within = sum(row["within_error"] for row in groups.values())
    total_outside = sum(row["outside_endpoint"] for row in groups.values())
    assert total_within == 7282
    assert total_cells == 236453 + total_outside
    budget = total_cells // 5
    queues = {
        "margin_uncertainty": sorted(groups, key=lambda k: (-groups[k]["mean_margin_uncertainty"], k)),
        "centroid_distance": sorted(groups, key=lambda k: (-groups[k]["mean_centroid_distance"], k)),
    }
    rng = random.Random(SEED)
    keys = list(groups)
    random_total = []
    random_outside = []
    for _ in range(RANDOM_DRAWS):
        rng.shuffle(keys)
        _, _, within, outside = allocate(keys, groups, budget)
        random_total.append(within + outside)
        random_outside.append(outside)
    random_total.sort()
    random_outside.sort()
    quantile = lambda values, p: values[int((len(values) - 1) * p)]
    results = {}
    for name, order in queues.items():
        selected, reviewed, within, outside = allocate(order, groups, budget)
        found = within + outside
        results[name] = {
            "ranked_keys": order,
            "selected_keys": selected,
            "reviewed_cells": reviewed,
            "found_within_error": within,
            "found_outside_endpoint": outside,
            "found_total": found,
            "missed_within_error": total_within - within,
            "missed_outside_endpoint": total_outside - outside,
            "missed_total": total_within + total_outside - found,
            "findings_per_reviewed_cell": found / reviewed,
            "random_fraction_at_least_total": sum(n >= found for n in random_total) / RANDOM_DRAWS,
            "random_fraction_at_least_outside": sum(n >= outside for n in random_outside) / RANDOM_DRAWS,
        }
    output = {
        "schema": "pazhou.f38.full_intake.v1",
        "source": {"url": base.URL, **original},
        "selection": reference["selection"],
        "training_publication": reference["training_publication"],
        "training_rows": int(is_source.sum()),
        "test_publication": chosen["publication"],
        "test_rows": total_cells,
        "test_groups": len(groups),
        "selected_three_class_rows": reference["test_rows"],
        "total_within_error": total_within,
        "total_outside_endpoint": total_outside,
        "total_review_findings": total_within + total_outside,
        "budget_cells": budget,
        "allocation": "score-only whole bio_sample keys, fitting within floor(all test rows/5), skip otherwise",
        "score_definition": "margin=mean 1/(1+top-two SGD score gap); comparator=mean source-trained nearest-centroid cosine distance",
        "review_endpoint": "outside HNOCA three-class endpoint or wrong within-class prediction, checked after ranking",
        "random_seed": SEED,
        "random_draws": RANDOM_DRAWS,
        "random_total_95_range": [quantile(random_total, .025), quantile(random_total, .975)],
        "random_outside_95_range": [quantile(random_outside, .025), quantile(random_outside, .975)],
        "queues": results,
        "per_group": groups,
        "limits": "Publication selected using HNOCA metadata and labels; same harmonized labels define later findings. Full row intake removes three-class row eligibility from the queue but is still retrospective and not independent expert review or measured labor.",
    }
    (args.output_dir / "review.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"test_rows": total_cells, "groups": len(groups), "within": total_within, "outside": total_outside,
                      "budget": budget, "queues": {name: {key: row[key] for key in ("reviewed_cells", "found_total", "found_outside_endpoint", "missed_total", "random_fraction_at_least_total", "random_fraction_at_least_outside")} for name, row in results.items()}}, indent=2))


if __name__ == "__main__":
    main()

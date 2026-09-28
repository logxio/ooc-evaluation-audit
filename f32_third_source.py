#!/usr/bin/env python3
"""F32 fixed Velasco model on a metadata-selected third HNOCA publication.

Selection uses publication, atlas class counts and sample-key counts only,
before fitting or inspecting any candidate predictions. It is still HNOCA's
shared gene panel and harmonized labels, not an independent blind gold label.
"""

import argparse
import hashlib
import json
import tempfile
from pathlib import Path

import h5py
import numpy as np
from sklearn.metrics import confusion_matrix

import organoid_phenotype as base


def choose_third(p, y, g, pc, lc):
    label_codes = [lc.index(label) for label in base.LABELS]
    source_code = pc.index(base.SOURCES[0])
    source_keys = set(g[p == source_code])
    candidates = []
    for code, publication in enumerate(pc):
        if publication in base.SOURCES:
            continue
        mask = p == code
        counts = {label: int(np.count_nonzero(mask & (y == label_codes[i])))
                  for i, label in enumerate(base.LABELS)}
        included = mask & np.isin(y, label_codes)
        total = int(np.count_nonzero(included))
        keys = set(g[included])
        eligible = 10000 <= total <= 250000 and min(counts.values()) >= 100 and len(keys) >= 5 and not (keys & source_keys)
        candidates.append({"publication": publication, "three_class_cells": total,
                           "class_counts": counts, "sample_keys": len(keys), "eligible": bool(eligible)})
    ranked = sorted((row for row in candidates if row["eligible"]),
                    key=lambda row: (-row["three_class_cells"], row["publication"]))
    if not ranked:
        raise RuntimeError("no third publication met the frozen metadata-only eligibility rule")
    return ranked[0], candidates


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("f32_third_source"))
    parser.add_argument("--input", type=Path)
    args = parser.parse_args()
    args.output_dir.mkdir(exist_ok=True, parents=True)
    with tempfile.TemporaryDirectory(prefix="f32-hnoca-", dir=args.output_dir) as tmp:
        source_path = args.input or Path(tmp) / "hnoca_minimal_for_mapping.h5ad"
        original = base.verify_source(source_path) if args.input else base.download(source_path)
        base.stage("source_verified", **original)
        with h5py.File(source_path, "r") as h:
            p, y, g, pc, lc, gc = base.meta(h)
            chosen, candidates = choose_third(p, y, g, pc, lc)
            selection = {"rule": "Exclude Velasco/Bhaduri; three-class rows 10000..250000; each of NPC/Neuron/Glioblast >=100; >=5 bio_sample keys; no group-key overlap with Velasco; choose largest row count then lexicographic publication name, without model outcomes",
                         "chosen": chosen, "candidates": candidates}
            (args.output_dir / "selection.json").write_text(json.dumps(selection, ensure_ascii=False, indent=2) + "\n")
            base.stage("third_selected_before_fit", publication=chosen["publication"], cells=chosen["three_class_cells"])
            wanted = np.isin(p, [pc.index(base.SOURCES[0]), pc.index(chosen["publication"])]) & np.isin(y, [lc.index(x) for x in base.LABELS])
            rows = np.flatnonzero(wanted)
            raw = base.extract(h, rows)
            ysel = np.array([base.LABELS.index(lc[z]) for z in y[rows]], dtype=np.int8)
            is_source = p[rows] == pc.index(base.SOURCES[0])
            gsel = g[rows]
        base.stage("rows_extracted", total=int(len(rows)), train=int(is_source.sum()), test=int((~is_source).sum()), nnz=int(raw.nnz))
    x = base.transform(raw)
    xd, xt = x[is_source], x[~is_source]
    yd, yt = ysel[is_source], ysel[~is_source]
    gt = gsel[~is_source]
    assert len(yd) == 135053 and len(yt) == chosen["three_class_cells"]
    clf = base.model().fit(xd, yd)
    pred = clf.predict(xt)
    majority = np.full(len(yt), int(np.bincount(yd, minlength=3).argmax()), dtype=np.int8)
    centroid = base.nearest_centroid(xd, yd, xt)
    group_rows = []
    for code in np.unique(gt):
        mask = gt == code
        group_rows.append({"group": gc[code], "cells": int(mask.sum()),
                           "model_confusion": confusion_matrix(yt[mask], pred[mask], labels=np.arange(3)).tolist(),
                           "centroid_confusion": confusion_matrix(yt[mask], centroid[mask], labels=np.arange(3)).tolist()})
    main_cms = np.array([r["model_confusion"] for r in group_rows], dtype=np.int64)
    centroid_cms = np.array([r["centroid_confusion"] for r in group_rows], dtype=np.int64)
    rng = np.random.default_rng(base.SEED)
    paired_draws = []
    for _ in range(2000):
        draw = rng.integers(0, len(group_rows), size=len(group_rows))
        cm = main_cms[draw].sum(axis=0)
        baseline_cm = centroid_cms[draw].sum(axis=0)
        if np.any(cm.sum(axis=1) == 0):
            continue
        paired_draws.append(base.macro_cm(cm) - base.macro_cm(baseline_cm))
    assert paired_draws
    preset_centroid_comparison = {"difference": base.metrics(yt, pred)["macro_f1"] - base.metrics(yt, centroid)["macro_f1"],
                                  "group_bootstrap_draws": 2000, "effective_draws": len(paired_draws),
                                  "ci95": np.quantile(paired_draws, [.025, .975]).tolist()}
    result = {"schema": "pazhou.f32.third_source.v1", "source": {"url": base.URL, **original},
              "selection": selection, "training_publication": base.SOURCES[0],
              "training_rows": int(len(yd)), "training_row_index_sha256": hashlib.sha256(rows[is_source].astype('<i8').tobytes()).hexdigest(),
              "test_publication": chosen["publication"], "test_rows": int(len(yt)),
              "test_groups": len(group_rows), "model": base.metrics(yt, pred),
              "source_majority": base.metrics(yt, majority), "nearest_centroid": base.metrics(yt, centroid),
              "paired_vs_preset_centroid": preset_centroid_comparison,
              "group_bootstrap": base.bootstrap(yt, pred, majority, centroid, gt),
              "per_group": group_rows,
              "limit": "Third acquisition publication is chosen from shared HNOCA metadata before model outcomes; labels and gene panel still come from shared HNOCA, no author-label or physical-chip gold standard, and this does not repair Bhaduri's failed unfiltered review queue."}
    (args.output_dir / "third_source.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    base.stage("done", publication=chosen["publication"], rows=len(yt), groups=len(group_rows),
               macro_f1=result["model"]["macro_f1"], centroid_macro_f1=result["nearest_centroid"]["macro_f1"])


if __name__ == "__main__":
    main()

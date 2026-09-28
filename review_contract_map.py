#!/usr/bin/env python3
"""F32 exploratory review-contract map from frozen F18/F24/F27/F29/F30 outputs.

The five rows below answer different retrospective questions. They are not a
causal or prospective comparison. No model is fit or tuned in this script.
"""

import csv
import hashlib
import json
import random
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent
F18 = ROOT / "review_reference/source/audit.json"
F24 = ROOT / "review_reference/source/author_label_sensitivity.json"
F27 = ROOT / "review_reference/source/unfiltered_review.json"
F29 = ROOT / "review_reference/source/distance_review.json"
F30 = ROOT / "review_reference/source/image_case.json"
OUT = ROOT / "review_reference/review_contract_map.json"
CSV = ROOT / "review_reference/review_contract_map.csv"
SVG = ROOT / "review_reference/review_contract_map.svg"
SEED = 320926


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rate(cm):
    return (sum(map(sum, cm)) - sum(cm[i][i] for i in range(len(cm)))) / sum(map(sum, cm))


def measure(name, queue, outcomes):
    keys = list(outcomes)
    assert len(keys) == 34 and len(queue) == 34 and set(keys) == set(queue)
    rates = {key: outcomes[key]["errors"] / outcomes[key]["n"] for key in keys}
    assert all(outcomes[key]["n"] > 0 for key in keys)
    top = queue[:8]
    top_mean = sum(rates[k] for k in top) / 8
    all_mean = sum(rates.values()) / 34
    ratio = top_mean / all_mean
    rng = random.Random(SEED)
    observed = ratio
    hits = 0
    for _ in range(10000):
        shuffled = list(rates.values())
        rng.shuffle(shuffled)
        den = sum(shuffled) / 34
        if (sum(shuffled[:8]) / 8) / den >= observed - 1e-12:
            hits += 1
    draws = []
    for _ in range(2000):
        sampled = [rng.randrange(34) for _ in range(34)]
        selected = [(i, rates[queue[i]]) for i in sampled]
        selected.sort(key=lambda pair: pair[0])
        den = sum(v for _, v in selected) / 34
        if den > 0:
            draws.append((sum(v for _, v in selected[:8]) / 8) / den)
    draws.sort()
    return {
        "contract": name,
        "group_count": len(queue),
        "outcome_rows": sum(v["n"] for v in outcomes.values()),
        "outcome_errors": sum(v["errors"] for v in outcomes.values()),
        "top8_keys": top,
        "top8_equal_key_rate": top_mean,
        "all_equal_key_rate": all_mean,
        "top8_lift": ratio,
        "exploratory_permutation_p_one_sided": (hits + 1) / 10001,
        "exploratory_group_bootstrap_95": [draws[int(.025 * (len(draws) - 1))], draws[int(.975 * (len(draws) - 1))]],
        "per_group": {k: {**outcomes[k], "rate": rates[k], "rank": queue.index(k) + 1} for k in queue},
    }


def svg(rows, image):
    width, height = 1160, 545
    x0, x1, scale = 350, 810, 190
    blocks = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
              '<rect width="1160" height="545" fill="white"/>',
              '<style>text{font-family:Arial,sans-serif;fill:#111} .title{font-size:26px;font-weight:700} .sub{font-size:15px;fill:#444} .lab{font-size:16px} .num{font-size:18px;font-weight:700}</style>',
              '<text x="44" y="48" class="title">Review Contract Map: where the sample order breaks</text>',
              '<text x="44" y="77" class="sub">34 Bhaduri sample keys; rows change eligibility, error endpoint or order. 1.0 = equal-key mean.</text>',
              f'<line x1="{x0+scale}" y1="115" x2="{x0+scale}" y2="385" stroke="#777" stroke-dasharray="4 4"/>',
              '<text x="531" y="107" class="sub">1.0</text>']
    labels = ["Selected / HNOCA / fixed score", "Selected / author binary / fixed score",
              "All rows / review findings / fixed score", "All rows / review findings / rescored",
              "All rows / review findings / combined"]
    for i, (row, label) in enumerate(zip(rows, labels)):
        y = 142 + 55 * i
        lift = row["top8_lift"]
        start, end = sorted((x0 + scale, x0 + scale * lift))
        color = "#1a6a51" if lift >= 1 else "#a3412c"
        blocks.append(f'<text x="44" y="{y+5}" class="lab">{escape(label)}</text>')
        blocks.append(f'<rect x="{start:.1f}" y="{y-12}" width="{max(2,end-start):.1f}" height="22" fill="{color}"/>')
        blocks.append(f'<text x="{x1}" y="{y+5}" class="num">{lift:.3f}×</text>')
    blocks.extend(['<line x1="44" y1="410" x2="1116" y2="410" stroke="#aaa"/>',
                   '<text x="44" y="444" class="title" font-size="18">Separate OoC image decision tradeoff</text>',
                   f'<text x="44" y="475" class="lab">Same {image["n"]} images: good-image false flags {image["source_good_false_flags"]} → {image["grouped_good_false_flags"]}; bad-image misses {image["source_bad_misses"]} → {image["grouped_bad_misses"]}.</text>',
                   '<text x="44" y="505" class="sub">Post hoc prefix selection; different image training/validation protocols. No cell–image pooled metric, causal claim, or prospective saving.</text>',
                   '</svg>'])
    return "\n".join(blocks) + "\n"


def main():
    a, b, c, d, e = map(read, [F18, F24, F27, F29, F30])
    fixed = [r["group"] for r in a["external"]["score_only_review"]["ranking"]]
    selected = a["external"]["review_validation"]["group_errors"]
    author = {r["bio_sample"]: {"n": r["cells"], "errors": round(rate(r["model_confusion"]) * r["cells"])} for r in b["per_group"]}
    full = {k: {"n": r["cells"], "errors": r["outside_three_class_endpoint"] + r["wrong_within_three_class_endpoint"]} for k, r in c["group_findings"].items()}
    assert set(fixed) == set(selected) == set(author) == set(full)
    assert sum(r["n"] for r in selected.values()) == 207871
    assert sum(r["n"] for r in author.values()) == 175160
    assert sum(r["n"] for r in full.values()) == 223453
    rows = [
        measure("selected_hnoca_frozen_queue", fixed, selected),
        measure("selected_author_binary_frozen_queue", fixed, author),
        measure("unfiltered_combined_findings_frozen_selected_queue", fixed, full),
        measure("unfiltered_combined_findings_full_rescored_queue", [r["group"] for r in c["score_queue"]["ranking"]], full),
        measure("unfiltered_combined_findings_f29_combined_queue", [r["group"] for r in d["combined_queue"]], full),
    ]
    selected_queue = {r["group"]: r for r in a["external"]["score_only_review"]["ranking"]}
    full_queue = {r["group"]: r for r in c["score_queue"]["ranking"]}
    dilution = []
    for key in fixed:
        inside, all_rows = selected_queue[key], full_queue[key]
        outside = all_rows["n"] - inside["n"]
        assert outside == c["group_findings"][key]["outside_three_class_endpoint"]
        outside_uncertainty = ((all_rows["n"] * all_rows["uncertainty"] - inside["n"] * inside["uncertainty"]) / outside) if outside else None
        assert outside_uncertainty is None or outside_uncertainty >= -1e-9
        dilution.append({"group": key, "selected_rank": inside["rank"], "full_rank": all_rows["rank"],
                         "rank_drop": all_rows["rank"] - inside["rank"], "selected_rows": inside["n"],
                         "outside_rows": outside, "all_rows": all_rows["n"],
                         "selected_uncertainty": inside["uncertainty"], "outside_uncertainty_derived": outside_uncertainty,
                         "full_uncertainty": all_rows["uncertainty"],
                         "full_review_finding_rate": full[key]["errors"] / full[key]["n"]})
    dilution.sort(key=lambda r: (-r["rank_drop"], r["group"]))
    image = e["selected_group"]
    assert image["n"] == 38 and image["group"] == "230529"
    out = {
        "schema": "pazhou.f32.review_contract_map.v1",
        "definition": "Each contract fixes eligible rows, a score-only sample-key queue, and a later error endpoint. The displayed measure is mean top-eight per-key error rate divided by mean all-34 per-key error rate; no pooling across datasets.",
        "source_sha256": {str(p.relative_to(ROOT)): sha(p) for p in [F18, F24, F27, F29, F30]},
        "seed": SEED,
        "selection_status": "All endpoint contrasts and F29 queue are retrospective and partly chosen after F27 failure; permutation/bootstrap are descriptive, not independent confirmation.",
        "limit": "Author binary endpoint changes labels and retained rows within the same Bhaduri acquisition; full-cohort outcome adds outside-endpoint findings. Fixed selected queue itself depends on HNOCA preselection. Source/grouped OoC predictions come from different training and test protocols.",
        "contracts": rows,
        "image_case": image,
        "key_overlap": {
            "selected_vs_full_score_top8": len(set(rows[0]["top8_keys"]) & set(rows[3]["top8_keys"])),
            "selected_vs_f29_top8": len(set(rows[0]["top8_keys"]) & set(rows[4]["top8_keys"])),
        },
        "endpoint_dilution": {"derivation": "outside mean uncertainty = (all_rows * full_mean - selected_rows * selected_mean) / outside_rows; same fixed model, score and sample key", "all_34_keys": dilution, "largest_rank_drop": dilution[0]},
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    with CSV.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["contract", "group_count", "outcome_rows", "outcome_errors", "top8_equal_key_rate", "all_equal_key_rate", "top8_lift", "exploratory_permutation_p_one_sided", "bootstrap_low", "bootstrap_high"], lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row[k] for k in writer.fieldnames if k in row} | {"bootstrap_low": row["exploratory_group_bootstrap_95"][0], "bootstrap_high": row["exploratory_group_bootstrap_95"][1]})
    SVG.write_text(svg(rows, image))
    for row in rows:
        print(row["contract"], row["outcome_rows"], f'{row["top8_lift"]:.6f}', row["exploratory_group_bootstrap_95"])


if __name__ == "__main__":
    main()

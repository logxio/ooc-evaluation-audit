#!/usr/bin/env python3
"""Exploratory fixed-cell-budget replay of frozen F32 sample-key queues.

Whole-key selection only; later known-label findings are counted after selection.
This is same-source retrospective analysis, never measured researcher time.
"""

import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "review_reference/review_contract_map.json"
OUTPUT = ROOT / "review_reference/fixed_budget.json"
SEED = 350928
DRAW_COUNT = 10000


def allocate(queue, groups, budget):
    selected = []
    used = 0
    findings = 0
    for key in queue:
        item = groups[key]
        if used + item["n"] <= budget:
            selected.append(key)
            used += item["n"]
            findings += item["errors"]
    return selected, used, findings


def run(row, rng):
    groups = row["per_group"]
    queue = sorted(groups, key=lambda key: groups[key]["rank"])
    assert len(queue) == 34
    total_cells = sum(v["n"] for v in groups.values())
    total_findings = sum(v["errors"] for v in groups.values())
    assert total_cells == row["outcome_rows"]
    assert total_findings == row["outcome_errors"]
    budget = total_cells // 5
    selected, used, findings = allocate(queue, groups, budget)
    random_findings = []
    random_yields = []
    for _ in range(DRAW_COUNT):
        shuffled = queue[:]
        rng.shuffle(shuffled)
        _, cells, errors = allocate(shuffled, groups, budget)
        random_findings.append(errors)
        random_yields.append(errors / cells)
    random_findings.sort()
    random_yields.sort()
    q = lambda xs, fraction: xs[int((len(xs) - 1) * fraction)]
    return {
        "contract": row["contract"],
        "total_cells": total_cells,
        "total_findings": total_findings,
        "budget_cells": budget,
        "selected_keys": selected,
        "selected_key_count": len(selected),
        "reviewed_cells": used,
        "reviewed_fraction": used / total_cells,
        "found": findings,
        "missed": total_findings - findings,
        "findings_fraction": findings / total_findings,
        "findings_per_reviewed_cell": findings / used,
        "yield_lift_over_all_cells": (findings / used) / (total_findings / total_cells),
        "random_findings_median": q(random_findings, .5),
        "random_findings_95_range": [q(random_findings, .025), q(random_findings, .975)],
        "random_yield_median": q(random_yields, .5),
        "random_yield_95_range": [q(random_yields, .025), q(random_yields, .975)],
        "random_fraction_at_least_observed_findings": sum(v >= findings for v in random_findings) / DRAW_COUNT,
        "random_fraction_at_least_observed_yield": sum(v >= findings / used for v in random_yields) / DRAW_COUNT,
    }


def main():
    source = json.loads(SOURCE.read_text())
    rng = random.Random(SEED)
    rows = [run(row, rng) for row in source["contracts"]]
    result = {
        "schema": "pazhou.f35.fixed_budget.v1",
        "source": SOURCE.name,
        "seed": SEED,
        "random_draw_count": DRAW_COUNT,
        "allocation": "floor(total cells / 5); in frozen score rank order, select any complete key that still fits and skip each that does not; no label used to allocate",
        "limits": "Same-source retrospective replay. The 20% cell count is a proxy, not measured human time. Review findings use known harmonized labels, not independently adjudicated errors. Random permutations are descriptive, not prospective confirmation.",
        "contracts": rows,
    }
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    for row in rows:
        print(row["contract"], row["reviewed_cells"], row["found"], row["missed"], f'{row["yield_lift_over_all_cells"]:.3f}', row["random_findings_95_range"])


if __name__ == "__main__":
    main()

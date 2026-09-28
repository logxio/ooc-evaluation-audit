#!/usr/bin/env python3
"""Check whether a saved sample-review order may be reused for an intake.

This checks metadata invariants only. It never inspects outcome labels or infers
that a review order improves yield on a new acquisition.
"""

import argparse
import json
from pathlib import Path


FIELDS = (
    "publication",
    "eligible_rows",
    "label_scheme",
    "score_definition",
    "group_key",
    "review_endpoint",
)


def check(frozen, intake):
    missing = [f"{side}.{key}" for side, record in (("frozen", frozen), ("intake", intake)) for key in FIELDS if key not in record]
    if missing:
        raise ValueError("Missing contract fields: " + ", ".join(missing))
    changed = [
        {"field": key, "frozen": frozen[key], "intake": intake[key]}
        for key in FIELDS if frozen[key] != intake[key]
    ]
    return {
        "status": "RECOMPUTE_AND_VALIDATE" if changed else "MATCHES_FROZEN_METADATA",
        "changed_fields": changed,
        "action": (
            "Do not reuse this sample order. Compute a new score-only order and measure its review yield against the specified endpoint on independently reviewed intake."
            if changed else
            "Metadata matches. Reuse only within the documented cohort; retrospective association does not establish prospective review benefit."
        ),
        "limits": "Matching metadata is necessary but insufficient. This gate does not measure correctness, labor time, or clinical validity.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="JSON with frozen_contract and candidate_intakes")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    frozen = manifest["frozen_contract"]
    cases = manifest["candidate_intakes"]
    result = {name: check(frozen, intake) for name, intake in cases.items()}
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

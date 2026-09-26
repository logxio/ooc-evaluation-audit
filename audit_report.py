#!/usr/bin/env python3
"""Export an offline image-evaluation audit from frozen OoC inputs or JSONL records."""
from __future__ import annotations

import argparse
import hashlib
from html import escape
import json
from pathlib import Path
import resource
import sys
import time

from evaluation_audit import audit


def peak_rss_mb() -> float:
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak / (1024 * 1024) if sys.platform == "darwin" else peak / 1024


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def near(actual, expected, name: str) -> None:
    if actual is None or expected is None or abs(actual - expected) > 1e-12:
        raise ValueError(f"frozen F4 mismatch at {name}: {actual!r} != {expected!r}")


def ooc_records(args: argparse.Namespace) -> tuple[list[dict], list[dict], dict]:
    from f4_paired import fit_split, load_data, reproduce

    grouped_parts, source_parts, data = load_data(args)
    grouped_fit = fit_split(grouped_parts, data["features"])
    source_fit = fit_split(source_parts, data["features"])
    reproduction = {
        "F2": reproduce(grouped_parts, grouped_fit, args.f2_result),
        "F3": reproduce(source_parts, source_fit, args.f3_result),
    }

    def records(parts: dict, fitted: dict) -> list[dict]:
        result = []
        for split in ("train", "val", "test"):
            for row in parts[split]:
                result.append({"id": row["id"], "group": row["id"][:6],
                               "label": row["label"] - 1, "split": split,
                               "prediction": int(fitted["test_prediction_by_id"][row["id"]])
                               if split == "test" else None,
                               "subgroup": row["cell_type"]})
        return result

    source_rows = records(source_parts, source_fit)
    grouped_rows = records(grouped_parts, grouped_fit)
    metadata = {
        "source": "https://zenodo.org/records/10203721",
        "group_definition": "First six digits of image ID; date-like acquisition-context proxy, not a physical chip ID",
        "group_caveat": "These prefixes do not identify physical chips or prove chip-level leakage.",
        "model": "Frozen F2/F3 29-feature random forest with validation-selected threshold",
        "source_threshold": source_fit["threshold"],
        "grouped_threshold": grouped_fit["threshold"],
        "training_and_validation": "The two models use different training rows, validation rows, and thresholds.",
        "reproduced_frozen_results": reproduction,
        "input_sha256": {key: hashlib.sha256(path.read_bytes()).hexdigest() for key, path in {
            "table": args.table, "source_split_map": args.mapping,
            "frozen_features": args.features, "F2": args.f2_result,
            "F3": args.f3_result, "F4": args.f4_result}.items()},
    }
    return source_rows, grouped_rows, metadata


def check_f4(result: dict, reference_path: Path) -> None:
    frozen = json.loads(reference_path.read_text())
    common = result["common_test"]
    if (common["n"], common["source"]["good"], common["source"]["bad"], common["groups"]) != (
        frozen["common_test"]["n"], frozen["common_test"]["good"],
        frozen["common_test"]["bad"], frozen["common_test"]["prefix_groups"]):
        raise ValueError("frozen F4 common-test denominators differ")
    for name, key in (("source", "F3_source_split"), ("grouped", "F2_prefix_split")):
        for field in ("balanced_accuracy", "good_false_positive_rate"):
            near(common[name][field], frozen["models"][key]["common_test"]["overall"][field],
                 f"{name}.{field}")
        matrix = frozen["models"][key]["common_test"]["overall"]["confusion"]
        cm = common[name]["confusion"]
        if cm != [[matrix["good_as_good"], matrix["good_as_bad"]],
                  [matrix["bad_as_good"], matrix["bad_as_bad"]]]:
            raise ValueError(f"frozen F4 {name} confusion differs")
    paired = frozen["paired_common_test"]
    near(common["balanced_accuracy_difference"], paired["source_minus_prefix_balanced_accuracy"],
         "paired BA difference")
    expected_transitions = paired["correctness_transition"]["all"]
    if common["transitions"] != {"both_correct": expected_transitions["both_correct"],
                                  "source_only_correct": expected_transitions["source_only_correct"],
                                  "grouped_only_correct": expected_transitions["group_only_correct"],
                                  "both_wrong": expected_transitions["both_wrong"]}:
        raise ValueError("frozen F4 transitions differ")
    for bound in ("low", "high"):
        near(common["paired_interval_95pct"][bound],
             paired["source_minus_prefix_ba_bootstrap_95pct"][bound], f"paired interval {bound}")


def number(value: float | None, digits: int = 6) -> str:
    return "undefined" if value is None else f"{value:.{digits}f}"


def matrix(value: dict) -> str:
    return escape(json.dumps(value["confusion"], separators=(",", ":")))


def score_row(title: str, value: dict) -> str:
    return (f"<tr><th scope='row'>{escape(title)}</th><td>{value['good']}</td><td>{value['bad']}</td>"
            f"<td>{number(value['balanced_accuracy'])}</td><td>{matrix(value)}</td>"
            f"<td>{value['good_false_positives']}/{value['good']} "
            f"({number(value['good_false_positive_rate'])})</td></tr>")


def html_report(result: dict) -> str:
    audit_result = result["audit"]
    evaluations = audit_result["evaluations"]
    common = audit_result["common_test"]
    interval = common["paired_interval_95pct"]
    source_overlap = evaluations["source"]["test_groups_also_in_train"]
    source_groups = evaluations["source"]["test_groups"]
    thresholds = result["metadata"]
    interval_text = (f"{number(interval['low'])} to {number(interval['high'])}"
                     if interval and interval["low"] is not None else "undefined")
    valid_draws = interval["valid_draws"] if interval else 0
    draws = interval["draws"] if interval else 0
    group_count = interval["group_count"] if interval else 0
    interval_reading = ("It crosses zero, so this dataset does not establish a general direction of bias."
                        if interval and interval["low"] is not None and interval["low"] <= 0 <= interval["high"]
                        else "This single-dataset interval does not establish a general direction of bias."
                        if interval and interval["low"] is not None else
                        "A paired interval needs shared test images from both classes.")
    rows = "".join((
        score_row("Source folders, full test", evaluations["source"]["test"]),
        score_row("Grouped split, full test", evaluations["grouped"]["test"]),
        score_row("Source model, shared test", common["source"]),
        score_row("Grouped model, shared test", common["grouped"]),
    ))
    transitions = common["transitions"]
    source_link = thresholds.get("source")
    source_line = (f"<a href='{escape(source_link, quote=True)}'>Source dataset</a>"
                   if source_link else "Your records")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Image evaluation audit</title>
<style>
:root{{color-scheme:light;font-family:system-ui,-apple-system,sans-serif;color:#1b2221;background:#f5f6f2}}
body{{max-width:1080px;margin:0 auto;padding:clamp(20px,5vw,64px);line-height:1.5}}
h1{{font-size:clamp(2rem,4vw,3.4rem);line-height:1.1;letter-spacing:-.04em;margin:0 0 16px}}
h2{{font-size:1.25rem;margin:42px 0 12px}}p{{max-width:75ch}}.lede{{font-size:1.2rem;max-width:65ch}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin:30px 0}}
.card{{background:white;border:1px solid #d9ddd5;padding:20px}}.card strong{{display:block;font-size:2rem;line-height:1.2}}
.card span{{color:#4c5751}}table{{width:100%;border-collapse:collapse;background:white;font-variant-numeric:tabular-nums}}
th,td{{padding:12px;text-align:left;border-bottom:1px solid #d9ddd5;vertical-align:top}}thead{{background:#e9ece5}}
.scroll{{overflow-x:auto}}.note{{border-left:3px solid #304c40;padding:4px 16px;background:#e9ece5}}
footer{{margin-top:44px;color:#4c5751;font-size:.9rem}}a{{color:#205b46}}
</style></head><body>
<main><h1>See what changes when image groups stay together.</h1>
<p class="lede">This report shows whether test image groups also appear in training, how the two test sets differ, and what happens when both models score the same images.</p>
<div class="cards"><div class="card"><strong>{source_overlap}/{source_groups}</strong><span>source test groups also in training</span></div>
<div class="card"><strong>{common['n']}</strong><span>images in both test sets, {common['source']['good']} good and {common['source']['bad']} bad</span></div>
<div class="card"><strong>{number(common['balanced_accuracy_difference'], 4)}</strong><span>source minus grouped balanced accuracy on shared images</span></div></div>
<p class="note">The paired 95% group bootstrap interval is {interval_text} ({valid_draws}/{draws} valid resamples across {group_count} groups). {interval_reading}</p>
<h2>Scores and denominators</h2><div class="scroll"><table><thead><tr><th>Evaluation</th><th>Good</th><th>Bad</th><th>Balanced accuracy</th><th>Confusion matrix</th><th>Good images flagged bad</th></tr></thead><tbody>{rows}</tbody></table></div>
<p>Confusion matrices use true good/bad rows and predicted good/bad columns. Balanced accuracy is undefined when either class is absent.</p>
<h2>What the comparison can say</h2>
<p>The full test scores differ by {number(audit_result['full_test_ba_difference'])}, but only {common['n']} test images are shared. The source test has {audit_result['test_set_difference']['source_only']} other images; the grouped test has {audit_result['test_set_difference']['grouped_only']}. This full-test gap is descriptive, not a same-image effect.</p>
<p>On the shared images, both models are correct on {transitions['both_correct']}; only the source model is correct on {transitions['source_only_correct']}, only the grouped model on {transitions['grouped_only_correct']}, and both are wrong on {transitions['both_wrong']}.</p>
<p>{escape(thresholds['training_and_validation'])} The recorded thresholds are {number(thresholds['source_threshold'])} and {number(thresholds['grouped_threshold'])}. Holding test images fixed does not isolate why their scores differ.</p>
<p>Groups are {escape(thresholds['group_definition'])}. Their overlap is directly observed in these records. {escape(thresholds['group_caveat'])}</p>
<footer>{source_line}. Evidence level: observed group overlap; descriptive full-test comparison; paired, single-dataset diagnostic with an uncertainty interval. The accompanying JSON includes the scored records and computed counts.</footer></main></body></html>"""


def main() -> None:
    cache = Path(".cache")
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    ooc = sub.add_parser("ooc", help="refit and reconcile the frozen Zenodo image evaluations")
    ooc.add_argument("--table", type=Path, default=cache / "OOC_datasheet.xlsx")
    ooc.add_argument("--mapping", type=Path, default=cache / "source_split.json")
    ooc.add_argument("--features", type=Path, default=cache / "image_features.jsonl")
    ooc.add_argument("--f2-result", type=Path, default=cache / "f2_rf_result.json")
    ooc.add_argument("--f3-result", type=Path, default=cache / "f3_source_result.json")
    ooc.add_argument("--f4-result", type=Path, default=cache / "f4_paired_result.json")
    generic = sub.add_parser("records", help="audit two JSONL files with per-sample records")
    generic.add_argument("--source-records", type=Path, required=True)
    generic.add_argument("--grouped-records", type=Path, required=True)
    for command in (ooc, generic):
        command.add_argument("--output", type=Path, default=cache / "audit_report")
    args = parser.parse_args()
    started = time.perf_counter()
    if args.command == "ooc":
        source_rows, grouped_rows, metadata = ooc_records(args)
    else:
        source_rows, grouped_rows = read_jsonl(args.source_records), read_jsonl(args.grouped_records)
        metadata = {"source": None, "group_definition": "the group field supplied in the records",
                    "group_caveat": "Interpret group overlap according to the provenance of those identifiers.",
                    "source_threshold": None, "grouped_threshold": None,
                    "training_and_validation": "Training and validation details must be supplied separately."}
    result = {"audit": audit(source_rows, grouped_rows), "metadata": metadata,
              "records": {"source": source_rows, "grouped": grouped_rows}}
    common = result["audit"]["common_test"]
    interval = common["paired_interval_95pct"]
    result["evidence"] = {
        "group_overlap": "directly observed for the supplied group IDs",
        "full_test_gap": "descriptive comparison on different test samples",
        "shared_test_gap": ("paired, single-dataset diagnostic; training and validation also differ"
                            if args.command == "ooc" else "paired, single-dataset diagnostic"),
        "paired_interval_crosses_zero": (interval["low"] <= 0 <= interval["high"]
                                         if interval and interval["low"] is not None else None),
        "physical_chip_leakage": ("not established by date-like filename prefixes"
                                  if args.command == "ooc" else "depends on supplied group-ID provenance"),
        "general_bias": "not established by one dataset",
    }
    if args.command == "ooc":
        check_f4(result["audit"], args.f4_result)
    result["runtime"] = {"seconds": time.perf_counter() - started,
                         "peak_rss_mb": peak_rss_mb()}
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "audit.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    (args.output / "audit.html").write_text(html_report(result), encoding="utf-8")
    print(json.dumps({"html": str(args.output / "audit.html"), "json": str(args.output / "audit.json"),
                      **result["runtime"]}, indent=2))


if __name__ == "__main__":
    main()

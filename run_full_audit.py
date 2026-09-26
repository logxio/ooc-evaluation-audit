#!/usr/bin/env python3
"""Resume a Zenodo original-to-report run using the frozen F1-F4 protocol."""
from __future__ import annotations

import argparse
import hashlib
from html import escape
import json
import math
import os
from pathlib import Path
import platform
import resource
import subprocess
import sys
import time

from ooc_qc import (IMAGE_MD5, IMAGE_SIZE, command_download_images,
                    command_extract_images, command_verify_images,
                    read_feature_cache, read_table)
from source_split_audit import load_mapping, map_local_zip

ROOT = Path(__file__).resolve().parent


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(8 * 1024 * 1024):
            h.update(block)
    return h.hexdigest()


def emit(stage: str, **values) -> None:
    print(json.dumps({"stage": stage, **values}), flush=True)


def equal_number(actual: float, expected: float, name: str) -> None:
    if not math.isclose(actual, expected, rel_tol=0, abs_tol=1e-12):
        raise ValueError(f"frozen reference mismatch: {name}: {actual} != {expected}")


def check_reference(cache: Path, reference_path: Path) -> dict:
    reference = json.loads(reference_path.read_text())
    f2 = json.loads((cache / "f2_rf_result.json").read_text())
    f3 = json.loads((cache / "f3_source_result.json").read_text())
    f4 = json.loads((cache / "f4_paired_result.json").read_text())
    for name, result in (("f2", f2), ("f3", f3)):
        frozen = reference[name]
        equal_number(result["test"]["overall"]["balanced_accuracy"], frozen["test_ba"],
                     f"{name} test BA")
        equal_number(result["threshold"], frozen["threshold"], f"{name} threshold")
        if result["test"]["overall"]["confusion"] != frozen["test_confusion"]:
            raise ValueError(f"frozen reference mismatch: {name} test confusion")
    if f3["prefix_overlap_with_train"]["test"] != reference["f3"]["test_prefix_overlap"]:
        raise ValueError("frozen reference mismatch: source test prefix overlap")
    if f4["common_test"] != reference["f4"]["common_test"]:
        raise ValueError("frozen reference mismatch: common test")
    equal_number(f4["paired_common_test"]["source_minus_prefix_balanced_accuracy"],
                 reference["f4"]["paired_ba_difference"], "paired difference")
    interval = f4["paired_common_test"]["source_minus_prefix_ba_bootstrap_95pct"]
    for key, expected in reference["f4"]["paired_interval"].items():
        if key in ("low", "high"):
            equal_number(interval[key], expected, f"paired interval {key}")
        elif interval[key] != expected:
            raise ValueError(f"frozen reference mismatch: paired interval {key}")
    feature_hash = digest(cache / "image_features.jsonl")
    if not all(item["matches_reference"] for item in f4["full_test_reproduction"].values()):
        raise ValueError("F4 failed to reproduce fresh F2/F3 result fields")
    return {"f2_test_ba": f2["test"]["overall"]["balanced_accuracy"],
            "f3_test_ba": f3["test"]["overall"]["balanced_accuracy"],
            "source_test_prefix_overlap": f3["prefix_overlap_with_train"]["test"],
            "common_test": f4["common_test"],
            "paired_ba_difference": f4["paired_common_test"]["source_minus_prefix_balanced_accuracy"],
            "paired_interval_95pct": interval,
            "feature_sha256": feature_hash,
            "feature_sha256_matches_canonical_reference": (
                feature_hash == reference["f4"]["feature_cache_sha256"]),
            "independent_frozen_reference_sha256": digest(reference_path)}


def result_command(filename: Path, script: str, command: str, *options: object) -> None:
    temporary = filename.with_suffix(filename.suffix + ".tmp")
    argv = [sys.executable, str(ROOT / script), command, *map(str, options)]
    if script == "ooc_qc.py":
        table_index = argv.index("--table")
        table_option = argv[table_index:table_index + 2]
        del argv[table_index:table_index + 2]
        argv[2:2] = table_option
    with temporary.open("w") as output:
        subprocess.run(argv, stdout=output, check=True)
    json.loads(temporary.read_text())
    os.replace(temporary, filename)
    emit("computed", result=filename.name)


def peak_mb(who: int) -> float:
    value = resource.getrusage(who).ru_maxrss
    return value / (1024 * 1024) if sys.platform == "darwin" else value / 1024


def finish_report(cache: Path, output: Path, reference: Path, table: Path,
                  mapping: Path, features: Path, image_ids: int,
                  started: float, reference_error: str | None) -> dict:
    report = json.loads((output / "audit.json").read_text())
    f2 = json.loads((cache / "f2_rf_result.json").read_text())
    f3 = json.loads((cache / "f3_source_result.json").read_text())
    f4 = json.loads((cache / "f4_paired_result.json").read_text())
    if report["audit"]["common_test"]["n"] != f4["common_test"]["n"]:
        raise ValueError("report shared-test count differs from F4")
    if reference_error:
        report["reference_check"] = {"status": "mismatch", "reason": reference_error,
                                     "reference_sha256": digest(reference)}
        (output / "audit.json").write_text(json.dumps(report, indent=2) + "\n")
        html_path = output / "audit.html"
        banner = ("<p class='note'><strong>Frozen reference mismatch.</strong> "
                  "These scores were recomputed here but differ from the earlier result. "
                  "Review run_evidence.json before citing them. "
                  f"{escape(reference_error)}</p>")
        html_path.write_text(html_path.read_text().replace("<main>", "<main>" + banner, 1))
    feature_hash = digest(features)
    evidence = {"status": "frozen_mismatch" if reference_error else "verified",
                "source": "https://zenodo.org/records/10203721",
                "image_zip_bytes": IMAGE_SIZE, "image_zip_md5": IMAGE_MD5,
                "table_sha256": digest(table), "source_split_map_sha256": digest(mapping),
                "image_feature_ids": image_ids,
                "feature_sha256": feature_hash,
                "feature_sha256_matches_canonical_reference": (
                    feature_hash == json.loads(reference.read_text())["f4"]["feature_cache_sha256"]),
                "independent_frozen_reference_sha256": digest(reference),
                "f2_test_ba": f2["test"]["overall"]["balanced_accuracy"],
                "f3_test_ba": f3["test"]["overall"]["balanced_accuracy"],
                "source_test_prefix_overlap": f3["prefix_overlap_with_train"]["test"],
                "common_test": f4["common_test"],
                "paired_ba_difference": f4["paired_common_test"]["source_minus_prefix_balanced_accuracy"],
                "paired_interval_95pct": f4["paired_common_test"]["source_minus_prefix_ba_bootstrap_95pct"],
                "frozen_reference_mismatch": reference_error,
                "audit_json_sha256": digest(output / "audit.json"),
                "audit_html_sha256": digest(output / "audit.html"),
                "elapsed_seconds": time.monotonic() - started,
                "peak_rss_mb": max(peak_mb(resource.RUSAGE_SELF), peak_mb(resource.RUSAGE_CHILDREN)),
                "platform": platform.platform(), "cpu_count": os.cpu_count()}
    (output / "run_evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=ROOT / ".cache")
    parser.add_argument("--output", type=Path, default=ROOT / ".cache" / "audit_report")
    parser.add_argument("--reference", type=Path, default=ROOT / "frozen_reference.json")
    parser.add_argument("--time-budget", type=int, default=240,
                        help="seconds before stopping for a resumable rerun; 0 disables the limit on remote CPU")
    args = parser.parse_args()
    started = time.monotonic()
    deadline = started + args.time_budget if args.time_budget else None
    cache = args.cache.resolve()
    output = args.output.resolve()
    cache.mkdir(parents=True, exist_ok=True)
    table = cache / "OOC_datasheet.xlsx"
    image_zip = cache / "OOC_image_dataset.zip"
    features = cache / "image_features.jsonl"
    mapping = cache / "source_split.json"

    def time_left() -> float:
        return deadline - time.monotonic() if deadline else float("inf")

    def require_budget() -> None:
        if time_left() < 25:
            emit("paused", reason="time budget", instruction="run the same command again",
                 elapsed_seconds=round(time.monotonic() - started, 2))
            raise SystemExit(2)

    rows = read_table(table)
    emit("table_verified", image_ids=len(rows), sha256=digest(table))
    stalled = 0
    while not image_zip.exists() or image_zip.stat().st_size < IMAGE_SIZE:
        require_budget()
        before = image_zip.stat().st_size if image_zip.exists() else 0
        try:
            seconds = 120 if deadline is None else min(120, max(1, int(time_left() - 20)))
            command_download_images(argparse.Namespace(zip=image_zip, seconds=seconds))
        except Exception as error:
            emit("download_retry", error=repr(error), bytes=image_zip.stat().st_size if image_zip.exists() else 0)
        after = image_zip.stat().st_size if image_zip.exists() else 0
        stalled = 0 if after > before else stalled + 1
        if stalled >= 8:
            raise RuntimeError("download made no progress in eight attempts; rerun the same command")
    require_budget()
    command_verify_images(argparse.Namespace(zip=image_zip))
    emit("zip_verified", bytes=IMAGE_SIZE, md5=IMAGE_MD5)
    if mapping.exists():
        load_mapping(mapping, table)
    else:
        emit("source_split_mapped", **map_local_zip(image_zip, table, mapping))
    while True:
        cached = read_feature_cache(features)
        if len(cached) == len(rows):
            if set(cached) != {row["id"] for row in rows}:
                raise ValueError("feature cache IDs differ from datasheet")
            break
        require_budget()
        command_extract_images(argparse.Namespace(zip=image_zip, table=table,
                                                 features=features, count=64))
    emit("features_complete", image_ids=len(cached), feature_sha256=digest(features))
    require_budget()
    result_command(cache / "f1_metadata_result.json", "ooc_qc.py", "metadata",
                   "--table", table)
    result_command(cache / "f1_image_result.json", "ooc_qc.py", "image-evaluate",
                   "--table", table, "--features", features)
    require_budget()
    result_command(cache / "f2_rf_result.json", "f2_rf.py", "evaluate",
                   "--table", table, "--features", features)
    require_budget()
    result_command(cache / "f3_source_result.json", "source_split_audit.py", "evaluate",
                   "--table", table, "--features", features, "--mapping", mapping)
    require_budget()
    result_command(cache / "f4_paired_result.json", "f4_paired.py", "evaluate",
                   "--table", table, "--features", features, "--mapping", mapping,
                   "--f2-result", cache / "f2_rf_result.json",
                   "--f3-result", cache / "f3_source_result.json")
    try:
        check_reference(cache, args.reference)
        reference_error = None
    except ValueError as error:
        reference_error = str(error)
    require_budget()
    subprocess.run([sys.executable, str(ROOT / "audit_report.py"), "ooc",
                    "--table", str(table), "--features", str(features),
                    "--mapping", str(mapping), "--f2-result", str(cache / "f2_rf_result.json"),
                    "--f3-result", str(cache / "f3_source_result.json"),
                    "--f4-result", str(cache / "f4_paired_result.json"),
                    "--output", str(output)], check=True)
    evidence = finish_report(cache, output, args.reference, table, mapping, features,
                             len(cached), started, reference_error)
    emit("complete" if not reference_error else "report_exported_with_frozen_mismatch", **evidence)
    if reference_error:
        raise SystemExit(3)


if __name__ == "__main__":
    main()

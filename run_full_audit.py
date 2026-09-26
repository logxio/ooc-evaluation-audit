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


def compare_reference(actual: object, expected: object, name: str,
                      tolerance: float) -> None:
    if type(actual) is not type(expected):
        raise ValueError(f"Linux reference mismatch: {name}: type differs")
    if isinstance(expected, dict):
        if set(actual) != set(expected):
            raise ValueError(f"Linux reference mismatch: {name}: fields differ")
        for key, value in expected.items():
            compare_reference(actual[key], value, f"{name}.{key}", tolerance)
    elif isinstance(expected, list):
        if len(actual) != len(expected):
            raise ValueError(f"Linux reference mismatch: {name}: length differs")
        for index, value in enumerate(expected):
            compare_reference(actual[index], value, f"{name}[{index}]", tolerance)
    elif isinstance(expected, float):
        if not math.isclose(actual, expected, rel_tol=0, abs_tol=tolerance):
            raise ValueError(f"Linux reference mismatch: {name}: {actual} != {expected}")
    elif actual != expected:
        raise ValueError(f"Linux reference mismatch: {name}: {actual!r} != {expected!r}")


def check_reference(cache: Path, reference_path: Path) -> dict:
    reference = json.loads(reference_path.read_text())
    inputs = reference["inputs"]
    if (inputs["image_zip_bytes"] != IMAGE_SIZE or
            inputs["image_zip_md5"] != IMAGE_MD5 or
            digest(cache / "OOC_datasheet.xlsx") != inputs["table_sha256"]):
        raise ValueError("Linux reference mismatch: original source identity differs")
    feature_hash = digest(cache / "image_features.jsonl")
    if feature_hash != inputs["feature_cache_sha256"]:
        raise ValueError("Linux reference mismatch: 3072-image feature hash differs")
    f2 = json.loads((cache / "f2_rf_result.json").read_text())
    f3 = json.loads((cache / "f3_source_result.json").read_text())
    f4 = json.loads((cache / "f4_paired_result.json").read_text())
    for name, result in (("f2", f2), ("f3", f3), ("f4", f4)):
        frozen = reference["canonical"][name]
        observed = {key: result[key] for key in frozen}
        compare_reference(observed, frozen, name, reference["numeric_abs_tolerance"])
    if not all(item["matches_reference"] for item in f4["full_test_reproduction"].values()):
        raise ValueError("F4 failed to reproduce fresh F2/F3 result fields")
    return {"f2_test_ba": f2["test"]["overall"]["balanced_accuracy"],
            "f3_test_ba": f3["test"]["overall"]["balanced_accuracy"],
            "source_test_prefix_overlap": f3["prefix_overlap_with_train"]["test"],
            "common_test": f4["common_test"],
            "paired_ba_difference": f4["paired_common_test"]["source_minus_prefix_balanced_accuracy"],
            "paired_interval_95pct": f4["paired_common_test"]["source_minus_prefix_ba_bootstrap_95pct"],
            "feature_sha256": feature_hash,
            "feature_sha256_matches_canonical_reference": True,
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
    frozen = json.loads(reference.read_text())
    if report["audit"]["common_test"]["n"] != f4["common_test"]["n"]:
        raise ValueError("report shared-test count differs from F4")
    feature_hash = digest(features)
    platform_difference = (reference_error is not None and platform.system() == "Darwin" and
                           feature_hash == frozen["inputs"]["feature_cache_sha256"])
    report["reference_check"] = {
        "status": "mismatch" if reference_error else "verified",
        "canonical_platform": frozen["provenance"]["canonical_platform"],
        "reference_sha256": digest(reference),
        "reason": reference_error,
        "platform_difference": platform_difference,
    }
    (output / "audit.json").write_text(json.dumps(report, indent=2) + "\n")
    if reference_error:
        html_path = output / "audit.html"
        context = ("Matching image features led to different random-forest trees on macOS. "
                   "The frozen scores come from a clean Linux CPU run. "
                   if platform_difference else
                   "This run differs from the verified Linux inputs or scores. ")
        banner = ("<p class='note'><strong>Linux reference mismatch.</strong> "
                  + context + "Review run_evidence.json before citing these scores. "
                  f"{escape(reference_error)}</p>")
        html_path.write_text(html_path.read_text().replace("<main>", "<main>" + banner, 1))
    evidence = {"status": "frozen_mismatch" if reference_error else "verified",
                "source": "https://zenodo.org/records/10203721",
                "image_zip_bytes": IMAGE_SIZE, "image_zip_md5": IMAGE_MD5,
                "table_sha256": digest(table), "source_split_map_sha256": digest(mapping),
                "image_feature_ids": image_ids,
                "feature_sha256": feature_hash,
                "feature_sha256_matches_canonical_reference": (
                    feature_hash == frozen["inputs"]["feature_cache_sha256"]),
                "canonical_platform": frozen["provenance"]["canonical_platform"],
                "platform_difference": platform_difference,
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
                   "--table", table, "--features", features, "--mapping", mapping,
                   "--f2-result", cache / "f2_rf_result.json")
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

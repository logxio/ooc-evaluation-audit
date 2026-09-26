#!/usr/bin/env python3
"""Read the source ZIP's split from its central directory, then compare F3 to F2.

The ZIP tail and central directory are fetched with HTTP Range. Source images
stay on Zenodo. The mapping and model output live in the ignored local cache.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import resource
import struct
import sys
import time
import urllib.request

from ooc_qc import (CACHE, DATASET_URL, IMAGE_FEATURE_NAMES, IMAGE_MD5,
                    IMAGE_SIZE, IMAGE_URL, TABLE_SHA256, prefix_bootstrap_interval,
                    read_feature_cache, read_table, split_summary)


F2_GROUP_TEST_BA = 0.6578014184397163
EXPECTED = {"train": (2130, 1199, 931), "val": (286, 163, 123),
            "test": (656, 365, 291)}
TAIL_BYTES = 128 * 1024


def peak_rss_mb() -> float:
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak / (1024 * 1024) if sys.platform == "darwin" else peak / 1024


def get_range(start: int, length: int, url: str = IMAGE_URL) -> bytes:
    if length <= 0 or start < 0 or start + length > IMAGE_SIZE:
        raise ValueError("invalid ZIP byte range")
    chunks = []
    received = 0
    for _ in range(4):
        current = start + received
        end = start + length - 1
        request = urllib.request.Request(url, headers={
            "Range": f"bytes={current}-{end}", "Accept-Encoding": "identity",
            "User-Agent": "OoC-source-split-audit/0.1"})
        with urllib.request.urlopen(request, timeout=40) as response:
            if response.status != 206:
                raise ValueError(f"Range request returned HTTP {response.status}, expected 206")
            content_range = response.headers.get("Content-Range", "")
            if content_range != f"bytes {current}-{end}/{IMAGE_SIZE}":
                raise ValueError(f"unexpected Content-Range: {content_range}")
            chunk = response.read(length - received + 1)
        if not chunk or len(chunk) > length - received:
            raise ValueError("invalid or empty ZIP Range response")
        chunks.append(chunk)
        received += len(chunk)
        if received == length:
            return b"".join(chunks)
    raise ValueError(f"Range response remained incomplete: {received}/{length} bytes")


def directory_location() -> dict:
    tail_start = IMAGE_SIZE - TAIL_BYTES
    tail = get_range(tail_start, TAIL_BYTES)
    eocd_at = tail.rfind(b"PK\x05\x06")
    if eocd_at < 20 or eocd_at + 22 > len(tail):
        raise ValueError("ZIP end-of-central-directory record missing")
    eocd = struct.unpack_from("<4s4H2IH", tail, eocd_at)
    if eocd_at + 22 + eocd[-1] != len(tail):
        raise ValueError("unexpected bytes after ZIP end record")
    locator = struct.unpack_from("<4sIQI", tail, eocd_at - 20)
    if locator[0] != b"PK\x06\x07" or locator[1] != 0 or locator[3] not in (0, 1):
        raise ValueError("ZIP64 locator missing or multi-disk archive")
    zip64_at = locator[2]
    zip64 = get_range(zip64_at, 56)
    header = struct.unpack_from("<4sQ2H2I4Q", zip64)
    if header[0] != b"PK\x06\x06" or header[1] < 44:
        raise ValueError("ZIP64 end record invalid")
    _, _, _, _, disk, disk_cd, entries_disk, entries_total, cd_bytes, cd_at = header
    if disk or disk_cd or entries_disk != entries_total or entries_total < 3072:
        raise ValueError("unexpected ZIP64 entry counts")
    if cd_bytes > 32 * 1024 * 1024 or cd_at + cd_bytes != zip64_at:
        raise ValueError("unexpected ZIP64 central-directory bounds")
    return {"central_directory_offset": cd_at, "central_directory_bytes": cd_bytes,
            "central_directory_entries": entries_total,
            "zip64_end_offset": zip64_at, "probe_download_bytes": TAIL_BYTES + 56}


def image_mapping(directory: bytes, expected_entries: int) -> list[dict]:
    result = []
    cursor = 0
    for _ in range(expected_entries):
        if directory[cursor:cursor + 4] != b"PK\x01\x02":
            raise ValueError(f"central-directory header missing at byte {cursor}")
        flags = struct.unpack_from("<H", directory, cursor + 8)[0]
        name_len, extra_len, comment_len = struct.unpack_from("<3H", directory, cursor + 28)
        end = cursor + 46 + name_len + extra_len + comment_len
        if end > len(directory):
            raise ValueError("central-directory entry runs past end")
        raw_name = directory[cursor + 46:cursor + 46 + name_len]
        name = raw_name.decode("utf-8" if flags & 0x800 else "cp437")
        cursor = end
        if not name.lower().endswith(".png"):
            continue
        path = PurePosixPath(name)
        parts = path.parts
        if (len(parts) != 6 or parts[0] != "OOC_image_dataset"
                or parts[1] not in EXPECTED or parts[2] not in ("good", "bad")
                or not parts[3].startswith("cell_type_")
                or not re.fullmatch(r"\d{6}_.+\.png", parts[5])):
            raise ValueError(f"unexpected source image path: {name}")
        result.append({"id": path.stem, "split": parts[1],
                       "quality": parts[2], "cell_type": parts[3][10:],
                       "path": name})
    if cursor != len(directory):
        raise ValueError("central-directory byte count mismatch")
    return result


def validate_mapping(entries: list[dict], rows: list[dict]) -> tuple[dict, dict]:
    by_id = {entry["id"]: entry for entry in entries}
    table = {row["id"]: row for row in rows}
    if len(entries) != 3072 or len(by_id) != 3072 or set(by_id) != set(table):
        raise ValueError("source ZIP image IDs do not match 3072 datasheet IDs one-to-one")
    parts = {name: [] for name in EXPECTED}
    for image_id, entry in by_id.items():
        row = table[image_id]
        if entry["quality"] != ("good" if row["label"] == 1 else "bad"):
            raise ValueError(f"source folder quality and datasheet label differ: {image_id}")
        if entry["cell_type"] != row["cell_type"]:
            raise ValueError(f"source folder cell type and datasheet differ: {image_id}")
        parts[entry["split"]].append(row)
    for name in parts:
        parts[name].sort(key=lambda row: row["id"])
        counts = (len(parts[name]), sum(row["label"] == 1 for row in parts[name]),
                  sum(row["label"] == 2 for row in parts[name]))
        if counts != EXPECTED[name]:
            raise ValueError(f"source {name} counts {counts} != {EXPECTED[name]}")
    prefix = {name: {row["id"][:6] for row in split_rows}
              for name, split_rows in parts.items()}
    overlap = {name: {"prefix_groups": len(prefix[name]),
                      "also_in_train": len(prefix[name] & prefix["train"])}
               for name in ("val", "test")}
    if overlap["test"] != {"prefix_groups": 57, "also_in_train": 57}:
        raise ValueError(f"unexpected source test prefix overlap: {overlap['test']}")
    if overlap["val"] != {"prefix_groups": 51, "also_in_train": 51}:
        raise ValueError(f"unexpected source validation prefix overlap: {overlap['val']}")
    return parts, overlap


def command_probe(args: argparse.Namespace) -> dict:
    started = time.perf_counter()
    location = directory_location()
    return {"kind": "zip64_range_probe_only", "source": IMAGE_URL,
            "source_size_bytes": IMAGE_SIZE, **location,
            "elapsed_seconds": time.perf_counter() - started,
            "peak_rss_mb": peak_rss_mb()}


def command_map(args: argparse.Namespace) -> dict:
    started = time.perf_counter()
    location = directory_location()
    raw = get_range(location["central_directory_offset"],
                    location["central_directory_bytes"])
    entries = image_mapping(raw, location["central_directory_entries"])
    rows = read_table(args.table)
    parts, overlap = validate_mapping(entries, rows)
    document = {"source": DATASET_URL, "image_url": IMAGE_URL,
                "image_zip_size": IMAGE_SIZE, "image_zip_md5_expected": IMAGE_MD5,
                "datasheet_sha256": TABLE_SHA256, "directory": location,
                "central_directory_sha256": hashlib.sha256(raw).hexdigest(),
                "entries": sorted(entries, key=lambda entry: entry["id"])}
    args.mapping.parent.mkdir(parents=True, exist_ok=True)
    args.mapping.write_text(json.dumps(document, indent=2) + "\n")
    return {"kind": "source_split_mapping", "image_count": len(entries),
            "split": split_summary(parts), "prefix_overlap_with_train": overlap,
            "central_directory_sha256": document["central_directory_sha256"],
            "download_bytes": location["probe_download_bytes"] + len(raw),
            "mapping_file": str(args.mapping),
            "elapsed_seconds": time.perf_counter() - started,
            "peak_rss_mb": peak_rss_mb()}


def load_mapping(path: Path, table: Path) -> tuple[dict, dict]:
    document = json.loads(path.read_text())
    if (document["image_zip_size"] != IMAGE_SIZE
            or document["image_zip_md5_expected"] != IMAGE_MD5
            or document["datasheet_sha256"] != TABLE_SHA256):
        raise ValueError("mapping source identity differs from pinned Zenodo record")
    parts, overlap = validate_mapping(document["entries"], read_table(table))
    return parts, overlap


def command_evaluate(args: argparse.Namespace) -> dict:
    from f2_rf import (PARAMETERS, detailed_metrics, forest, peak_rss_mb,
                       select_f2_threshold, sklearn_version)
    import numpy as np

    started = time.perf_counter()
    parts, overlap = load_mapping(args.mapping, args.table)
    cache = read_feature_cache(args.features)
    expected_ids = {row["id"] for rows in parts.values() for row in rows}
    if set(cache) != expected_ids:
        raise ValueError("frozen 29D feature cache IDs differ from source mapping")
    x = {name: np.asarray([cache[row["id"]] for row in rows], dtype=np.float64)
         for name, rows in parts.items()}
    y = {name: np.asarray([row["label"] == 2 for row in rows], dtype=np.int64)
         for name, rows in parts.items()}
    if any(matrix.shape != (len(parts[name]), len(IMAGE_FEATURE_NAMES))
           or not np.isfinite(matrix).all() for name, matrix in x.items()):
        raise ValueError("invalid frozen image feature matrix")
    fit_started = time.perf_counter()
    model = forest()
    model.fit(x["train"], y["train"])
    fit_seconds = time.perf_counter() - fit_started
    if list(model.classes_) != [0, 1]:
        raise ValueError("unexpected class order")
    val_probability = model.predict_proba(x["val"])[:, 1]
    threshold, _, selection = select_f2_threshold(y["val"], val_probability)
    prediction = {"val": val_probability >= threshold,
                  "test": model.predict_proba(x["test"])[:, 1] >= threshold}
    val = detailed_metrics(parts["val"], y["val"], prediction["val"])
    test = detailed_metrics(parts["test"], y["test"], prediction["test"])
    test_ba = test["overall"]["balanced_accuracy"]
    delta = test_ba - F2_GROUP_TEST_BA
    return {"phase": "F3_source_image_split_vs_F2_prefix_split",
            "source": DATASET_URL, "mapping": str(args.mapping),
            "feature_count": len(IMAGE_FEATURE_NAMES),
            "feature_names": list(IMAGE_FEATURE_NAMES),
            "model": "sklearn.ensemble.RandomForestClassifier",
            "sklearn_version": sklearn_version,
            "model_parameters": PARAMETERS,
            "other_parameters": "scikit-learn defaults",
            "selection": selection, "threshold": threshold,
            "split": split_summary(parts), "prefix_overlap_with_train": overlap,
            "validation": val, "test": test,
            "test_ba_prefix_bootstrap_95pct": prefix_bootstrap_interval(
                parts["test"], y["test"], prediction["test"]),
            "f2_prefix_split_test_ba": F2_GROUP_TEST_BA,
            "source_minus_f2_test_ba": delta,
            "audit_direction_gate": {"source_test_ba_ge_0.75": test_ba >= 0.75,
                                     "delta_ge_0.10": delta >= 0.10,
                                     "passes_both": test_ba >= 0.75 and delta >= 0.10},
            "comparison_note": "Different test samples; diagnostic association, not a same-sample causal effect or proof of chip leakage.",
            "fit_seconds": fit_seconds,
            "total_seconds": time.perf_counter() - started,
            "peak_rss_mb": peak_rss_mb()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["probe", "map", "evaluate"])
    parser.add_argument("--table", type=Path, default=CACHE / "OOC_datasheet.xlsx")
    parser.add_argument("--mapping", type=Path, default=CACHE / "source_split.json")
    parser.add_argument("--features", type=Path, default=CACHE / "image_features.jsonl")
    args = parser.parse_args()
    if args.command == "probe":
        result = command_probe(args)
    elif args.command == "map":
        result = command_map(args)
    else:
        result = command_evaluate(args)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

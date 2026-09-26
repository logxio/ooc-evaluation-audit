#!/usr/bin/env python3
"""Reproducible, CPU-only baselines for organ-on-a-chip image quality.

The source images and datasheet stay with Zenodo. This program downloads them
on demand and does not redistribute source data or trained weights.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

import numpy as np

DATASET_URL = "https://zenodo.org/records/10203721"
TABLE_URL = "https://zenodo.org/api/records/10203721/files/OOC_datasheet.xlsx/content"
TABLE_SHA256 = "863fc133f8be825c010c41ea26168fedb75af8d2722646f61402779583073eba"
IMAGE_URL = "https://zenodo.org/api/records/10203721/files/OOC_image_dataset.zip/content"
IMAGE_SIZE = 6710767405
IMAGE_MD5 = "8f7e058996203d48eb03b2d86c0a2e4d"
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
CACHE = Path(__file__).resolve().parent / ".cache"


def fetch_table(path: Path) -> None:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(TABLE_URL, headers={"User-Agent": "OoC-QC-baseline/0.1"})
        with urllib.request.urlopen(req, timeout=30) as response:
            path.write_bytes(response.read())
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != TABLE_SHA256:
        raise ValueError(f"datasheet SHA-256 mismatch: {digest}")


def read_table(path: Path) -> list[dict[str, str]]:
    fetch_table(path)
    with zipfile.ZipFile(path) as z:
        shared = ET.fromstring(z.read("xl/sharedStrings.xml"))
        strings = ["".join(item.itertext()) for item in shared.findall(NS + "si")]
        sheet = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
    rows = []
    for row in sheet.findall(".//" + NS + "sheetData/" + NS + "row"):
        cells = {}
        for cell in row.findall(NS + "c"):
            value = cell.find(NS + "v")
            if value is None:
                continue
            column = re.match(r"[A-Z]+", cell.attrib["r"]).group()
            cells[column] = (strings[int(value.text)]
                             if cell.attrib.get("t") == "s" else value.text)
        if cells.get("A") and cells["A"] != "imageID":
            rows.append({
                "id": cells["A"],
                "cell_type": cells.get("B", ""),
                "density": cells.get("C", ""),
                "hours": cells.get("D", ""),
                "day": cells.get("E", ""),
                "label": int(cells["F"]),
                "flow": cells.get("G", ""),
            })
    if len(rows) != 3072 or len({row["id"] for row in rows}) != 3072:
        raise ValueError("expected exactly 3072 distinct image IDs")
    if Counter(row["label"] for row in rows) != {1: 1727, 2: 1345}:
        raise ValueError("unexpected label counts")
    return rows


def group_bucket(image_id: str) -> int:
    prefix = image_id[:6]
    if not re.fullmatch(r"\d{6}", prefix):
        raise ValueError(f"unexpected image ID: {image_id}")
    return int(hashlib.sha256(("26" + prefix).encode("utf-8")).hexdigest(), 16) % 100


def split_for(image_id: str) -> str:
    bucket = group_bucket(image_id)
    return "test" if bucket < 20 else "val" if bucket < 30 else "train"


def split_rows(rows: list[dict]) -> dict[str, list[dict]]:
    result = {"train": [], "val": [], "test": []}
    for row in rows:
        result[split_for(row["id"])].append(row)
    return result


def split_summary(parts: dict[str, list[dict]]) -> dict:
    return {
        name: {
            "n": len(rows),
            "good": sum(row["label"] == 1 for row in rows),
            "bad": sum(row["label"] == 2 for row in rows),
            "prefix_groups": len({row["id"][:6] for row in rows}),
            "cell_type": dict(sorted(Counter(row["cell_type"] for row in rows).items())),
        }
        for name, rows in parts.items()
    }


def numeric(text: str) -> float:
    if not text:
        return math.nan
    match = re.search(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?", text.replace(",", ""))
    if not match:
        raise ValueError(f"unknown numeric format: {text}")
    return float(match.group())


def metadata_features(parts: dict[str, list[dict]]) -> tuple[dict[str, np.ndarray], list[str]]:
    train = parts["train"]
    cell_types = sorted({row["cell_type"] for row in train})
    numeric_keys = ("density", "hours", "day", "flow")
    names = [f"cell={name}" for name in cell_types]
    names += [name for name in numeric_keys]
    names += [name + ":missing" for name in numeric_keys]

    raw = {}
    for split, rows in parts.items():
        values = np.empty((len(rows), len(cell_types) + len(numeric_keys) * 2), dtype=np.float64)
        for i, row in enumerate(rows):
            values[i, :len(cell_types)] = [float(row["cell_type"] == c) for c in cell_types]
            nums = [numeric(row[key]) for key in numeric_keys]
            values[i, len(cell_types):len(cell_types) + len(numeric_keys)] = nums
            values[i, len(cell_types) + len(numeric_keys):] = [float(math.isnan(v)) for v in nums]
        raw[split] = values

    start = len(cell_types)
    for j in range(len(numeric_keys)):
        train_column = raw["train"][:, start + j]
        finite = train_column[np.isfinite(train_column)]
        median = float(np.median(finite)) if finite.size else 0.0
        for values in raw.values():
            column = values[:, start + j]
            column[~np.isfinite(column)] = median

    mean = raw["train"].mean(axis=0)
    std = raw["train"].std(axis=0)
    std[std < 1e-12] = 1.0
    transformed = {}
    for split, values in raw.items():
        normalized = (values - mean) / std
        transformed[split] = np.column_stack([np.ones(len(values)), normalized])
    return transformed, ["intercept", *names]


def sigmoid(values: np.ndarray) -> np.ndarray:
    values = np.clip(values, -40, 40)
    return 1.0 / (1.0 + np.exp(-values))


def fit_logistic(x: np.ndarray, y: np.ndarray, penalty: float = 10.0) -> np.ndarray:
    """Deterministic Newton fit; sum log loss plus L2 penalty, intercept exempt."""
    weight = np.zeros(x.shape[1], dtype=np.float64)
    ridge = np.diag([0.0] + [penalty] * (x.shape[1] - 1))
    for _ in range(80):
        prob = sigmoid(x @ weight)
        gradient = x.T @ (prob - y) + ridge @ weight
        curvature = prob * (1.0 - prob)
        hessian = x.T @ (x * curvature[:, None]) + ridge
        step = np.linalg.solve(hessian, gradient)
        weight -= step
        if np.max(np.abs(step)) < 1e-9:
            break
    return weight


def confusion(y: np.ndarray, prediction: np.ndarray) -> dict[str, int]:
    return {
        "good_as_good": int(np.sum((y == 0) & (prediction == 0))),
        "good_as_bad": int(np.sum((y == 0) & (prediction == 1))),
        "bad_as_good": int(np.sum((y == 1) & (prediction == 0))),
        "bad_as_bad": int(np.sum((y == 1) & (prediction == 1))),
    }


def metrics(y: np.ndarray, prediction: np.ndarray) -> dict:
    cm = confusion(y, prediction)
    good_n = cm["good_as_good"] + cm["good_as_bad"]
    bad_n = cm["bad_as_good"] + cm["bad_as_bad"]
    good_recall = cm["good_as_good"] / good_n if good_n else None
    bad_recall = cm["bad_as_bad"] / bad_n if bad_n else None
    ba = (good_recall + bad_recall) / 2 if good_n and bad_n else None
    return {
        "n": len(y),
        "good_n": good_n,
        "bad_n": bad_n,
        "balanced_accuracy": ba,
        "good_recall": good_recall,
        "bad_recall": bad_recall,
        "confusion": cm,
    }


def select_threshold(y: np.ndarray, probability: np.ndarray) -> tuple[float, dict]:
    unique = sorted(set(map(float, probability)))
    candidates = [0.0, 0.5, 1.0]
    candidates += [(a + b) / 2 for a, b in zip(unique, unique[1:])]
    candidates += unique
    scored = [(metrics(y, probability >= t)["balanced_accuracy"], -abs(t - 0.5), -t, t)
              for t in candidates]
    threshold = max(scored)[-1]
    return threshold, metrics(y, probability >= threshold)


def evaluate_model(parts: dict[str, list[dict]], matrices: dict[str, np.ndarray], feature_names: list[str]) -> dict:
    y = {name: np.asarray([row["label"] == 2 for row in rows], dtype=np.float64)
         for name, rows in parts.items()}
    weight = fit_logistic(matrices["train"], y["train"])
    probabilities = {name: sigmoid(matrix @ weight) for name, matrix in matrices.items()}
    threshold, val_metric = select_threshold(y["val"], probabilities["val"])
    prediction = probabilities["test"] >= threshold
    test_metric = metrics(y["test"], prediction)
    per_cell = {}
    for cell in sorted({row["cell_type"] for row in parts["test"]}):
        mask = np.asarray([row["cell_type"] == cell for row in parts["test"]])
        per_cell[cell] = metrics(y["test"][mask], prediction[mask])
    return {
        "feature_names": feature_names,
        "model": "logistic regression, deterministic Newton fit, L2=10",
        "threshold": threshold,
        "validation": val_metric,
        "test": test_metric,
        "test_by_cell": per_cell,
        "test_prefix_groups": len({row["id"][:6] for row in parts["test"]}),
    }


def command_prepare(args: argparse.Namespace) -> None:
    rows = read_table(args.table)
    parts = split_rows(rows)
    print(json.dumps({
        "source": DATASET_URL,
        "datasheet_sha256": TABLE_SHA256,
        "split": split_summary(parts),
    }, indent=2))
    if args.limit:
        matrices, names = metadata_features(parts)
        print(json.dumps({
            "probe_train_rows": min(args.limit, len(parts["train"])),
            "feature_count": len(names),
            "probe_matrix_shape": list(matrices["train"][:args.limit].shape),
            "probe_matrix_bytes": int(matrices["train"][:args.limit].nbytes),
        }, indent=2))


def command_metadata(args: argparse.Namespace) -> None:
    parts = split_rows(read_table(args.table))
    matrices, names = metadata_features(parts)
    result = {
        "baseline": "metadata",
        "source": DATASET_URL,
        "datasheet_sha256": TABLE_SHA256,
        "split": split_summary(parts),
        "features": ["cell type", "seeding density", "time after seeding (h)", "day", "flow rate"],
        "preprocessing": "train-only median imputation, missing indicators and standardization",
        "constant_good_test": metrics(
            np.asarray([row["label"] == 2 for row in parts["test"]], dtype=np.float64),
            np.zeros(len(parts["test"]), dtype=np.float64)),
        **evaluate_model(parts, matrices, names),
    }
    print(json.dumps(result, indent=2))


def command_download_images(args: argparse.Namespace) -> None:
    """Resume the source ZIP; one local call stops before the process budget."""
    path = args.zip
    path.parent.mkdir(parents=True, exist_ok=True)
    current = path.stat().st_size if path.exists() else 0
    if current > IMAGE_SIZE:
        raise ValueError("local ZIP is larger than the Zenodo source")
    if current == IMAGE_SIZE:
        print(json.dumps({"bytes": current, "complete": True}))
        return
    headers = {"User-Agent": "OoC-QC-baseline/0.1"}
    if current:
        headers["Range"] = f"bytes={current}-"
    request = urllib.request.Request(IMAGE_URL, headers=headers)
    deadline = time.monotonic() + args.seconds
    with urllib.request.urlopen(request, timeout=20) as response:
        if current and response.status != 206:
            raise RuntimeError(f"resume requires HTTP 206; received {response.status}")
        with path.open("ab") as output:
            while current < IMAGE_SIZE and time.monotonic() < deadline:
                block = response.read(min(1024 * 1024, IMAGE_SIZE - current))
                if not block:
                    break
                output.write(block)
                current += len(block)
    print(json.dumps({"bytes": current, "total_bytes": IMAGE_SIZE,
                      "complete": current == IMAGE_SIZE,
                      "next": "repeat download-images to resume" if current < IMAGE_SIZE else None}))


def command_verify_images(args: argparse.Namespace) -> None:
    if args.zip.stat().st_size != IMAGE_SIZE:
        raise ValueError("image ZIP has the wrong byte count")
    digest = hashlib.md5()
    with args.zip.open("rb") as source:
        while block := source.read(8 * 1024 * 1024):
            digest.update(block)
    actual = digest.hexdigest()
    if actual != IMAGE_MD5:
        raise ValueError(f"image ZIP MD5 mismatch: {actual}")
    print(json.dumps({"image_zip_md5": actual, "verified": True}))


IMAGE_FEATURE_NAMES = (
    "p05", "p25", "p50", "p75", "p95", "mean", "std", "laplacian_variance",
    "horizontal_difference", "vertical_difference", "edge_fraction",
    *(f"hist_{i}" for i in range(8)),
    *(f"quadrant_mean_{i}" for i in range(4)),
    *(f"quadrant_std_{i}" for i in range(4)),
    "row_mean_std", "column_mean_std",
)


def image_features(image_file) -> list[float]:
    from PIL import Image

    with Image.open(image_file) as image:
        if image.format != "PNG":
            raise ValueError("expected PNG")
        gray = image.convert("L").resize((128, 96), Image.Resampling.BILINEAR)
        array = np.asarray(gray, dtype=np.float64) / 255.0
    p = np.percentile(array, [5, 25, 50, 75, 95])
    core = array[1:-1, 1:-1]
    lap = (array[:-2, 1:-1] + array[2:, 1:-1]
           + array[1:-1, :-2] + array[1:-1, 2:] - 4 * core)
    dx = np.abs(array[:, 1:] - array[:, :-1])
    dy = np.abs(array[1:, :] - array[:-1, :])
    histogram, _ = np.histogram(array, bins=8, range=(0.0, 1.0))
    quadrants = [array[y:y + 48, x:x + 64]
                 for y in (0, 48) for x in (0, 64)]
    values = [
        *map(float, p), float(array.mean()), float(array.std()), float(lap.var()),
        float(dx.mean()), float(dy.mean()), float(np.mean(np.abs(lap) > 0.08)),
        *map(float, histogram / array.size),
        *(float(part.mean()) for part in quadrants),
        *(float(part.std()) for part in quadrants),
        float(array.mean(axis=1).std()), float(array.mean(axis=0).std()),
    ]
    if len(values) != len(IMAGE_FEATURE_NAMES) or not all(math.isfinite(x) for x in values):
        raise ValueError("invalid image feature vector")
    return values


def read_feature_cache(path: Path) -> dict[str, list[float]]:
    result = {}
    if not path.exists():
        return result
    with path.open() as source:
        for number, line in enumerate(source, 1):
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"invalid feature cache line {number}") from error
            if record["id"] in result:
                raise ValueError(f"duplicate image feature: {record['id']}")
            if len(record["features"]) != len(IMAGE_FEATURE_NAMES):
                raise ValueError(f"wrong feature length at line {number}")
            result[record["id"]] = record["features"]
    return result


def command_extract_images(args: argparse.Namespace) -> None:
    if args.zip.stat().st_size != IMAGE_SIZE:
        raise ValueError("image ZIP is incomplete; resume download-images")
    rows = read_table(args.table)
    cache = read_feature_cache(args.features)
    remaining = [row["id"] for row in rows if row["id"] not in cache]
    if not remaining:
        print(json.dumps({"extracted": 0, "cached_total": len(cache), "complete": True}))
        return
    selected = remaining[:args.count]
    args.features.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.zip) as z:
        image_names = {Path(info.filename).stem: info.filename
                       for info in z.infolist() if info.filename.lower().endswith(".png")}
        if len(image_names) != 3072 or set(image_names) != {row["id"] for row in rows}:
            raise ValueError("ZIP images and datasheet IDs do not match")
        with args.features.open("a") as output:
            for image_id in selected:
                with z.open(image_names[image_id]) as image_file:
                    vector = image_features(image_file)
                output.write(json.dumps({"id": image_id, "features": vector}) + "\n")
                output.flush()
    print(json.dumps({"extracted": len(selected), "cached_total": len(cache) + len(selected),
                      "complete": len(cache) + len(selected) == len(rows)}))


def command_image_evaluate(args: argparse.Namespace) -> None:
    parts = split_rows(read_table(args.table))
    cache = read_feature_cache(args.features)
    expected = {row["id"] for rows in parts.values() for row in rows}
    if set(cache) != expected:
        raise ValueError(f"feature cache incomplete: {len(cache)} of {len(expected)}")
    raw = {split: np.asarray([cache[row["id"]] for row in rows], dtype=np.float64)
           for split, rows in parts.items()}
    mean = raw["train"].mean(axis=0)
    std = raw["train"].std(axis=0)
    std[std < 1e-12] = 1.0
    matrices = {
        split: np.column_stack([np.ones(len(parts[split])), (raw[split] - mean) / std])
        for split in parts
    }
    result = {
        "baseline": "image_features_only",
        "source": DATASET_URL,
        "datasheet_sha256": TABLE_SHA256,
        "image_zip_md5_expected": IMAGE_MD5,
        "split": split_summary(parts),
        "feature_extraction": "128x96 grayscale; quantiles, contrast, blur, gradients, histograms and spatial summaries",
        "preprocessing": "train-only standardization",
        **evaluate_model(parts, matrices, ["intercept", *IMAGE_FEATURE_NAMES]),
    }
    print(json.dumps(result, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--table", type=Path, default=CACHE / "OOC_datasheet.xlsx")
    sub = parser.add_subparsers(dest="command", required=True)
    probe = sub.add_parser("prepare", help="verify table and frozen split; no model fit")
    probe.add_argument("--limit", type=int, default=0, help="report a small in-memory feature probe")
    sub.add_parser("metadata", help="fit metadata baseline and evaluate the held-out test once")
    download = sub.add_parser("download-images", help="resume source ZIP for a bounded duration")
    download.add_argument("--zip", type=Path, default=CACHE / "OOC_image_dataset.zip")
    download.add_argument("--seconds", type=int, default=200)
    verify = sub.add_parser("verify-images", help="verify source ZIP against Zenodo MD5")
    verify.add_argument("--zip", type=Path, default=CACHE / "OOC_image_dataset.zip")
    extract = sub.add_parser("extract-images", help="append a bounded batch of image features")
    extract.add_argument("--zip", type=Path, default=CACHE / "OOC_image_dataset.zip")
    extract.add_argument("--features", type=Path, default=CACHE / "image_features.jsonl")
    extract.add_argument("--count", type=int, default=64)
    evaluate = sub.add_parser("image-evaluate", help="evaluate frozen image features on test")
    evaluate.add_argument("--features", type=Path, default=CACHE / "image_features.jsonl")
    args = parser.parse_args()
    if args.command == "prepare":
        command_prepare(args)
    elif args.command == "metadata":
        command_metadata(args)
    elif args.command == "download-images":
        command_download_images(args)
    elif args.command == "verify-images":
        command_verify_images(args)
    elif args.command == "extract-images":
        command_extract_images(args)
    elif args.command == "image-evaluate":
        command_image_evaluate(args)


if __name__ == "__main__":
    main()

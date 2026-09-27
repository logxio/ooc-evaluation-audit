#!/usr/bin/env python3
"""Secondary original-author label endpoint for the fixed HNOCA model."""

import hashlib
import io
from collections import OrderedDict
import requests
import json
import resource
import time

import h5py
import numpy as np
from sklearn.metrics import confusion_matrix




# The original-author labels are held in a separate official HNOCA CC BY archive.
URL = "https://zenodo.org/api/records/14161275/files/hnoca_cleanedmeta.h5ad/content"
SIZE = 18_740_061_388
BLOCK = 1024 * 1024
MAX_BYTES = 500 * 1024 * 1024
MAX_SECONDS = 20 * 60
MAX_CACHED = 64

class RangeFile(io.RawIOBase):
    def __init__(self):
        self.session = requests.Session()
        self.url = URL
        self.position = 0
        self.blocks = OrderedDict()
        self.downloaded = 0
        self.requests = 0
        self.start = time.monotonic()

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=io.SEEK_SET):
        if whence == io.SEEK_SET:
            pos = offset
        elif whence == io.SEEK_CUR:
            pos = self.position + offset
        elif whence == io.SEEK_END:
            pos = SIZE + offset
        else:
            raise ValueError(whence)
        if pos < 0:
            raise ValueError(pos)
        self.position = pos
        return pos

    def _block(self, index):
        if time.monotonic() - self.start > MAX_SECONDS:
            raise TimeoutError("Range probe exceeded 20-minute cap")
        if index in self.blocks:
            self.blocks.move_to_end(index)
            return self.blocks[index]
        start = index * BLOCK
        end = min(start + BLOCK, SIZE) - 1
        if self.downloaded + end - start + 1 > MAX_BYTES:
            raise RuntimeError("Range probe exceeded 500 MiB cap")
        with self.session.get(self.url, headers={"Range": f"bytes={start}-{end}",
                                                 "User-Agent": "organoid-original-label-sensitivity/1"},
                              timeout=(20, 45)) as response:
            if response.status_code != 206:
                raise RuntimeError(f"Range status {response.status_code}, expected 206")
            expected = f"bytes {start}-{end}/{SIZE}"
            if response.headers.get("Content-Range") != expected:
                raise RuntimeError(f"Range mismatch {response.headers.get('Content-Range')}")
            data = response.content
            if len(data) != end - start + 1:
                raise RuntimeError(f"Range length {len(data)}, expected {end-start+1}")
            self.url = response.url
        self.downloaded += len(data)
        self.requests += 1
        self.blocks[index] = data
        if len(self.blocks) > MAX_CACHED:
            self.blocks.popitem(last=False)
        return data

    def read(self, size=-1):
        if size < 0:
            size = SIZE - self.position
        size = min(size, SIZE - self.position)
        chunks = []
        while size:
            index, within = divmod(self.position, BLOCK)
            part = self._block(index)[within:within + size]
            if not part:
                break
            chunks.append(part)
            self.position += len(part)
            size -= len(part)
        return b"".join(chunks)

    def readinto(self, target):
        data = self.read(len(target))
        target[:len(data)] = data
        return len(data)


def string(value):
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


EXPECTED_INDEX_SHA256 = "77a0ff74a31468084253534e0244d3368b706e0bcb3514d067f821f74d5986ee"
SEED = 26
DRAW = 2000


def ordered_hash(values):
    h = hashlib.sha256()
    for value in values:
        encoded = value if isinstance(value, bytes) else str(value).encode("utf-8")
        h.update(len(encoded).to_bytes(4, "little"))
        h.update(encoded)
    return h.hexdigest()


def author_class(label):
    low = label.lower()
    if "low quality" in low or "low-quality" in low:
        return -1
    if label.startswith("Excitatory Neuron") or label.startswith("Inhibitory Neuron"):
        return 1
    if label.startswith("Radial Glia"):
        return 0
    return -1


def evaluate(test_global_rows, pred, pmajor, pcentroid, groups, macro_cm, group_names):
    start = time.monotonic()
    remote = RangeFile()
    with h5py.File(remote, "r") as archive:
        obs = archive["obs"]
        publication = obs["publication"]
        categories = [string(x) for x in publication["categories"][:]]
        code = categories.index("Bhaduri, 2020")
        rows = np.flatnonzero(publication["codes"][:] == code)
        if len(rows) != 223_453 or not np.all(np.diff(rows) == 1):
            raise RuntimeError("Bhaduri row block changed")
        first, stop = int(rows[0]), int(rows[-1]) + 1
        index_values = obs["_index"][first:stop]
        index_hash = ordered_hash(index_values)
        if index_hash != EXPECTED_INDEX_SHA256:
            raise RuntimeError("Original-label archive cannot align to fixed score source")
        label_node = obs["cell_type_original"]
        names = [string(x) for x in label_node["categories"][:]]
        codes = label_node["codes"][first:stop]
        if (codes < 0).any():
            raise RuntimeError("Missing author label")
        if test_global_rows.min() < first or test_global_rows.max() >= stop:
            raise RuntimeError("Test rows outside Bhaduri block")
        selected = codes[test_global_rows - first]
        author_labels = [names[int(x)] for x in selected]
    truth = np.array([author_class(x) for x in author_labels], dtype=np.int8)
    keep = truth >= 0
    kept_groups = groups[keep]
    y = truth[keep]
    predictions = {
        "model": (pred[keep] == 1).astype(np.int8),
        "source_majority": (pmajor[keep] == 1).astype(np.int8),
        "nearest_centroid": (pcentroid[keep] == 1).astype(np.int8),
    }
    keys = np.unique(kept_groups)
    by_key = {}
    output = {}
    for name, p in predictions.items():
        cm = confusion_matrix(y, p, labels=np.arange(2))
        output[name] = {"macro_f1": macro_cm(cm), "confusion": cm.tolist()}
        by_key[name] = np.stack([confusion_matrix(y[kept_groups == g], p[kept_groups == g],
                                                  labels=np.arange(2)) for g in keys])
    rng = np.random.default_rng(SEED)
    scores = {name: [] for name in predictions}
    valid = 0
    for _ in range(DRAW):
        draw = rng.integers(0, len(keys), size=len(keys))
        cms = {name: matrices[draw].sum(axis=0) for name, matrices in by_key.items()}
        if np.any(cms["model"].sum(axis=1) == 0):
            continue
        for name, cm in cms.items():
            scores[name].append(macro_cm(cm))
        valid += 1
    if valid == 0:
        raise RuntimeError("No valid group bootstrap draw")
    for name in predictions:
        output[name]["group_ci95"] = np.quantile(scores[name], [.025, .975]).tolist()
    for name in ("source_majority", "nearest_centroid"):
        output[name]["paired_model_advantage"] = output["model"]["macro_f1"] - output[name]["macro_f1"]
        differences = np.asarray(scores["model"]) - np.asarray(scores[name])
        output[name]["paired_advantage_ci95"] = np.quantile(differences, [.025, .975]).tolist()
    counts = {label: author_labels.count(label) for label in sorted(set(author_labels))}
    per_group = [{"bio_sample": group_names[int(key)],
                  "cells": int(np.sum(kept_groups == key)),
                  "model_confusion": by_key["model"][i].tolist(),
                  "source_majority_confusion": by_key["source_majority"][i].tolist(),
                  "nearest_centroid_confusion": by_key["nearest_centroid"][i].tolist()}
                 for i, key in enumerate(keys)]
    return {"endpoint": "original_author_neuron_vs_radial_glia_in_HNOCA_selected_three_class_cohort",
            "eligibility": {"all_test_cells": int(len(truth)), "retained": int(keep.sum()),
                            "excluded": int((~keep).sum()), "original_label_counts": counts,
                            "retained_neuron": int((y == 1).sum()), "retained_radial_glia": int((y == 0).sum()),
                            "retained_bio_sample_keys": int(len(keys))},
            "method": {"author_neuron": "Excitatory Neuron* or Inhibitory Neuron*",
                       "author_non_neuron": "Radial Glia*",
                       "excluded": "Low quality/Low-Quality, Mixed, Unknown, other",
                       "model_neuron": "HNOCA prediction Neuron; NPC/Glioblast are non-neuron",
                       "bootstrap": {"seed": SEED, "draws": DRAW, "effective": valid}},
            "results": output,
            "per_group": per_group,
            "provenance": {"clean_archive": URL, "declared_archive_size": 18_740_061_388,
                           "license_record": "https://zenodo.org/records/14161275",
                           "index_ordered_sha256": index_hash,
                           "data_lineage": "Bhaduri supplementary Type+Subtype -> sfaira celltype -> HNOCA preserved original obs"},
            "range": {"downloaded_bytes": remote.downloaded, "requests": remote.requests,
                      "seconds": round(time.monotonic() - start, 3),
                      "maxrss_bytes_linux": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)}}

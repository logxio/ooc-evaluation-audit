#!/usr/bin/env python3
"""Download and verify Tiriac et al. (2018) source tables; export PDO AUCs.

Uses only the Python standard library. Clinical outcomes are never selected.
The five drugs share an assay; their errors are not assumed independent.
Source: doi:10.1158/2159-8290.CD-18-0349, AACR Figshare, CC BY 4.0.
"""

import argparse
import csv
import hashlib
import json
from pathlib import Path
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
import zipfile


SOURCES = {
    "s1": {
        "filename": "tiriac_s1.xlsx",
        "url": "https://ndownloader.figshare.com/files/39996304",
        "metadata_url": "https://api.figshare.com/v2/articles/22533058",
        "sha256": "0a2e0220e3cbc41359c5b68744d216507d331aadbe2a590fd5555c1d5b1ca16d",
    },
    "s4": {
        "filename": "tiriac_s4.xlsx",
        "url": "https://ndownloader.figshare.com/files/39996295",
        "metadata_url": "https://api.figshare.com/v2/articles/22533049",
        "sha256": "d80eb561b653f9a2c78d7db79e9c9220a105d3c8bbe8ece700a7698ed0abc8c8",
    },
    "s6": {
        "filename": "tiriac_supplementary_figures.pdf",
        "url": "https://ndownloader.figshare.com/files/39996310",
        "metadata_url": "https://api.figshare.com/v2/articles/22533064",
        "sha256": "1a8d3529cd3f874c4909111e43da4ded15457afb9a3807c4da51090eebb98df6",
    },
}
NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

# Figure S6A labels, transcribed before reading outcome values. Components are
# preserved in the original readout-file order; the frozen model sorts them.
REPORTED_COMPONENTS = {
    "hF31": "gemcitabine+paclitaxel",
    "hF2": "gemcitabine+sn38+5fu",
    "hM1A": "sn38+5fu+oxaliplatin",
    "hF57": "gemcitabine+paclitaxel",
    "hF44": "sn38+5fu+oxaliplatin",
    "hF23": "gemcitabine+paclitaxel",
    "hF50": "5fu",
    "hF3": "5fu+oxaliplatin",
    "hF28": "gemcitabine+5fu",
}


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def fetch_sources(cache, include_figure=False):
    """Reuse only hash-matching cached originals; otherwise fetch official bytes."""
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    paths, receipts = {}, {}
    for key in ("s1", "s4", "s6") if include_figure else ("s1", "s4"):
        source = SOURCES[key]
        path = cache / source["filename"]
        cached = path.exists()
        if not cached:
            request = urllib.request.Request(
                source["url"], headers={"User-Agent": "Tiriac-reproduction/1.0"}
            )
            with urllib.request.urlopen(request, timeout=90) as response:
                payload = response.read()
            actual = hashlib.sha256(payload).hexdigest()
            if actual != source["sha256"]:
                raise ValueError(f"Downloaded {key} hash mismatch: {actual}")
            path.write_bytes(payload)
        actual = sha256(path)
        if actual != source["sha256"]:
            raise ValueError(f"Cached {key} hash mismatch: {actual}")
        paths[key] = path
        receipts[key] = {**source, "bytes": path.stat().st_size, "cache_hit": cached}
    return paths, receipts


def worksheet_rows(path, title):
    """Read the selected original XLSX sheet, including literal #N/A cells."""
    with zipfile.ZipFile(path) as book:
        strings = []
        if "xl/sharedStrings.xml" in book.namelist():
            shared = ET.fromstring(book.read("xl/sharedStrings.xml"))
            strings = ["".join(item.itertext()) for item in shared]
        workbook = ET.fromstring(book.read("xl/workbook.xml"))
        sheets = workbook.find("s:sheets", NS)
        sheet = next((item for item in sheets if item.attrib["name"] == title), None)
        if sheet is None:
            raise ValueError(f"Missing source sheet: {title}")
        relation_id = sheet.attrib[f"{{{REL_NS}}}id"]
        relationships = ET.fromstring(book.read("xl/_rels/workbook.xml.rels"))
        target = next(item.attrib["Target"] for item in relationships
                      if item.attrib["Id"] == relation_id)
        target = target.lstrip("/") if target.startswith("/") else "xl/" + target
        document = ET.fromstring(book.read(target))
        for row in document.findall("s:sheetData/s:row", NS):
            cells = {}
            for cell in row.findall("s:c", NS):
                letters = "".join(c for c in cell.attrib["r"] if c.isalpha())
                col = 0
                for letter in letters:
                    col = col * 26 + ord(letter) - ord("A") + 1
                value = cell.findtext("s:v", default=None, namespaces=NS)
                kind = cell.attrib.get("t")
                if kind == "s" and value is not None:
                    value = strings[int(value)]
                elif kind == "inlineStr":
                    value = "".join(cell.find("s:is", NS).itertext())
                elif value is not None and kind not in ("str", "e", "b"):
                    value = float(value) if any(c in value for c in ".eE") else int(value)
                cells[col - 1] = value
            yield int(row.attrib["r"]), cells


def readouts(paths):
    patient_by_pdo = {}
    for row_number, row in worksheet_rows(paths["s1"], "Patient-Derived Organoid Cohort"):
        if row_number >= 3 and row.get(2) is not None:
            patient_by_pdo[str(row[2])] = str(row[1])
    output = []
    for row_number, row in worksheet_rows(paths["s4"], "Chemo "):
        if not 3 <= row_number <= 68 or row.get(0) is None:
            continue
        pdo = str(row[0])
        if pdo not in patient_by_pdo:
            raise ValueError(f"PDO has no patient mapping: {pdo}")
        output.append({
            "source": "Tiriac2018", "patient_id": patient_by_pdo[pdo], "pdo_id": pdo,
            "gemcitabine_auc": row.get(1), "paclitaxel_auc": row.get(2),
            "sn38_auc": row.get(3), "5fu_auc": row.get(4), "oxaliplatin_auc": row.get(5),
        })
    return output


def split_readouts(rows):
    clinical = [dict(row, regimen=REPORTED_COMPONENTS[row["pdo_id"]])
                for row in rows if row["pdo_id"] in REPORTED_COMPONENTS]
    if {row["pdo_id"] for row in clinical} != set(REPORTED_COMPONENTS):
        raise ValueError("The original table is missing a frozen clinical PDO")
    clinical_patients = {row["patient_id"] for row in clinical}
    reference = [row for row in rows if row["patient_id"] not in clinical_patients]
    return reference, clinical


def write_csv(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--out", type=Path, default=Path("tiriac_readouts.csv"))
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="tiriac-readouts-") as temporary:
        paths, receipts = fetch_sources(args.cache_dir or Path(temporary))
        rows = readouts(paths)
        write_csv(args.out, rows)
    print(json.dumps({"pdo_rows": len(rows),
                      "patient_numbers": len({row["patient_id"] for row in rows}),
                      "readouts_sha256": sha256(args.out), "sources": receipts}))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Audit patient-held-out chip readouts against published clinical response."""

import argparse
import hashlib
import io
import json
import statistics
import urllib.request
import zipfile
from pathlib import Path

import openpyxl
from PIL import Image


ARTICLE = 'https://doi.org/10.1016/j.xcrm.2026.102873'
SOURCE_URL = 'https://pmc-oa-opendata.s3.amazonaws.com/PMC13400167.1/mmc11.zip'
FIGURE_URL = 'https://pmc-oa-opendata.s3.amazonaws.com/PMC13400167.1/gr5.jpg'
SOURCE_SHA256 = '4e5aa07e09b1782d61628d11fcae7ab0989b39ca1fc3be2aed457e0efb3848c8'
FIGURE_SHA256 = '5f3b2bf81757d76c0a111b071f137f596dc17627634104181aacebddb8d0c73f'
SHEET = 'Source data/Source data figure 5.xlsx'
PATIENTS = ('P01', 'P02', 'P03', 'P05', 'P06', 'P10', 'P11', 'P12', 'P13', 'P14',
            'P32', 'P33', 'P34', 'P35', 'P36', 'P37', 'P38', 'P39', 'P40', 'P41', 'P42', 'P43')


def source_bytes(path, url, expected):
    if path:
        data = path.read_bytes()
    else:
        with urllib.request.urlopen(url, timeout=60) as response:
            data = response.read()
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        raise ValueError(f'{url} SHA256 mismatch: {actual}')
    return data


def read_chip(source):
    with zipfile.ZipFile(io.BytesIO(source)) as archive:
        workbook = openpyxl.load_workbook(io.BytesIO(archive.read(SHEET)), read_only=True, data_only=True)
        output = {}
        for sheet, key in (('5n', 'vessel'), ('5o', 'tumoroid')):
            rows = list(workbook[sheet].values)[2:]
            assert tuple(row[0] for row in rows) == PATIENTS
            for row in rows:
                values = row[1:7]
                assert len(values) == 6 and all(isinstance(x, (int, float)) for x in values)
                output.setdefault(row[0], {})[key] = {
                    'original': statistics.mean(values[:3]),
                    'optimized': statistics.mean(values[3:]),
                }
    return output


def read_clinical(figure):
    # Figure 5P's third colored row is the clinical patient response. The
    # first two rows are the authors' chip calls and must not be used as truth.
    image = Image.open(io.BytesIO(figure)).convert('RGB')
    assert image.size == (738, 1038)
    labels = {}
    for i, patient in enumerate(PATIENTS):
        red, green, blue = image.getpixel((350 + int(12.5 * i), 885))
        sensitive = blue > red + 30 and blue > green + 30
        resistant = red > blue + 80 and green > blue + 50
        assert sensitive != resistant, (patient, red, green, blue)
        labels[patient] = int(sensitive)
    assert sum(labels.values()) == 11
    return labels


def balanced_accuracy(truth, predicted):
    sensitivity = sum(p == 1 for t, p in zip(truth, predicted) if t == 1) / sum(t == 1 for t in truth)
    specificity = sum(p == 0 for t, p in zip(truth, predicted) if t == 0) / sum(t == 0 for t in truth)
    return (sensitivity + specificity) / 2, sensitivity, specificity


def threshold(scores, truth):
    ordered = sorted(set(scores))
    candidates = [ordered[0] - 1] + [(a + b) / 2 for a, b in zip(ordered, ordered[1:])] + [ordered[-1] + 1]
    return min(candidates, key=lambda cut: (-balanced_accuracy(truth, [int(x <= cut) for x in scores])[0], cut))


def auc(truth, scores):
    positive = [s for t, s in zip(truth, scores) if t == 1]
    negative = [s for t, s in zip(truth, scores) if t == 0]
    return sum(int(p < n) + .5 * int(p == n) for p in positive for n in negative) / (len(positive) * len(negative))


def evaluate(truth, scores):
    predictions = []
    cuts = []
    for held in range(len(truth)):
        train_scores = [x for i, x in enumerate(scores) if i != held]
        train_truth = [x for i, x in enumerate(truth) if i != held]
        cut = threshold(train_scores, train_truth)
        cuts.append(cut)
        predictions.append(int(scores[held] <= cut))
    ba, sensitivity, specificity = balanced_accuracy(truth, predictions)
    return {'balanced_accuracy': ba, 'clinical_sensitive_recall': sensitivity,
            'clinical_resistant_recall': specificity,
            'accuracy': sum(t == p for t, p in zip(truth, predictions)) / len(truth),
            'auc': auc(truth, scores), 'predictions': predictions, 'training_cutoffs': cuts}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-zip', type=Path)
    parser.add_argument('--figure', type=Path)
    parser.add_argument('--out', type=Path, help='Optional private patient-level audit JSON; stdout is aggregate only')
    args = parser.parse_args()
    source = source_bytes(args.source_zip, SOURCE_URL, SOURCE_SHA256)
    figure = source_bytes(args.figure, FIGURE_URL, FIGURE_SHA256)
    chip, clinical = read_chip(source), read_clinical(figure)
    truth = [clinical[p] for p in PATIENTS]
    scores = {}
    for condition in ('original', 'optimized'):
        for key in ('vessel', 'tumoroid'):
            scores[f'{condition}_{key}'] = [chip[p][key][condition] for p in PATIENTS]
        scores[f'{condition}_mean'] = [statistics.mean((chip[p]['vessel'][condition], chip[p]['tumoroid'][condition])) for p in PATIENTS]
    evaluations = {name: evaluate(truth, score) for name, score in scores.items()}
    baseline = balanced_accuracy(truth, [0] * len(truth))
    result = {
        'schema': 'chip.clinical_holdout.v1', 'article': ARTICLE,
        'source_url': SOURCE_URL, 'source_sha256': SOURCE_SHA256,
        'figure_url': FIGURE_URL, 'figure_sha256': FIGURE_SHA256,
        'source_license': 'CC BY-NC-ND 4.0; original article files are downloaded from PMC, not redistributed',
        'clinical_label_provenance': 'Figure 5P third colored row, blue=clinical sensitive and orange=clinical resistant; 22 IDs follow Source Data Figure 5n/o order',
        'unit': 'patient; three chip replicates averaged within each patient/model/marker',
        'patients': list(PATIENTS), 'clinical_sensitive': truth,
        'scores': scores, 'evaluations': evaluations,
        'fixed_resistant_baseline': {'balanced_accuracy': baseline[0], 'clinical_sensitive_recall': baseline[1], 'clinical_resistant_recall': baseline[2]},
        'authors_in_sample_optimized_accuracy': .8636,
        'limits': 'Single paper and treatment, 22 patients; clinical labels transcribed from a published figure; thresholds are 21-patient trained, not external-lab or prospective validation.'
    }
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2) + '\n')
    brief = {name: {k: round(v, 6) for k, v in values.items() if isinstance(v, float)} for name, values in evaluations.items()}
    print(json.dumps({'n': len(truth), 'clinical_sensitive': sum(truth), 'evaluations': brief}, indent=2))


if __name__ == '__main__':
    main()

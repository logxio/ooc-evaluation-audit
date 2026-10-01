#!/usr/bin/env python3
"""Reproduce the frozen lung-organoid comparison from its original public PDF.

    python lung_reproduce.py --out lung_reproduction.json
    python lung_reproduce.py --source-pdf supplement.pdf --out lung_reproduction.json

Requires Python and Poppler's free ``pdftotext`` command
(Debian/Ubuntu: apt install poppler-utils; macOS: brew install poppler).
All Python imports for this entry point use the standard library.
The default command downloads the original supplement into a temporary directory.
The PDF and extracted patient tables are never written to the output JSON.
This is a replay of the published freeze, not another outcome-blind experiment.
"""

import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import urllib.request
from xml.etree import ElementTree as ET

from lung_signal import GRID, calibrate, fit, predict
from pooled_signal import counts, summary
from conditional_calibration import upper_bound
from release_calibration import digest


SOURCE_URL = 'https://pmc-oa-opendata.s3.amazonaws.com/PMC9975107.1/mmc1.pdf'
SOURCE_SHA256 = 'aa43b02a1c0bb3aeb87fbfccfcb77e33343887f3d5ccfc94cf35e4c9aac7796e'
ARTICLE_URL = 'https://doi.org/10.1016/j.xcrm.2022.100911'
READOUT_FIELDS = ('patient_id', 'organoid_id', 'regimen', 'ic50_raw', 'pdf_page', 'pdf_y')
NS = {'x': 'http://www.w3.org/1999/xhtml'}
RESPONSE = {'PR': 1, 'CR': 1, 'SD': 0, 'PD': 0,
            'PARTIALRESPONSE': 1, 'COMPLETERESPONSE': 1,
            'STABLEDISEASE': 0, 'PROGRESSIVEDISEASE': 0}


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require_equal(actual, expected, description):
    if actual != expected:
        raise ValueError(f'{description} differs from the published freeze')


def verify_certificate(actual, expected, model, training, reference, method):
    """Verify decisions exactly and libm diagnostics against archived training scores."""
    differences = []
    def compare(a, b, path):
        if isinstance(a, dict) and isinstance(b, dict):
            require_equal(set(a), set(b), path + ' keys')
            for key in a:
                compare(a[key], b[key], path + '.' + key)
        elif isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
            require_equal(len(a), len(b), path + ' length')
            for index, (x, y) in enumerate(zip(a, b)):
                compare(x, y, f'{path}[{index}]')
        elif isinstance(a, float) and isinstance(b, float):
            if a != b:
                if not math.isclose(a, b, rel_tol=0., abs_tol=1e-12):
                    raise ValueError(f'{path}: {a!r} versus frozen {b!r}')
                differences.append({'field': path, 'actual': a, 'frozen': b,
                                    'absolute_difference': abs(a-b)})
        else:
            require_equal(a, b, path)

    archived = reference['methods'][method]
    require_equal(digest(archived), expected['ordering_sha256'], 'Archived training ordering hash')
    cases = predict(model, training, method)
    ordering = []
    for margin in GRID[:-1]:
        n, e = counts(cases, training, margin)
        ordering.append((upper_bound(e, n, expected['eta']), -n, margin))
    ordering.sort()
    require_equal(digest(ordering), actual['ordering_sha256'], 'Recomputed training ordering hash')
    # Candidate identity and order are discrete decisions, kept exact.
    require_equal([tuple(row[1:]) for row in ordering],
                  [tuple(row[1:]) for row in archived], 'Training candidate order and counts')
    compare(ordering, archived, method + '.training_order')
    for key in ('overall_margin', 'conditional_margin', 'conditional_certified'):
        require_equal(actual[key], expected[key], method + '.' + key)
    compare({k:v for k,v in actual.items() if k != 'ordering_sha256'},
            {k:v for k,v in expected.items() if k != 'ordering_sha256'}, method + '.certificate')
    return {'ordering_hash_exact': actual['ordering_sha256'] == expected['ordering_sha256'],
            'decisions_exact': True, 'absolute_tolerance': 1e-12,
            'maximum_absolute_difference': max((r['absolute_difference'] for r in differences), default=0.),
            'floating_differences': differences}


def parse_table(pdf, temporary):
    """Extract Table S6 by column coordinates from the hash-pinned supplement."""
    require_equal(file_hash(pdf), SOURCE_SHA256, 'Source PDF SHA256')
    executable = shutil.which('pdftotext')
    if executable is None:
        raise RuntimeError('Install the free Poppler pdftotext command; see module help.')
    bbox = temporary / 'table.xml'
    subprocess.run([executable, '-bbox-layout', str(pdf), str(bbox)],
                   check=True, capture_output=True, text=True, timeout=90)
    pages = ET.parse(bbox).findall('.//x:page', NS)
    readouts, outcomes = [], {}
    for index in (17, 18, 19):
        words = pages[index].findall('.//x:word', NS)
        anchors = sorted(
            [word for word in words
             if 70 <= float(word.attrib['xMin']) < 107
             and re.fullmatch(r'P-\d+-O\d+[A-Z]+', word.text or '')],
            key=lambda word: float(word.attrib['yMin']))
        for position, anchor in enumerate(anchors):
            y = float(anchor.attrib['yMin'])
            low = (float(anchors[position - 1].attrib['yMin']) + y) / 2 if position else y - 9
            high = (float(anchors[position + 1].attrib['yMin']) + y) / 2 if position + 1 < len(anchors) else y + 9

            def column(left, right, drug_order=False):
                selected = [word for word in words
                            if left <= float(word.attrib['xMin']) < right
                            and low < float(word.attrib['yMin']) < high]
                selected.sort(key=lambda word: (
                    round(float(word.attrib['yMin']) / 2) if drug_order else float(word.attrib['yMin']),
                    float(word.attrib['xMin'])))
                return ' '.join(word.text or '' for word in selected)

            organoid = anchor.text
            row = {'patient_id': re.match(r'P-\d+', organoid)[0],
                   'organoid_id': organoid,
                   'regimen': column(453, 534, drug_order=True),
                   'ic50_raw': column(534, 568).replace('ͽ', '>'),
                   'pdf_page': str(index + 1), 'pdf_y': str(y)}
            if not row['regimen'] or not row['ic50_raw']:
                raise ValueError(f'Table S6 readout parsing failed on page {index + 1}')
            readouts.append(row)
            # The adjacent outcome-derived Consistency column is never a feature.
            outcomes[organoid] = column(568, 603)
    require_equal(len(readouts), 54, 'Table S6 record count')
    buffer = io.StringIO(newline='')
    writer = csv.DictWriter(buffer, fieldnames=READOUT_FIELDS)
    writer.writeheader()
    writer.writerows(readouts)
    csv_hash = hashlib.sha256(buffer.getvalue().encode()).hexdigest()
    first = {}
    for row in readouts:
        first.setdefault(row['patient_id'], dict(row, patient=row['patient_id']))
    require_equal(len(first), 36, 'Unique patient count')
    version = subprocess.run([executable, '-v'], capture_output=True, text=True,
                             check=True, timeout=10)
    parser_version = (version.stderr or version.stdout).splitlines()[0]
    return first, outcomes, csv_hash, parser_version


def replay(first, outcomes, readout_hash, protocol, frozen_model, frozen_test):
    require_equal(readout_hash, protocol['source_sha256'], 'Extracted readout CSV SHA256')
    split = protocol['split']
    # The public split is authoritative; also check patient independence and coverage.
    assigned = [patient for role in ('training', 'calibration', 'test') for patient in split[role]]
    require_equal(len(assigned), len(set(assigned)), 'Disjoint patient split')
    require_equal(set(assigned), set(first), 'Split patient coverage')
    require_equal({role: len(ids) for role, ids in split.items()},
                  {'training': 12, 'calibration': 12, 'test': 12}, 'Split sizes')

    excluded = []

    def labelled(role):
        rows = []
        for patient in split[role]:
            row = first[patient]
            raw = outcomes[row['organoid_id']]
            normalized = re.sub('[^A-Za-z]', '', raw).upper()
            if normalized not in RESPONSE:
                excluded.append({'stage': role, 'reason': 'Unrecognized clinical response'})
                continue
            rows.append(dict(row, response_raw=raw, y=RESPONSE[normalized]))
        return rows

    training = labelled('training')
    model = fit(training)
    require_equal(model, frozen_model, 'Refitted training model')
    require_equal(model, frozen_test['model'], 'Model embedded in test freeze')
    calibration = labelled('calibration')
    future = [first[patient] for patient in split['test']]
    require_equal(split['test'], frozen_test['test_ids'], 'Test patient order')
    methods = {}
    numerical_checks = {}
    reference = json.loads((Path(__file__).resolve().parent / 'lung_ordering_reference.json').read_text())
    require_equal(reference['training_sha256'], model['training_sha256'], 'Ordering reference training hash')
    for method in ('shrinkage', 'fixed_baseline'):
        frozen = frozen_test['methods'][method]
        certificate = calibrate(model, training, calibration, method)
        numerical_checks[method] = verify_certificate(
            certificate, frozen['certificate'], model, training, reference, method)
        cases = predict(model, future, method)
        require_equal(cases, frozen['cases'], f'{method} patient predictions and margins')
        calibration_cases = predict(model, calibration, method)
        modes = {}
        for mode, margin in (('uncontrolled', -1.),
                             ('overall_crc', certificate['overall_margin']),
                             ('conditional_ltt', certificate['conditional_margin'])):
            pilot = summary(calibration_cases, calibration, margin)
            released = sum(case['margin'] > margin for case in cases)
            modes[mode] = {'margin': margin, 'calibration': pilot,
                           'forecast': {'released': released, 'retests': len(cases) - released,
                                        'accuracy': (pilot['released'] - pilot['wrong_released'] + .5) /
                                        (pilot['released'] + 1) if pilot['released'] else None}}
        require_equal(modes, frozen['modes'], f'{method} calibration denominators and forecasts')
        methods[method] = modes
    # Match the original stages: fit, calibrate and reproduce predictions before test scoring.
    test = labelled('test')
    require_equal(len(test), len(future), 'Recognized test denominator')
    for method, modes in methods.items():
        cases = predict(model, future, method)
        for value in modes.values():
            value['test'] = summary(cases, test, value['margin'])
    return {'patients': len(test), 'methods': methods,
            'global_cut_log10': model['global_cut'],
            'global_cut_micromolar': math.pow(10, model['global_cut']),
            'drug_cuts_micromolar': {drug: math.pow(10, cut) for drug, cut in model['drug_cuts'].items()},
            'excluded_count': len(excluded), 'exclusion_reasons': excluded,
            'model_sha256': model['model_sha256'], 'numerical_verification': numerical_checks,
            'checks': {'readout_csv_matches': True, 'refitted_model_matches': True,
                       'calibration_certificates_match': True, 'patient_predictions_match': True,
                       'calibration_denominators_and_forecasts_match': True}}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--source-pdf', type=Path, help='Reuse a local copy with the exact source SHA256')
    parser.add_argument('--out', type=Path, default=Path('lung_reproduction.json'))
    args = parser.parse_args()
    directory = Path(__file__).resolve().parent
    paths = {name: directory / filename for name, filename in
             (('protocol', 'lung_protocol.json'), ('model', 'lung_model_frozen.json'),
              ('test', 'lung_test_frozen.json'))}
    objects = {name: json.loads(path.read_text()) for name, path in paths.items()}
    require_equal(file_hash(paths['protocol']), objects['test']['protocol_sha256'], 'Protocol file SHA256')
    require_equal(file_hash(paths['model']), objects['test']['model_file_sha256'], 'Model file SHA256')
    with tempfile.TemporaryDirectory(prefix='lung-replay-') as temporary_name:
        temporary = Path(temporary_name)
        pdf = args.source_pdf
        if pdf is None:
            pdf = temporary / 'supplement.pdf'
            with urllib.request.urlopen(SOURCE_URL, timeout=45) as response:
                content = response.read(50 * 1024 * 1024 + 1)
            if len(content) > 50 * 1024 * 1024:
                raise ValueError('Source download exceeds the expected supplement size limit')
            pdf.write_bytes(content)
        first, outcomes, readout_hash, version = parse_table(pdf, temporary)
        result = replay(first, outcomes, readout_hash, objects['protocol'], objects['model'], objects['test'])
    result.update({'schema': 'release.lung_reproduction.v1',
                   'source': {'article': ARTICLE_URL, 'supplement': SOURCE_URL,
                              'sha256': SOURCE_SHA256, 'license': 'CC BY-NC-ND 4.0',
                              'table': 'Table S6, PDF pages 18-20'},
                   'parser': version, 'source_records': 54, 'unique_patients': 36,
                   'split_counts': {role: len(ids) for role, ids in objects['protocol']['split'].items()},
                   'protocol_sha256': file_hash(paths['protocol']),
                   'test_freeze_sha256': file_hash(paths['test']),
                   'limitations': [
                       'Published retrospective cohort; this command replays an existing freeze.',
                       'One first-occurring organoid record per patient; 18 later records are excluded from the primary analysis.',
                       'IC50 spans distinct treatment regimens; drug-specific estimates shrink toward the training-only pooled cutoff.',
                       'Overall wrong release uses all test patients as denominator; conditional error uses released patients.',
                       'Zero conditional releases give zero coverage and no measured released accuracy.',
                       'Right-censored and extreme extrapolated IC50 values retain the frozen interpretation.',
                       'Original publisher files and patient-level clinical tables are temporary runtime inputs, not output artifacts.']})
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print(json.dumps({'output': str(args.out), 'global_cut_micromolar': result['global_cut_micromolar'],
                      'patients': result['patients'], 'checks': result['checks'],
                      'test': {method: {mode: detail['test'] for mode, detail in modes.items()}
                               for method, modes in result['methods'].items()}}, indent=2))


if __name__ == '__main__':
    main()

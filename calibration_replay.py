#!/usr/bin/env python3
"""Replay a disjoint training/calibration/test release pipeline on three publications.

These outcomes were already public and previously analysed. This is a retrospective
implementation experiment, with one fixed patient split and no test-guided search.
Every point forecast uses calibration outcomes only; saved test calls and forecasts
are written before the scoring step. Original blind-test files remain unchanged.
"""
import argparse
import csv
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from blind2_predict import RECTAL, CRLM_REGIMENS, crlm_values
from blind2_score import RECTAL_CLINICAL, CRLM_CLINICAL
from blind3_predict import READOUT_SHA256, read_table, by_patient, fetch
from release_calibration import fit, calibrate, apply, measure, digest

ALPHAS = (.10, .15, .20)
SEED = 'release-calibration-v2-20261001'


def sources(xlsx):
    rectal = [{'patient': 'Patient' + str(p), 'x': [v[0], v[1]],
               'y': int(RECTAL_CLINICAL[p][1].lower() in ('0', '1', 'ccr', 'pcr'))}
              for p, v in RECTAL.items() if 'radiation' in RECTAL_CLINICAL[p][0].lower()]
    vals = crlm_values('both')
    liver = []
    for p, (regimen, response) in CRLM_CLINICAL.items():
        pair = CRLM_REGIMENS[regimen]
        liver.append({'patient': p, 'x': [vals[p][d] for d in pair], 'y': int(response != 'PD')})
    blob = Path(xlsx).read_bytes() if xlsx else fetch()
    if hashlib.sha256(blob).hexdigest() != READOUT_SHA256:
        raise ValueError('Third-study source checksum differs')
    values, _, _ = by_patient(read_table(blob))
    scored = json.loads(Path('blind3_score.json').read_text())
    tan, seen = [], set()
    for row in scored['analyses']['primary']['rows']:
        p = row['patient']
        if p in seen:
            continue
        seen.add(p)
        tan.append({'patient': p, 'x': [values[p][d] for d in row['readout_pair']],
                    'y': int(row['clinical_benefit'])})
    return {'rectal_2025': rectal, 'liver_metastasis_2022': liver, 'tan_2023': tan}


def split(name, rows):
    ranked = sorted(rows, key=lambda r: hashlib.sha256((SEED + '|' + name + '|' + r['patient']).encode()).hexdigest())
    size = len(ranked) // 3
    return ranked[:size], ranked[size:2*size], ranked[2*size:]


def table(rows, path, labels=True):
    with open(path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['patient', 'readout1', 'readout2'] + (['response'] if labels else []))
        for r in rows:
            writer.writerow([r['patient'], *r['x']] + ([r['y']] if labels else []))


def pilot_forecast(cert, rows, future_n):
    c = measure(cert, rows)
    n = len(rows)
    cases = apply(cert, rows)
    p1, p2 = [sum(a['calls'][j] == r['y'] for a, r in zip(cases, rows)) / n for j in (0, 1)]
    denominator = p1*p2 + (1-p1)*(1-p2)
    return {'basis': 'calibration outcomes only; calculated before test scoring',
            'pilot_readout_accuracies': [p1, p2],
            'independence_formula_for_plain_agreement': p1*p2 / denominator if denominator else None,
            'certificate_release_share': c['coverage'],
            'certificate_released_accuracy_smoothed': (c['released_correct'] + .5) / (c['released'] + 1) if c['released'] else None,
            'expected_releases_from_pilot': future_n * c['coverage'],
            'expected_retests_from_pilot': future_n * (1-c['coverage']),
            'assumptions': 'transportable calibration distribution; smoothed empirical accuracy is a point estimate, not the CRC risk bound'}


def run_source(name, rows, directory):
    directory.mkdir(parents=True, exist_ok=True)
    training, calibration, test = split(name, rows)
    assert not ({r['patient'] for r in training} & {r['patient'] for r in calibration})
    assert not ({r['patient'] for r in test} & {r['patient'] for r in training + calibration})
    table(training, directory / 'training.csv'); table(calibration, directory / 'calibration.csv')
    table(test, directory / 'new_patients.csv', labels=False)
    model = fit(training)
    result = {'patients': len(rows), 'split': {'training': len(training), 'calibration': len(calibration), 'test': len(test)},
              'ids': {k: [r['patient'] for r in v] for k, v in [('training', training), ('calibration', calibration), ('test', test)]},
              'model_sha256': model['model_sha256'], 'levels': []}
    for alpha in ALPHAS:
        certpath = directory / f'certificate_{alpha}.json'
        command = [sys.executable, 'chip_release.py', str(directory / 'calibration.csv'), '--train', str(directory / 'training.csv'),
                   '--a', 'readout1', '--b', 'readout2', '--outcome', 'response', '--certify', str(alpha), '--save-certificate', str(certpath)]
        calstdout = subprocess.check_output(command, text=True)
        (directory / f'calibration_{alpha}.stdout.json').write_text(calstdout)
        cert = json.loads(certpath.read_text())
        assert cert['model'] == model
        actions = directory / f'actions_{alpha}.csv'
        deployed = subprocess.check_output([sys.executable, 'chip_release.py', str(directory / 'new_patients.csv'),
                    '--a', 'readout1', '--b', 'readout2', '--certificate', str(certpath), '--out', str(actions)], text=True)
        (directory / f'deploy_{alpha}.stdout.json').write_text(deployed)
        future_inputs = [{'patient': r['patient'], 'x': r['x']} for r in test]
        predictions = apply(cert, future_inputs)
        forecast = pilot_forecast(cert, calibration, len(test))
        freeze = {'model_sha256': model['model_sha256'], 'alpha': alpha, 'predictions': predictions, 'forecast': forecast}
        frozen_path = directory / f'before_scoring_{alpha}.json'
        frozen_path.write_text(json.dumps(freeze, indent=2, allow_nan=False) + '\n')
        frozen_sha = hashlib.sha256(frozen_path.read_bytes()).hexdigest()
        observed = measure(cert, test)
        with open(actions, newline='') as f:
            cli_actions = list(csv.DictReader(f))
        assert [r['action'].startswith('release') for r in cli_actions] == [r['released'] for r in predictions]
        assert json.loads(deployed)['summary']['model_sha256'] == model['model_sha256']
        assert json.loads(deployed)['summary']['patients_seen_in_training_or_calibration'] == 0
        result['levels'].append({'alpha': alpha, 'threshold': cert['margin'], 'fallback': cert['fallback'],
             'calibration': {k:v for k,v in measure(cert, calibration).items() if k != 'rows'},
             'test': {k:v for k,v in observed.items() if k != 'rows'}, 'forecast': forecast,
             'forecast_released_accuracy_error': observed['released_accuracy'] - forecast['certificate_released_accuracy_smoothed'] if observed['released'] and forecast['certificate_released_accuracy_smoothed'] is not None else None,
             'before_scoring_sha256': frozen_sha, 'test_predictions': predictions,
             'same_model_in_calibration_and_deployment': True, 'cli_actions_equal_library': True})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--third-xlsx', type=Path)
    parser.add_argument('--work-dir', type=Path, help='keep local training tables, certificates and before-scoring predictions')
    parser.add_argument('--out', type=Path, default=Path('calibration_replay.json'))
    args = parser.parse_args()
    data = sources(args.third_xlsx)
    with tempfile.TemporaryDirectory() as tmp:
        root = args.work_dir or Path(tmp)
        results = {name: run_source(name, rows, root / name) for name, rows in data.items()}
    result = {'schema': 'release.calibration.replay.v2', 'seed': SEED,
              'split_rule': 'hash of seed|source|patient; floor(n/3) training, floor(n/3) calibration, remainder test',
              'data_status': 'retrospective replay of previously seen outcomes, one fixed split; no test-guided tuning',
              'sources': results, 'claim': 'Expected overall wrong-release risk under exchangeability; observed overall and released-subset errors reported separately',
              'scope': 'Three different publications; no cross-study exchangeability assumption or patient pooling. Tan uses first eligible treatment per patient with original regimen proxies. Readout2 is the mapped partner drug in regimen cohorts.'}
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print(json.dumps({name: {'split': s['split'], 'levels': [{k:v for k,v in l.items() if k in ('alpha','threshold','fallback','test','forecast_released_accuracy_error')} for l in s['levels']]} for name,s in results.items()}, indent=2))


if __name__ == '__main__':
    main()

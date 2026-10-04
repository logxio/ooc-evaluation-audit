#!/usr/bin/env python3
"""Second, independent benchmark: the frozen AnchorBoost on the US EPA acute MEA screen (Kosnik et al. 2020).

384 ToxCast chemicals were added for about one hour to mature rat cortical networks on 48-well MEA plates at seven
concentrations, one well per concentration in each of three independent culture runs, and 43 network parameters were
recorded before and after dosing (US EPA ScienceHub, DOI 10.23719/1504294, public domain). Responses follow EPA's own
preparation script (wells with fewer than 10 active electrodes at baseline removed, dose minus baseline, values beyond
6 SD of each parameter removed); each plate is then centred on its DMSO wells and each parameter is divided by the robust
SD of all DMSO wells (the SD where that is zero) and clipped to +-10, as for the developmental assay. Concentrations are
grouped per chemical on a 0.1 log10 grid; chemical folds come from a hash of the sample ID. Model, features,
hyperparameters, seeded designs, curve metric and paired chemical bootstrap are those of chip_forecast.py, unchanged.
No choice was made on this dataset, so all five folds are held out (protocol: chip_forecast_acute_protocol.json).
Run: python chip_forecast_acute.py --folds 0 1 2 3 4 --out chip_forecast_acute.json   (one fold per run also works;
     --merge acute_fold*.csv summarizes per-fold CSVs)
"""
import argparse
import csv
import hashlib
import io
import json
import urllib.request
import warnings
import zipfile
from pathlib import Path

import numpy as np

import chip_forecast as cf

ROOT = Path(__file__).resolve().parent
URL = 'https://pasteur.epa.gov/uploads/10.23719/1504294/MEA_All_Data_Scripts.zip'
SHA256 = '38494e1688ee6eafcbc30832755f5df28453893745c5bf8bc3bbfe4800753247'
MEMBER = 'MEA_Data/MEA_Data_Input.csv'
K = 3
BASELINES = ('loglinear_interp', 'hill_per_endpoint', 'analog_knn')


def fetch(cache):
    path = cache / 'MEA_All_Data_Scripts.zip'
    if not path.exists():
        cache.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(URL, timeout=300) as r:
            path.write_bytes(r.read())
    got = hashlib.sha256(path.read_bytes()).hexdigest()
    if got != SHA256:
        raise ValueError(f'{path.name}: SHA-256 {got} differs from pinned {SHA256}')
    return path


def load_tasks(path):
    with zipfile.ZipFile(path) as z:
        table = list(csv.reader(io.TextIOWrapper(z.open(MEMBER), encoding='utf-8')))
    head, body = table[0], table[1:]
    col = {name: i for i, name in enumerate(head)}
    num = lambda name: np.array([float(r[col[name]]) if r[col[name]] not in ('', 'NA') else np.nan for r in body])
    params = [c[:-len('_BASELINE')] for c in head if c.endswith('_BASELINE')]
    bad = num('MEA_NUMBER_OF_ACTIVE_ELECTRODES_BASELINE') < 10
    cols = []
    for p in params:  # EPA preparation script, 1_MEA_Data_Prep.r
        v = num(p + '_DOSE') - num(p + '_BASELINE')
        v[bad] = np.nan
        mu, sd = np.nanmean(v), np.nanstd(v, ddof=1)
        v[(v < mu - 6 * sd) | (v > mu + 6 * sd)] = np.nan
        cols.append(v)
    X = np.column_stack(cols)
    sample = np.array([r[col['SampleID']] for r in body])
    plate = np.array([r[col['PlateID']] for r in body])
    dmso = sample == 'DMSO'
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', RuntimeWarning)  # a plate whose DMSO wells all lack one parameter leaves it missing
        for p in np.unique(plate):
            rows = plate == p
            X[rows] -= np.nanmedian(X[rows & dmso], axis=0)
        mad = 1.4826 * np.nanmedian(np.abs(X[dmso]), axis=0)
        X = np.clip(X / np.where(mad > 0, mad, np.nanstd(X[dmso], axis=0)), -10, 10)
        logc = np.round(np.log10(num('Conc')), 1).astype(np.float32)  # vehicle wells have concentration 0 and are not tasks
    cf.ND, cf.NF, cf.D = 1, len(params), len(params)  # one recording time, 43 parameters
    tasks = []
    for spid in sorted({s for s in sample if s.startswith('TX')}):
        i = np.where(sample == spid)[0]
        y = X[i].reshape(len(i), 1, len(params))
        fold = int(hashlib.sha256(f'acute-mea|{spid}'.encode()).hexdigest()[:8], 16) % 5
        tasks.append(cf.Task(spid, fold, 'unknown', logc[i], np.nan_to_num(y).astype(np.float32), np.isfinite(y)))
    return tasks, params


def summarize(rows, folds):
    pick = lambda name: {r['chemical']: r['curve_mae'] for r in rows if r['method'] == name and r['fold'] in folds}
    ours = pick('anchorboost')
    out = dict(n_chemicals=len(ours), anchorboost=round(float(np.mean(list(ours.values()))), 4), versus={}, fold_means={})
    for name in BASELINES:
        theirs = pick(name)
        out[name] = round(float(np.mean(list(theirs.values()))), 4)
        out['versus'][name] = cf.paired(ours, theirs)
    for f in folds:
        out['fold_means'][f'fold{f}'] = {name: round(float(np.mean([r['curve_mae'] for r in rows if r['method'] == name and r['fold'] == f])), 4)
                                         for name in ('anchorboost',) + BASELINES}
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--cache', type=Path, default=ROOT / '.cache' / 'epa_acute_mea')
    p.add_argument('--folds', type=int, nargs='+', default=[0, 1, 2, 3, 4])
    p.add_argument('--out', type=Path, default=ROOT / 'chip_forecast_acute.json')
    p.add_argument('--merge', type=Path, nargs='+', help='summarize per-fold CSVs written by earlier runs')
    a = p.parse_args()
    if a.merge:
        rows = []
        for path in a.merge:
            with open(path, newline='') as f:
                rows += [dict(r, fold=int(r['fold']), curve_mae=float(r['curve_mae'])) for r in csv.DictReader(f)]
        folds, times = sorted({r['fold'] for r in rows}), None
    else:
        tasks, params = load_tasks(fetch(a.cache))
        rows, times = cf.run(tasks, a.folds, [K])
        folds = a.folds
        with open(a.out.with_suffix('.csv'), 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    res = dict(source=dict(url=URL, sha256=SHA256, member=MEMBER), k=K, folds=folds, timing=times,
               summary=summarize(rows, folds), code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               model_sha256=hashlib.sha256(Path(cf.__file__).read_bytes()).hexdigest())
    a.out.write_text(json.dumps(res, indent=1) + '\n')
    print(json.dumps(res['summary'], indent=1))


if __name__ == '__main__':
    main()

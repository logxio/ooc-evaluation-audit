#!/usr/bin/env python3
"""From forecast to decision: call a chemical active or inactive from three measured concentrations, or measure the full series.

Forecasts are the frozen AnchorBoost of chip_forecast.py at three measured concentrations, for the five published designs
of every held-out chemical (--predict, one model per outer fold). The decision endpoint is the full-series activity call of
epa_release.py: a chemical is active when its largest absolute DIV-mean response over the 17 features and all tested
concentrations reaches 3. A design's score is that largest response over the full series, with measured concentrations as
measured and the others as forecast; log-linear interpolation never exceeds the measured values, so its score is the
measured-only call. The release rule is the one behind the patient report list (matched_regimen.py): two training folds
fix the score cutoff and its reference ranks, two calibration folds fix the release margin by conformal risk control at
alpha 0.10, and calls that clear the margin are released from three concentrations; the rest go to the full series.
Run: python chip_forecast_decision.py --predict --folds 0 --out decision_fold0.npz   (one or more folds)
     python chip_forecast_decision.py --analyze decision_fold*.npz --test 1 2 3 4
"""
import argparse
import hashlib
import json
import time
import warnings
from pathlib import Path

import numpy as np

import chip_forecast as cf

ROOT = Path(__file__).resolve().parent
K = 3
THRESHOLD = 3.0
ALPHA = 0.10
SPLITS = {f: ([g for g in range(5) if g != f][:2], [g for g in range(5) if g != f][2:]) for f in range(5)}  # (training, calibration)
METHODS = ('anchorboost', 'measured_only')


def predict(tasks, folds):
    out, seconds = {}, {}
    for fold in folds:
        start = time.time()
        model = cf.AnchorBoost([t for t in tasks if t.fold != fold], K)
        rec = dict(chem=[], design=[], level=[], pred=[])
        for t in tasks:
            if t.fold != fold or K >= len(t.levels):
                continue
            for di, ctx in enumerate(cf.designs(t, K)):
                ic = np.isin(t.logc, ctx)
                lv = np.unique(t.logc[~ic])
                for q, row in zip(lv, model(t, ic, lv).reshape(len(lv), cf.D)):
                    rec['chem'].append(t.chem)
                    rec['design'].append(di)
                    rec['level'].append(int(np.searchsorted(t.levels, q)))
                    rec['pred'].append(row)
        out[fold] = rec
        seconds[f'fold{fold}'] = round(time.time() - start, 1)
    return out, seconds


def save(out, seconds, path):
    arrays = {}
    for fold, r in out.items():
        arrays[f'fold{fold}_chem'] = np.array(r['chem'])
        arrays[f'fold{fold}_design'] = np.array(r['design'], np.int16)
        arrays[f'fold{fold}_level'] = np.array(r['level'], np.int16)
        arrays[f'fold{fold}_pred'] = np.array(r['pred'], np.float32)
    np.savez_compressed(path, **arrays)
    path.with_suffix('.json').write_text(json.dumps(dict(k=K, folds=sorted(out), seconds=seconds,
                                                         code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()), indent=1) + '\n')


def load(paths):
    forecasts = {}
    for path in paths:
        z = np.load(path)
        for fold in sorted({int(k.split('_')[0][4:]) for k in z.files}):
            for c, d, lvl, p in zip(*(z[f'fold{fold}_{n}'] for n in ('chem', 'design', 'level', 'pred'))):
                forecasts.setdefault((str(c), int(d)), {})[int(lvl)] = p
    return forecasts


def rows(tasks, forecasts):
    """One row per held-out (chemical, design): forecast and measured-only scores, full-series label and wells."""
    out = []
    for t in tasks:
        if K >= len(t.levels) or (t.chem, 0) not in forecasts:
            continue
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', RuntimeWarning)
            effect = np.nan_to_num(np.abs(np.nanmean(np.where(t.ok, t.mu, np.nan), axis=1)), nan=0.0)  # level x feature
        wells = np.bincount(t.lvidx, minlength=len(t.levels))
        for di, ctx in enumerate(cf.designs(t, K)):
            m = np.searchsorted(t.levels, ctx)
            measured = float(effect[m].max())
            forecast = max(float(np.abs(p.reshape(cf.ND, cf.NF).mean(0)).max()) for p in forecasts[(t.chem, di)].values())
            out.append(dict(patient=f'{t.chem}|{di}', chem=t.chem, fold=t.fold, y=int(effect.max() < THRESHOLD),
                            anchorboost=max(measured, forecast), measured_only=measured,
                            wells_measured=int(wells[m].sum()), wells_full=int(wells.sum())))
    return out


def decide(table, test, method):
    """Fit, calibrate and apply the patient release rule to one method's scores for one test fold."""
    import matched_regimen as mr  # the release rule behind the patient report list
    fit_folds, cal_folds = SPLITS[test]
    unit = lambda r: dict(patient=r['patient'], x=r[method], y=r['y'])
    train = [unit(r) for r in table if r['fold'] in fit_folds]
    model = mr.fit(train)
    cert = mr.calibrate(model, train, [unit(r) for r in table if r['fold'] in cal_folds], alpha=ALPHA)
    held = [r for r in table if r['fold'] == test]
    for r, c in zip(held, mr.predict(model, [dict(patient=r['patient'], x=r[method]) for r in held])):
        r[method + '_release'] = c['margin'] > cert['overall_margin']
        r[method + '_call'] = c['prediction']
        r[method + '_margin'] = c['margin']
    return dict(cutoff=round(model['cutoff'], 4), margin=cert['overall_margin'])


def summary(table, method):
    n = len(table)
    released = [r for r in table if r[method + '_release']]
    wrong = sum(r[method + '_call'] != r['y'] for r in released)
    used = sum(r['wells_measured'] if r[method + '_release'] else r['wells_full'] for r in table)
    full = sum(r['wells_full'] for r in table)
    return dict(designs=n, released=len(released), wrong_released=wrong, retests=n - len(released),
                coverage=round(len(released) / n, 4), overall_wrong_release=round(wrong / n, 4),
                released_error=round(wrong / len(released), 4) if released else None,
                wells_used=used, wells_full=full, wells_saved_fraction=round(1 - used / full, 4),
                full_coverage_errors=sum(r[method + '_call'] != r['y'] for r in table))


def paired(table, n=4000, seed=0):
    """Chemical bootstrap of AnchorBoost minus measured-only: released share, wrong releases per design, wells saved,
    and wrong calls per design when every call is released at the training cutoff."""
    chems = sorted({r['chem'] for r in table})
    per = {c: np.zeros(6) for c in chems}
    for r in table:
        v = per[r['chem']]
        v[0] += 1
        v[1] += r['anchorboost_release'] - r['measured_only_release']
        v[2] += (r['anchorboost_release'] and r['anchorboost_call'] != r['y']) - (r['measured_only_release'] and r['measured_only_call'] != r['y'])
        v[3] += (r['wells_full'] - r['wells_measured']) * (r['anchorboost_release'] - r['measured_only_release'])
        v[4] += r['wells_full']
        v[5] += (r['anchorboost_call'] != r['y']) - (r['measured_only_call'] != r['y'])
    a = np.array([per[c] for c in chems])
    rng = np.random.default_rng(seed)
    stats = lambda s: (s[:, 1].sum() / s[:, 0].sum(), s[:, 2].sum() / s[:, 0].sum(), s[:, 3].sum() / s[:, 4].sum(),
                       s[:, 5].sum() / s[:, 0].sum())
    boot = np.array([stats(a[rng.integers(0, len(a), len(a))]) for _ in range(n)])
    est = stats(a)
    ci = lambda j: [round(float(np.percentile(boot[:, j], 2.5)), 4), round(float(np.percentile(boot[:, j], 97.5)), 4)]
    return dict(chemicals=len(chems),
                released_share=dict(value=round(est[0], 4), ci95=ci(0)),
                wrong_release_per_design=dict(value=round(est[1], 4), ci95=ci(1)),
                wells_saved_share=dict(value=round(est[2], 4), ci95=ci(2)),
                full_coverage_wrong_calls_per_design=dict(value=round(est[3], 4), ci95=ci(3)))


def at_risk(a, risk):
    """Largest released share whose wrong releases stay within risk x designs, releasing by margin (largest first)."""
    best = 0
    for n, wrong in enumerate(np.cumsum(a[np.argsort(-a[:, 0], kind='stable'), 1]), 1):
        if wrong <= risk * len(a):
            best = n
    return best / len(a)


def equal_risk(table, risks=(0.05, 0.10), n=4000, seed=0):
    """Released share of each method at the same realized wrong-release share, ranking by its own margin; chemical bootstrap of the gap."""
    chems = sorted({r['chem'] for r in table})
    group = {c: i for i, c in enumerate(chems)}
    arr = {m: np.array([[r[m + '_margin'], r[m + '_call'] != r['y'], group[r['chem']]] for r in table], float) for m in METHODS}
    idx = [np.where(arr[METHODS[0]][:, 2] == i)[0] for i in range(len(chems))]
    rng = np.random.default_rng(seed)
    out = {}
    for risk in risks:
        est = {m: at_risk(arr[m], risk) for m in METHODS}
        gaps = []
        for _ in range(n):
            pick = np.concatenate([idx[i] for i in rng.integers(0, len(chems), len(chems))])
            gaps.append(at_risk(arr[METHODS[0]][pick], risk) - at_risk(arr[METHODS[1]][pick], risk))
        out[f'risk_{risk:.2f}'] = dict(**{m: round(est[m], 4) for m in METHODS},
                                       gap=round(est[METHODS[0]] - est[METHODS[1]], 4),
                                       gap_ci95=[round(float(np.percentile(gaps, 2.5)), 4), round(float(np.percentile(gaps, 97.5)), 4)])
    return out


def analyze(tasks, forecasts, test):
    table = rows(tasks, forecasts)
    rules = {f'fold{f}': {m: decide(table, f, m) for m in METHODS} for f in test}
    held = [r for r in table if r['fold'] in test]
    return dict(test_folds=list(test), threshold=THRESHOLD, alpha=ALPHA, splits={f'fold{f}': SPLITS[f] for f in test},
                full_series_inactive_share=round(float(np.mean([r['y'] for r in held])), 4),
                rules=rules, **{m: summary(held, m) for m in METHODS},
                anchorboost_minus_measured_only=paired(held), equal_risk=equal_risk(held))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--cache', type=Path, default=ROOT / '.cache' / 'neurochip_twin')
    p.add_argument('--predict', action='store_true')
    p.add_argument('--folds', type=int, nargs='+', default=[0, 1, 2, 3, 4])
    p.add_argument('--out', type=Path, default=ROOT / 'chip_forecast_decision.json')
    p.add_argument('--analyze', type=Path, nargs='+')
    p.add_argument('--test', type=int, nargs='+', default=[1, 2, 3, 4])
    a = p.parse_args()
    files = cf.fetch(a.cache)
    tasks = cf.load_tasks(files['data_bundle/nfa_tasks.npz'])
    if a.predict:
        out, seconds = predict(tasks, a.folds)
        save(out, seconds, a.out)
        print(json.dumps(seconds))
        return
    res = analyze(tasks, load(a.analyze), a.test)
    res['code_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    text = json.dumps(res, indent=1) + '\n'
    a.out.write_text(text)
    print(text, end='')


if __name__ == '__main__':
    main()

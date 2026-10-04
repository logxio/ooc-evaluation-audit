#!/usr/bin/env python3
"""Build workbench/data/ooc-data.js, the one data file the workbench page reads (window.OOC).

Every value is read from a repository file or recomputed with repository code; nothing is typed in. Each recomputation
is checked against the published summary it must reproduce before anything is written: the decision chain against
chip_forecast_decision.json, the action list against chip_forecast_actions.csv, per-chemical comparisons against
chip_forecast_result.json, the example forecasts against chip_forecast_examples.json, plain interval coverage exactly and
learned interval coverage within 0.002 of chip_forecast_intervals.json (the quantile width model is refitted here).

Run from the repository root; each step is one short process (about 30 s and under 1 GB on a laptop CPU):
  for f in 1 2 3 4; do python workbench/build_data.py widths --fold $f; done
  python workbench/build_data.py export
"""
import argparse
import base64
import csv
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = REL = HERE.parent
OUT = HERE / 'data' / 'ooc-data.js'
BUILD = HERE / '.build'
sys.path[:0] = [str(REL), str(REL / 'src')]

import chip_forecast as cf  # noqa: E402
import chip_forecast_decision as dc  # noqa: E402
import chip_forecast_selfcheck as sc  # noqa: E402

FEATURES = ['mean firing rate', 'burst rate', 'interspike interval within bursts', 'percent of spikes in bursts',
            'mean burst duration', 'mean interburst interval', 'active electrodes', 'bursting electrodes',
            'network spikes', 'network spike peak', 'mean spike duration', 'percent of spikes in network spikes',
            'mean network-spike interval', 'network-spike duration SD', 'spikes per network spike',
            'mean correlation coefficient', 'normalised mutual information']  # chip_forecast_figure.FEATURES order
DIVS = [5, 7, 9, 12]
TEST = [1, 2, 3, 4]
SOURCES = {}


def find(name):
    """A repository input, wherever the current layout keeps it."""
    for base in (REL, REL / 'results', REL / 'src'):
        if (base / name).exists():
            return base / name
    raise FileNotFoundError(name)


def read(path):
    path = Path(path)
    SOURCES[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return path


def load_json(path):
    return json.loads(read(path).read_text())


def tasks_all():
    files = cf.fetch(REL / '.cache' / 'neurochip_twin')
    read(files['data_bundle/nfa_tasks.npz'])
    return cf.load_tasks(files['data_bundle/nfa_tasks.npz'])


def selfcheck_parts():
    return sc.load([read(p) for p in sorted(find('chip_forecast_runs').glob('selfcheck_fold*.npz'))])


# ---------------------------------------------------------------- widths
def widths(test):
    import chip_forecast_intervals as ci
    tasks = tasks_all()
    parts = selfcheck_parts()
    ci.attach(parts, tasks)
    f = test
    cal = [g for g in sorted(parts) if g != f]
    rng = np.random.default_rng(0)
    P = parts[f]
    e, d = (np.concatenate([parts[g][n] for g in cal]) for n in ('errs', 'dims'))
    plain_by_dim = np.array([sc.quantile(e[d == j]) for j in range(cf.D)])
    plain = plain_by_dim[P['dims']]
    scores, scale = [], np.zeros(len(P['errs']))
    for g in cal:
        model = ci.width_model(parts, [h for h in cal if h != g], rng)
        scores.append(parts[g]['errs'] / model(parts[g]['X']))
        scale += model(P['X']) / len(cal)
    learned = sc.quantile(np.concatenate(scores)) * scale
    got = dict(plain=dict(coverage=round(float((P['errs'] <= plain).mean()), 4), half_width=round(float(plain.mean()), 3)),
               learned=dict(coverage=round(float((P['errs'] <= learned).mean()), 4), half_width=round(float(learned.mean()), 3)))
    pub = load_json(find('chip_forecast_intervals.json'))['per_fold'][f'fold{f}']
    # plain intervals use no model and must match exactly; the quantile width model is a pinned-version rerun whose
    # float summation order differs between the registered Kaggle x86 run and this machine
    if got['plain'] != pub['plain'] or abs(got['learned']['coverage'] - pub['learned']['coverage']) > 0.002 \
            or abs(got['learned']['half_width'] - pub['learned']['half_width']) > 0.02:
        raise SystemExit(f'fold {f}: recomputed {got} differs from chip_forecast_intervals.json {pub}')
    BUILD.mkdir(exist_ok=True)
    np.savez_compressed(BUILD / f'widths_fold{f}.npz', learned=learned.astype(np.float32), plain_by_dim=plain_by_dim.astype(np.float32))
    print(json.dumps(dict(fold=f, intervals=got)), flush=True)


# ---------------------------------------------------------------- export helpers
def b64(values, scale=100):
    """Int16 fixed point (value * scale), -32768 marks a missing value; base64 for a compact script file."""
    a = np.asarray(values, np.float64)
    q = np.where(np.isfinite(a), np.clip(np.round(a * scale), -32767, 32767), -32768).astype('<i2')
    return base64.b64encode(q.tobytes()).decode()


def r(x, n=4):
    return None if x is None or (isinstance(x, float) and not math.isfinite(x)) else round(float(x), n)


def entry_layout(t, ctx):
    """Held-out (well index, output) order of chip_forecast_selfcheck / chip_forecast_intervals for one design."""
    ic = np.isin(t.logc, ctx)
    held = np.where(~ic)[0]
    W, J = np.nonzero(t.m[~ic].reshape(len(held), cf.D))
    return ic, held, W, J


def export():
    tasks = tasks_all()
    by_chem = {t.chem: t for t in tasks}
    forecasts = dc.load([read(p) for p in sorted(find('chip_forecast_runs').glob('decision_fold*.npz'))])

    # decision chain, both methods, exactly as chip_forecast_decision.analyze
    table = dc.rows(tasks, forecasts)
    rules = {f: {m: dc.decide(table, f, m) for m in dc.METHODS} for f in TEST}
    held_rows = [x for x in table if x['fold'] in TEST]
    pub_dec = load_json(find('chip_forecast_decision.json'))
    for m in dc.METHODS:
        got = dc.summary(held_rows, m)
        if got != pub_dec[m]:
            raise SystemExit(f'decision summary {m}: {got} != {pub_dec[m]}')
    dec_by = {(x['chem'], int(x['patient'].rsplit('|', 1)[1])): x for x in held_rows}

    # action list must agree with the recomputed chain row for row
    with read(find('chip_forecast_actions.csv')).open(newline='') as fh:
        actions = list(csv.DictReader(fh))
    for a in actions:
        x = dec_by[(a['chemical'], int(a['design']))]
        if (a['action'] == 'report call') != bool(x['anchorboost_release']) or round(x['anchorboost_margin'], 4) != float(a['margin']):
            raise SystemExit(f'actions.csv disagrees for {a["chemical"]} design {a["design"]}')

    # per-chemical method errors (k=3) and the published neural process
    res = {}
    with read(find('chip_forecast_result.csv')).open(newline='') as fh:
        for row in csv.DictReader(fh):
            if row['k'] == '3' and int(row['fold']) in TEST:
                res.setdefault(row['chemical'], {})[row['method']] = float(row['curve_mae'])
    pub = cf.published(read(REL / '.cache' / 'neurochip_twin' / 'trajectory_cv_per_chemical.csv'))
    for c in res:
        res[c]['published_neural_process'] = pub[(3, 'neurotrajectory')][c]
    summary = load_json(find('chip_forecast_result.json'))['summary_folds_1to4']['k3']
    for name, v in summary['versus'].items():
        d = np.array([res[c]['anchorboost'] - res[c][name] for c in res])
        frac = round(float((d < 0).mean()), 3)
        rel = round(float(100 * d.mean() / np.mean([res[c][name] for c in res])), 2)
        if frac != v['frac_chem_improved'] or rel != v['rel_change_pct']:
            raise SystemExit(f'versus {name}: {frac},{rel} != {v}')

    # learned widths and errors per held-out entry
    parts = selfcheck_parts()
    wid = {f: np.load(BUILD / f'widths_fold{f}.npz') for f in TEST}
    cov_hit = np.zeros(cf.D)
    cov_hit_plain = np.zeros(cf.D)
    cov_n = np.zeros(cf.D)
    max_err_gap = 0.0

    held = [t for t in tasks if t.fold in TEST and dc.K < len(t.levels)]
    chems = []
    for f in TEST:
        P = parts[f]
        names = list(P['names'])
        learned = wid[f]['learned']
        plain_by_dim = wid[f]['plain_by_dim']
        ftasks = [t for t in tasks if t.fold == f and dc.K < len(t.levels)]
        assert [t.chem for t in ftasks] == names
        offsets = {}
        start = 0
        for ci_, t in enumerate(ftasks):
            for di, ctx in enumerate(cf.designs(t, dc.K)):
                ic, hidx, W, J = entry_layout(t, ctx)
                n = len(J)
                sl = slice(start, start + n)
                assert np.all(P['chem'][sl] == ci_) and np.all(P['design'][sl] == di) and np.array_equal(P['dims'][sl], J)
                offsets[(ci_, di)] = (start, n, ic, hidx, W, J)
                start += n
        assert start == len(P['errs'])

        for ci_, t in enumerate(ftasks):
            designs = []
            for di, ctx in enumerate(cf.designs(t, dc.K)):
                s0, n, ic, hidx, W, J = offsets[(ci_, di)]
                err = P['errs'][s0:s0 + n]
                lw = learned[s0:s0 + n]
                q = np.unique(t.logc[~ic])
                qi = np.searchsorted(t.levels, q)
                pred = np.stack([forecasts[(t.chem, di)][int(i)] for i in qi])  # (Q, 68)
                # the decision-chain forecasts are the same frozen model as the self-check errors
                lvl_of_w = np.searchsorted(q, t.logc[hidx][W])
                chk = np.abs(pred[lvl_of_w, J] - t.y[hidx].reshape(len(hidx), cf.D)[W, J].astype(np.float32))
                max_err_gap = max(max_err_gap, float(np.abs(chk - err).max()))
                width = np.full((len(q), cf.D), np.nan)
                width[lvl_of_w, J] = lw
                outerr = np.full(cf.D, np.nan)
                for j in range(cf.D):
                    m = J == j
                    if m.any():
                        outerr[j] = float(err[m].mean())
                hit = err <= lw
                np.add.at(cov_hit, J, hit)
                np.add.at(cov_hit_plain, J, err <= plain_by_dim[J])
                np.add.at(cov_n, J, 1)
                loglin = cf.predict_interp(t, ic, q).reshape(len(q), cf.D)
                x = dec_by[(t.chem, di)]
                designs.append(dict(
                    m=[int(i) for i in np.searchsorted(t.levels, np.unique(t.logc[ic]))],
                    q=[int(i) for i in qi],
                    f=b64(pred), ll=b64(loglin), w=b64(width), e=b64(outerr, 1000),
                    act=int(bool(x['anchorboost_release'])), call=int(x['anchorboost_call']), mar=float(x['anchorboost_margin']),
                    score=r(x['anchorboost']), mo=r(x['measured_only']), moAct=int(bool(x['measured_only_release'])),
                    moCall=int(x['measured_only_call']), moMar=float(x['measured_only_margin']),
                    y=int(x['y']), wm=int(x['wells_measured']), wf=int(x['wells_full'])))
            chems.append(dict(name=t.chem, fold=t.fold, label=t.label, d=designs,
                              err={k: r(v) for k, v in res[t.chem].items()},
                              rm=rules[t.fold]['anchorboost']['margin'], cut=rules[t.fold]['anchorboost']['cutoff'],
                              moRm=rules[t.fold]['measured_only']['margin'], moCut=rules[t.fold]['measured_only']['cutoff']))
    if max_err_gap > 1e-3:
        raise SystemExit(f'decision forecasts differ from self-check errors by {max_err_gap}')
    pub_int = load_json(find('chip_forecast_intervals.json'))
    cov_total = round(float(cov_hit.sum() / cov_n.sum()), 4)
    if abs(cov_total - pub_int['learned']['coverage']) > 0.002 or int(cov_n.sum()) != pub_int['wells']:
        raise SystemExit(f'coverage {cov_total} / {int(cov_n.sum())} != intervals.json')

    # wells of every chemical (plates hold held-out and development chemicals side by side)
    wells = []
    for t in tasks:
        y = np.where(t.m, t.y.astype(np.float64), np.nan).reshape(len(t.logc), cf.D)
        wells.append(dict(name=t.chem, fold=t.fold, levels=[r(v, 6) for v in t.levels], lv=[int(i) for i in t.lvidx], y=b64(y)))
    z = np.load(REL / '.cache' / 'neurochip_twin' / 'nfa_tasks.npz')
    off = z['offsets']
    plate_of = {str(c): [str(p) for p in z['plate'][off[i]:off[i + 1]]] for i, c in enumerate(z['chem'])}
    for w in wells:
        w['plate'] = plate_of[w['name']]

    # design patterns (7-level chemicals): rank positions of the three measured concentrations
    patterns = {}
    for c in chems:
        if len(next(w for w in wells if w['name'] == c['name'])['levels']) != 7:
            continue
        for dd in c['d']:
            key = ''.join(str(i) for i in dd['m'])
            p = patterns.setdefault(key, dict(n=0, rep=0, wrong=0))
            p['n'] += 1
            p['rep'] += dd['act']
            p['wrong'] += int(dd['act'] and dd['call'] != dd['y'])

    # examples file must agree with the decision forecasts (design 0, DIV 12, its feature)
    examples = load_json(find('chip_forecast_examples.json'))
    for ex in examples:
        t = by_chem[ex['chemical']]
        fidx = FEATURES.index(ex['feature'])
        qi = np.searchsorted(t.levels, np.array(ex['queries'], np.float32))
        got = [float(forecasts[(t.chem, 0)][int(i)].reshape(cf.ND, cf.NF)[3, fidx]) for i in qi]
        if max(abs(a - b) for a, b in zip(got, ex['anchorboost'])) > 1e-3:
            raise SystemExit(f'example {ex["chemical"]} differs from decision forecasts')

    # patients (combined-regimen primary packet)
    pw = load_json(find('patient_workbench_result.json'))
    frozen = load_json(find('matched_regimen_frozen.json'))['model']
    agent = agent_replay()
    forest = forest_rows()
    abl = load_json(find('chip_forecast_ablations.json'))
    curve = load_json(find('chip_forecast_designcurve.json'))
    fres = load_json(find('chip_forecast_result.json'))
    timing = fres['timing']
    designs_enumerated = {f'fold{f}': sum(math.comb(len(t.levels), dc.K) for t in tasks if t.fold != f and dc.K < len(t.levels)) for f in range(5)}
    train_chems = {f'fold{f}': sum(1 for t in tasks if t.fold != f and dc.K < len(t.levels)) for f in range(5)}

    data = dict(
        schema='ooc.workbench.demo.v1',
        features=FEATURES, divs=DIVS, threshold=dc.THRESHOLD, alpha=dc.ALPHA,
        chems=chems, wells=wells, patterns=patterns,
        coverage=dict(hit=[int(v) for v in cov_hit], plainHit=[int(v) for v in cov_hit_plain], n=[int(v) for v in cov_n]),
        intervals=pub_int, decision=pub_dec,
        versus=summary, examples=[dict(chemical=e['chemical'], role=e['role'], feature=e['feature']) for e in examples],
        ablations=abl, designcurve=curve, forest=forest,
        model=dict(params=fres['model'], timing=timing, designs_enumerated=designs_enumerated, train_chems=train_chems,
                   wells=int(sum(len(t.logc) for t in tasks)), chemicals=len(tasks), held_out=len(held)),
        patients=dict(rows=pw['rows'], cases=pw['cases'], rule=pw['rule'], study=pw['study'],
                      cutoff=frozen['cutoff'], training=len(frozen['training_ids'])),
        agent=agent, sources=SOURCES)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    text = 'window.OOC = ' + json.dumps(data, separators=(',', ':'), allow_nan=False) + ';\n'
    OUT.write_text(text)
    print(json.dumps(dict(out=str(OUT), bytes=len(text), chemicals=len(chems), designs=sum(len(c['d']) for c in chems),
                          coverage=cov_total, max_err_gap=max_err_gap, patterns=len(patterns))))


def forest_rows():
    fres = load_json(find('chip_forecast_result.json'))
    rows = []
    for f in TEST:
        v = fres['summary_by_fold'][f'fold{f}']['k3']['versus']['loglinear_interp']
        rows.append(dict(screen='nfa', fold=f, d=v['mean_diff'], lo=v['ci95'][0], hi=v['ci95'][1], rel=v['rel_change_pct'], n=v['n_chemicals']))
    for f in range(5):
        v = load_json(find('chip_forecast_runs') / f'acute_fold{f}.json')['summary']['versus']['loglinear_interp']
        rows.append(dict(screen='acute', fold=f, d=v['mean_diff'], lo=v['ci95'][0], hi=v['ci95'][1], rel=v['rel_change_pct'], n=v['n_chemicals']))
    dnt = load_json(find('chip_forecast_dnt.json'))['summary']
    for f in range(5):
        v = dnt['fold_versus_loglinear'][f'fold{f}']
        rows.append(dict(screen='dnt', fold=f, d=v['mean_diff'], lo=v['ci95'][0], hi=v['ci95'][1], rel=v['rel_change_pct'], n=v['n_chemicals']))
    acute = load_json(find('chip_forecast_acute.json'))['summary']
    totals = dict(nfa=fres['summary_folds_1to4']['k3']['versus']['loglinear_interp'],
                  acute=acute['versus']['loglinear_interp'], dnt=dnt['versus']['loglinear_interp'])
    return dict(rows=rows, totals=totals,
                chemicals=dict(nfa=fres['summary_folds_1to4']['k3']['n_chemicals'], acute=acute['n_chemicals'], dnt=dnt['n_chemicals']))


def find_key(obj, key):
    """First value stored under `key` anywhere in a nested JSON object."""
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        obj = list(obj.values())
    if isinstance(obj, list):
        for v in obj:
            hit = find_key(v, key)
            if hit is not None:
                return hit
    return None


def agent_replay():
    base = find('contract_agent')
    res = load_json(base / 'agent_results.json')
    paper = 'pmc10777586'
    chain = base / 'agent_archive' / 'round5' / 'strong' / paper
    idx = load_json(base / 'agent_archive' / 'sources' / paper / 'index.json')
    prov = load_json(base / 'agent_archive' / 'provenance' / f'{paper}.json')['provenance']
    state = load_json(chain / 'state.json')
    audit = load_json(base / 'agent_archive' / 'audit.json')
    steps = []
    for path in sorted(chain.glob('call*.tools.json')):
        call = int(path.name[4:6])
        receipt = load_json(chain / f'call{call:02d}.receipt.json')
        for tool in load_json(path):
            out = tool.get('output') or {}
            step = dict(call=call, tool=tool['name'], args=tool.get('arguments'), usage=receipt.get('usage'))
            if tool['name'] == 'preview_table':
                step['rows'] = [[c['value'] for c in row['cells']] for row in out.get('rows', [])]
                step['caption'] = out.get('caption')
            elif tool['name'] == 'read_figure':
                step['columns'] = out.get('columns')
                step['legend'] = out.get('legend')
                step['rows'] = [[c['value'] for c in row['cells']] for row in out.get('rows', [])]
                step['source'] = out.get('source')
            elif tool['name'] in ('initial_code', 'finish'):
                con = out.get('contract') or (tool.get('arguments') or {}).get('contract')
                step['status'] = (con or {}).get('status')
            steps.append(step)
    final = state['checkpoints']['tool_loop']['contract']
    quotes = {}
    for f in final['fields'].values():
        for ev in f['evidence']:
            if ev.startswith('article:') and ev in idx:
                quotes[ev] = idx[ev]
    rd = res['rounds']['round5']['strong']['papers'][paper]
    return dict(paper=paper, title=prov['title'], doi=prov['doi'], citation=prov['citation'], license=prov['metadata_license'],
                fields={k: dict(value=v['value'], explanation=v['explanation'], evidence=v['evidence']) for k, v in final['fields'].items()},
                headline={k: final['headline'][k] for k in ('metric', 'reported', 'threshold', 'op', 'score_direction')},
                records=len(final['headline']['records']), evaluation=state.get('last_evaluation'),
                quotes=quotes, steps=steps, run=dict(model_calls=rd['model_calls'], reader_calls=rd['reader_calls'],
                                                     prompt_tokens=rd['prompt_tokens'], seconds=rd['model_seconds']),
                audit=find_key(audit, paper),
                cohort=res['final']['round5/strong'], development=res['final']['round4/strong'])


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('widths').add_argument('--fold', type=int, required=True, choices=TEST)
    sub.add_parser('export')
    a = ap.parse_args()
    widths(a.fold) if a.cmd == 'widths' else export()

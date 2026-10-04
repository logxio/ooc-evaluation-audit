#!/usr/bin/env python3
"""Measured versus forecast responses for three held-out chemicals (chip_forecast_examples.png).

Each panel uses the chemical's first published three-concentration design, the model of its own held-out
fold and the DIV 12 feature whose measured concentration means vary most. Computing the series trains two
fold models (a few minutes on CPU) and saves them to JSON; drawing reads only that JSON.

Run: python src/chip_forecast_figure.py --data chip_forecast_examples.json  (compute, then draw)
     python src/chip_forecast_figure.py --plot chip_forecast_examples.json  (draw only)
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
EXAMPLES = [('Trimethyltin hydroxide', 'largest gain over interpolation'),
            ('Cariporide mesylate', 'median gain over interpolation'),
            ('Sodium valproate', 'largest loss')]
FEATURES = ['mean firing rate', 'burst rate', 'interspike interval within bursts', 'percent of spikes in bursts',
            'mean burst duration', 'mean interburst interval', 'active electrodes', 'bursting electrodes',
            'network spikes', 'network spike peak', 'mean spike duration', 'percent of spikes in network spikes',
            'mean network-spike interval', 'network-spike duration SD', 'spikes per network spike',
            'mean correlation coefficient', 'normalised mutual information']
INK, MUTED, GRID, SURFACE, AB, LL = '#0b0b0b', '#52514e', '#ecebe7', '#fcfcfb', '#2a78d6', '#eb6834'


def compute(cache):
    import chip_forecast as cf
    files = cf.fetch(cache)
    tasks = cf.load_tasks(files['data_bundle/nfa_tasks.npz'])
    pub = cf.published(files['results/trajectory_cv_per_chemical.csv'])
    by_name, models, panels = {t.chem: t for t in tasks}, {}, []
    for chem, role in EXAMPLES:
        t = by_name[chem]
        if t.fold not in models:
            models[t.fold] = cf.AnchorBoost([x for x in tasks if x.fold != t.fold], 3)
        model = models[t.fold]
        ctx = cf.designs(t, 3)[0]
        ic = np.isin(t.logc, ctx)
        q = np.unique(t.logc[~ic])
        mu, ok = t.mu[:, 3], t.ok[:, 3]
        f = int(np.argmax(np.where(ok.all(0), mu.max(0) - mu.min(0), -1)))
        errs = []
        for d in cf.designs(t, 3):
            dc = np.isin(t.logc, d)
            errs.append(cf.errors(model(t, dc, np.unique(t.logc[~dc])), t, ~dc)[0])
        panels.append(dict(chemical=chem, role=role, fold=t.fold, feature=FEATURES[f], levels=t.levels.tolist(),
                           measured=mu[:, f].tolist(), context=np.unique(t.logc[ic]).tolist(), queries=q.tolist(),
                           anchorboost=model(t, ic, q)[:, 3, f].tolist(), loglinear=cf.predict_interp(t, ic, q)[:, 3, f].tolist(),
                           error=dict(anchorboost=float(np.mean(errs)), loglinear=pub[(3, 'loglinear_interp')][chem],
                                      neural_process=pub[(3, 'neurotrajectory')][chem])))
    return panels


def tick(c):
    return f'{c:.0f}' if c >= 100 else f'{c:g}'


def draw(panels, out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, len(panels), figsize=(13, 4.8), facecolor=SURFACE, layout='constrained')
    for ax, p in zip(axes, panels):
        lv, mu = np.array(p['levels']), np.array(p['measured'])
        ctx, q = np.array(p['context']), np.array(p['queries'])
        mc = mu[np.searchsorted(lv, ctx)]
        x = np.r_[ctx, q]
        order = np.argsort(x)
        ax.set_facecolor(SURFACE)
        ax.plot(x[order], np.r_[mc, p['loglinear']][order], color=LL, lw=2, ls=(0, (5, 3)), zorder=2)
        ax.plot(x[order], np.r_[mc, p['anchorboost']][order], color=AB, lw=2, zorder=3)
        ax.scatter(q, p['loglinear'], s=40, color=LL, edgecolor=SURFACE, linewidth=1.5, zorder=4)
        ax.scatter(q, p['anchorboost'], s=40, color=AB, edgecolor=SURFACE, linewidth=1.5, zorder=5)
        ax.scatter(lv, mu, s=72, facecolor=SURFACE, edgecolor=INK, linewidth=1.4, zorder=6)
        ax.scatter(ctx, mc, s=72, color=INK, zorder=7)
        ax.set_xticks(lv)
        ax.set_xticklabels([tick(10 ** v) for v in lv], fontsize=7.5, color=MUTED, rotation=45)
        ax.tick_params(axis='y', labelsize=8, colors=MUTED)
        for side in ('top', 'right'):
            ax.spines[side].set_visible(False)
        for side in ('left', 'bottom'):
            ax.spines[side].set_color('#c9c8c3')
        ax.grid(axis='y', color=GRID, lw=0.8)
        e = p['error']
        ax.set_title(f"{p['chemical']}, {p['role']}\n{p['feature']}, DIV 12", fontsize=9.5, color=INK, loc='left')
        ax.set_xlabel(f"Concentration (µM)\nchemical error: AnchorBoost {e['anchorboost']:.2f}, interpolation "
                      f"{e['loglinear']:.2f},\nneural process {e['neural_process']:.2f}", fontsize=7.5, color=MUTED)
    axes[0].set_ylabel('Response, vehicle-normalised units', fontsize=8.5, color=MUTED)
    handles = [plt.Line2D([], [], marker='o', color=INK, ls='', ms=7, label='Measured, given to the model'),
               plt.Line2D([], [], marker='o', mfc=SURFACE, mec=INK, ls='', ms=7, label='Measured, held out'),
               plt.Line2D([], [], color=AB, lw=2, marker='o', ms=5, label='AnchorBoost forecast'),
               plt.Line2D([], [], color=LL, lw=2, ls=(0, (5, 3)), marker='o', ms=5, label='Log-linear interpolation')]
    fig.legend(handles=handles, loc='outside upper center', ncol=4, frameon=False, fontsize=9)
    fig.savefig(out, dpi=200, facecolor=SURFACE)
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--cache', type=Path, default=ROOT / '.cache' / 'neurochip_twin')
    p.add_argument('--data', type=Path, help='compute the series, save them here, then draw')
    p.add_argument('--plot', type=Path, help='draw from a saved series file')
    p.add_argument('--out', type=Path, default=ROOT / 'chip_forecast_examples.png')
    a = p.parse_args()
    if a.plot:
        panels = json.loads(a.plot.read_text())
    else:
        panels = compute(a.cache)
        (a.data or ROOT / 'chip_forecast_examples.json').write_text(json.dumps(panels, indent=1) + '\n')
    print(draw(panels, a.out))


if __name__ == '__main__':
    main()

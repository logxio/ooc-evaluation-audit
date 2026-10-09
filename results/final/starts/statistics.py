"""Frozen start-design statistics, extracted without training code."""
import numpy as np
import hashlib
from collections import defaultdict
METHODS = ["anchorboost", "measured_only", "loglinear"]
RATES = ["report_rate", "wrong_loss", "fn_loss", "fp_loss"]
SCREEN = ["reports_screen", "fn_screen", "fp_screen", "wrong_screen", "wells_screen"]
NATIVE = ["reports", "fn", "fp", "wrong", "wells_used"]
SOURCE_SHA256 = "560881875da908a5703559e4077696632341f53ba79fe52d393b2f384cf8c242"
CEILING_SOURCE_SHA256 = "7b8dd379a70d06f2f20b9290356ee3da52d4d3b2de7c888685fdf7c0632e5be8"

class Boot:
    """Identity-group bootstrap; one index matrix per population, reused for every statistic."""

    def __init__(self, groups, replicates=4000, seed=0):
        self.groups = sorted(groups)
        self.n = len(self.groups)
        self.index = {g: i for i, g in enumerate(self.groups)}
        self.ix = np.random.default_rng(seed).integers(0, self.n, (replicates, self.n))
        self.W = np.stack([np.bincount(row, minlength=self.n) for row in self.ix]).astype(np.float64)

    @staticmethod
    def _est(point, reps):
        lo, hi = np.quantile(reps, [.025, .975])
        return {'estimate': float(point), 'ci95': [float(lo), float(hi)]}

    def mean(self, v, present=None):
        if present is None or present.all():
            return self._est(v.mean(), self.W @ v / self.n)
        drawn = self.W @ present.astype(float)
        if drawn.min() <= 0:
            raise AssertionError('A bootstrap replicate has no group in the stratum')
        return self._est(v[present].mean(), (self.W @ (v * present)) / drawn)

    def total(self, v):
        return self._est(v.sum(), self.W @ v)

    def ratio(self, a, b, complement=False):
        if b.sum() == 0:
            return None
        den = self.W @ b
        point, reps = a.sum() / b.sum(), (self.W @ a) / np.where(den == 0, np.nan, den)
        if np.isnan(reps).any():
            return {'estimate': float(1 - point if complement else point), 'ci95': None}
        return self._est(1 - point, 1 - reps) if complement else self._est(point, reps)

    def difference_of_means(self, a, pa, b, pb):
        da, db = self.W @ pa.astype(float), self.W @ pb.astype(float)
        return self._est(a[pa].mean() - b[pb].mean(), (self.W @ (a * pa)) / da - (self.W @ (b * pb)) / db)

    def difference_of_savings(self, a1, b1, a2, b2):
        point = (1 - a1.sum() / b1.sum()) - (1 - a2.sum() / b2.sum())
        reps = (1 - (self.W @ a1) / (self.W @ b1)) - (1 - (self.W @ a2) / (self.W @ b2))
        return self._est(point, reps)

def group_values(boot, chems, groups, rep, fn, fp, used, full):
    """Per identity group: counts over all rows, rates as the mean over rows, and one-screening-per-substance sums."""
    n = boot.n
    rep, fn, fp, used, full = (np.asarray(x, float) for x in (rep, fn, fp, used, full))
    gi = np.array([boot.index[g] for g in groups])
    names, ci = np.unique(np.array(chems), return_inverse=True)
    per_substance = np.bincount(ci).astype(float)
    sub_group = np.zeros(len(names), int)
    sub_group[ci] = gi
    designs = np.bincount(gi, minlength=n).astype(float)
    present = designs > 0
    gsum = lambda x: np.bincount(gi, weights=x, minlength=n)
    rate = lambda x: gsum(x) / np.maximum(designs, 1)
    screen = lambda x: np.bincount(sub_group, weights=np.bincount(ci, weights=x) / per_substance, minlength=n)
    wrong = fn + fp
    return dict(present=present, designs=designs, substances=np.bincount(sub_group, minlength=n).astype(float),
                reports=gsum(rep), fn=gsum(fn), fp=gsum(fp), wrong=gsum(wrong), wells_used=gsum(used), wells_full=gsum(full),
                report_rate=rate(rep), wrong_loss=rate(wrong), fn_loss=rate(fn), fp_loss=rate(fp),
                reports_screen=screen(rep), fn_screen=screen(fn), fp_screen=screen(fp), wrong_screen=screen(wrong),
                wells_screen=screen(used), full_screen=screen(full))

def cell_summary(boot, v):
    out = dict(designs=float(v['designs'].sum()), substances=int(v['substances'].sum()), groups=int(v['present'].sum()))
    for k in NATIVE + ['wells_full']:
        out[k] = boot.total(v[k])
    for k in RATES:
        out[k] = boot.mean(v[k], v['present'])
    for k in SCREEN + ['full_screen']:
        out[k] = boot.total(v[k])
    out['saving_vs_full'] = boot.ratio(v['wells_screen'], v['full_screen'], complement=True)
    out['error_among_reports'] = boot.ratio(v['wrong'], v['reports'])
    out['fn_among_reports'] = boot.ratio(v['fn'], v['reports'])
    return out

def contrast(boot, a, b):
    """a minus b on the same population and the same groups."""
    present = a['present'] & b['present']
    if not (np.array_equal(a['present'], b['present'])):
        raise AssertionError('Contrast cells cover different groups')
    out = dict(groups=int(present.sum()))
    for k in RATES:
        out[k] = boot.mean(a[k] - b[k], present)
    for k in SCREEN:
        out[k] = boot.total(a[k] - b[k])
    if np.array_equal(a['designs'], b['designs']):
        for k in NATIVE:
            out[k + '_native'] = boot.total(a[k] - b[k])
    out['relative_well_saving'] = boot.ratio(a['wells_screen'], b['wells_screen'], complement=True)
    return out

def three_point(boot, rows, method, release):
    """Group values of a three-point arm: rows with one method's call and a release flag per row."""
    release = np.asarray(release, bool)
    call = np.array([r[method + '_call'] for r in rows])
    truth = np.array([r['truth'] for r in rows])
    wm = np.array([r['wells_measured'] for r in rows], float)
    wf = np.array([r['wells_full'] for r in rows], float)
    return group_values(boot, [r['chemical'] for r in rows], [r['drug_group'] for r in rows], release,
                        release & (call == 1) & (truth == 0), release & (call == 0) & (truth == 1), np.where(release, wm, wf), wf)

def q1_block(three_rows, joint_rows):
    """Stratification by whether the published start contains the highest tested concentration."""
    boot = Boot({r['drug_group'] for r in three_rows})
    strata = {'contains_top': True, 'not_contains_top': False}
    out = dict(population=dict(designs=len(three_rows), substances=len({r['chemical'] for r in three_rows}), groups=boot.n), three_point={}, closed_loop={})
    table = []

    def emit(block, stratum, name, summary, kind='cell', comparator=''):
        row = dict(block=block, stratum=stratum, kind=kind, method=name, comparator=comparator)
        for k, v in summary.items():
            if isinstance(v, dict):
                row[k] = v['estimate']
                row[k + '_lo'], row[k + '_hi'] = v['ci95'] if v['ci95'] else ('', '')
            elif v is not None:
                row[k] = v
        table.append(row)

    values = {}
    for stratum, flag in list(strata.items()) + [('all', None)]:
        rr = [r for r in three_rows if flag is None or r['contains_top'] == flag]
        out['three_point'][stratum] = dict(designs=len(rr), substances=len({r['chemical'] for r in rr}), groups=len({r['drug_group'] for r in rr}), methods={}, contrasts={})
        for m in METHODS:
            values[stratum, m] = v = three_point(boot, rr, m, [r['release'][f'published|{m}'] for r in rr])
            out['three_point'][stratum]['methods'][m] = s = cell_summary(boot, v)
            emit('three_point', stratum, m, s)
        for comparator in ['measured_only', 'loglinear']:
            c = contrast(boot, values[stratum, 'anchorboost'], values[stratum, comparator])
            out['three_point'][stratum]['contrasts'][f'anchorboost__minus__{comparator}'] = c
            emit('three_point', stratum, 'anchorboost', c, 'contrast', comparator)
    out['three_point']['between_strata'] = {}
    for comparator in ['measured_only', 'loglinear']:
        a, b = ('contains_top', 'not_contains_top')
        cell = {}
        for k in RATES:
            da = values[a, 'anchorboost'][k] - values[a, comparator][k]
            db = values[b, 'anchorboost'][k] - values[b, comparator][k]
            cell[k] = boot.difference_of_means(da, values[a, 'anchorboost']['present'], db, values[b, 'anchorboost']['present'])
        cell['relative_well_saving'] = boot.difference_of_savings(values[a, 'anchorboost']['wells_screen'], values[a, comparator]['wells_screen'],
                                                                 values[b, 'anchorboost']['wells_screen'], values[b, comparator]['wells_screen'])
        out['three_point']['between_strata'][f'anchorboost__minus__{comparator}'] = cell
        emit('three_point', 'contains_top__minus__not_contains_top', 'anchorboost', cell, 'between_strata', comparator)
    if joint_rows:
        jvalues = {}
        for stratum, flag in list(strata.items()) + [('all', None)]:
            out['closed_loop'][stratum] = dict(methods={}, contrasts={})
            for policy in POLICIES + BASELINES:
                rr = [r for r in joint_rows if r['policy'] == policy and (flag is None or r['contains_top'] == flag)]
                jvalues[stratum, policy] = v = group_values(boot, [r['chemical'] for r in rr], [r['drug_group'] for r in rr],
                                                           [r['reports'] for r in rr], [r['fn'] for r in rr], [r['fp'] for r in rr],
                                                           [r['wells_used'] for r in rr], [r['wells_full'] for r in rr])
                s = cell_summary(boot, v)
                s['stage1_reports'] = float(sum(r['stage1_reports'] for r in rr))
                s['stage2_reports'] = float(sum(r['stage2_reports'] for r in rr))
                s['completed'] = float(sum(r['completed'] for r in rr))
                out['closed_loop'][stratum]['methods'][policy] = s
                emit('closed_loop', stratum, policy, s)
            for policy in POLICIES:
                for baseline in BASELINES:
                    c = contrast(boot, jvalues[stratum, policy], jvalues[stratum, baseline])
                    out['closed_loop'][stratum]['contrasts'][f'{policy}__minus__{baseline}'] = c
                    emit('closed_loop', stratum, policy, c, 'contrast', baseline)
            for policy in POLICIES[1:]:
                c = contrast(boot, jvalues[stratum, 'model_disagreement'], jvalues[stratum, policy])
                out['closed_loop'][stratum]['contrasts'][f'model_disagreement__minus__{policy}'] = c
                emit('closed_loop', stratum, 'model_disagreement', c, 'contrast', policy)
    return out, table

def ceiling(rows, release_key):
    """AnchorBoost gain by rank of the highest measured concentration; rows of all 35 starts of seven-level substances."""
    groups = sorted({r['drug_group'] for r in rows})
    G = len(groups)
    gidx = {g: i for i, g in enumerate(groups)}
    designs = sorted({r['design'] for r in rows})
    if len(designs) != 35 or len(rows) != 35 * len({r['chemical'] for r in rows}):
        raise AssertionError('Ceiling rows are not the complete 35-start family')
    ix = np.random.default_rng(0).integers(0, G, (4000, G))
    W = np.stack([np.bincount(row, minlength=G) for row in ix]).astype(float)

    def est(point, reps):
        lo, hi = np.quantile(reps, [.025, .975])
        return float(point), float(lo), float(hi)

    def group_rates(rr, m):
        n = np.zeros(G)
        rep = np.zeros(G)
        wrong = np.zeros(G)
        for r in rr:
            g = gidx[r['drug_group']]
            rel = r['release'][release_key.format(m=m)]
            call, truth = r[m + '_call'], r['truth']
            n[g] += 1
            rep[g] += rel
            wrong[g] += rel and call != truth
        assert (n > 0).all()
        return rep / n, wrong / n

    def paired(rr, comp):
        a_rep, a_wr = group_rates(rr, 'anchorboost')
        b_rep, b_wr = group_rates(rr, comp)
        d_rep, d_wr = 100 * (a_rep - b_rep), 100 * (a_wr - b_wr)
        return est(d_rep.mean(), W @ d_rep / G), est(d_wr.mean(), W @ d_wr / G), d_rep

    top_rank = {d: max(int(c) for c in d) + 1 for d in designs}
    span = {d: max(int(c) for c in d) - min(int(c) for c in d) for d in designs}
    by_design = {d: [r for r in rows if r['design'] == d] for d in designs}
    per_design = []
    for d in designs:
        rr = by_design[d]
        row = dict(design=d, levels_1based='-'.join(str(int(c) + 1) for c in d), top_rank=top_rank[d], span=span[d], contains_top=top_rank[d] == 7)
        for m in METHODS:
            rep, _ = group_rates(rr, m)
            row[f'{m}_report_rate'] = round(100 * rep.mean(), 10)
        for comp in ['measured_only', 'loglinear']:
            (g, glo, ghi), (w, wlo, whi), _ = paired(rr, comp)
            row.update({f'gain_vs_{comp}': g, f'gain_vs_{comp}_lo': glo, f'gain_vs_{comp}_hi': ghi,
                        f'wrong_loss_diff_vs_{comp}': w, f'wrong_loss_diff_vs_{comp}_lo': wlo, f'wrong_loss_diff_vs_{comp}_hi': whi})
        per_design.append(row)

    def class_table(key, label):
        out, vecs = [], {}
        for k in sorted({key[d] for d in designs}):
            ds = [d for d in designs if key[d] == k]
            rr = [r for d in ds for r in by_design[d]]
            row = {label: k, 'n_starts': len(ds), 'starts': ';'.join(ds)}
            for comp in ['measured_only', 'loglinear']:
                (g, glo, ghi), (w, wlo, whi), vec = paired(rr, comp)
                vecs[k, comp] = vec
                pts = [x[f'gain_vs_{comp}'] for x in per_design if x['design'] in ds]
                row.update({f'gain_vs_{comp}': g, f'gain_vs_{comp}_lo': glo, f'gain_vs_{comp}_hi': ghi,
                            f'min_start_gain_vs_{comp}': min(pts), f'max_start_gain_vs_{comp}': max(pts),
                            f'mean_of_start_gains_vs_{comp}': float(np.mean(pts)),
                            f'wrong_loss_diff_vs_{comp}': w, f'wrong_loss_diff_vs_{comp}_lo': wlo, f'wrong_loss_diff_vs_{comp}_hi': whi})
            out.append(row)
        return out, vecs

    rank_rows, rank_vecs = class_table(top_rank, 'top_rank')
    span_rows, _ = class_table(span, 'span')
    contrasts = []
    for comp in ['measured_only', 'loglinear']:
        for r in range(3, 7):
            v = rank_vecs[r, comp] - rank_vecs[r + 1, comp]
            g, lo, hi = est(v.mean(), W @ v / G)
            contrasts.append(dict(comparator=comp, contrast=f'rank{r}_minus_rank{r + 1}', difference=g, lo=lo, hi=hi,
                                  share_of_draws_positive=float(((W @ v / G) > 0).mean())))
    far = [r for d in designs if top_rank[d] <= 5 for r in by_design[d]]
    nontop = [r for d in designs if top_rank[d] < 7 for r in by_design[d]]
    top = [r for d in designs if top_rank[d] == 7 for r in by_design[d]]
    pooled = {}
    for name, rr in [('nontop20', nontop), ('top15', top), ('rank_le5_10starts', far)]:
        for comp in ['measured_only', 'loglinear']:
            (g, lo, hi), (w, wlo, whi), _ = paired(rr, comp)
            pooled[f'{name}|{comp}'] = [g, lo, hi]
            pooled[f'{name}|{comp}|wrong_loss_diff'] = [w, wlo, whi]
    pm = {x['design']: x for x in per_design}
    r5 = [pm[d]['gain_vs_measured_only'] for d in designs if top_rank[d] == 5]
    r6 = [pm[d]['gain_vs_measured_only'] for d in designs if top_rank[d] == 6]
    cross = sorted(d for d in designs if top_rank[d] < 7 and pm[d]['gain_vs_measured_only_lo'] <= 0 <= pm[d]['gain_vs_measured_only_hi'])
    means = [r['gain_vs_measured_only'] for r in rank_rows]
    span_means = [r['gain_vs_measured_only'] for r in span_rows]
    facts = dict(
        rank_means_vs_measured_only={r['top_rank']: r['gain_vs_measured_only'] for r in rank_rows},
        monotone_ranks_4_to_7=bool(all(a > b for a, b in zip(means[1:], means[2:]))),
        rank3_below_rank4=bool(means[0] < means[1]),
        rank6_max_start=max(r6), rank5_min_start=min(r5), rank5_rank6_disjoint=bool(max(r6) < min(r5)),
        nontop_intervals_touching_zero=cross,
        nontop_intervals_strictly_crossing_zero=sorted(d for d in cross if pm[d]['gain_vs_measured_only_lo'] < 0),
        span_means_vs_measured_only={r['span']: r['gain_vs_measured_only'] for r in span_rows},
        span_monotone=bool(all(a >= b for a, b in zip(span_means, span_means[1:])) or all(a <= b for a, b in zip(span_means, span_means[1:]))),
        span2_range=[min(pm[d]['gain_vs_measured_only'] for d in designs if span[d] == 2), max(pm[d]['gain_vs_measured_only'] for d in designs if span[d] == 2)])

    def eta2(key):
        y = np.array([pm[d]['gain_vs_measured_only'] for d in designs])
        k = np.array([key[d] for d in designs])
        between = sum((k == c).sum() * (y[k == c].mean() - y.mean()) ** 2 for c in set(k))
        total = ((y - y.mean()) ** 2).sum()
        return float(between / total) if total > 0 else None

    facts['between_start_variance_explained'] = dict(top_rank=eta2(top_rank), span=eta2(span))
    return dict(population=dict(rows=len(rows), substances=len({r['chemical'] for r in rows}), identity_groups=G, starts=len(designs)),
                bootstrap=dict(replicates=4000, seed=0, W_sha256=hashlib.sha256(W.astype(np.uint16).tobytes()).hexdigest()),
                per_design=per_design, rank_classes=rank_rows, span_classes=span_rows, adjacent_contrasts=contrasts, pooled=pooled, facts=facts)

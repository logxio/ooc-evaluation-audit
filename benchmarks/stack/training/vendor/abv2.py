#!/usr/bin/env python3
"""AnchorBoost-v2: the release AnchorBoost plus neighbour-curve residual columns.

Every added column varies with the query concentration and the output. A neighbour set's mean response curve is
read two ways: through the same interpolation anchor as the target (`res`: the set's own deviation from straight
lines through the revealed concentrations, the quantity the booster predicts) and against the predicted chemical's
anchor (`lvl`, the convention of the release `near` column). Neighbour sets hold training chemicals only and never
the predicted chemical or any member of its identity group:

  date    training chemicals recorded on a date of the predicted chemical's revealed wells
  plate   training chemicals on a plate of the revealed wells
  datew   the date set weighted by response similarity at the revealed concentrations (release Analog weights)
  struct  the m training chemicals nearest in the Monroe structure embedding (cosine), similarity-weighted

Training rows use the same construction with the training chemical's own revealed wells, so a row never sees
itself or its identity group. With no block the model is chip_forecast.AnchorBoost line for line (same rows, same
column order, same booster), which `--check` style tests assert prediction for prediction.

The model takes the chemical metadata it may read (well log-concentrations, well dates and plates, identity group,
structure row) from `meta`, keyed by chemical name. Metadata carries no response; at prediction time only the
dates and plates of wells at the revealed concentrations enter. `__call__(task, ic, q)` is the release signature.
"""
from __future__ import annotations

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor

D = 68
BLOCKS = ('date', 'plate', 'datew', 'struct', 'structw', 'struct2')


def anchor_curve(lv, M, q):
    """Piecewise-linear between the rows of M (L, 68) at levels lv, flat outside: the release anchor operator."""
    q = np.asarray(q, np.float64)
    if len(lv) == 1:
        return np.repeat(M[:1], len(q), 0)
    i = np.clip(np.searchsorted(lv, q), 1, len(lv) - 1)
    x0, x1 = lv[i - 1], lv[i]
    w = np.clip((q - x0) / np.where(x1 > x0, x1 - x0, 1), 0, 1)[:, None]
    return M[i - 1] * (1 - w) + M[i] * w


class Library:
    """GRID profiles of the training chemicals (n, G, 68), measured-output mask (n, 68), batch and structure index."""

    def __init__(self, cf, train, meta, struct_m=10, struct_temp=None):
        self.cf = cf
        self.G = np.asarray(cf.GRID, np.float64)
        self.P = np.stack([cf.interp_rows(t.levels, t.mu, t.ok, cf.GRID).reshape(len(cf.GRID), D)
                           for t in train]).astype(np.float64)
        self.V = np.stack([t.ok.reshape(len(t.levels), D).any(0) for t in train]).astype(np.float64)
        self.names = [t.chem for t in train]
        self.at_name = {c: i for i, c in enumerate(self.names)}
        self.group = np.array([meta[c]['group'] for c in self.names])
        self.members = {'date': {}, 'plate': {}}
        for i, c in enumerate(self.names):
            for b in ('date', 'plate'):
                for key in set(meta[c][b].tolist()):
                    self.members[b].setdefault(key, set()).add(i)
        self.struct_m = struct_m
        self.struct_temp = struct_temp
        self.index = {}
        for key in ('struct', 'struct2'):
            Z = [meta[c].get(key) for c in self.names]
            has = np.array([z is not None and np.isfinite(z).all() for z in Z])
            dim = next((len(z) for z in Z if z is not None), 0)
            self.index[key] = (np.stack([z / np.linalg.norm(z) if ok else np.zeros(dim) for z, ok in zip(Z, has)]) if dim else None, has)
        self.Z, self.has_z = self.index['struct']
        self._cache = {}

    def at(self, idx, x):
        """Profiles of chemicals idx at log-concentrations x: (m, len(x), 68)."""
        x = np.asarray(x, np.float64)
        G = self.G
        i = np.clip(np.searchsorted(G, x), 1, len(G) - 1)
        w = np.clip((x - G[i - 1]) / (G[i] - G[i - 1]), 0, 1)
        P = self.P[idx]
        return P[:, i - 1] * (1 - w)[None, :, None] + P[:, i] * w[None, :, None]

    def batch_mates(self, block, keys, group):
        ck = (block, keys, group)
        if ck not in self._cache:
            idx = set()
            for key in keys:
                idx |= self.members[block].get(key, set())
            self._cache[ck] = np.array(sorted(j for j in idx if self.group[j] != group), int)
        return self._cache[ck]

    def drop_plates(self, idx, plates):
        """idx without the chemicals that have any well on one of the given plates (plate-held-out isolation)."""
        bad = set()
        for key in plates:
            bad |= self.members['plate'].get(key, set())
        return np.array([j for j in idx if j not in bad], int)

    def struct_mates(self, z, group, key='struct'):
        """m nearest training chemicals by cosine similarity (identity group excluded), weights = similarity."""
        Zk, has = self.index[key]
        if Zk is None or z is None or not np.isfinite(z).all():
            return np.zeros(0, int), np.zeros(0)
        ck = (key, z.tobytes(), group)
        if ck not in self._cache:
            sim = Zk @ (z / np.linalg.norm(z))
            sim[~has | (self.group == group)] = -np.inf
            order = np.argsort(-sim, kind='stable')[:self.struct_m]
            order = order[np.isfinite(sim[order])]
            if self.struct_temp:
                w = np.exp((sim[order] - sim[order].max()) / self.struct_temp) if len(order) else np.zeros(0)
            else:
                w = np.clip(sim[order], 1e-3, None)
            self._cache[ck] = (order, w)
        return self._cache[ck]

    def curve(self, idx, w, x):
        """Weighted mean curve of chemicals idx at x over the outputs each one measured: (len(x), 68), NaN if none."""
        if len(idx) == 0:
            return np.full((len(x), D), np.nan)
        A = self.at(idx, x)
        W = np.asarray(w, np.float64)[:, None] * self.V[idx]
        den = W.sum(0)
        out = np.einsum('mxo,mo->xo', A, W) / np.where(den > 0, den, 1)
        out[:, den <= 0] = np.nan
        return out


def mate_columns(lib, idx, w, lv, q, base):
    """res = curve(q) - anchor(curve at lv)(q); lvl = curve(q) - base; both (Q, 68)."""
    x = np.concatenate([lv, q])
    C = lib.curve(idx, w, x)
    CS, CQ = C[:len(lv)], C[len(lv):]
    return CQ - anchor_curve(lv, CS, q), CQ - base


class AnchorBoostV2:
    """chip_forecast.AnchorBoost with neighbour-curve columns, optional pooled-k training and chemical bagging.

    cfg keys: blocks (subset of BLOCKS, in order), params (booster settings; default chip_forecast.MODEL),
    train_ks (revealed-level counts whose training designs are pooled; default [k]), n_bag (1 = no bagging),
    bag_frac (fraction of training identity groups per bag), struct_m (structure neighbours), seed."""

    def __init__(self, cf, train, k, meta, cfg=None):
        cfg = dict(cfg or {})
        self.cf, self.meta, self.k = cf, meta, k
        self.blocks = list(cfg.get('blocks', []))
        assert all(b in BLOCKS for b in self.blocks), self.blocks
        self.params = dict(cfg.get('params') or cf.MODEL)
        self.train_ks = list(cfg.get('train_ks') or [k])
        self.pool = self.train_ks != [k]
        self.n_bag = int(cfg.get('n_bag', 1))
        self.bag_frac = float(cfg.get('bag_frac', 0.8))
        self.seed = int(cfg.get('seed', 0))
        # batch_dropout: share of training identity groups whose training rows carry no batch neighbours (NaN), so the
        # booster learns the unseen-batch path; isolate (set after fitting): None, 'plate' or 'date' at prediction time.
        self.batch_dropout = float(cfg.get('batch_dropout', 0.0))
        self.isolate = None
        self.analog_train = cf.Analog(train, exclude_self=True)
        self.analog = cf.Analog(train)
        self.profiles = cf.Profiles(train)
        self.lib = Library(cf, train, meta, int(cfg.get('struct_m', 10)), cfg.get('struct_temp')) if self.blocks else None
        X, y, chem = self._rows(train)
        self.rows = int(len(y))
        self.n_features = int(X.shape[1])
        if self.n_bag == 1:
            self.models = [HistGradientBoostingRegressor(**self.params).fit(X, y)]
        else:
            groups = np.array([meta[c]['group'] for c in chem])
            names = np.array(sorted(set(groups.tolist())))
            rng = np.random.default_rng(self.seed)
            self.models = []
            for b in range(self.n_bag):
                keep = set(rng.choice(names, size=int(round(self.bag_frac * len(names))), replace=False).tolist())
                sel = np.array([g in keep for g in groups])
                p = dict(self.params, random_state=int(self.params.get('random_state', 0)) + b)
                self.models.append(HistGradientBoostingRegressor(**p).fit(X[sel], y[sel]))

    # ------------------------------------------------------------------ features
    def _dropped(self, group):
        if self.batch_dropout <= 0:
            return False
        import hashlib
        h = int(hashlib.sha256(f'abv2.batch_dropout|{self.seed}|{group}'.encode()).hexdigest()[:8], 16) / 16 ** 8
        return h < self.batch_dropout

    def _keys(self, chem, lv, block):
        m = self.meta[chem]
        sel = np.isin(m['logc'], lv)
        return tuple(sorted(set(m[block][sel].tolist())))

    def _extra(self, task, ic, lv, q, base, training):
        """Added columns for one design: list of (Q, 68) arrays or scalars."""
        cols = []
        if not self.blocks:
            return cols
        lib, chem = self.lib, task.chem
        group = self.meta[chem]['group']
        no_batch = (training and self._dropped(group)) or (not training and self.isolate == 'date')
        held_plates = self._keys(chem, lv, 'plate') if (not training and self.isolate == 'plate') else ()
        for b in self.blocks:
            if b in ('date', 'plate'):
                idx = lib.batch_mates(b, self._keys(chem, lv, b), group)
                if no_batch or (held_plates and b == 'plate'):
                    idx = idx[:0]
                elif held_plates:
                    idx = lib.drop_plates(idx, held_plates)
                res, lvl = mate_columns(lib, idx, np.ones(len(idx)), lv, q, base)
                cols += [res, lvl, float(len(idx))]
            elif b == 'datew':
                idx = lib.batch_mates('date', self._keys(chem, lv, 'date'), group)
                if no_batch:
                    idx = idx[:0]
                elif held_plates:
                    idx = lib.drop_plates(idx, held_plates)
                if len(idx):
                    _, mu, ok = self.cf.level_means(task, ic)
                    A = lib.at(idx, lv).reshape(len(idx), len(lv), D)
                    okf = ok.reshape(len(lv), D)
                    d2 = (((A - mu.reshape(len(lv), D)[None]) ** 2) * okf[None]).sum((1, 2)) / max(okf.sum(), 1)
                    w = 1.0 / (d2 + 1e-3)
                else:
                    w = np.zeros(0)
                res, lvl = mate_columns(lib, idx, w, lv, q, base)
                cols += [res, lvl]
            elif b == 'struct':
                idx, w = lib.struct_mates(self.meta[chem].get('struct'), group)
                res, lvl = mate_columns(lib, idx, w, lv, q, base)
                cols += [res, lvl, float(w.max()) if len(w) else np.nan]
            elif b == 'struct2':
                idx, w = lib.struct_mates(self.meta[chem].get('struct2'), group, 'struct2')
                res, lvl = mate_columns(lib, idx, w, lv, q, base)
                cols += [res, lvl, float(w.max()) if len(w) else np.nan]
            elif b == 'structw':
                idx, w = lib.struct_mates(self.meta[chem].get('struct'), group)
                if len(idx):
                    _, mu, ok = self.cf.level_means(task, ic)
                    A = lib.at(idx, lv).reshape(len(idx), len(lv), D)
                    okf = ok.reshape(len(lv), D)
                    d2 = (((A - mu.reshape(len(lv), D)[None]) ** 2) * okf[None]).sum((1, 2)) / max(okf.sum(), 1)
                    w = w / (d2 + 1e-3)
                res, lvl = mate_columns(lib, idx, w, lv, q, base)
                cols += [res, lvl]
        return cols

    def _design(self, task, ic, q, analog, training):
        cf = self.cf
        base, f = cf.features(task, ic, q, analog, self.profiles, None)
        extra = []
        if self.pool:
            extra.append(float(len(np.unique(task.logc[ic]))))
        lv = np.unique(task.logc[ic]).astype(np.float64)
        extra += self._extra(task, ic, lv, np.asarray(q, np.float64), base, training)
        if not extra:
            return base, f
        out = np.empty(f.shape[:2] + (f.shape[2] + len(extra),), np.float64)
        out[:, :, :f.shape[2]] = f
        for c, v in enumerate(extra):
            out[:, :, f.shape[2] + c] = v
        return base, out

    def _rows(self, train):
        cf = self.cf
        rows = [(t, ctx) for kk in self.train_ks for t in train if kk < len(t.levels) for ctx in cf.all_designs(t, kk)]
        sizes = [int(t.ok[~np.isin(t.levels, ctx)].sum()) for t, ctx in rows]
        t0, c0 = rows[0]
        n_feat = self._design(t0, np.isin(t0.logc, c0), t0.levels[:1], self.analog, False)[1].shape[-1]
        X = np.empty((sum(sizes), n_feat), np.float64)
        y = np.empty(sum(sizes), np.float64)
        chem = np.empty(sum(sizes), object)
        at = 0
        for (t, ctx), size in zip(rows, sizes):
            ic = np.isin(t.logc, ctx)
            lv, mu, ok = cf.level_means(t, ~ic)
            base, f = self._design(t, ic, lv, self.analog_train, True)
            keep = ok.reshape(-1)
            X[at:at + size] = f.reshape(-1, n_feat)[keep]
            y[at:at + size] = (mu.reshape(len(lv), D) - base).ravel()[keep]
            chem[at:at + size] = t.chem
            at += size
        return X, y, chem

    def __call__(self, task, ic, q):
        base, f = self._design(task, ic, q, self.analog, False)
        F = f.reshape(-1, f.shape[-1])
        pred = np.mean([m.predict(F) for m in self.models], axis=0).reshape(len(q), D)
        return (pred + base).reshape(len(q), self.cf.ND, self.cf.NF)


def kit_meta(tasks, plate, identity, struct=None, struct2=None):
    """Metadata for release tasks: per-well dates and plates from the package's 'plate' field ('PLATE|YYYYMMDD')."""
    meta, at = {}, 0
    for t in tasks:
        p = np.asarray(plate[at:at + len(t.logc)]).astype(str)
        at += len(t.logc)
        meta[t.chem] = dict(logc=np.asarray(t.logc, np.float64), plate=p,
                            date=np.array([x.split('|')[1] for x in p]), group=str(identity[t.chem]),
                            struct=None if struct is None else struct.get(t.chem),
                            struct2=None if struct2 is None else struct2.get(t.chem))
    assert at == len(plate)
    return meta

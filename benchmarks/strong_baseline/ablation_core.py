"""Frozen row-matching implementation used by the released ablation."""
import hashlib
import time
import numpy as np

def rows_for(cf, task, contexts):
    return sum(int(task.ok[~np.isin(task.levels, ctx)].sum()) for ctx in contexts)

def fit_matched(cf, train, iterations):
    start = time.perf_counter()
    analog_train = cf.Analog(train, exclude_self=True)
    analog = cf.Analog(train)
    profiles = cf.Profiles(train)
    budgets = []
    for task in train:
        assert len(task.levels) > 3
        full_contexts, five_contexts = cf.all_designs(task, 3), cf.designs(task, 3)
        assert len(five_contexts) == 5
        total, unique = rows_for(cf, task, full_contexts), rows_for(cf, task, five_contexts)
        budgets.append(dict(chemical=task.chem, full_designs=len(full_contexts), five_designs=5,
                            full_rows=total, five_unique_rows=unique,
                            repetition_quotient=total // unique, repetition_remainder=total % unique))
    first = train[0]
    n_feat = cf.features(first, np.isin(first.logc, cf.all_designs(first, 3)[0]),
                         first.levels[:1], analog, profiles)[1].shape[-1]
    total = sum(b['full_rows'] for b in budgets)
    X = np.empty((total, n_feat), dtype=np.float64)
    y = np.empty(total, dtype=np.float64)
    at = 0
    for task, budget in zip(train, budgets):
        chunks, labels = [], []
        for ctx in cf.designs(task, 3):
            ic = np.isin(task.logc, ctx)
            lv, mu, ok = cf.level_means(task, ~ic)
            base, features = cf.features(task, ic, lv, analog_train, profiles)
            keep = ok.reshape(-1)
            chunks.append(features.reshape(-1, n_feat)[keep])
            labels.append((mu.reshape(len(lv), cf.D) - base).ravel()[keep])
        xc, yc = np.concatenate(chunks), np.concatenate(labels)
        assert len(yc) == budget['five_unique_rows']
        q, rem = budget['repetition_quotient'], budget['repetition_remainder']
        seed = int(hashlib.sha256(f'{task.chem}|rowmatch|3'.encode()).hexdigest()[:8], 16)
        order = np.random.default_rng(seed).permutation(len(yc))
        ix = np.concatenate([np.tile(np.arange(len(yc)), q), order[:rem]])
        size = budget['full_rows']
        assert len(ix) == size
        X[at:at + size] = xc[ix]
        y[at:at + size] = yc[ix]
        at += size
    assert at == total
    materialized = time.perf_counter()
    model = cf.HistGradientBoostingRegressor(**dict(cf.MODEL, max_iter=iterations)).fit(X, y)
    fitted = time.perf_counter()
    timing = dict(feature_seconds=materialized-start, fit_seconds=fitted-materialized,
                  feature_plus_fit_seconds=fitted-start, training_rows=total,
                  five_unique_rows=sum(b['five_unique_rows'] for b in budgets),
                  feature_width=n_feat, iterations=int(model.n_iter_),
                  row_iteration_budget=int(total * model.n_iter_), chemical_budgets=budgets)
    def predict(task, ic, query):
        base, feature = cf.features(task, ic, query, analog, profiles)
        pred = model.predict(feature.reshape(-1, n_feat)).reshape(len(query), cf.D)
        return (base + pred).reshape(len(query), cf.ND, cf.NF)
    return predict, timing

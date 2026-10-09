#!/usr/bin/env python3
"""Large Perturbation Model (Miladinovic et al., Nat. Comput. Sci. 5, 1029-1040, 2025; perturblib) adapted to dose.

Architecture as perturb_lib/models/collection/lpm.py (Apache-2.0): context, perturbation and readout
embeddings concatenated into an MLP that predicts one readout value; the perturbation embedding is the mean
over the sample's perturbation symbols (nn.EmbeddingBag, mode='mean'). Adaptations, listed in protocol.json:
perturbation = {compound, dose}; readouts = the 68 outputs; context = plate, recording date or one constant;
training samples are single wells of training chemicals. A test chemical's compound embedding is fitted from its
revealed cells only, by inference-time optimisation (decoder frozen) or by an amortised encoder; its level mean
at a query concentration is the decoder output averaged over the plates of its revealed wells.

    python lpm_run.py time                          # one training on a minimal batch, then one full epoch
    python lpm_run.py dev --arch lincs --context plate --dose lookup --seed 13
    python lpm_run.py final --seed 13               # frozen setting, folds 0-4, k = 1..4
"""
import argparse
import json
import math
import time
import warnings

import numpy as np
import torch
from torch import nn

from common import D, HERE, KIT, NC, curve_mae, load_kit, load_tasks, to_query_array

ARCH = {
    'lincs': dict(embedding_dim=128, hidden_dim=256, num_layers=2, dropout=0.1, batch_size=1000, lr=0.002,
                  decay=0.97, epochs=50),
    'replogle': dict(embedding_dim=32, hidden_dim=512, num_layers=2, dropout=0.0, batch_size=5000, lr=0.002,
                     decay=0.99, epochs=50),
}
LAMBDAS = [0.01, 0.1, 1.0, 10.0]
N_FREQ = 8


def load_wells():
    w = np.load(KIT / 'data' / 'wells.npz')
    plate = w['plate'].astype(str)
    return dict(chem=w['chemical_row'].astype(int), conc=w['conc_index'].astype(int), plate=plate,
                date=np.array([p.split('|')[1] for p in plate]), y=w['y'].astype(np.float32), valid=w['valid'])


def fourier(logc):
    x = (logc + 5.0) / 8.0
    k = torch.arange(N_FREQ, dtype=torch.float32, device=logc.device)
    ang = x[:, None] * math.pi * (2.0 ** k)[None, :]
    return torch.cat([x[:, None], torch.sin(ang), torch.cos(ang)], 1)


class LPM(nn.Module):
    """perturblib LPM with a two-symbol perturbation bag {compound, dose} (or a continuous dose embedding)."""

    def __init__(self, n_ctx, n_comp, n_dose, a, dose_mode):
        super().__init__()
        E, H, L = a['embedding_dim'], a['hidden_dim'], a['num_layers']
        self.n_comp, self.dose_mode = n_comp, dose_mode
        self.context_embedding_layer = nn.Embedding(n_ctx, E)
        self.perturb_embedding_layer = nn.EmbeddingBag(n_comp + (n_dose if dose_mode == 'lookup' else 0), E, mode='mean')
        self.readout_embedding_layer = nn.Embedding(D, E)
        if dose_mode == 'continuous':
            self.dose_projection = nn.Linear(1 + 2 * N_FREQ, E)
        net = nn.Sequential()
        for i in range(L):
            net.append(nn.Linear(H if i > 0 else 3 * E, H))
            net.append(nn.ReLU())
            net.append(nn.Dropout(a['dropout']))
        net.append(nn.Linear(H if L > 0 else 3 * E, 1))
        net.apply(self._init_weights)
        self.predictor = net

    @staticmethod
    def _init_weights(module):
        if isinstance(module, (nn.Linear, nn.Embedding, nn.EmbeddingBag)):
            nn.init.xavier_uniform_(module.weight, gain=nn.init.calculate_gain('relu'))

    def dose_vec(self, dose_idx, logc):
        if self.dose_mode == 'lookup':
            return self.perturb_embedding_layer.weight[self.n_comp + dose_idx]
        return self.dose_projection(fourier(logc))

    def forward(self, comp_vec, dose_idx, logc, read_idx, ctx_vec):
        pert = 0.5 * (comp_vec + self.dose_vec(dose_idx, logc))           # EmbeddingBag mean of the two symbols
        h = torch.cat([ctx_vec, pert, self.readout_embedding_layer(read_idx)], 1)
        return self.predictor(h).squeeze(1)


class Vocab:
    """Training-fold vocabularies; unseen doses map to the nearest seen concentration, unseen contexts to the
    mean context embedding."""

    def __init__(self, wells, train_mask, context, conc):
        self.context = context
        tr_chem = np.unique(wells['chem'][train_mask])
        self.comp = {c: i for i, c in enumerate(tr_chem)}
        seen_dose = np.unique(wells['conc'][train_mask])
        self.dose = {c: i for i, c in enumerate(seen_dose)}
        self.dose_of = np.array([self.dose[seen_dose[np.argmin(np.abs(conc[seen_dose] - conc[c]))]] for c in range(NC)])
        keys = self.ctx_keys(wells)[train_mask]
        self.ctx = {k: i for i, k in enumerate(sorted(set(keys)))}

    def ctx_keys(self, wells):
        if self.context == 'plate':
            return wells['plate']
        if self.context == 'date':
            return wells['date']
        return np.array(['all'] * len(wells['plate']))


def train_model(kit, wells, f, arch, context, dose_mode, seed, device, epochs=None, max_samples=None):
    a = dict(ARCH[arch])
    if epochs is not None:
        a['epochs'] = epochs
    torch.manual_seed(seed)
    np.random.seed(seed)
    train_mask = kit['folds'][wells['chem']] != f
    voc = Vocab(wells, train_mask, context, kit['conc'])
    idx_w, idx_o = np.where(wells['valid'] & train_mask[:, None])
    if max_samples:
        keep = np.random.default_rng(seed).choice(len(idx_w), max_samples, replace=False)
        idx_w, idx_o = idx_w[keep], idx_o[keep]
    ctxk = voc.ctx_keys(wells)
    t = lambda x, dt=torch.long: torch.as_tensor(x, dtype=dt, device=device)
    comp = t([voc.comp[c] for c in wells['chem'][idx_w]])
    dose = t(voc.dose_of[wells['conc'][idx_w]])
    logc = t(kit['conc'][wells['conc'][idx_w]], torch.float32)
    read = t(idx_o)
    ctx = t([voc.ctx[k] for k in ctxk[idx_w]])
    y = t(wells['y'][idx_w, idx_o], torch.float32)
    model = LPM(len(voc.ctx), len(voc.comp), len(voc.dose), a, dose_mode).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=a['lr'])
    sched = torch.optim.lr_scheduler.ExponentialLR(opt, gamma=a['decay'])
    n, bs = len(y), a['batch_size']
    g = torch.Generator(device='cpu').manual_seed(seed)
    loss_hist = []
    for ep in range(a['epochs']):
        model.train()
        perm = torch.randperm(n, generator=g).to(device)
        tot = 0.0
        for s in range(0, n, bs):
            b = perm[s:s + bs]
            pred = model(model.perturb_embedding_layer.weight[comp[b]], dose[b], logc[b], read[b],
                         model.context_embedding_layer(ctx[b]))
            loss = ((pred - y[b]) ** 2).mean()
            opt.zero_grad(set_to_none=True)
            loss.backward()
            opt.step()
            tot += float(loss) * len(b)
        sched.step()
        loss_hist.append(tot / n)
    model.eval()
    return model, voc, loss_hist


_PLATES = {}


def design_contexts(wells, voc, i, seen):
    """Context ids of the plates holding chemical i's wells at its revealed concentrations (-1 = unseen)."""
    if not _PLATES:
        for ch, c, p in zip(wells['chem'], wells['conc'], wells['plate']):
            _PLATES.setdefault((int(ch), int(c)), set()).add(str(p))
    plates = sorted(set().union(*[_PLATES.get((int(i), int(c)), set()) for c in seen]))
    if voc.context == 'plate':
        keys = plates
    elif voc.context == 'date':
        keys = [p.split('|')[1] for p in plates]
    else:
        keys = ['all']
    return [voc.ctx.get(k, -1) for k in keys]


class Batch:
    """Every design of one fold and k: its contexts (no padding), revealed cells and query cells, with the
    (cell, context) pairs whose decoder outputs are averaged into level means."""

    def __init__(self, kit, wells, voc, tasks, device):
        Y = kit['Y']
        self.tasks, self.device = tasks, device
        self.ctx_lists = [design_contexts(wells, voc, t['row'], t['seen']) for t in tasks]
        if not tasks:
            return
        self.unseen_ctx = sum(int(x < 0) for c in self.ctx_lists for x in c)
        fd, fc, fo, fy = [], [], [], []
        for d, t in enumerate(tasks):
            for c in t['seen']:
                for o in np.where(~np.isnan(Y[t['row'], c]))[0]:
                    fd.append(d), fc.append(c), fo.append(o), fy.append(Y[t['row'], c, o])
        self.fit = self.cells(fd, fc, fo) + (torch.tensor(fy, dtype=torch.float32, device=device),)
        qd, qc, qo = [], [], []
        for d, t in enumerate(tasks):
            for _, c in t['queries']:
                qd += [d] * D
                qc += [c] * D
                qo += list(range(D))
        self.query = self.cells(qd, qc, qo)

    def cells(self, d, c, o):
        """Tensors for cells (design d, concentration c, output o) and their (cell, context, weight) pairs."""
        n = np.array([len(self.ctx_lists[x]) for x in d])
        cell = np.repeat(np.arange(len(d)), n)
        ctx = np.concatenate([self.ctx_lists[x] for x in d]) if len(d) else np.zeros(0, int)
        w = np.repeat(1.0 / n, n)
        dev = self.device
        return (torch.tensor(d, device=dev), torch.tensor(c, device=dev), torch.tensor(o, device=dev),
                torch.tensor(cell, device=dev), torch.tensor(ctx, device=dev), torch.tensor(w, dtype=torch.float32, device=dev))


def ctx_vectors(model, ids):
    """Context embeddings for ids, with the mean training context for unseen ones (-1)."""
    W = model.context_embedding_layer.weight
    mean = W.mean(0, keepdim=True)
    v = W[ids.clamp(min=0)]
    return torch.where((ids < 0)[..., None], mean.expand_as(v), v)


def pair_constants(model, kit, voc, cells):
    """First-layer pre-activation of every (cell, context) pair without the compound part: the MLP input is
    [context, (compound + dose) / 2, readout], so W [x] = W_c ctx + W_p compound / 2 + W_p dose / 2 + W_r readout."""
    d, c, o, cell, ctx, w = cells[:6]
    E = model.readout_embedding_layer.weight.shape[1]
    lin = model.predictor[0]
    Wc, Wp, Wr = lin.weight[:, :E], lin.weight[:, E:2 * E], lin.weight[:, 2 * E:]
    cc = c[cell]
    dose = torch.as_tensor(voc.dose_of, device=d.device)[cc]
    logc = torch.as_tensor(kit['conc'], dtype=torch.float32, device=d.device)[cc]
    with torch.no_grad():
        K = ctx_vectors(model, ctx) @ Wc.T + 0.5 * model.dose_vec(dose, logc) @ Wp.T \
            + model.readout_embedding_layer(o[cell]) @ Wr.T + lin.bias
    return K, 0.5 * Wp


def level_mean(model, kit, voc, comp_vecs, cells, K=None):
    """Decoder output averaged over each design's contexts, for the cells built by Batch.cells. Identical to
    model.forward on every pair, with the compound-free part of the first layer precomputed (K)."""
    d, c, o, cell, ctx, w = cells[:6]
    if K is None:
        K = pair_constants(model, kit, voc, cells)
    Kc, halfWp = K
    z = Kc + (comp_vecs @ halfWp.T)[d[cell]]
    out = model.predictor[1:](z).squeeze(1)
    return torch.zeros(len(d), device=d.device).index_add_(0, cell, out * w)


def fit_embeddings(model, kit, voc, batch, lam, checkpoints=(300,), lr=0.05):
    """Inference-time optimisation: one compound embedding per design, decoder frozen, Gaussian prior toward the
    mean training compound embedding (scaled by its per-dimension spread). Returns {steps: embeddings}."""
    W = model.perturb_embedding_layer.weight[:model.n_comp].detach()
    mu, sd = W.mean(0), W.std(0) + 1e-6
    e = mu.repeat(len(batch.tasks), 1).clone().requires_grad_(True)
    opt = torch.optim.Adam([e], lr=lr)
    d, y = batch.fit[0], batch.fit[6]
    nd = torch.bincount(d, minlength=len(batch.tasks)).clamp(min=1).float()
    for p in model.parameters():
        p.requires_grad_(False)
    K = pair_constants(model, kit, voc, batch.fit)
    out = {}
    for step in range(1, max(checkpoints) + 1):
        pred = level_mean(model, kit, voc, e, batch.fit, K)
        sq = torch.zeros(len(batch.tasks), device=e.device).index_add_(0, d, (pred - y) ** 2) / nd
        loss = (sq + lam * (((e - mu) / sd) ** 2).mean(1)).sum()
        opt.zero_grad()
        loss.backward()
        opt.step()
        if step in checkpoints:
            out[step] = e.detach().clone()
    for p in model.parameters():
        p.requires_grad_(True)
    return out


class Encoder(nn.Module):
    """Amortised compound embedding from revealed (dose, 68 level means) points: per-point MLP, mean pool, MLP."""

    def __init__(self, E, H=256):
        super().__init__()
        self.point = nn.Sequential(nn.Linear(E + 2 * D, H), nn.ReLU(), nn.Linear(H, H), nn.ReLU())
        self.head = nn.Sequential(nn.Linear(H, H), nn.ReLU(), nn.Linear(H, E))

    def forward(self, dose_vecs, vals, mask, point_mask):
        h = self.point(torch.cat([dose_vecs, vals * mask, mask], -1))
        h = (h * point_mask[..., None]).sum(1) / point_mask.sum(1, keepdim=True).clamp(min=1)
        return self.head(h)


def train_encoder(model, kit, wells, voc, f, seed, device, checkpoints=(600,), bs=32, on_checkpoint=None):
    """Encoder fitted on training chemicals: random revealed subsets (k = 1-4 of the tested concentrations),
    loss = decoder error on every tested concentration of that chemical, decoder frozen."""
    torch.manual_seed(seed + 1000)
    rng = np.random.default_rng(seed + 1000)
    Y = kit['Y']
    E = model.perturb_embedding_layer.weight.shape[1]
    W = model.perturb_embedding_layer.weight[:model.n_comp].detach()
    mu = W.mean(0)
    enc = Encoder(E).to(device)
    opt = torch.optim.Adam(enc.parameters(), lr=1e-3)
    train_rows = np.where(kit['folds'] != f)[0]
    cells = {}
    for i in train_rows:
        tested = np.where(kit['tested'][i])[0]
        cc, oo = np.where(~np.isnan(Y[i][tested]))
        cells[i] = (tested, tested[cc], oo, Y[i][tested][cc, oo])
    shell = Batch(kit, wells, voc, [], device)
    for p in model.parameters():
        p.requires_grad_(False)
    for step in range(1, max(checkpoints) + 1):
        rows = rng.choice(train_rows, bs, replace=False)
        tasks = []
        for i in rows:
            tested = cells[i][0]
            k = int(rng.integers(1, 5))
            tasks.append(dict(row=i, seen=sorted(rng.choice(tested, min(k, len(tested)), replace=False).tolist())))
        e = encode(enc, model, kit, voc, tasks, mu, device)
        shell.ctx_lists = [design_contexts(wells, voc, t['row'], t['seen']) for t in tasks]
        dd = np.concatenate([np.full(len(cells[t['row']][1]), d) for d, t in enumerate(tasks)])
        cc = np.concatenate([cells[t['row']][1] for t in tasks])
        oo = np.concatenate([cells[t['row']][2] for t in tasks])
        yy = np.concatenate([cells[t['row']][3] for t in tasks])
        pred = level_mean(model, kit, voc, e, shell.cells(dd, cc, oo))
        loss = ((pred - torch.tensor(yy, dtype=torch.float32, device=device)) ** 2).mean()
        opt.zero_grad()
        loss.backward()
        opt.step()
        if step in checkpoints and on_checkpoint is not None:
            enc.eval()
            on_checkpoint(step, enc, mu)
            enc.train()
    for p in model.parameters():
        p.requires_grad_(True)
    enc.eval()
    return enc, mu


def encode(enc, model, kit, voc, tasks, mu, device):
    Y = kit['Y']
    K = max(len(t['seen']) for t in tasks)
    E = mu.shape[0]
    dose_idx = np.zeros((len(tasks), K), int)
    logc = np.zeros((len(tasks), K), np.float32)
    vals = np.zeros((len(tasks), K, D), np.float32)
    mask = np.zeros((len(tasks), K, D), np.float32)
    pm = np.zeros((len(tasks), K), np.float32)
    for d, t in enumerate(tasks):
        for j, c in enumerate(t['seen']):
            dose_idx[d, j] = voc.dose_of[c]
            logc[d, j] = kit['conc'][c]
            v = Y[t['row'], c]
            vals[d, j] = np.nan_to_num(v)
            mask[d, j] = ~np.isnan(v)
            pm[d, j] = 1
    dv = model.dose_vec(torch.tensor(dose_idx.reshape(-1), device=device),
                        torch.tensor(logc.reshape(-1), device=device)).reshape(len(tasks), K, E)
    return mu + enc(dv, torch.tensor(vals, device=device), torch.tensor(mask, device=device), torch.tensor(pm, device=device))


def predict(model, kit, voc, batch, comp_vecs):
    with torch.no_grad():
        out = level_mean(model, kit, voc, comp_vecs, batch.query)
    P = out.reshape(-1, D).cpu().numpy().astype(np.float64)
    res, r = {}, 0
    for t in batch.tasks:
        n = len(t['queries'])
        res[t['task_id']] = P[r:r + n]
        r += n
    return res


ITO_STEPS = (25, 50, 100, 200, 400)
ENC_STEPS = (300, 600, 1200, 2400)


def evaluate(kit, wells, model, voc, f, k, device, modes, seed, keep=None):
    """Predictions per inference mode for every design of fold f at k: {mode: {task_id: (n_q, 68)}}.
    Modes: 'opt<lambda>@<steps>' (inference-time optimisation) and 'enc@<steps>' (amortised encoder)."""
    tasks, _ = load_tasks(k, [f])
    batch = Batch(kit, wells, voc, tasks, device)
    out = {}
    lams = sorted({float(m[3:].split('@')[0]) for m in modes if m.startswith('opt')})
    for lam in lams:
        steps = sorted({int(m.split('@')[1]) for m in modes if m.startswith('opt') and float(m[3:].split('@')[0]) == lam})
        for st, e in fit_embeddings(model, kit, voc, batch, lam, checkpoints=tuple(steps)).items():
            out[f'opt{lam:g}@{st}'] = predict(model, kit, voc, batch, e)
            if keep is not None:
                np.savez_compressed(keep, task_ids=np.array([t['task_id'] for t in tasks]), embeddings=e.cpu().numpy(),
                                    contexts=np.array(json.dumps(batch.ctx_lists)))
    enc_steps = sorted({int(m.split('@')[1]) for m in modes if m.startswith('enc')})
    if enc_steps:
        def grab(st, enc, mu):
            with torch.no_grad():
                e = encode(enc, model, kit, voc, tasks, mu, device)
                out[f'enc@{st}'] = predict(model, kit, voc, batch, e)
            if keep is not None and f'enc@{st}' in modes:
                np.savez_compressed(keep, task_ids=np.array([t['task_id'] for t in tasks]), embeddings=e.cpu().numpy(),
                                    contexts=np.array(json.dumps(batch.ctx_lists)))
        train_encoder(model, kit, wells, voc, f, seed, device, checkpoints=tuple(enc_steps), on_checkpoint=grab)
    return {m: out[m] for m in modes}, batch.unseen_ctx


def all_modes():
    return [f'opt{lam:g}@{st}' for lam in LAMBDAS for st in ITO_STEPS] + [f'enc@{st}' for st in ENC_STEPS]


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('stage', choices=['time', 'dev', 'final'])
    p.add_argument('--arch', choices=list(ARCH), default='lincs')
    p.add_argument('--context', choices=['plate', 'date', 'none'], default='plate')
    p.add_argument('--dose', choices=['lookup', 'continuous'], default='lookup')
    p.add_argument('--seed', type=int, default=13)
    p.add_argument('--device', default='cpu')
    p.add_argument('--threads', type=int, default=0)
    a = p.parse_args()
    if a.threads:
        torch.set_num_threads(a.threads)
    warnings.simplefilter('ignore')
    kit, wells = load_kit(), load_wells()
    if a.stage == 'time':
        t0 = time.time()
        train_model(kit, wells, 0, a.arch, a.context, a.dose, a.seed, a.device, epochs=1, max_samples=20000)
        t1 = time.time()
        model, voc, _ = train_model(kit, wells, 0, a.arch, a.context, a.dose, a.seed, a.device, epochs=1)
        t2 = time.time()
        tasks, _ = load_tasks(3, [0])
        batch = Batch(kit, wells, voc, tasks, a.device)
        fit_embeddings(model, kit, voc, batch, 0.1, checkpoints=(20,))
        t3 = time.time()
        print(json.dumps(dict(arch=a.arch, context=a.context, dose=a.dose, device=a.device,
                              minimal_batch_epoch_s=round(t1 - t0, 2), full_epoch_s=round(t2 - t1, 2),
                              full_training_estimate_s=round((t2 - t1) * ARCH[a.arch]['epochs'], 1),
                              fit_20_steps_s=round(t3 - t2, 2), samples=int((wells['valid'] & (kit['folds'][wells['chem']] != 0)[:, None]).sum()))))
        return
    if a.stage == 'dev':
        t0 = time.time()
        model, voc, hist = train_model(kit, wells, 0, a.arch, a.context, a.dose, a.seed, a.device)
        t1 = time.time()
        modes = all_modes()
        preds, unseen = evaluate(kit, wells, model, voc, 0, 3, a.device, modes, a.seed)
        tag = f'{a.arch}_{a.context}_{a.dose}_s{a.seed}'
        (HERE / 'dev' / 'lpm').mkdir(parents=True, exist_ok=True)
        tids = sorted(preds[modes[0]])
        np.savez_compressed(HERE / 'dev' / 'lpm' / f'{tag}.npz', task_ids=np.array(tids),
                            **{m: np.concatenate([preds[m][t] for t in tids]) for m in modes})
        tasks, _ = load_tasks(3, [0])
        rec = dict(arch=a.arch, context=a.context, dose=a.dose, seed=a.seed, train_s=round(t1 - t0, 1),
                   eval_s=round(time.time() - t1, 1), final_train_mse=hist[-1], unseen_contexts=unseen,
                   mae_fold0={m: curve_mae(kit['Y'], tasks, preds[m])[0] for m in modes})
        (HERE / 'dev' / 'lpm' / f'{tag}.json').write_text(json.dumps(rec, indent=1) + '\n')
        print(json.dumps(rec))
        return
    fz = json.loads((HERE / 'protocol.json').read_text())['frozen']['LPM']
    out = {}
    art = HERE / 'preds' / 'lpm_artifacts'
    art.mkdir(parents=True, exist_ok=True)
    for f in range(5):
        model, voc, hist = train_model(kit, wells, f, fz['arch'], fz['context'], fz['dose'], a.seed, a.device)
        torch.save(dict(state=model.state_dict(), comp=voc.comp, dose=voc.dose, dose_of=voc.dose_of.tolist(), ctx=voc.ctx,
                        loss=hist), art / f'model_f{f}_s{a.seed}.pt')
        for k in (1, 2, 3, 4):
            preds, _ = evaluate(kit, wells, model, voc, f, k, a.device, [fz['inference']], a.seed,
                                keep=art / f'embeddings_f{f}_k{k}_s{a.seed}.npz')
            out.setdefault(k, {}).update(preds[fz['inference']])
        print(f'fold {f} done', flush=True)
    res = {}
    for k in (1, 2, 3, 4):
        tasks, nq = load_tasks(k)
        res[f'k{k}'] = to_query_array(tasks, out[k], nq)
    (HERE / 'preds' / 'lpm_seeds').mkdir(parents=True, exist_ok=True)
    np.savez_compressed(HERE / 'preds' / 'lpm_seeds' / f'lpm_s{a.seed}.npz', **res)
    print('wrote', f'preds/lpm_seeds/lpm_s{a.seed}.npz')


if __name__ == '__main__':
    main()

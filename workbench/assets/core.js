/* Workbench core: decodes window.OOC, derives every plotted quantity in the browser, holds the shared selection. */
(function () {
  'use strict';
  const O = window.OOC;
  const D = 68, NF = 17, ND = 4;

  function dec(s, scale) {
    const bin = atob(s), n = bin.length >> 1, out = new Float32Array(n), k = scale || 100;
    for (let i = 0; i < n; i++) {
      let v = bin.charCodeAt(2 * i) | (bin.charCodeAt(2 * i + 1) << 8);
      if (v >= 32768) v -= 65536;
      out[i] = v === -32768 ? NaN : v / k;
    }
    return out;
  }

  /* ---------- chemicals, wells, designs ---------- */
  const order = new Map(O.wells.map((w, i) => [w.name, i]));
  const wellsBy = new Map(O.wells.map(w => [w.name, w]));
  O.chems.forEach((c, i) => { c.i = i; c.w = wellsBy.get(c.name); c.order = order.get(c.name); });
  const chemBy = new Map(O.chems.map(c => [c.name, c]));

  function wells(w) {
    if (!w._y) w._y = dec(w.y);
    return w;
  }
  /* level means and replicate counts per output, the published level_means without masks */
  function levelStats(w) {
    if (w._mu) return w;
    wells(w);
    const L = w.levels.length, mu = new Float32Array(L * D).fill(NaN), n = new Uint8Array(L * D), sum = new Float64Array(L * D);
    w.lv.forEach((l, r) => {
      for (let j = 0; j < D; j++) {
        const v = w._y[r * D + j];
        if (!Number.isNaN(v)) { sum[l * D + j] += v; n[l * D + j]++; }
      }
    });
    for (let i = 0; i < L * D; i++) if (n[i]) mu[i] = sum[i] / n[i];
    w._mu = mu; w._n = n;
    return w;
  }
  function design(c, k) {
    const d = c.d[k];
    if (!d._f) { d._f = dec(d.f); d._ll = dec(d.ll); d._w = dec(d.w); d._e = dec(d.e, 1000); }
    return d;
  }

  /* decision quantity per concentration: largest |DIV-mean| response over the 17 features (chip_forecast_decision.rows) */
  function divMeanEffect(get) {
    let best = 0, arg = 0;
    for (let f = 0; f < NF; f++) {
      let s = 0, m = 0;
      for (let t = 0; t < ND; t++) { const v = get(t * NF + f); if (!Number.isNaN(v)) { s += v; m++; } }
      const e = m ? Math.abs(s / m) : 0;
      if (e > best) { best = e; arg = f; }
    }
    return { e: best, f: arg };
  }
  function track(c, k) {
    const w = levelStats(c.w), d = design(c, k), L = w.levels.length;
    const meas = [], fore = [];
    for (let l = 0; l < L; l++) meas.push(divMeanEffect(j => w._mu[l * D + j]));
    d.q.forEach((l, qi) => fore.push(Object.assign({ l }, divMeanEffect(j => d._f[qi * D + j]))));
    let score = 0, at = null;
    d.m.forEach(l => { if (meas[l].e > score) { score = meas[l].e; at = { l, f: meas[l].f, src: 'measured' }; } });
    fore.forEach(x => { if (x.e > score) { score = x.e; at = { l: x.l, f: x.f, src: 'forecast' }; } });
    const truth = Math.max(...meas.map(x => x.e));
    return { meas, fore, score, at, truth };
  }

  /* the published figure's view: the DIV 12 feature whose measured level means vary most */
  function defaultOutput(c) {
    const w = levelStats(c.w), L = w.levels.length;
    let best = -1, arg = 3 * NF;
    for (let f = 0; f < NF; f++) {
      const j = 3 * NF + f;
      let lo = Infinity, hi = -Infinity, ok = true;
      for (let l = 0; l < L; l++) { const v = w._mu[l * D + j]; if (Number.isNaN(v)) { ok = false; break; } lo = Math.min(lo, v); hi = Math.max(hi, v); }
      if (ok && hi - lo > best) { best = hi - lo; arg = j; }
    }
    return arg;
  }

  /* ---------- decision frontier over the 970 held-out designs ---------- */
  const designsAll = [];
  O.chems.slice().sort((a, b) => a.order - b.order).forEach(c => c.d.forEach((d, k) => designsAll.push({ c, k, d })));
  const N = designsAll.length;
  const wellsFull = designsAll.reduce((s, x) => s + x.d.wf, 0);
  function frontier(method) {
    const mo = method === 'measured';
    const rows = designsAll.map((x, i) => ({ i, mar: mo ? x.d.moMar : x.d.mar, wrong: (mo ? x.d.moCall : x.d.call) !== x.d.y ? 1 : 0, wm: x.d.wm, wf: x.d.wf }));
    rows.sort((a, b) => b.mar - a.mar || a.i - b.i);
    const pts = [{ k: 0, wrong: 0, settled: 0, saved: 0, mar: Infinity }];
    let wrong = 0, used = wellsFull;
    rows.forEach((r, n) => {
      wrong += r.wrong; used -= r.wf - r.wm;
      pts.push({ k: n + 1, wrong: wrong / N, settled: (n + 1) / N, saved: 1 - used / wellsFull, mar: r.mar });
    });
    return pts;
  }
  function atRisk(pts, risk) {
    let best = pts[0];
    pts.forEach(p => { if (p.wrong * N <= risk * N + 1e-9) best = p; });
    return best;
  }
  function registered(method) {
    const mo = method === 'measured';
    let rel = 0, wrong = 0, used = 0;
    designsAll.forEach(x => {
      const r = mo ? x.d.moAct : x.d.act, call = mo ? x.d.moCall : x.d.call;
      rel += r; wrong += r && call !== x.d.y ? 1 : 0; used += r ? x.d.wm : x.d.wf;
    });
    return { settled: rel / N, wrong: wrong / N, saved: 1 - used / wellsFull, k: rel };
  }
  function optimum(pts, cost) {
    let best = pts[0], bv = Infinity;
    pts.forEach(p => { const v = p.wrong + cost * (1 - p.settled); if (v < bv - 1e-12) { bv = v; best = p; } });
    return Object.assign({ cost: bv }, best);
  }

  /* ---------- design layouts (7-concentration chemicals) ---------- */
  function layouts() {
    return Object.entries(O.patterns).map(([key, v]) => ({ key, pos: key.split('').map(Number), n: v.n, rep: v.rep, wrong: v.wrong, rate: v.rep / v.n }))
      .sort((a, b) => b.rate - a.rate || b.n - a.n || a.key.localeCompare(b.key));
  }

  /* ---------- patients ---------- */
  const P = O.patients;
  /* published cohort: the frozen combined-regimen cutoff; call 1 = sensitive, 0 = resistant, null = retest */
  function publishedPatients() {
    return P.rows.map((r, i) => ({ id: r.patient, mode: 'combined', combined: r.baseline_readout, irr: r.readout1, fu: r.readout2, response: r.response, call: Number(P.cases[i].action), reason: 'Combined-regimen readout at the frozen cutoff' }));
  }
  function callPatients(rows) { return rows.map(r => Object.assign({ mode: 'combined', reason: 'Combined-regimen readout at the frozen cutoff' }, r, { call: r.combined <= P.cutoff ? 1 : 0 })); }
  /* two separate readouts: the frozen two-readout release rule of result.js reports agreeing calls and sends the rest to retest */
  function twoReadout(text) {
    const packet = window.WORKBENCH_RESULT, rows = window.ChainEngine.parse(text), pred = window.ChainEngine.predict(packet, rows);
    return rows.map((r, i) => {
      const c = pred.cases[i];
      return { id: r.patient, mode: 'two', r1: r.readout1, r2: r.readout2, combined: r.baseline_readout, response: r.response,
        call: c.action === 'retest' ? null : Number(c.action), reason: c.reason };
    });
  }
  function patientStats(rows) {
    const s = { tp: 0, fp: 0, tn: 0, fn: 0, n: rows.length, known: 0, retest: rows.filter(r => r.call === null).length };
    rows.forEach(r => {
      if ((r.response !== 0 && r.response !== 1) || r.call === null) return;
      s.known++;
      if (r.call === 1) r.response === 1 ? s.tp++ : s.fp++;
      else r.response === 0 ? s.tn++ : s.fn++;
    });
    s.correct = s.tp + s.tn;
    s.sens = s.tp / (s.tp + s.fn); s.spec = s.tn / (s.tn + s.fp);
    s.ppv = s.tp / (s.tp + s.fp); s.npv = s.tn / (s.tn + s.fn);
    return s;
  }

  /* ---------- paste parsers ---------- */
  function table(text) {
    const lines = text.replace(/^﻿/, '').split(/\r?\n/).map(l => l.trim()).filter(Boolean);
    if (lines.length < 2) throw Error('Add a header row and at least one patient.');
    const sep = lines[0].includes('\t') ? '\t' : ',';
    const head = lines[0].split(sep).map(h => h.trim().toLowerCase());
    return lines.slice(1).map((l, i) => {
      const cells = l.split(sep).map(x => x.trim());
      if (cells.length !== head.length) throw Error(`Row ${i + 2} has ${cells.length} cells; the header has ${head.length}.`);
      return Object.fromEntries(head.map((h, j) => [h, cells[j]]));
    });
  }
  const pick = (r, names) => { for (const n of names) if (r[n] !== undefined && r[n] !== '') return r[n]; return undefined; };
  function parsePatients(text) {
    const head = text.replace(/^﻿/, '').trim().split(/\r?\n/)[0].toLowerCase();
    if (/(^|[,\t])readout1([,\t]|$)/.test(head)) return twoReadout(text);
    const rows = table(text).map((r, i) => {
      const id = pick(r, ['patient', 'id', 'sample']);
      const combined = Number(pick(r, ['combined', 'baseline_readout', 'regimen', 'size_ratio']));
      if (!id) throw Error(`Row ${i + 2}: add a patient ID.`);
      if (!Number.isFinite(combined) || combined < 0) throw Error(`Row ${i + 2}: the combined-regimen size ratio must be a number of 0 or more.`);
      const num = v => (v === undefined ? null : Number(v));
      const resp = pick(r, ['response', 'outcome']);
      return { id, combined, irr: num(pick(r, ['irradiation', 'readout1'])), fu: num(pick(r, ['5fu', 'fu', 'readout2'])), response: resp === undefined ? null : Number(resp) };
    });
    return callPatients(rows);
  }
  function mergeOutcomes(rows, text) {
    const got = new Map();
    table(text).forEach((r, i) => {
      const id = pick(r, ['patient', 'id']), v = pick(r, ['response', 'outcome']);
      if (!id || !['0', '1'].includes(String(v))) throw Error(`Row ${i + 2}: use patient,response with response 0 or 1.`);
      got.set(id, Number(v));
    });
    const out = rows.map(r => (got.has(r.id) ? Object.assign({}, r, { response: got.get(r.id) }) : r));
    if (!rows.some(r => got.has(r.id))) throw Error('No outcome matches a patient ID in the table.');
    return out;
  }
  function actionsCSV(rows, reveal) {
    const q = v => { const s = v === null || v === undefined ? '' : String(v); return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
    const act = r => (r.call === null ? 'retest' : r.call === 1 ? 'report sensitive' : 'report resistant');
    return ['patient,action,reason,response'].concat(rows.map(r => [r.id, act(r), r.reason, reveal ? r.response : ''].map(q).join(','))).join('\r\n') + '\r\n';
  }
  function parseSeries(text) {
    const pts = text.split(/[\n,;]+/).map(t => t.trim()).filter(Boolean).map(t => {
      const m = t.match(/^([0-9]*\.?[0-9]+(?:e-?\d+)?)\s*(\*|x|✓)?/i);
      if (!m) throw Error(`“${t}” is not a concentration.`);
      return { c: Number(m[1]), on: !!m[2] };
    });
    pts.sort((a, b) => a.c - b.c);
    if (pts.length !== 7) throw Error(`Paste 7 concentrations; this series has ${pts.length}.`);
    const pos = pts.map((p, i) => (p.on ? i : -1)).filter(i => i >= 0);
    return { pts, key: pos.length === 3 ? pos.join('') : null, marked: pos.length };
  }

  /* ---------- selection store ---------- */
  const listeners = new Set();
  const first = chemBy.get(O.examples[0].chemical);
  const state = { chem: first.i, design: 0, output: defaultOutput(first), full: false, truth: true, reveal: false, cost: 0.25, versus: 'loglinear_interp', patient: null, patients: publishedPatients(), patientSource: 'published', layout: null };
  const hash = new URLSearchParams(typeof location !== 'undefined' ? location.hash.slice(1) : '');
  if (hash.has('chem') && chemBy.has(hash.get('chem'))) { const c = chemBy.get(hash.get('chem')); state.chem = c.i; state.output = defaultOutput(c); }
  if (hash.has('design')) state.design = Math.max(0, Math.min(4, Number(hash.get('design')) - 1));
  if (hash.has('output')) state.output = Number(hash.get('output'));
  ['reveal', 'full'].forEach(k => { if (hash.has(k)) state[k] = hash.get(k) === '1'; });
  if (hash.has('truth')) state.truth = hash.get('truth') !== '0';
  if (hash.has('patient')) state.patient = hash.get('patient');
  if (hash.has('cost')) state.cost = Number(hash.get('cost'));
  if (hash.has('versus')) state.versus = hash.get('versus');
  if (hash.has('measure') && typeof window.addEventListener === 'function') window.addEventListener('load', () => setTimeout(() => {
    const boxes = { page: [0, 0, document.documentElement.scrollWidth, document.documentElement.scrollHeight] };
    document.querySelectorAll('[id]').forEach(el => { const r = el.getBoundingClientRect(); if (r.width && r.height) boxes[el.id] = [r.left + scrollX, r.top + scrollY, r.width, r.height].map(Math.round); });
    document.body.dataset.boxes = JSON.stringify(boxes);
  }, 300));
  function set(patch) {
    if ('chem' in patch && !('output' in patch)) patch.output = defaultOutput(O.chems[patch.chem]);
    if ('chem' in patch && !('design' in patch)) patch.design = 0;
    Object.assign(state, patch);
    listeners.forEach(fn => fn(state, patch));
  }
  function on(fn) { listeners.add(fn); fn(state, {}); return () => listeners.delete(fn); }

  /* ---------- formatting ---------- */
  const pct = (x, d = 1) => (100 * x).toFixed(d) + '%';
  const fix = (x, d = 2) => (x === null || x === undefined || Number.isNaN(x) ? '—' : Number(x).toFixed(d));
  const int = x => Math.round(x).toLocaleString('en-US');
  const uM = lv => { const v = Math.pow(10, lv); return v >= 100 ? v.toFixed(0) : String(+v.toPrecision(6)); };
  const outName = j => `${O.features[j % NF]} · DIV ${O.divs[Math.floor(j / NF)]}`;

  /* ---------- tooltip ---------- */
  let tipEl = null;
  function tip(evt, value, rows, opt) {
    if (!tipEl) { tipEl = document.createElement('div'); tipEl.className = 'tip'; document.body.appendChild(tipEl); }
    tipEl.textContent = '';
    tipEl.classList.toggle('line', !!(opt && opt.line));
    if (value) { const v = document.createElement('div'); v.className = 'tv'; v.textContent = value; tipEl.appendChild(v); }
    (rows || []).forEach(r => {
      const e = document.createElement('div'); e.className = 'tr';
      if (r.color) { const i = document.createElement('i'); i.style.background = r.color; e.appendChild(i); }
      e.appendChild(document.createTextNode(r.text !== undefined ? r.text : r));
      tipEl.appendChild(e);
    });
    const pad = 14, w = tipEl.offsetWidth, h = tipEl.offsetHeight;
    let x = evt.clientX + pad, y = evt.clientY + pad;
    if (x + w > window.innerWidth - 8) x = evt.clientX - w - pad;
    if (y + h > window.innerHeight - 8) y = evt.clientY - h - pad;
    tipEl.style.left = x + 'px'; tipEl.style.top = y + 'px';
    tipEl.classList.add('on');
  }
  function untip() { if (tipEl) tipEl.classList.remove('on'); }

  /* ---------- consistency check against the exported decision scores (run from the console) ---------- */
  function selfTest() {
    let worst = 0;
    O.chems.forEach(c => c.d.forEach((d, k) => { worst = Math.max(worst, Math.abs(track(c, k).score - d.score)); }));
    const f = frontier('forecast'), m = frontier('measured');
    return { scoreGap: worst, risk05: [atRisk(f, 0.05).settled, atRisk(m, 0.05).settled], risk10: [atRisk(f, 0.10).settled, atRisk(m, 0.10).settled], registered: registered('forecast') };
  }

  window.Core = { O, D, NF, ND, dec, chemBy, hash, wells, levelStats, design, track, defaultOutput, frontier, atRisk, registered, optimum, layouts, designsAll, wellsFull,
    publishedPatients, callPatients, patientStats, parsePatients, parseSeries, mergeOutcomes, actionsCSV, state, set, on, pct, fix, int, uM, outName, tip, untip, selfTest };
})();

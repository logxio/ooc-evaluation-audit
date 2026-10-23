/* Sample size: pilot counts in, the further reported patients a 95% one-sided bound needs out.
   Recalculates on every edit and draws the bound falling as correct calls accumulate. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id), S = WorkbenchStats, start = performance.now(), events = [];
  const NS = 'http://www.w3.org/2000/svg';
  let result = null, inputs = null;
  const log = (type, data = {}) => events.push({ type, elapsed_ms: Math.round(performance.now() - start), ...data });
  const pct = (x, d = 1) => (100 * x).toFixed(d) + '%';
  const num = x => x.toLocaleString('en');
  const svg = (tag, attrs, parent) => { const n = document.createElementNS(NS, tag); for (const k in attrs) n.setAttribute(k, attrs[k]); if (parent) parent.appendChild(n); return n; };
  const step = v => { const p = 10 ** Math.floor(Math.log10(v)), f = v / p; return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * p; };

  /* sample.html?n=84&e=14&alpha=10 opens on those counts */
  const q = new URLSearchParams(location.search);
  [['n', 'pilot-n'], ['e', 'pilot-e'], ['alpha', 'pilot-alpha']].forEach(([k, id]) => { if (q.has(k)) $(id).value = q.get(k); });

  function calculate() {
    try {
      const n = Number($('pilot-n').value), e = Number($('pilot-e').value), a = Number($('pilot-alpha').value) / 100;
      if (!Number.isInteger(n) || !Number.isInteger(e) || n < e || n < 0 || e < 0) throw Error('Use whole numbers with 0 ≤ wrong calls ≤ reported calls.');
      result = S.budget(n, e, a); inputs = { n, e, a };
      log('calculated', { inputs: { n, e, alpha: a }, result });
      $('sample-error').hidden = true;
      render();
    } catch (err) { $('sample-error').hidden = false; $('sample-error').textContent = err.message; }
  }

  function render() {
    const { n, e, a } = inputs, r = result, target = +(100 * a).toFixed(2) + '%';
    $('kpi-alpha').textContent = target;
    $('kpi-total').textContent = r.total === null ? '>10M' : num(r.total);
    $('sample-answer').textContent = r.additional === null ? 'This plan needs more than 10 million reported patients'
      : r.additional === 0 ? `Your ${num(n)} reported calls already meet the ${target} target`
      : `${num(r.additional)} more reported patients with zero further wrong calls`;
    const cards = [
      ['Observed error', n ? pct(e / n, 2) : 'NA', `${e} wrong of ${n} reported calls`, ''],
      ['Upper bound now', pct(r.upper, 2), 'Exact 95% one-sided Clopper-Pearson bound on the pilot counts', r.upper > a ? 'retest' : 'report'],
      ['Target error', pct(a, 2), 'Largest share of wrong calls you accept among reported patients', ''],
      ['Required total', r.total === null ? '>10M' : num(r.total), 'Pilot calls plus further correct calls; a planning minimum, not a power calculation', 'report']
    ];
    $('sample-metrics').replaceChildren(...cards.map(([k, v, tip, tone]) => {
      const d = document.createElement('div'); d.className = 'stat' + (tone ? ' ' + tone : ''); d.setAttribute('aria-description', tip);
      d.innerHTML = `<div class="v">${v}</div><div class="k">${k}</div>`; return d;
    }));
    chart();
  }

  /* the 95% bound against reported patients: pilot shaded, target dashed, today's bound and the crossing marked */
  function chart() {
    const box = $('plan-chart'); box.textContent = '';
    if (!result || result.total === null) return;
    const { n, e, a } = inputs, total = result.total;
    const W = Math.max(320, box.clientWidth), H = 300, m = { l: 48, r: 24, t: 16, b: 36 };
    const m0 = Math.max(n, 1), xs = step(Math.max(total * 1.15, n + 4, 10) / 5), xMax = Math.ceil(Math.max(total * 1.15, n + 4, 10) / xs) * xs;
    const yTop = Math.min(1, Math.max(S.upper(e, m0), a) * 1.12), ys = step(yTop / 4), yMax = Math.min(1, Math.ceil(yTop / ys) * ys);
    const X = v => m.l + (W - m.l - m.r) * v / xMax, Y = v => m.t + (H - m.t - m.b) * (1 - v / yMax);
    const g = svg('svg', { class: 'chart', viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': `Upper bound falls below ${pct(a)} at ${total} reported patients` }, box);
    if (n) {
      svg('rect', { class: 'past', x: X(0), y: m.t, width: X(n) - X(0), height: H - m.t - m.b }, g);
      svg('text', { class: 'label', x: X(n) - 6, y: H - m.b - 8, 'text-anchor': 'end' }, g).textContent = 'pilot';
    }
    const ax = svg('g', { class: 'axis' }, g);
    for (let v = 0; v <= yMax + 1e-9; v += ys) {
      svg('line', { x1: m.l, x2: W - m.r, y1: Y(v), y2: Y(v), class: v ? 'guide' : '' }, ax);
      svg('text', { x: m.l - 8, y: Y(v) + 4, 'text-anchor': 'end' }, ax).textContent = pct(v, ys < .01 ? 1 : 0);
    }
    for (let v = 0; v <= xMax + 1e-9; v += xs) svg('text', { x: X(v), y: H - m.b + 18, 'text-anchor': 'middle' }, ax).textContent = num(v);
    svg('text', { class: 'axis-title', x: W - m.r, y: H - 2, 'text-anchor': 'end' }, g).textContent = 'Reported patients';
    svg('text', { class: 'axis-title', x: m.l, y: m.t - 4 }, g).textContent = 'Upper bound on the wrong-call rate';
    svg('line', { class: 'cutoff', x1: m.l, x2: W - m.r, y1: Y(a), y2: Y(a) }, g);
    svg('text', { class: 'label', x: W - m.r, y: Y(a) - 6, 'text-anchor': 'end' }, g).textContent = `${+(100 * a).toFixed(2)}% target`;
    const count = e > 2000 ? 40 : 120, pts = new Set([m0, total]);
    for (let i = 0; i <= count; i++) pts.add(Math.round(m0 + (xMax - m0) * i / count));
    const path = [...pts].filter(v => v >= m0 && v <= xMax).sort((p, q) => p - q).map(v => [v, S.upper(e, v)]);
    svg('path', { class: 'curve', d: path.map(([x, y], i) => `${i ? 'L' : 'M'}${X(x).toFixed(1)} ${Y(Math.min(y, yMax)).toFixed(1)}`).join('') }, g);
    const u = S.upper(e, total);
    svg('line', { class: 'guide', x1: X(total), x2: X(total), y1: Y(u), y2: H - m.b }, g);
    if (n) {
      svg('circle', { class: 'now', cx: X(n), cy: Y(Math.min(result.upper, yMax)), r: 4.5 }, g);
      svg('text', { class: 'label strong', x: X(n) + 8, y: Y(Math.min(result.upper, yMax)) - 8 }, g).textContent = `now ${pct(result.upper)}`;
    }
    svg('circle', { class: 'goal', cx: X(total), cy: Y(u), r: 5 }, g);
    const right = X(total) > W - 140;
    svg('text', { class: 'label strong', x: X(total) + (right ? -10 : 10), y: Y(u) + 18, 'text-anchor': right ? 'end' : 'start' }, g).textContent =
      result.additional ? `+${num(result.additional)} → ${num(total)} patients` : `${num(total)} patients`;
    /* hover: the bound at any total */
    const line = svg('line', { class: 'hover', y1: m.t, y2: H - m.b, visibility: 'hidden' }, g);
    const dot = svg('circle', { class: 'now', r: 3.5, visibility: 'hidden' }, g);
    const hit = svg('rect', { class: 'hit', x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b }, g);
    hit.addEventListener('pointermove', ev => {
      const r = g.getBoundingClientRect(), px = (ev.clientX - r.left) * W / r.width - m.l;
      const v = Math.round(Math.max(m0, Math.min(xMax, px * xMax / (W - m.l - m.r))));
      const b = S.upper(e, Math.max(v, m0));
      line.setAttribute('x1', X(v)); line.setAttribute('x2', X(v)); dot.setAttribute('cx', X(v)); dot.setAttribute('cy', Y(Math.min(b, yMax)));
      line.setAttribute('visibility', 'visible'); dot.setAttribute('visibility', 'visible');
      window.Tip && Tip.show(ev.clientX, ev.clientY, `${num(v)} reported patients, ${num(v - n)} more · bound ${pct(b, 2)}${b <= a ? ' · meets target' : ''}`);
    });
    hit.addEventListener('pointerleave', () => { line.setAttribute('visibility', 'hidden'); dot.setAttribute('visibility', 'hidden'); window.Tip && Tip.hide(); });
  }

  for (const id of ['pilot-n', 'pilot-e', 'pilot-alpha']) $(id).oninput = () => { log('input_change', { field: id, value: $(id).value }); calculate(); };
  $('sample-export').onclick = () => {
    log('export');
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([JSON.stringify({ schema: 'workbench.sample-plan.v1', record_type: 'local_calculation', result, events }, null, 2)], { type: 'application/json' }));
    a.download = 'sample-plan.json'; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  };
  let frame = 0;
  new ResizeObserver(() => { cancelAnimationFrame(frame); frame = requestAnimationFrame(() => result && chart()); }).observe($('plan-chart'));
  calculate();
})();

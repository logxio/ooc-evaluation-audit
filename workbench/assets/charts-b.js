/* Charts B: per-chemical waterfall, interval calibration, decision frontier, cross-screen forest, ablations. */
(function () {
  'use strict';
  const C = window.Core, O = C.O, NF = C.NF;
  const Charts = window.Charts, layer = Charts.layer;
  const css = n => `var(--${n})`;
  const VERSUS = {
    loglinear_interp: 'log-linear interpolation',
    analog_knn: 'analog chemicals',
    hill_per_endpoint: 'per-output Hill fits',
    published_neural_process: 'the published neural process'
  };
  Charts.VERSUS = VERSUS;

  /* ---------------- 5. waterfall: error reduction per chemical against one comparator ---------------- */
  Charts.waterfall = function (el, opt) {
    opt = opt || {};
    const M = { t: 16, r: 8, b: 24, l: 44 };
    const draw = Charts.mount(el, (svg, W, S, patch) => {
      const dur = Charts.dur(patch), H1 = opt.height || 200, H = M.t + H1 + M.b, iw = W - M.l - M.r;
      svg.attr('viewBox', `0 0 ${W} ${H}`).attr('height', H);
      const rows = O.chems.map(c => ({ c, v: c.err[S.versus] - c.err.anchorboost })).sort((a, b) => b.v - a.v);
      const x = d3.scaleBand().domain(rows.map(r => r.c.i)).range([0, iw]).paddingInner(0.25);
      const ext = d3.extent(rows, r => r.v);
      const y = d3.scaleLinear().domain([Math.min(0, ext[0]) * 1.06, Math.max(0, ext[1]) * 1.06]).range([H1, 0]);
      const g = layer(svg, 'g').attr('transform', `translate(${M.l},${M.t})`);
      layer(g, 'yax').attr('class', 'yax axis').call(d3.axisLeft(y).ticks(4).tickSize(4).tickPadding(6)).call(a => a.select('.domain').remove());
      layer(g, 'bars').selectAll('rect').data(rows, r => r.c.i).join('rect').attr('class', 'mark')
        .attr('fill', r => (r.c.i === S.chem ? css('ink') : r.v > 0 ? css('forecast') : css('compare')))
        .attr('rx', 1)
        .transition().duration(dur)
        .attr('x', r => x(r.c.i)).attr('width', x.bandwidth())
        .attr('y', r => Math.min(y(0), y(r.v))).attr('height', r => Math.max(1, Math.abs(y(r.v) - y(0))));
      layer(g, 'zero').selectAll('line').data([0]).join('line').attr('class', 'zero').attr('x1', 0).attr('x2', iw).attr('y1', y(0)).attr('y2', y(0));
      const named = rows.filter(r => /^(Colchicine|Sodium valproate)$/.test(r.c.name) || r.c.i === S.chem);
      layer(g, 'names').selectAll('text').data(named, r => r.c.i).join('text').attr('class', r => (r.c.i === S.chem ? 'label strong' : 'label'))
        .attr('text-anchor', r => (x(r.c.i) > iw / 2 ? 'end' : 'start'))
        .transition().duration(dur)
        .attr('x', r => x(r.c.i) + (x(r.c.i) > iw / 2 ? -6 : x.bandwidth() + 6))
        .attr('y', r => (r.v > 0 ? y(r.v) + 4 : y(r.v) + 4))
        .text(r => `${r.c.name} ${r.v > 0 ? '+' : ''}${C.fix(r.v)}`);
      layer(g, 'xt').selectAll('text').data(['held-out chemicals, sorted by error reduction against the comparator']).join('text').attr('class', 'tick-label')
        .attr('x', 0).attr('y', H1 + 18).text(t => t);
      layer(g, 'hits').selectAll('rect').data(rows, r => r.c.i).join('rect').attr('class', 'hit')
        .attr('x', r => x(r.c.i) - 1).attr('width', x.step()).attr('y', 0).attr('height', H1)
        .on('pointermove', (ev, r) => C.tip(ev, `${r.c.name}`, [
          { text: `forecast error ${C.fix(r.c.err.anchorboost)}`, color: css('forecast') },
          { text: `${VERSUS[S.versus]} ${C.fix(r.c.err[S.versus])}`, color: css('compare') },
          `${r.v > 0 ? 'closer by' : 'behind by'} ${C.fix(Math.abs(r.v))} · click to open`]))
        .on('pointerleave', C.untip)
        .on('click', (ev, r) => C.set({ chem: r.c.i }));
      if (opt.onClaim) opt.onClaim(S.versus, O.versus.versus[S.versus]);
    });
    C.on((S, p) => { if (!p || !Object.keys(p).length || 'chem' in p || 'versus' in p) draw(S, p); });
    return draw;
  };

  /* ---------------- 6. interval calibration by recording day and by feature ---------------- */
  Charts.calibrationRows = (() => {
    const cov = O.coverage;
    const agg = (pick) => {
      let h = 0, p = 0, n = 0;
      for (let j = 0; j < C.D; j++) if (pick(j)) { h += cov.hit[j]; p += cov.plainHit[j]; n += cov.n[j]; }
      return { learned: h / n, plain: p / n, n };
    };
    return [
      ...O.divs.map((v, t) => Object.assign({ key: 'd' + t, label: `DIV ${v}`, t }, agg(j => Math.floor(j / NF) === t))),
      ...O.features.map((v, f) => Object.assign({ key: 'f' + f, label: v, f }, agg(j => j % NF === f)))
    ];
  })();
  Charts.calibration = function (el, opt) {
    opt = opt || {};
    const rows = Charts.calibrationRows;
    const draw = Charts.mount(el, (svg, W, S, patch) => {
      const lab = opt.labelWidth || 208, rh = 16, top = 24, gapAt = 4, H = top + rows.length * rh + 16 + 24;
      svg.attr('viewBox', `0 0 ${W} ${H}`).attr('height', H);
      const lo = d3.min(rows, r => Math.min(r.learned, r.plain)), hi = d3.max(rows, r => Math.max(r.learned, r.plain));
      const x = d3.scaleLinear().domain([Math.min(0.88, lo - 0.005), Math.max(0.92, hi + 0.005)]).range([lab, W - 16]);
      const yOf = i => top + i * rh + (i >= gapAt ? 16 : 0) + rh / 2;
      layer(svg, 'xax').attr('transform', `translate(0,${H - 24})`).attr('class', 'xax axis')
        .call(d3.axisBottom(x).ticks(5).tickFormat(v => `${(v * 100).toFixed(0)}%`).tickSize(4).tickPadding(6)).call(a => a.select('.domain').attr('stroke', css('axis')));
      layer(svg, 'nom').selectAll('line').data([0.9]).join('line').attr('class', 'cutoff').attr('x1', x(0.9)).attr('x2', x(0.9)).attr('y1', top - 8).attr('y2', H - 24);
      layer(svg, 'noml').selectAll('text').data(['90% target']).join('text').attr('class', 'tick-label').attr('x', x(0.9)).attr('y', 12).attr('text-anchor', 'middle').text(t => t);
      const selT = Math.floor(S.output / NF), selF = S.output % NF;
      layer(svg, 'labels').selectAll('text').data(rows, r => r.key).join('text')
        .attr('class', r => ((r.t === selT && r.t !== undefined) || (r.f === selF && r.f !== undefined) ? 'label strong' : 'label'))
        .attr('x', lab - 8).attr('text-anchor', 'end').attr('y', (r, i) => yOf(i) + 4).text(r => r.label);
      layer(svg, 'guides').selectAll('line').data(rows, r => r.key).join('line').attr('stroke', css('line'))
        .attr('x1', (r) => x(Math.min(r.learned, r.plain))).attr('x2', r => x(Math.max(r.learned, r.plain))).attr('y1', (r, i) => yOf(i)).attr('y2', (r, i) => yOf(i)).attr('stroke-width', 2);
      layer(svg, 'plain').selectAll('circle').data(rows, r => r.key).join('circle').attr('r', 3.5).attr('fill', css('surface')).attr('stroke', css('compare')).attr('stroke-width', 1.5)
        .attr('cx', r => x(r.plain)).attr('cy', (r, i) => yOf(i));
      layer(svg, 'learned').selectAll('circle').data(rows, r => r.key).join('circle').attr('r', 4).attr('fill', css('forecast')).attr('stroke', css('surface')).attr('stroke-width', 2)
        .attr('cx', r => x(r.learned)).attr('cy', (r, i) => yOf(i));
      layer(svg, 'hits').selectAll('rect').data(rows, r => r.key).join('rect').attr('class', 'hit').attr('x', 0).attr('width', W).attr('y', (r, i) => yOf(i) - rh / 2).attr('height', rh)
        .on('pointermove', (ev, r) => C.tip(ev, `${C.pct(r.learned)} inside the 90% interval`, [r.label, `${C.int(r.n)} held-out readings`,
          { text: `learned width ${C.pct(r.learned)}`, color: css('forecast') }, { text: `plain conformal ${C.pct(r.plain)}`, color: css('compare') }]))
        .on('pointerleave', C.untip);
    });
    C.on((S, p) => { if (!p || !Object.keys(p).length || 'output' in p) draw(S, p); });
    return draw;
  };

  /* ---------------- 7. decision frontier: wells left unrun against wrong calls ---------------- */
  Charts.tradeoff = function (el, opt) {
    opt = opt || {};
    const F = C.frontier('forecast'), Mo = C.frontier('measured');
    const regF = C.registered('forecast'), regM = C.registered('measured');
    const M = { t: 16, r: 16, b: 40, l: 48 };
    const draw = Charts.mount(el, (svg, W, S, patch) => {
      const dur = Charts.dur(patch), H1 = opt.height || 240, H = M.t + H1 + M.b, iw = W - M.l - M.r;
      svg.attr('viewBox', `0 0 ${W} ${H}`).attr('height', H);
      const x = d3.scaleLinear().domain([0, 0.11]).range([0, iw]);
      const y = d3.scaleLinear().domain([0, 0.6]).range([H1, 0]);
      const g = layer(svg, 'g').attr('transform', `translate(${M.l},${M.t})`);
      layer(g, 'xax').attr('transform', `translate(0,${H1})`).attr('class', 'xax axis')
        .call(d3.axisBottom(x).ticks(6).tickFormat(v => `${Math.round(v * 100)}%`).tickSize(4).tickPadding(6)).call(a => a.select('.domain').attr('stroke', css('axis')));
      layer(g, 'yax').attr('class', 'yax axis').call(d3.axisLeft(y).ticks(4).tickFormat(v => `${Math.round(v * 100)}%`).tickSize(4).tickPadding(6)).call(a => a.select('.domain').remove());
      layer(g, 'xt').selectAll('text').data(['wrong calls, share of designs']).join('text').attr('class', 'axis-title').attr('x', iw).attr('y', H1 + 34).attr('text-anchor', 'end').text(t => t);
      layer(g, 'yt').selectAll('text').data(['wells left unrun']).join('text').attr('class', 'axis-title').attr('x', 0).attr('y', -6).text(t => t);
      const line = d3.line().x(p => x(p.wrong)).y(p => y(p.saved));
      const clip = pts => pts.filter(p => p.wrong <= 0.11);
      layer(g, 'risk').selectAll('line').data([0.05]).join('line').attr('class', 'cutoff').attr('x1', x(0.05)).attr('x2', x(0.05)).attr('y1', 0).attr('y2', H1);
      layer(g, 'riskl').selectAll('text').data(['5% wrong calls']).join('text').attr('class', 'tick-label').attr('x', x(0.05) + 6).attr('y', 10).text(t => t);
      layer(g, 'mo').selectAll('path').data([clip(Mo)]).join('path').attr('fill', 'none').attr('stroke', css('measured')).attr('stroke-width', 1.5).attr('d', line);
      layer(g, 'fo').selectAll('path').data([clip(F)]).join('path').attr('fill', 'none').attr('stroke', css('forecast')).attr('stroke-width', 2).attr('d', line);
      const a5 = C.atRisk(F, 0.05), m5 = C.atRisk(Mo, 0.05);
      layer(g, 'reg').selectAll('circle').data([{ p: regF, c: 'forecast' }, { p: regM, c: 'measured' }, { p: a5, c: 'forecast', s: 1 }, { p: m5, c: 'measured', s: 1 }])
        .join('circle').attr('r', q => (q.s ? 3.5 : 5)).attr('fill', q => (q.s ? css(q.c) : css('surface'))).attr('stroke', q => css(q.c)).attr('stroke-width', 2)
        .attr('cx', q => x(q.p.wrong)).attr('cy', q => y(q.p.saved));
      layer(g, 'regl').selectAll('text').data([{ p: regF, t: 'release rule' }]).join('text').attr('class', 'label')
        .attr('x', q => x(q.p.wrong) + 9).attr('y', q => y(q.p.saved) + 14).text(q => q.t);
      const opt0 = C.optimum(F, S.cost);
      layer(g, 'opt').selectAll('circle').data([opt0]).join('circle').attr('r', 6).attr('fill', css('forecast')).attr('stroke', css('surface')).attr('stroke-width', 2)
        .transition().duration(dur).attr('cx', p => x(p.wrong)).attr('cy', p => y(p.saved));
      const cross = layer(g, 'cross');
      layer(g, 'hover').selectAll('rect').data([0]).join('rect').attr('class', 'hit').attr('width', iw).attr('height', H1)
        .on('pointermove', ev => {
          const [mx] = d3.pointer(ev), wv = x.invert(mx);
          const p = C.atRisk(F, Math.max(0, wv)), q = C.atRisk(Mo, Math.max(0, wv));
          cross.selectAll('line').data([0]).join('line').attr('stroke', css('axis')).attr('x1', x(wv)).attr('x2', x(wv)).attr('y1', 0).attr('y2', H1);
          C.tip(ev, `${C.pct(wv)} wrong-call budget`, [
            { text: `forecast: ${C.pct(p.saved)} of wells unrun, ${C.pct(p.settled)} of designs settled`, color: css('forecast') },
            { text: `three measured alone: ${C.pct(q.saved)} unrun, ${C.pct(q.settled)} settled`, color: css('measured') }]);
        })
        .on('pointerleave', () => { cross.selectAll('line').remove(); C.untip(); });
      if (opt.onOptimum) opt.onOptimum(opt0, S.cost);
      if (opt.onClaim) opt.onClaim({ a5, m5, regF, regM });
    });
    C.on((S, p) => { if (!p || !Object.keys(p).length || 'cost' in p) draw(S, p); });
    return draw;
  };
  Charts.costSlider = function (el, readout, sentence) {
    el.textContent = '';
    const lab = document.createElement('label'); lab.className = 'row2'; lab.style.width = '100%';
    const name = document.createElement('span'); name.className = 't1 ink2'; name.style.whiteSpace = 'nowrap'; name.textContent = 'Retest cost';
    const input = document.createElement('input'); input.type = 'range'; input.min = 0.05; input.max = 1; input.step = 0.05; input.value = C.state.cost;
    const val = document.createElement('span'); val.className = 't1 num strong'; val.style.minWidth = '32px'; val.textContent = C.fix(C.state.cost);
    input.oninput = () => { val.textContent = C.fix(+input.value); C.set({ cost: +input.value }); };
    lab.append(name, input, val); el.appendChild(lab);
    if (readout) C.on((S, p) => {
      if (p && Object.keys(p).length && !('cost' in p)) return;
      readout.textContent = sentence(C.optimum(C.frontier('forecast'), S.cost));
    });
  };

  /* ---------------- 9. forest: every held-out fold of three neural screens, rat and human, against two comparators ----------------
     one label column, two panels: the same folds against log-linear interpolation and against the published neural process
     given the same five three-concentration contexts; reductions are positive when the boosted forecast has the lower error */
  const screens = [
    ['nfa', 'Rat cortical networks, chronic', 'static 48-well MEA'],
    ['acute', 'Rat cortical networks, acute', 'static MEA'],
    ['human', 'Human neural progenitors and neurons', 'hNP1 and hN2 cells']
  ];
  const ns = r => r.lo < 0 && r.hi > 0;
  Charts.forestPanels = () => {
    const interp = screens.map(([k]) => {
      const key = k === 'human' ? 'dnt' : k, t = O.forest.totals[key];
      return { k, n: O.forest.chemicals[key], folds: O.forest.rows.filter(r => r.screen === key).map(r => ({ fold: r.fold, v: -r.d, lo: -r.hi, hi: -r.lo, n: r.n })),
        total: { v: -t.mean_diff, lo: -t.ci95[1], hi: -t.ci95[0], rel: -t.rel_change_pct, n: t.n_chemicals, frac: t.frac_chem_improved } };
    });
    const neural = C.strong.screens.map(s => ({ k: s.key, n: s.total.n, of: s.labels, excluded: s.excluded, folds: s.folds, total: s.total, extra: s.extra }));
    return [
      { key: 'interp', title: 'vs log-linear interpolation', name: 'log-linear interpolation', groups: interp },
      { key: 'neural', title: 'vs published neural process', name: 'the published neural process', groups: neural }
    ];
  };
  Charts.forest = function (el, opt) {
    opt = opt || {};
    const panels = Charts.forestPanels();
    const draw = Charts.mount(el, (svg, W) => {
      const lab = opt.labelWidth || 176, rh = 18, top = 24, gap = 32, tail = 96;
      const items = [];
      screens.forEach(([k, name, kind], gi) => {
        items.push({ head: true, k, label: name, kind, gi });
        panels[0].groups[gi].folds.forEach((f, fi) => items.push({ k, gi, fi, label: `fold ${f.fold}` }));
        items.push({ k, gi, sum: true, label: 'all folds' });
      });
      const H = top + items.length * rh + 44;
      svg.attr('viewBox', `0 0 ${W} ${H}`).attr('height', H);
      const yOf = i => top + i * rh + rh / 2, pw = (W - lab - gap) / 2;
      /* screen rows carry the platform after the name: the header runs across the empty first panel row */
      layer(svg, 'labels').selectAll('text').data(items).join('text').attr('class', r => (r.head || r.sum ? 'label strong' : 'label'))
        .attr('x', r => (r.head ? 0 : lab - 8)).attr('text-anchor', r => (r.head ? 'start' : 'end')).attr('y', (r, i) => yOf(i) + 4)
        .each(function (r) {
          const t = d3.select(this); t.text(null);
          t.append('tspan').text(r.label);
          if (r.head) t.append('tspan').attr('class', 'kind').style('font-weight', 400).style('fill', css('ink-3')).text(` · ${r.kind}`);
          /* a narrow sheet keeps the platform in the tooltip only, clear of the count column */
          if (r.head && this.getComputedTextLength() > lab + pw - tail - 8) t.select('.kind').remove();
        });
      panels.forEach((P, pi) => {
        const x0 = lab + pi * (pw + gap), g = layer(svg, 'p' + pi);
        const rows = items.map((r, i) => {
          if (r.head) return null;
          const grp = P.groups[r.gi], d = r.sum ? grp.total : grp.folds[r.fi];
          return Object.assign({ i, sum: !!r.sum, label: r.label, grp }, d);
        }).filter(Boolean);
        const lo = d3.min(rows, r => Math.min(r.lo, r.lo2 === null || r.lo2 === undefined ? r.lo : r.lo2)), hi = d3.max(rows, r => Math.max(r.hi, r.hi2 || r.hi));
        const x = d3.scaleLinear().domain([Math.min(0, lo), hi]).nice(4).range([x0, x0 + pw - tail]);
        layer(g, 'title').selectAll('text').data([P.title]).join('text').attr('class', 'label strong').attr('x', x0).attr('y', 12).text(t => t);
        layer(g, 'n').selectAll('text').data(items.map((r, i) => ({ r, i })).filter(q => q.r.head)).join('text').attr('class', 'tick-label').attr('x', x0 + pw - tail + 8).attr('y', q => yOf(q.i) + 4)
          .text(q => { const grp = P.groups[q.r.gi]; return grp.of && grp.of !== grp.n ? `${grp.n} of ${grp.of} labels` : `${grp.n} chemicals`; });
        const spans = screens.map((s, gi) => { const idx = rows.filter(r => r.grp === P.groups[gi]).map(r => r.i); return { gi, a: yOf(d3.min(idx)) - rh / 2, b: yOf(d3.max(idx)) + rh / 2 }; });
        layer(g, 'zero').selectAll('line').data(spans).join('line').attr('class', 'zero').attr('x1', x(0)).attr('x2', x(0)).attr('y1', s => s.a).attr('y2', s => s.b);
        layer(g, 'ci2').selectAll('line').data(rows.filter(r => r.lo2 !== null && r.lo2 !== undefined && r.sum)).join('line').attr('stroke', css('ink-3')).attr('stroke-width', 1)
          .attr('x1', r => x(r.lo2)).attr('x2', r => x(r.hi2)).attr('y1', r => yOf(r.i)).attr('y2', r => yOf(r.i));
        layer(g, 'ci').selectAll('line').data(rows).join('line').attr('stroke', r => (r.sum ? css('forecast') : css('ink-2'))).attr('stroke-width', r => (r.sum ? 2.5 : 1.5))
          .attr('x1', r => x(r.lo)).attr('x2', r => x(r.hi)).attr('y1', r => yOf(r.i)).attr('y2', r => yOf(r.i));
        layer(g, 'pt').selectAll('path').data(rows).join('path')
          .attr('d', r => (r.sum ? 'M0,-6L6,0L0,6L-6,0Z' : 'M-3.5,-3.5h7v7h-7Z')).attr('transform', r => `translate(${x(r.v)},${yOf(r.i)})`)
          .attr('fill', r => (r.sum ? (ns(r) ? css('surface') : css('forecast')) : css('ink'))).attr('stroke', r => (r.sum && ns(r) ? css('forecast') : css('surface'))).attr('stroke-width', 1.5);
        layer(g, 'rel').selectAll('text').data(rows.filter(r => r.sum)).join('text').attr('class', r => (ns(r) ? 'label' : 'label strong')).attr('x', x0 + pw - tail + 8).attr('y', r => yOf(r.i) + 4)
          .text(r => `${C.fix(r.rel, 1)}% lower${ns(r) ? ', ns' : ''}`);
        layer(g, 'xax').attr('transform', `translate(0,${top + items.length * rh + 4})`).attr('class', 'xax axis')
          .call(d3.axisBottom(x).ticks(4).tickSize(4).tickPadding(6)).call(a => a.select('.domain').attr('stroke', css('axis')));
        layer(g, 'hits').selectAll('rect').data(rows).join('rect').attr('class', 'hit').attr('x', x0).attr('width', pw).attr('y', r => yOf(r.i) - rh / 2).attr('height', rh)
          .on('pointermove', (ev, r) => C.tip(ev, r.sum ? `${C.fix(r.rel, 1)}% lower error than ${P.name}` : `${r.label}: reduction ${C.fix(r.v, 3)}`, Charts.forestTip(P, r)))
          .on('pointerleave', C.untip);
      });
      layer(svg, 'xt').selectAll('text').data(['error reduction, curve MAE, 95% interval; thin line 97.5%; ns: 95% interval includes 0']).join('text').attr('class', 'axis-title')
        .attr('x', W).attr('y', H - 2).attr('text-anchor', 'end').text(t => t);
    });
    C.on((S, p) => { if (!p || !Object.keys(p).length) draw(S, p); });
    return draw;
  };
  Charts.forestTip = (P, r) => {
    const s = screens.find(q => q[0] === r.grp.k), iv = (a, b) => `${C.fix(a, 3)} to ${C.fix(b, 3)}`;
    const rows = [`${s[1]} · ${s[2]}`, `${r.n} chemicals · reduction ${C.fix(r.v, 3)}, 95% interval ${iv(r.lo, r.hi)}` + (r.lo2 !== null && r.lo2 !== undefined && r.sum ? `, 97.5% ${iv(r.lo2, r.hi2)}` : '')];
    if (r.k !== undefined) rows.push(`curve MAE ${C.fix(r.k, 3)} boosted forecast against ${C.fix(r.c, 3)}`);
    if (r.win !== undefined) rows.push(`${r.win} of ${r.win + r.loss} chemicals closer` + (r.sum && r.foldWin !== undefined ? ` · ${r.foldWin} of ${r.foldWin + r.foldLoss} folds` : ''));
    else if (r.frac) rows.push(`closer on ${C.pct(r.frac)} of chemicals`);
    if (r.sum && r.grp.extra) r.grp.extra.forEach(e => rows.push(`${e.label}, ${e.n} chemicals: reduction ${C.fix(e.v, 3)}, 95% ${iv(e.lo, e.hi)}`));
    if (r.sum && r.grp.excluded && r.grp.excluded.length) rows.push(`${r.grp.excluded.join(' and ')} left out: one parent compound split across folds`);
    if (r.sum && r.grp.of && r.grp.of !== r.n && !(r.grp.excluded && r.grp.excluded.length)) rows.push(`${r.grp.of} source IDs; IDs of one chemical in the same fold count once`);
    return rows;
  };

  /* ---------------- 10. perfused liver chips: five endpoints, each in its own published units ----------------
     one row per endpoint with its own axis; the point is the error reduction against interpolation with its 95% interval over drugs */
  Charts.CHIP = { Ewart2022: ['Ewart 2022', 'primary human hepatocytes, perfused'], Yuan2025: ['Yuan 2025', 'human cell lines, perfused'] };
  Charts.CHIP_END = { ALBUMIN: 'albumin, normalized', ALT: 'ALT', Morphology: 'morphology score', LDH: 'LDH' };
  Charts.chips = function (el, opt) {
    opt = opt || {};
    const rows = [];
    C.strong.chips.forEach(r => {
      if (!rows.some(q => q.head && q.dataset === r.dataset)) rows.push({ head: true, dataset: r.dataset, config: r.config });
      rows.push(r);
    });
    const draw = Charts.mount(el, (svg, W) => {
      const lab = opt.labelWidth || 152, tail = 88, hh = 24, rh = 40;
      let y = 0;
      rows.forEach(r => { r.y = y; y += r.head ? hh : rh; });
      const H = y + 20;
      svg.attr('viewBox', `0 0 ${W} ${H}`).attr('height', H);
      /* each dataset row links to its paper */
      layer(svg, 'heads').selectAll('a').data(rows.filter(r => r.head)).join('a').attr('href', r => C.strong.chipUrls[r.dataset]).attr('target', '_blank').attr('rel', 'noopener')
        .each(function (r) {
          const t = d3.select(this).selectAll('text').data([r]).join('text').attr('class', 'label strong').attr('x', 0).attr('y', r.y + 16).text(null);
          t.append('tspan').style('fill', css('accent-ink')).text(Charts.CHIP[r.dataset][0]);
          t.append('tspan').text(` · ${r.config} · ${Charts.CHIP[r.dataset][1]}`);
        });
      const ends = rows.filter(r => !r.head);
      const g = layer(svg, 'rows').selectAll('g.row').data(ends, r => r.dataset + r.endpoint).join('g').attr('class', 'row').attr('transform', r => `translate(0,${r.y})`);
      g.each(function (r) {
        const s = d3.select(this), m = Math.max(Math.abs(r.lo), Math.abs(r.hi)) * 1.1;
        const x = d3.scaleLinear().domain([-m, m]).nice(2).range([lab, W - tail]);
        layer(s, 'name').selectAll('text').data([0]).join('text').attr('class', 'label').attr('x', lab - 8).attr('y', 14).attr('text-anchor', 'end')
          .text(`${Charts.CHIP_END[r.endpoint]} · ${r.n} drugs`);
        const end = x.domain()[1];
        layer(s, 'xax').attr('transform', 'translate(0,20)').attr('class', 'xax axis').call(d3.axisBottom(x).tickValues([-end, 0, end]).tickSize(3).tickPadding(4).tickFormat(d3.format('~g')))
          .call(a => a.select('.domain').attr('stroke', css('axis')));
        layer(s, 'zero').selectAll('line').data([0]).join('line').attr('class', 'zero').attr('x1', x(0)).attr('x2', x(0)).attr('y1', 0).attr('y2', 20);
        layer(s, 'ci').selectAll('line').data([0]).join('line').attr('stroke', css('ink')).attr('stroke-width', 2).attr('x1', x(r.lo)).attr('x2', x(r.hi)).attr('y1', 10).attr('y2', 10);
        layer(s, 'pt').selectAll('circle').data([0]).join('circle').attr('r', 4.5).attr('cx', x(r.v)).attr('cy', 10)
          .attr('fill', r.lo > 0 ? css('forecast') : r.hi < 0 ? css('compare') : css('surface')).attr('stroke', r.hi < 0 ? css('compare') : css('forecast')).attr('stroke-width', 2);
        layer(s, 'res').selectAll('text').data([0]).join('text').attr('class', r.hi < 0 ? 'label' : 'label strong').attr('x', W - tail + 8).attr('y', 14)
          .text(r.hi < 0 ? `behind, ${r.win} of ${r.n}` : `${r.win} of ${r.n} closer`);
        layer(s, 'hit').selectAll('rect').data([0]).join('rect').attr('class', 'hit').attr('x', 0).attr('width', W).attr('y', -4).attr('height', rh - 4)
          .on('pointermove', ev => C.tip(ev, `${Charts.CHIP[r.dataset][0]} ${r.config} · ${Charts.CHIP_END[r.endpoint]}`, [
            `${r.n} drugs, leave one drug out · ${r.win} closer, ${r.loss} farther than interpolation`,
            `MAE ${C.fix(r.k, 4)} boosted forecast against ${C.fix(r.li, 4)} interpolation, published units`,
            `error reduction ${d3.format('+.3~g')(r.v)}, 95% interval ${d3.format('+.3~g')(r.lo)} to ${d3.format('+.3~g')(r.hi)} over drugs`]))
          .on('pointerleave', C.untip);
      });
      layer(svg, 'xt').selectAll('text').data(['error reduction vs interpolation, published units, 95% interval']).join('text')
        .attr('class', 'axis-title').attr('x', W - tail).attr('y', H - 2).attr('text-anchor', 'end').text(t => t);
    });
    C.on((S, p) => { if (!p || !Object.keys(p).length) draw(S, p); });
    return draw;
  };

  /* ---------------- 11. ablations: what each input is worth, in curve MAE ----------------
     the layout ablation is matched on training rows times boosting iterations; the anchor row compares residual and direct targets on identical rows */
  Charts.ablationRows = () => {
    const A = O.ablations.ablations, S = C.strong;
    const old = (k, label, short, note) => ({ label, short, v: A[k].minus_full.mean_diff, lo: A[k].minus_full.ci95[0], hi: A[k].minus_full.ci95[1], n: A[k].minus_full.n_chemicals, note });
    return [
      { label: 'Every layout in training', short: 'every layout', v: S.ablation.v, lo: S.ablation.lo, hi: S.ablation.hi, n: S.ablation.n,
        note: [`five designs per chemical, rows repeated to the same count, 600 iterations: MAE ${C.fix(S.ablation.other, 4)} against ${C.fix(S.ablation.full, 4)}`,
          `${S.ablation.win} of ${S.ablation.n} chemicals and ${S.ablation.foldWin} of ${S.ablation.foldWin + S.ablation.foldLoss} folds favour every layout`,
          `matched on training rows times iterations${S.ablation.wallClock ? '' : '; wall-clock time is not matched'}`] },
      old('no_analog', 'Analog chemicals', 'analog chemicals', ['analog-chemical features removed, retrained per fold']),
      old('no_hill', 'Hill fit', 'the Hill fit', ['per-output Hill features removed, retrained per fold']),
      { label: 'Interpolation anchor', short: 'the interpolation anchor', v: S.control.v, lo: S.control.lo, hi: S.control.hi, n: S.control.n,
        note: [`residual on interpolation against a direct target, identical rows and 600 iterations: MAE ${C.fix(S.control.full, 4)} against ${C.fix(S.control.other, 4)}`,
          `${S.control.win} of ${S.control.n} chemicals favour the residual, ${S.control.loss} the direct target` + (S.control.retrospective ? '; control run after the main results' : '')] }
    ];
  };
  Charts.ablation = function (el, opt) {
    opt = opt || {};
    const rows = Charts.ablationRows();
    const draw = Charts.mount(el, (svg, W) => {
      const lab = opt.labelWidth || 176, rh = 32, tail = 96, H = rows.length * rh + 44;
      svg.attr('viewBox', `0 0 ${W} ${H}`).attr('height', H);
      const x = d3.scaleLinear().domain([Math.min(0, d3.min(rows, r => r.lo)), d3.max(rows, r => r.hi)]).nice(4).range([lab, W - tail]);
      layer(svg, 'xax').attr('transform', `translate(0,${rows.length * rh + 4})`).attr('class', 'xax axis')
        .call(d3.axisBottom(x).ticks(5).tickFormat(v => (v === 0 ? '0' : d3.format('+.2~f')(v))).tickSize(4).tickPadding(6)).call(a => a.select('.domain').attr('stroke', css('axis')));
      layer(svg, 'xt').selectAll('text').data(['error added without it, curve MAE over 194 held-out chemicals, 95% interval']).join('text').attr('class', 'axis-title')
        .attr('x', W - tail).attr('y', H - 2).attr('text-anchor', 'end').text(t => t);
      layer(svg, 'zero').selectAll('line').data([0]).join('line').attr('class', 'zero').attr('x1', x(0)).attr('x2', x(0)).attr('y1', 0).attr('y2', rows.length * rh + 4);
      layer(svg, 'labels').selectAll('text').data(rows).join('text').attr('class', 'label').attr('x', lab - 8).attr('text-anchor', 'end').attr('y', (r, i) => i * rh + rh / 2 + 4).text(r => r.label);
      layer(svg, 'bars').selectAll('rect').data(rows).join('rect').attr('fill', r => (ns(r) ? css('band') : css('forecast'))).attr('rx', 3)
        .attr('x', r => Math.min(x(0), x(r.v))).attr('y', (r, i) => i * rh + rh / 2 - 6).attr('height', 12).attr('width', r => Math.max(2, Math.abs(x(r.v) - x(0))));
      layer(svg, 'ci').selectAll('line').data(rows).join('line').attr('stroke', css('ink')).attr('stroke-width', 1.25)
        .attr('x1', r => x(r.lo)).attr('x2', r => x(r.hi)).attr('y1', (r, i) => i * rh + rh / 2).attr('y2', (r, i) => i * rh + rh / 2);
      layer(svg, 'val').selectAll('text').data(rows).join('text').attr('class', r => (ns(r) ? 'label' : 'label strong')).attr('x', W - tail + 8).attr('y', (r, i) => i * rh + rh / 2 + 4)
        .text(r => `${d3.format('+.3f')(r.v)}${ns(r) ? ', ns' : ''}`);
      layer(svg, 'hits').selectAll('rect').data(rows).join('rect').attr('class', 'hit').attr('x', 0).attr('width', W).attr('y', (r, i) => i * rh).attr('height', rh)
        .on('pointermove', (ev, r) => C.tip(ev, `${r.label}: ${d3.format('+.4f')(r.v)} curve MAE when removed`, [`95% interval ${d3.format('+.4f')(r.lo)} to ${d3.format('+.4f')(r.hi)}, ${r.n} chemicals, paired`].concat(r.note)))
        .on('pointerleave', C.untip);
    });
    C.on((S, p) => { if (!p || !Object.keys(p).length) draw(S, p); });
    return draw;
  };
})();

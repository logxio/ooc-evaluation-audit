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
      layer(g, 'riskl').selectAll('text').data(['5% budget']).join('text').attr('class', 'tick-label').attr('x', x(0.05) + 6).attr('y', 10).text(t => t);
      layer(g, 'mo').selectAll('path').data([clip(Mo)]).join('path').attr('fill', 'none').attr('stroke', css('measured')).attr('stroke-width', 1.5).attr('d', line);
      layer(g, 'fo').selectAll('path').data([clip(F)]).join('path').attr('fill', 'none').attr('stroke', css('forecast')).attr('stroke-width', 2).attr('d', line);
      const a5 = C.atRisk(F, 0.05), m5 = C.atRisk(Mo, 0.05);
      layer(g, 'reg').selectAll('circle').data([{ p: regF, c: 'forecast' }, { p: regM, c: 'measured' }, { p: a5, c: 'forecast', s: 1 }, { p: m5, c: 'measured', s: 1 }])
        .join('circle').attr('r', q => (q.s ? 3.5 : 5)).attr('fill', q => (q.s ? css(q.c) : css('surface'))).attr('stroke', q => css(q.c)).attr('stroke-width', 2)
        .attr('cx', q => x(q.p.wrong)).attr('cy', q => y(q.p.saved));
      layer(g, 'regl').selectAll('text').data([{ p: regF, t: 'registered rule' }]).join('text').attr('class', 'label')
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
  Charts.costSlider = function (el, readout) {
    el.textContent = '';
    const lab = document.createElement('label'); lab.className = 'row2'; lab.style.width = '100%';
    const name = document.createElement('span'); name.className = 't1 ink2'; name.style.whiteSpace = 'nowrap'; name.textContent = 'Retest cost';
    const input = document.createElement('input'); input.type = 'range'; input.min = 0.05; input.max = 1; input.step = 0.05; input.value = C.state.cost;
    const val = document.createElement('span'); val.className = 't1 num strong'; val.style.minWidth = '32px'; val.textContent = C.fix(C.state.cost);
    input.oninput = () => { val.textContent = C.fix(+input.value); C.set({ cost: +input.value }); };
    lab.append(name, input, val); el.appendChild(lab);
    if (readout) C.on((S, p) => {
      if (p && Object.keys(p).length && !('cost' in p)) return;
      const o = C.optimum(C.frontier('forecast'), S.cost);
      readout.textContent = `Best setting at this cost: settle ${o.k} of ${C.designsAll.length} designs from three concentrations, leave ${C.pct(o.saved)} of wells unrun, ${C.fix(o.wrong * 100, 1)} wrong calls per 100 designs.`;
    });
  };

  /* ---------------- 9. forest: every held-out fold of three screens, rat and human ---------------- */
  Charts.forest = function (el, opt) {
    opt = opt || {};
    const groups = [
      ['nfa', 'Rat cortical networks, chronic', 'network formation assay'],
      ['acute', 'Rat cortical networks, acute', 'acute MEA screen'],
      ['dnt', 'Human neural progenitors and neurons', 'hNP1 and hN2 imaging and plate reader']
    ];
    const draw = Charts.mount(el, (svg, W) => {
      const lab = opt.labelWidth || 208, rh = 18, items = [];
      groups.forEach(([k, name]) => {
        items.push({ head: true, k, label: name, n: O.forest.chemicals[k] });
        O.forest.rows.filter(r => r.screen === k).forEach(r => items.push({ k, label: `fold ${r.fold}`, v: -r.d, lo: -r.hi, hi: -r.lo, rel: -r.rel, n: r.n }));
        const t = O.forest.totals[k];
        items.push({ k, sum: true, label: 'all folds', v: -t.mean_diff, lo: -t.ci95[1], hi: -t.ci95[0], rel: -t.rel_change_pct, n: t.n_chemicals, frac: t.frac_chem_improved });
      });
      const H = 8 + items.length * rh + 48;
      svg.attr('viewBox', `0 0 ${W} ${H}`).attr('height', H);
      const x = d3.scaleLinear().domain([0, d3.max(items, r => r.hi || 0)]).nice(4).range([lab, W - 96]);
      const yOf = i => 8 + i * rh + rh / 2;
      const axisY = 8 + items.length * rh + 4;
      layer(svg, 'xax').attr('transform', `translate(0,${axisY})`).attr('class', 'xax axis')
        .call(d3.axisBottom(x).ticks(4).tickSize(4).tickPadding(6)).call(a => a.select('.domain').attr('stroke', css('axis')));
      layer(svg, 'xt').selectAll('text').data(['error reduction against log-linear interpolation, 95% interval']).join('text').attr('class', 'axis-title').attr('x', W - 96).attr('y', H - 2).attr('text-anchor', 'end').text(t => t);
      const spans = groups.map(([k]) => { const idx = items.map((r, i) => (r.k === k && !r.head ? i : -1)).filter(i => i >= 0); return { k, a: yOf(idx[0]) - rh / 2, b: yOf(idx[idx.length - 1]) + rh / 2 }; });
      layer(svg, 'zero').selectAll('line').data(spans, s => s.k).join('line').attr('class', 'zero').attr('x1', x(0)).attr('x2', x(0)).attr('y1', s => s.a).attr('y2', s => s.b);
      layer(svg, 'labels').selectAll('text').data(items).join('text').attr('class', r => (r.head || r.sum ? 'label strong' : 'label'))
        .attr('x', r => (r.head ? 0 : lab - 8)).attr('text-anchor', r => (r.head ? 'start' : 'end')).attr('y', (r, i) => yOf(i) + 4)
        .text(r => (r.head ? `${r.label} · ${r.n} chemicals` : r.label));
      const data = items.map((r, i) => Object.assign({ i }, r)).filter(r => !r.head);
      layer(svg, 'ci').selectAll('line').data(data).join('line').attr('stroke', r => (r.sum ? css('forecast') : css('ink-2'))).attr('stroke-width', r => (r.sum ? 2 : 1.5))
        .attr('x1', r => x(r.lo)).attr('x2', r => x(r.hi)).attr('y1', r => yOf(r.i)).attr('y2', r => yOf(r.i));
      layer(svg, 'pt').selectAll('path').data(data).join('path')
        .attr('d', r => (r.sum ? 'M0,-6L6,0L0,6L-6,0Z' : 'M-3.5,-3.5h7v7h-7Z')).attr('transform', r => `translate(${x(r.v)},${yOf(r.i)})`)
        .attr('fill', r => (r.sum ? css('forecast') : css('ink'))).attr('stroke', css('surface')).attr('stroke-width', 1.5);
      layer(svg, 'rel').selectAll('text').data(data.filter(r => r.sum)).join('text').attr('class', 'label strong').attr('x', W - 88).attr('y', r => yOf(r.i) + 4)
        .text(r => `${C.fix(r.rel, 1)}% lower`);
      layer(svg, 'hits').selectAll('rect').data(data).join('rect').attr('class', 'hit').attr('x', 0).attr('width', W).attr('y', r => yOf(r.i) - rh / 2).attr('height', rh)
        .on('pointermove', (ev, r) => C.tip(ev, `${C.fix(r.rel, 1)}% lower error`, [`${r.label} · ${r.n} chemicals`, `reduction ${C.fix(r.v, 3)} (95% interval ${C.fix(r.lo, 3)} to ${C.fix(r.hi, 3)})`].concat(r.frac ? [`closer on ${C.pct(r.frac)} of chemicals`] : [])))
        .on('pointerleave', C.untip);
    });
    C.on((S, p) => { if (!p || !Object.keys(p).length) draw(S, p); });
    return draw;
  };

  /* ---------------- 10. ablations: what each input is worth ---------------- */
  Charts.ablation = function (el, opt) {
    opt = opt || {};
    const A = O.ablations, full = A.full_model_mean;
    const names = { no_analog: 'Analog chemicals', five_designs: 'Every layout in training', no_anchor: 'Interpolation anchor', no_hill: 'Hill fit' };
    const rows = ['no_analog', 'five_designs', 'no_anchor', 'no_hill'].map(k => ({ k, label: names[k], v: A.ablations[k].minus_full.rel_change_pct,
      lo: 100 * A.ablations[k].minus_full.ci95[0] / full, hi: 100 * A.ablations[k].minus_full.ci95[1] / full }));
    const draw = Charts.mount(el, (svg, W) => {
      const lab = opt.labelWidth || 160, rh = 32, H = rows.length * rh + 32;
      svg.attr('viewBox', `0 0 ${W} ${H}`).attr('height', H);
      const x = d3.scaleLinear().domain([Math.min(0, d3.min(rows, r => r.lo)), d3.max(rows, r => r.hi)]).nice(4).range([lab, W - 56]);
      layer(svg, 'xax').attr('transform', `translate(0,${H - 28})`).attr('class', 'xax axis')
        .call(d3.axisBottom(x).ticks(4).tickFormat(v => `${v > 0 ? '+' : ''}${v}%`).tickSize(4).tickPadding(6)).call(a => a.select('.domain').attr('stroke', css('axis')));
      layer(svg, 'zero').selectAll('line').data([0]).join('line').attr('class', 'zero').attr('x1', x(0)).attr('x2', x(0)).attr('y1', 0).attr('y2', H - 28);
      layer(svg, 'labels').selectAll('text').data(rows).join('text').attr('class', 'label').attr('x', lab - 8).attr('text-anchor', 'end').attr('y', (r, i) => i * rh + rh / 2 + 4).text(r => r.label);
      layer(svg, 'bars').selectAll('rect').data(rows).join('rect').attr('fill', css('forecast')).attr('rx', 3)
        .attr('x', x(0)).attr('y', (r, i) => i * rh + rh / 2 - 6).attr('height', 12).attr('width', r => Math.max(2, x(r.v) - x(0)));
      layer(svg, 'ci').selectAll('line').data(rows).join('line').attr('stroke', css('ink')).attr('stroke-width', 1.25)
        .attr('x1', r => x(r.lo)).attr('x2', r => x(r.hi)).attr('y1', (r, i) => i * rh + rh / 2).attr('y2', (r, i) => i * rh + rh / 2);
      layer(svg, 'hits').selectAll('rect').data(rows).join('rect').attr('class', 'hit').attr('x', 0).attr('width', W).attr('y', (r, i) => i * rh).attr('height', rh)
        .on('pointermove', (ev, r) => C.tip(ev, `+${C.fix(r.v, 2)}% error without it`, [r.label, `95% interval ${C.fix(r.lo, 2)}% to ${C.fix(r.hi, 2)}%`, '194 held-out chemicals, paired']))
        .on('pointerleave', C.untip);
    });
    C.on((S, p) => { if (!p || !Object.keys(p).length) draw(S, p); });
    return draw;
  };
})();

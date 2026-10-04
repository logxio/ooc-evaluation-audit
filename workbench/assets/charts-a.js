/* Charts A: concentration-response curve with call track, per-output error matrix, plate map, layout matrix. */
(function () {
  'use strict';
  const C = window.Core, O = C.O, D = C.D, NF = C.NF;
  const Charts = window.Charts = window.Charts || {};
  const T = 240;
  const css = n => `var(--${n})`;

  /* shared mounting: one svg per container, redrawn on width change */
  Charts.mount = function (el, draw) {
    const svg = d3.select(el).append('svg').attr('class', 'chart');
    let seen = -1, last = null, raf = 0;
    const run = (S, patch) => { last = S; seen = Math.round(el.clientWidth); draw(svg, Math.max(240, seen), S, patch || {}); };
    new ResizeObserver(() => {
      const w = Math.round(el.clientWidth);
      if (!last || !w || w === seen) return;
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => run(last, { resize: true }));
    }).observe(el);
    return run;
  };
  Charts.dur = patch => (!patch || patch.resize || patch.init || !Object.keys(patch).length ? 0 : T);
  Charts.keys = function (el, items) {
    el.textContent = '';
    el.classList.add('keys');
    items.forEach(([kind, color, label]) => {
      const s = document.createElement('span'); s.className = 'key';
      const i = document.createElement('i'); i.className = kind; i.style.color = color;
      if (kind !== 'ring' && kind !== 'dash' && kind !== 'dots') i.style.background = color;
      s.append(i, document.createTextNode(label)); el.appendChild(s);
    });
  };
  const layer = (sel, cls) => { let g = sel.select('g.' + cls); if (g.empty()) g = sel.append('g').attr('class', cls); return g; };
  Charts.layer = layer;

  /* ---------------- 1. concentration-response curve with call track ---------------- */
  Charts.curve = function (el, opt) {
    opt = opt || {};
    const M = { t: 8, r: 16, b: 32, l: 44 }, GAP = 24, H2 = opt.track || 72;
    const draw = Charts.mount(el, (svg, W, S, patch) => {
      const H1 = opt.height || 280, dur = Charts.dur(patch);
      const c = O.chems[S.chem], d = C.design(c, S.design), w = C.levelStats(c.w), L = w.levels.length, j = S.output;
      const iw = W - M.l - M.r, H = M.t + H1 + GAP + H2 + M.b;
      svg.attr('viewBox', `0 0 ${W} ${H}`).attr('height', H);
      const lv = w.levels, measured = new Set(d.m), qIndex = new Map(d.q.map((l, i) => [l, i]));
      const x = d3.scaleLinear().domain([lv[0] - 0.3, lv[L - 1] + 0.3]).range([0, iw]);
      const reps = new Map();
      const pts = [];
      w.lv.forEach((l, r) => {
        const v = w._y[r * D + j]; if (Number.isNaN(v)) return;
        const k = reps.get(l) || 0; reps.set(l, k + 1);
        pts.push({ id: r, l, v, k, run: measured.has(l) });
      });
      const nAt = l => reps.get(l) || 1;
      const jit = p => x(lv[p.l]) + (p.k - (nAt(p.l) - 1) / 2) * 6;
      const fc = d.q.map((l, i) => ({ l, f: d._f[i * D + j], h: d._w[i * D + j], ll: d._ll[i * D + j] }));
      const vals = pts.map(p => p.v).concat(fc.flatMap(p => [p.f - (p.h || 0), p.f + (p.h || 0), p.ll]));
      const ext = d3.extent(vals.filter(Number.isFinite));
      const y = d3.scaleLinear().domain([Math.min(ext[0], 0), Math.max(ext[1], 0)]).nice(5).range([H1, 0]).clamp(true);
      y.domain([Math.max(-10.5, y.domain()[0]), Math.min(10.5, y.domain()[1])]);
      const g = layer(svg, 'main').attr('transform', `translate(${M.l},${M.t})`);
      const clipId = 'clip-' + (el.id || 'curve');
      layer(svg, 'defs').selectAll('clipPath').data([0]).join('clipPath').attr('id', clipId)
        .selectAll('rect').data([0]).join('rect').attr('x', -8).attr('y', -4).attr('width', iw + 16).attr('height', H1 + 8);
      layer(g, 'yax').call(d3.axisLeft(y).ticks(5).tickSize(4).tickPadding(6)).attr('class', 'yax axis').call(a => a.select('.domain').remove());
      layer(g, 'zero').selectAll('line').data([0]).join('line').attr('class', 'zero').attr('x1', 0).attr('x2', iw)
        .transition().duration(dur).attr('y1', y(0)).attr('y2', y(0));
      layer(g, 'name').selectAll('text').data([C.outName(j)]).join('text').attr('class', 'label').attr('x', 8).attr('y', 12).text(t => t);
      // 90% interval capsules
      layer(g, 'band').attr('clip-path', `url(#${clipId})`).selectAll('rect').data(fc.filter(p => Number.isFinite(p.h)), p => p.l).join(
        e => e.append('rect').attr('rx', 6).attr('width', 12).attr('fill', css('band')).attr('x', p => x(lv[p.l]) - 6).attr('y', p => y(p.f + p.h)).attr('height', p => Math.max(1, y(p.f - p.h) - y(p.f + p.h))),
        u => u, x0 => x0.remove())
        .transition().duration(dur).attr('x', p => x(lv[p.l]) - 6).attr('y', p => y(p.f + p.h)).attr('height', p => Math.max(1, y(p.f - p.h) - y(p.f + p.h)));
      // comparator: log-linear interpolation through the measured means
      const meanAt = l => w._mu[l * D + j];
      const seq = (val) => lv.map((_, l) => ({ l, v: measured.has(l) ? meanAt(l) : val(qIndex.get(l)) })).filter(p => Number.isFinite(p.v));
      const line = d3.line().x(p => x(lv[p.l])).y(p => y(p.v));
      layer(g, 'll').selectAll('path').data([seq(i => fc[i].ll)]).join('path').attr('fill', 'none').attr('stroke', css('compare'))
        .attr('stroke-width', 2).attr('stroke-dasharray', '0.5 4').attr('stroke-linecap', 'round').transition().duration(dur).attr('d', line);
      layer(g, 'fl').selectAll('path').data([seq(i => fc[i].f)]).join('path').attr('fill', 'none').attr('stroke', css('forecast'))
        .attr('stroke-width', 2).attr('stroke-linejoin', 'round').transition().duration(dur).attr('d', line);
      // wells: measured solid, held out hollow
      layer(g, 'wells').selectAll('circle').data(pts.filter(p => p.run || S.truth !== false), p => p.id).join(
        e => e.append('circle').attr('r', 3).attr('cx', jit).attr('cy', p => y(p.v)),
        u => u, x0 => x0.remove())
        .attr('fill', p => (p.run ? css('measured') : 'none')).attr('stroke', p => (p.run ? css('surface') : css('ink-3')))
        .attr('stroke-width', p => (p.run ? 1.5 : 1.25))
        .transition().duration(dur).attr('cx', jit).attr('cy', p => y(p.v));
      layer(g, 'fdots').selectAll('circle').data(fc, p => p.l).join('circle').attr('r', 4.5).attr('fill', css('forecast'))
        .attr('stroke', css('surface')).attr('stroke-width', 2).transition().duration(dur).attr('cx', p => x(lv[p.l])).attr('cy', p => y(p.f));
      // call track
      const tr = C.track(c, S.design);
      const items = lv.map((_, l) => (measured.has(l) ? { l, v: tr.meas[l].e, src: 'm' } : { l, v: tr.fore[qIndex.get(l)].e, src: 'f', truth: tr.meas[l].e }));
      const top = Math.max(3.6, tr.score, S.truth !== false ? tr.truth : 0) * 1.08;
      const y2 = d3.scaleLinear().domain([0, top]).range([H2, 0]);
      const g2 = layer(svg, 'track').attr('transform', `translate(${M.l},${M.t + H1 + GAP})`);
      layer(g2, 'xax').attr('transform', `translate(0,${H2})`).attr('class', 'xax axis')
        .call(d3.axisBottom(x).tickValues(lv).tickFormat(C.uM).tickSize(4).tickPadding(6)).call(a => a.select('.domain').attr('stroke', css('axis')));
      layer(g2, 'unit').selectAll('text').data(['µM']).join('text').attr('class', 'tick-label').attr('x', iw).attr('y', H2 + 30).attr('text-anchor', 'end').text(t => t);
      layer(g2, 'cut').selectAll('line').data([3]).join('line').attr('class', 'cutoff').attr('x1', 0).attr('x2', iw)
        .transition().duration(dur).attr('y1', y2(3)).attr('y2', y2(3));
      layer(g2, 'cutl').selectAll('text').data(['cutoff 3']).join('text').attr('class', 'tick-label').attr('x', -8).attr('text-anchor', 'end')
        .transition().duration(dur).attr('y', y2(3) + 4).text(t => t);
      layer(g2, 'stems').selectAll('line').data(items, p => p.l).join('line').attr('stroke-width', 2).attr('stroke-linecap', 'round')
        .attr('stroke', p => (p.src === 'm' ? css('measured') : css('forecast')))
        .transition().duration(dur).attr('x1', p => x(lv[p.l])).attr('x2', p => x(lv[p.l])).attr('y1', y2(0)).attr('y2', p => y2(p.v));
      layer(g2, 'heads').selectAll('circle').data(items, p => p.l).join('circle').attr('r', 3.5)
        .attr('fill', p => (p.src === 'm' ? css('measured') : css('forecast'))).attr('stroke', css('surface')).attr('stroke-width', 1.5)
        .transition().duration(dur).attr('cx', p => x(lv[p.l])).attr('cy', p => y2(p.v));
      layer(g2, 'truth').selectAll('circle').data(S.truth !== false ? items.filter(p => p.src === 'f') : [], p => p.l).join('circle')
        .attr('r', 3.5).attr('fill', 'none').attr('stroke', css('ink-3')).attr('stroke-width', 1.25)
        .transition().duration(dur).attr('cx', p => x(lv[p.l]) + 9).attr('cy', p => y2(p.truth));
      const best = items.reduce((a, b) => (b.v > a.v ? b : a));
      const left = p => x(lv[p.l]) > 96;
      layer(g2, 'score').selectAll('text').data([best]).join('text').attr('class', 'label strong').attr('text-anchor', p => (left(p) ? 'end' : 'start'))
        .text(`score ${C.fix(tr.score)}`)
        .transition().duration(dur).attr('x', p => x(lv[p.l]) + (left(p) ? -8 : 18)).attr('y', p => y2(p.v) + 4);
      layer(g2, 'tname').selectAll('text').data(['largest |DIV-mean| response across features']).join('text').attr('class', 'label').attr('x', 8).attr('y', -6).text(t => t);
      // hover: snap to the nearest concentration
      const cross = layer(g, 'cross');
      const hov = layer(svg, 'hover').attr('transform', `translate(${M.l},${M.t})`);
      hov.selectAll('rect').data([0]).join('rect').attr('class', 'hit').attr('width', iw).attr('height', H1 + GAP + H2)
        .on('pointermove', ev => {
          const [mx] = d3.pointer(ev);
          const l = d3.minIndex(lv, v => Math.abs(x(v) - mx));
          cross.selectAll('line').data([l]).join('line').attr('stroke', css('axis')).attr('y1', 0).attr('y2', H1).attr('x1', x(lv[l])).attr('x2', x(lv[l]));
          const here = pts.filter(p => p.l === l), vs = here.map(p => C.fix(p.v)).join(', ');
          if (measured.has(l)) {
            C.tip(ev, `${C.uM(lv[l])} µM · measured`, [{ text: `mean ${C.fix(meanAt(l))} · wells ${vs}`, color: css('measured') },
              { text: `DIV-mean response ${C.fix(tr.meas[l].e)} (${O.features[tr.meas[l].f]})` }]);
          } else {
            const p = fc[qIndex.get(l)], inside = here.filter(h => Math.abs(h.v - p.f) <= p.h).length;
            C.tip(ev, `${C.uM(lv[l])} µM · forecast ${C.fix(p.f)}`, [
              { text: `90% interval ${C.fix(p.f - p.h)} to ${C.fix(p.f + p.h)}`, color: css('band') },
              { text: `log-linear ${C.fix(p.ll)}`, color: css('compare') },
              { text: `held-out wells ${vs || '—'} · ${inside} of ${here.length} inside`, color: css('ink-3') }]);
          }
        })
        .on('pointerleave', () => { cross.selectAll('line').remove(); C.untip(); });
    });
    C.on((S, p) => { if (!p || 'chem' in p || 'design' in p || 'output' in p || 'truth' in p || !Object.keys(p).length) draw(S, Object.keys(p || {}).length ? p : { init: true }); });
    return draw;
  };

  /* readout beside the curve: action, hit call, margins, this chemical's errors */
  Charts.callReadout = function (el) {
    C.on((S, p) => {
      if (p && Object.keys(p).length && !('chem' in p || 'design' in p)) return;
      const c = O.chems[S.chem], d = c.d[S.design];
      el.textContent = '';
      const row = document.createElement('div'); row.className = 'row'; row.style.flexWrap = 'wrap';
      const b = (cls, t) => { const s = document.createElement('span'); s.className = 'badge ' + cls; s.textContent = t; return s; };
      row.append(b(d.act ? 'report' : 'retest', d.act ? 'Report call' : 'Measure full series'), b('plain', `hit call: ${d.call === 0 ? 'active' : 'inactive'}`));
      if (S.truth !== false) row.append(b(d.call === d.y ? 'plain' : 'wrong', d.call === d.y ? 'full series agrees' : 'full series disagrees'));
      el.appendChild(row);
    });
  };

  /* ---------------- 2. per-output error matrix (17 features x 4 recording days) ---------------- */
  Charts.heat = function (el, opt) {
    opt = opt || {};
    const draw = Charts.mount(el, (svg, W, S, patch) => {
      const c = O.chems[S.chem], d = C.design(c, S.design), lab = opt.labelWidth || 208, rh = opt.row || 16, top = 20;
      const cw = Math.floor((W - lab) / 4), H = top + NF * rh + 4;
      svg.attr('viewBox', `0 0 ${W} ${H}`).attr('height', H);
      const color = d3.scaleSequential(d3.interpolateLab(getComputedStyle(el).getPropertyValue('--heat-lo').trim(), getComputedStyle(el).getPropertyValue('--heat-hi').trim())).domain([0, 3]).clamp(true);
      const cells = d3.range(D).map(j => ({ j, f: j % NF, t: Math.floor(j / NF), e: d._e[j] }));
      layer(svg, 'cols').selectAll('text').data(O.divs).join('text').attr('class', 'tick-label').attr('text-anchor', 'middle')
        .attr('x', (v, i) => lab + i * cw + cw / 2).attr('y', 12).text(v => `DIV ${v}`);
      layer(svg, 'rows').selectAll('text').data(O.features).join('text').attr('class', (v, i) => (i === S.output % NF ? 'label strong' : 'label'))
        .attr('x', lab - 8).attr('text-anchor', 'end').attr('y', (v, i) => top + i * rh + rh / 2 + 4).text(v => v);
      layer(svg, 'cells').selectAll('rect').data(cells, p => p.j).join('rect').attr('class', 'mark')
        .attr('x', p => lab + p.t * cw + 1).attr('y', p => top + p.f * rh + 1).attr('width', cw - 2).attr('height', rh - 2).attr('rx', 2)
        .attr('fill', p => (Number.isFinite(p.e) ? color(p.e) : css('sunk')))
        .attr('stroke', p => (p.j === S.output ? css('accent') : 'none')).attr('stroke-width', 2)
        .style('cursor', 'pointer')
        .on('pointermove', (ev, p) => C.tip(ev, Number.isFinite(p.e) ? `mean |error| ${C.fix(p.e)}` : 'no held-out wells', [`${O.features[p.f]} · DIV ${O.divs[p.t]}`, 'click to plot this output']))
        .on('pointerleave', C.untip)
        .on('click', (ev, p) => C.set({ output: p.j }));
      if (opt.scale) {
        const s = opt.scale; s.textContent = '';
        const bar = document.createElement('span'); bar.className = 'key';
        const g = document.createElement('i'); g.style.cssText = `width:64px;height:8px;border-radius:2px;background:linear-gradient(90deg,${color(0)},${color(3)})`;
        bar.append(document.createTextNode('0'), g, document.createTextNode('3+ mean |error|'));
        s.appendChild(bar);
      }
    });
    C.on((S, p) => { if (!p || !Object.keys(p).length || 'chem' in p || 'design' in p || 'output' in p) draw(S, p); });
    return draw;
  };

  /* ---------------- 3. plate map: run wells lit, unrun wells left to the forecast ---------------- */
  const plates = new Map();
  O.wells.forEach(w => w.plate.forEach((p, r) => { if (!plates.has(p)) plates.set(p, []); plates.get(p).push({ name: w.name, r, l: w.lv[r] }); }));
  Charts.plates = plates;
  Charts.plate = function (el, opt) {
    opt = opt || {};
    const draw = Charts.mount(el, (svg, W, S, patch) => {
      const dur = Charts.dur(patch), c = O.chems[S.chem], d = c.d[S.design], run = new Set(d.m);
      const ids = [...new Set(c.w.plate)];
      const per = Math.min(opt.max || 3, ids.length), gap = 16;
      const pw = Math.min(opt.plateWidth || 232, Math.floor((W - (per - 1) * gap) / per));
      const cell = Math.floor(pw / 8), r = Math.min(10, cell / 2 - 2), ph = cell * 6 + 24;
      const rowsN = Math.ceil(ids.length / per), H = rowsN * (ph + gap) - gap;
      svg.attr('viewBox', `0 0 ${W} ${H}`).attr('height', H);
      const wells = [];
      ids.forEach((id, pi) => {
        const ox = (pi % per) * (pw + gap), oy = Math.floor(pi / per) * (ph + gap) + 20;
        const list = plates.get(id), names = [...new Set(list.map(x => x.name))].sort();
        let row = 0;
        names.forEach(n => {
          const mine = list.filter(x => x.name === n).sort((a, b) => a.l - b.l);
          mine.forEach((x, k) => {
            const rr = row + Math.floor(k / 8), cc = k % 8;
            wells.push({ key: `${id}|${n}|${x.r}`, id, name: n, l: x.l, r: x.r, cx: ox + cc * cell + cell / 2, cy: oy + rr * cell + cell / 2, self: n === c.name });
          });
          row += Math.ceil(mine.length / 8);
        });
        for (let rr = 0; rr < 6; rr++) for (let cc = 0; cc < 8; cc++) {
          const taken = wells.some(wl => wl.id === id && Math.abs(wl.cx - (ox + cc * cell + cell / 2)) < 1 && Math.abs(wl.cy - (oy + rr * cell + cell / 2)) < 1);
          if (!taken) wells.push({ key: `${id}|empty|${rr}|${cc}`, id, empty: true, cx: ox + cc * cell + cell / 2, cy: oy + rr * cell + cell / 2 });
        }
      });
      layer(svg, 'frames').selectAll('rect').data(ids.map((id, pi) => ({ id, x: (pi % per) * (pw + gap), y: Math.floor(pi / per) * (ph + gap) + 20 })), p => p.id)
        .join('rect').attr('x', p => p.x - 4).attr('y', p => p.y - 4).attr('width', cell * 8 + 8).attr('height', cell * 6 + 8).attr('rx', 10).attr('fill', css('sunk'));
      layer(svg, 'names').selectAll('text').data(ids.map((id, pi) => ({ id, x: (pi % per) * (pw + gap), y: Math.floor(pi / per) * (ph + gap) + 12 })), p => p.id)
        .join('text').attr('class', 'tick-label').attr('x', p => p.x - 4).attr('y', p => p.y).text(p => `plate ${p.id.split('|')[0]}`);
      const state = wl => (wl.empty ? 'empty' : !wl.self ? 'other' : run.has(wl.l) || S.full ? 'run' : 'saved');
      layer(svg, 'wells').selectAll('circle').data(wells, p => p.key).join('circle').attr('class', 'mark').attr('cx', p => p.cx).attr('cy', p => p.cy).attr('r', r)
        .style('cursor', p => (!p.empty && !p.self && C.chemBy.has(p.name) ? 'pointer' : null))
        .on('pointermove', (ev, p) => {
          if (p.empty) return C.tip(ev, 'Well outside the exposure table', [`plate ${p.id.split('|')[0]}`]);
          const s = state(p), cw = O.wells.find(x => x.name === p.name);
          C.tip(ev, `${p.name}`, [`${C.uM(cw.levels[p.l])} µM · plate ${p.id.split('|')[0]}`,
            p.self ? (s === 'run' ? (run.has(p.l) ? 'measured in this design' : 'measured in the full series') : 'left unrun; the forecast fills it') : (C.chemBy.has(p.name) ? 'click to open this chemical' : 'shares the plate')]);
        })
        .on('pointerleave', C.untip)
        .on('click', (ev, p) => { if (!p.empty && !p.self && C.chemBy.has(p.name)) C.set({ chem: C.chemBy.get(p.name).i }); })
        .style('fill', p => ({ empty: css('paper'), other: css('line'), run: css('measured'), saved: css('surface') })[state(p)])
        .style('stroke', p => (state(p) === 'saved' ? css('forecast') : 'none')).attr('stroke-width', 1.5);
      if (dur === 0) svg.selectAll('circle.mark').style('transition', 'none'); else svg.selectAll('circle.mark').style('transition', null);
      if (opt.onCount) {
        const mine = wells.filter(x => x.self), saved = mine.filter(x => !run.has(x.l)).length;
        opt.onCount({ total: mine.length, run: mine.length - saved, saved, plates: ids.length });
      }
    });
    C.on((S, p) => { if (!p || !Object.keys(p).length || 'chem' in p || 'design' in p || 'full' in p) draw(S, p); });
    return draw;
  };

  /* ---------------- 4. layout matrix: which three of seven concentrations settle the call ---------------- */
  Charts.layouts = function (el, opt) {
    opt = opt || {};
    const all = C.layouts();
    const draw = Charts.mount(el, (svg, W, S, patch) => {
      const dur = Charts.dur(patch), c = O.chems[S.chem], seven = c.w.levels.length === 7;
      const mine = new Map(seven ? c.d.map((d, k) => [d.m.join(''), k]) : []);
      const lab = 72, top = 96, rh = 14, H = top + 16 + 7 * rh + 8;
      svg.attr('viewBox', `0 0 ${W} ${H}`).attr('height', H);
      const x = d3.scaleBand().domain(all.map(p => p.key)).range([lab, W - 4]).paddingInner(0.18);
      const y = d3.scaleLinear().domain([0.75, 1]).range([top - 8, 8]);
      layer(svg, 'yax').attr('transform', `translate(${lab - 8},0)`).attr('class', 'yax axis')
        .call(d3.axisLeft(y).tickValues([0.8, 0.9, 1]).tickFormat(v => `${Math.round(v * 100)}%`).tickSize(4).tickPadding(6)).call(a => a.select('.domain').remove());
      layer(svg, 'sel').selectAll('rect').data(all.filter(p => mine.get(p.key) === S.design || p.key === S.layout), p => p.key).join('rect')
        .attr('fill', p => (p.key === S.layout && mine.get(p.key) !== S.design ? 'none' : css('sunk')))
        .attr('stroke', p => (p.key === S.layout ? css('accent') : 'none')).attr('stroke-width', 1.5)
        .attr('rx', 4).attr('y', 0).attr('height', H).transition().duration(dur).attr('x', p => x(p.key) - 3).attr('width', x.bandwidth() + 6);
      layer(svg, 'guides').selectAll('line').data(all, p => p.key).join('line').attr('stroke', css('line'))
        .attr('x1', p => x(p.key) + x.bandwidth() / 2).attr('x2', p => x(p.key) + x.bandwidth() / 2).attr('y1', p => y(p.rate)).attr('y2', top - 4);
      layer(svg, 'rates').selectAll('circle').data(all, p => p.key).join('circle').attr('class', 'mark').attr('r', 4)
        .attr('cx', p => x(p.key) + x.bandwidth() / 2).attr('cy', p => y(p.rate))
        .attr('fill', p => (mine.has(p.key) ? css('forecast') : css('ink-3'))).attr('stroke', css('surface')).attr('stroke-width', 2);
      const ranks = ['lowest', '', '', '', '', '', 'highest'];
      layer(svg, 'rlab').selectAll('text').data(ranks).join('text').attr('class', 'tick-label').attr('x', 0).attr('y', (v, i) => top + 16 + i * rh + 4).text(v => v);
      const dots = all.flatMap(p => d3.range(7).map(i => ({ p, i, on: p.pos.includes(i) })));
      layer(svg, 'links').selectAll('line').data(all, p => p.key).join('line').attr('stroke-width', 2).attr('stroke-linecap', 'round')
        .attr('stroke', p => (mine.has(p.key) ? css('forecast') : css('ink-2')))
        .attr('x1', p => x(p.key) + x.bandwidth() / 2).attr('x2', p => x(p.key) + x.bandwidth() / 2)
        .attr('y1', p => top + 16 + p.pos[0] * rh).attr('y2', p => top + 16 + p.pos[2] * rh);
      layer(svg, 'dots').selectAll('circle').data(dots, q => q.p.key + q.i).join('circle').attr('class', 'mark').attr('r', q => (q.on ? 4 : 2.5))
        .attr('cx', q => x(q.p.key) + x.bandwidth() / 2).attr('cy', q => top + 16 + q.i * rh)
        .attr('fill', q => (q.on ? (mine.has(q.p.key) ? css('forecast') : css('ink')) : css('line')));
      layer(svg, 'hits').selectAll('rect').data(all, p => p.key).join('rect').attr('class', 'hit').attr('x', p => x(p.key) - 2).attr('width', x.bandwidth() + 4).attr('y', 0).attr('height', H)
        .style('cursor', p => (mine.has(p.key) ? 'pointer' : 'default'))
        .on('pointermove', (ev, p) => C.tip(ev, `${p.rep} of ${p.n} settled`, [
          `measure concentrations ${p.pos.map(i => i + 1).join(', ')} of 7`, `${p.wrong} wrong ${p.wrong === 1 ? 'call' : 'calls'} among them`,
          mine.has(p.key) ? `this chemical's design ${mine.get(p.key) + 1}` : 'held-out designs of other chemicals']))
        .on('pointerleave', C.untip)
        .on('click', (ev, p) => { if (mine.has(p.key)) C.set({ design: mine.get(p.key) }); });
    });
    C.on((S, p) => { if (!p || !Object.keys(p).length || 'chem' in p || 'design' in p || 'layout' in p) draw(S, p); });
    return draw;
  };
})();

/* Charts C: patient decision map and plate, agent replay, model band, paste input, pickers. */
(function () {
  'use strict';
  const C = window.Core, O = C.O, P = O.patients;
  const Charts = window.Charts, layer = Charts.layer;
  const css = n => `var(--${n})`;
  const h = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; };
  Charts.h = h;
  const wrong = (r, S) => S.reveal && (r.response === 0 || r.response === 1) && r.call !== null && r.call !== r.response;
  const action = r => (r.reference ? 'reference' : r.call === null ? 'retest' : r.call === 1 ? 'sensitive' : 'resistant');
  const fillOf = (r, S) => (wrong(r, S) ? css('wrong') : r.call === 1 ? css('report') : css('surface'));
  const strokeOf = (r, S) => (wrong(r, S) ? css('wrong') : r.reference ? css('compare') : r.call === null ? css('retest') : css('report'));
  Charts.patientAction = action;

  /* 8a. patient decision map
     combined mode: combined-regimen readout against irradiation, one frozen cutoff;
     two-readout mode: readout 1 against readout 2, both frozen cutoffs, disagreement goes to retest */
  Charts.patients = function (el, opt) {
    opt = opt || {};
    const M = { t: 24, r: 16, b: 40, l: 48 };
    const cert = () => window.WORKBENCH_RESULT && window.WORKBENCH_RESULT.rule.certificate.model.cutoffs;
    const draw = Charts.mount(el, (svg, W, S, patch) => {
      const dur = Charts.dur(patch), rows = S.patients, H1 = opt.height || 260, H = M.t + H1 + M.b, iw = W - M.l - M.r;
      svg.attr('viewBox', `0 0 ${W} ${H}`).attr('height', H);
      const two = rows.length && rows[0].mode === 'two', assayOnly = !!(S.patientCohort && S.patientCohort.assayOnly);
      const cut = two ? (S.patientSource === 'final1009' ? S.patientCutoffs : cert()) : [P.cutoff];
      const xKey = two ? 'r1' : 'combined';
      const yKey = two ? 'r2' : rows.some(r => r.irr > 0) ? 'irr' : rows.some(r => r.fu > 0) ? 'fu' : null;
      const pos = v => Math.max(0.004, v);
      const has = r => r[xKey] !== null && r[xKey] !== undefined;
      const shown = rows.filter(has);
      const xs = shown.map(r => pos(r[xKey])), ys = yKey ? shown.map(r => pos(r[yKey] || 0.004)) : shown.map((r, i) => i + 1);
      const x = d3.scaleLog().domain([Math.min(d3.min(xs) || 1, cut[0]) / 1.4, Math.max(d3.max(xs) || 1, cut[0]) * 1.4]).range([0, iw]);
      const yc = two ? cut[1] : null;
      const y = yKey ? d3.scaleLog().domain([Math.min(d3.min(ys) || 1, yc || Infinity) / 1.4, Math.max(d3.max(ys) || 1, yc || 0) * 1.4]).range([H1, 0]) : d3.scaleLinear().domain([0, shown.length + 1]).range([H1, 0]);
      const g = layer(svg, 'g').attr('transform', `translate(${M.l},${M.t})`);
      layer(g, 'side').selectAll('rect').data(assayOnly ? [] : [0]).join('rect').attr('fill', css('band')).attr('opacity', 0.45).attr('x', 0)
        .attr('y', two ? y(yc) : 0).attr('height', two ? H1 - y(yc) : H1).attr('width', x(cut[0]));
      layer(g, 'xax').attr('transform', `translate(0,${H1})`).attr('class', 'xax axis')
        .call(d3.axisBottom(x).ticks(5, '~g').tickSize(4).tickPadding(6)).call(a => a.select('.domain').attr('stroke', css('axis')));
      layer(g, 'yax').attr('class', 'yax axis').call(yKey ? d3.axisLeft(y).ticks(4, '~g').tickSize(4).tickPadding(6) : d3.axisLeft(y).ticks(0)).call(a => a.select('.domain').remove());
      const labels = S.patientSource === 'final1009' ? S.patientAxisLabels : ['readout 1', 'readout 2'];
      layer(g, 'xt').selectAll('text').data([two ? labels[0] : 'organoid size, day 24 / day 0, combined regimen']).join('text').attr('class', 'axis-title').attr('x', iw).attr('y', H1 + 34).attr('text-anchor', 'end').text(t => t);
      layer(g, 'yt').selectAll('text').data([two ? labels[1] : yKey === 'irr' ? 'irradiation alone' : yKey === 'fu' ? '5-FU alone' : 'patients']).join('text').attr('class', 'axis-title').attr('x', -M.l).attr('y', -12).text(t => t);
      layer(g, 'cut').selectAll('line').data(assayOnly ? [] : [cut[0]]).join('line').attr('class', 'cutoff').attr('y1', 0).attr('y2', H1).attr('x1', v => x(v)).attr('x2', v => x(v));
      layer(g, 'cuty').selectAll('line').data(two && !assayOnly ? [yc] : []).join('line').attr('class', 'cutoff').attr('x1', 0).attr('x2', iw).attr('y1', v => y(v)).attr('y2', v => y(v));
      const sides = assayOnly ? [] : two ? [['report sensitive', 8, H1 - 8, 'start'], ['report resistant', iw - 8, 14, 'end'], ['retest', 8, 14, 'start'], ['retest', iw - 8, H1 - 8, 'end']]
        : [[`sensitive ≤ ${P.cutoff}`, x(P.cutoff) - 6, 14, 'end'], ['resistant', x(P.cutoff) + 6, 14, 'start']];
      layer(g, 'sides').selectAll('text').data(sides).join('text').attr('class', 'label').attr('x', d => d[1]).attr('y', d => d[2]).attr('text-anchor', d => d[3]).text(d => d[0]);
      const off = rows.length - shown.length;
      layer(g, 'off').selectAll('text').data(off ? [off] : []).join('text').attr('class', 'label')
        .attr('x', shown.length ? 0 : iw - 8).attr('y', shown.length ? H1 + 34 : H1 * 0.7).attr('text-anchor', shown.length ? 'start' : 'end')
        .text(n => (shown.length ? `${n} more without numerical readouts, in the plate` : `No readouts in this source; ${n} calls in the plate`));
      const pts = shown.map((r, i) => ({ r, cx: x(xs[i]), cy: yKey ? y(ys[i]) : y(i + 1) }));
      layer(g, 'pts').selectAll('circle').data(pts, p => p.r.id).join(
        e => e.append('circle').attr('cx', p => p.cx).attr('cy', p => p.cy).attr('r', 5),
        u => u, x0 => x0.remove())
        .attr('class', 'mark').style('cursor', 'pointer')
        .on('pointermove', (ev, p) => Charts.patientTip(ev, p.r, S))
        .on('pointerleave', C.untip)
        .on('click', (ev, p) => C.set({ patient: p.r.id === S.patient ? null : p.r.id }))
        .style('transition', dur ? null : 'none')
        .style('fill', p => fillOf(p.r, S)).style('stroke', p => (p.r.id === S.patient ? css('ink') : strokeOf(p.r, S)))
        .attr('stroke-width', p => (p.r.id === S.patient ? 2.5 : 2))
        .transition().duration(dur)
        .attr('cx', p => p.cx).attr('cy', p => p.cy).attr('r', p => (p.r.id === S.patient ? 7 : 5));
    });
    C.on((S, p) => { if (!p || !Object.keys(p).length || 'patients' in p || 'reveal' in p || 'patient' in p) draw(S, p); });
    return draw;
  };
  Charts.patientTip = function (ev, r, S) {
    const out = r.response === 1 ? 'responder' : r.response === 0 ? 'non-responder' : 'outcome not given';
    const f = v => (v === null || v === undefined ? null : C.fix(v, 3));
    const rows = (r.mode === 'two' ? [['readout 1', r.cohort ? r.readout1 : r.r1], ['readout 2', r.cohort ? r.readout2 : r.r2]] : [['combined regimen', r.combined], ['irradiation', r.irr], ['5-FU', r.fu]])
      .filter(([, v]) => f(v) !== null).map(([k, v]) => `${k} ${f(v)}`);
    rows.push(r.reason);
    rows.push(S.reveal ? { text: `clinical: ${out}`, color: wrong(r, S) ? css('wrong') : css('ink-3') } : 'clinical outcome hidden until reveal');
    C.tip(ev, `${r.id} · ${r.call === null ? action(r) : 'report ' + action(r)}`, rows);
  };

  /* 8b. the same patients as wells, linked by selection */
  Charts.patientPlate = function (el, opt) {
    opt = opt || {};
    const draw = Charts.mount(el, (svg, W, S, patch) => {
      const dur = Charts.dur(patch), rows = S.patients, cols = 8, nRows = Math.max(6, Math.ceil(rows.length / cols));
      const cell = Math.min(opt.cell || 40, Math.floor((W - 8) / cols)), r = cell / 2 - 3, H = nRows * cell + 8;
      svg.attr('viewBox', `0 0 ${W} ${H}`).attr('height', H);
      layer(svg, 'frame').selectAll('rect').data([0]).join('rect').attr('x', 0).attr('y', 0).attr('width', cols * cell + 8).attr('height', H).attr('rx', 12).attr('fill', css('sunk'));
      const cells = d3.range(nRows * cols).map(i => ({ i, r: rows[i], cx: 4 + (i % cols) * cell + cell / 2, cy: 4 + Math.floor(i / cols) * cell + cell / 2 }));
      layer(svg, 'wells').selectAll('circle').data(cells, q => q.i).join('circle').attr('class', 'mark').attr('cx', q => q.cx).attr('cy', q => q.cy).attr('r', r)
        .style('cursor', q => (q.r ? 'pointer' : null))
        .on('pointermove', (ev, q) => { if (q.r) Charts.patientTip(ev, q.r, S); })
        .on('pointerleave', C.untip)
        .on('click', (ev, q) => { if (q.r) C.set({ patient: q.r.id === S.patient ? null : q.r.id }); })
        .style('transition', dur ? null : 'none')
        .style('fill', q => (q.r ? fillOf(q.r, S) : css('paper')))
        .style('stroke', q => (!q.r ? 'none' : q.r.id === S.patient ? css('ink') : strokeOf(q.r, S)))
        .attr('stroke-width', q => (q.r && q.r.id === S.patient ? 3 : 1.5));
      layer(svg, 'ids').selectAll('text').data(cells.filter(q => q.r), q => q.i).join('text').attr('class', 'tick-label')
        .attr('x', q => q.cx).attr('y', q => q.cy + 4).attr('text-anchor', 'middle').style('pointer-events', 'none').style('font-weight', 600)
        .text(q => (q.r.id.match(/\d+$/) || [q.r.id.slice(0, 3)])[0].slice(-3))
        .style('fill', q => (q.r.call === 1 || wrong(q.r, S) ? css('surface') : css('ink')));
    });
    C.on((S, p) => { if (!p || !Object.keys(p).length || 'patients' in p || 'reveal' in p || 'patient' in p) draw(S, p); });
    return draw;
  };
  Charts.patientSummary = function (el) {
    C.on((S, p) => {
      if (p && Object.keys(p).length && !('patients' in p || 'reveal' in p)) return;
      const s = C.patientStats(S.patients), rows = S.patients;
      if (S.patientCohort && S.patientCohort.assayOnly) {
        el.textContent = `${rows.length} distinct patient assay pairs. Values are AUC (%) from the published drug screen. Clinical follow-up is a separate pool of 13; 7 meet the frozen audit definition, with no individual outcome joined to this view.`;
        return;
      }
      const sens = rows.filter(r => r.call === 1).length, res = rows.filter(r => r.call === 0).length;
      const ref = rows.filter(r => r.reference).length, retest = s.retest - ref;
      const unit = S.patientSource === 'final1009' && S.patientCohort ? S.patientCohort.evaluationUnit.replace('assay_patient', 'patient') : 'patient';
      el.textContent = '';
      if (ref === rows.length) {
        el.textContent = `${ref} patients whose frozen assays set the reference medians; their scored treatments are under Tan clinical.`;
        return;
      }
      if (!S.reveal || !s.known) {
        el.textContent = `${rows.length - ref} ${unit}s called before any outcome is opened: ${sens} sensitive, ${res} resistant` + (retest ? `, ${retest} to retest` : '') + (ref ? `; ${ref} reference assays.` : '.');
        return;
      }
      const miss = rows.filter(r => wrong(r, S)).map(r => r.id);
      el.textContent = (s.fp === 0 ? 'Every clinical non-responder is classified resistant in this retrospective replay' : `${s.tn} clinical non-responders are classified resistant in this retrospective replay`) +
        (miss.length ? `; ${miss.join(', ')} ${miss.length === 1 ? 'is the single wrong call' : 'are the wrong calls'}.` : '.');
    });
  };

  /* 12. agent replay: one external paper, call by call */
  const sentence = (text, needles) => {
    const parts = text.split(/(?<=[.!?])\s+(?=[A-Z(])/);
    return parts.find(s => needles.some(n => s.includes(n))) || parts[0];
  };
  Charts.agent = function (el, opt) {
    opt = opt || {};
    const A = O.agent, steps = A.steps.filter(s => s.tool !== 'view_source');
    const labels = {
      0: 'Drafts the contract from the article text',
      1: 'Revises it after one round of feedback',
      2: 'Opens Supplementary Table 2',
      3: 'Sends Figure 2I to a blind reader',
      4: 'Recomputes the headline and stops'
    };
    const fig = steps.find(s => s.tool === 'read_figure');
    const quotes = [
      ['Cohort', 'article:p18', ['12 out of 13']],
      ['Readout', 'article:p17', ['AUC']],
      ['Threshold', 'article:p15', ['0.559']],
      ['Direction', 'article:p16', ['responder', 'lower']]
    ].filter(q => A.quotes[q[1]]);
    let at = opt.start !== undefined ? opt.start : 3;
    const list = h('ol', 'agent-steps'), pane = h('div', 'agent-pane');
    el.textContent = ''; el.append(list, pane);
    function render() {
      list.textContent = '';
      steps.forEach((s, i) => {
        const li = h('li'); li.setAttribute('aria-current', i === at ? 'step' : 'false');
        const b = h('button', 'agent-step'); b.type = 'button';
        b.append(h('span', 't1 ink3 num', `Call ${s.call + 1}`), h('span', 't2', labels[s.call] || s.tool));
        b.onclick = () => { at = i; render(); };
        li.appendChild(b); list.appendChild(li);
      });
      pane.textContent = '';
      const s = steps[at];
      if (s.tool === 'read_figure') pane.append(figure());
      else if (s.tool === 'preview_table') pane.append(tableView(s));
      else if (s.tool === 'finish') pane.append(result());
      else pane.append(quoteView());
    }
    function quoteView() {
      const box = h('div', 'stack2');
      quotes.forEach(([k, ref, needles]) => {
        const q = h('figure', 'quote');
        q.append(h('figcaption', 't1 ink3', `${k} · ${ref.replace('article:', 'paragraph ')}`), h('blockquote', 't2', `“${sentence(A.quotes[ref], needles)}”`));
        box.appendChild(q);
      });
      return box;
    }
    function tableView(s) {
      const wrap = h('div', 'stack1');
      wrap.append(h('p', 't1 ink3', `${s.args.file} · rows ${s.args.start} to ${s.args.start + s.rows.length - 1}`));
      const t = h('table', 'mini');
      const head = h('tr'); ['Organoid', 'Age', 'Sex', 'Site', 'Clinical stage', 'Pathology', 'Regression grade'].forEach(x => head.appendChild(h('th', null, x)));
      t.appendChild(head);
      s.rows.slice(0, 12).forEach(r => { const tr = h('tr'); r.slice(0, 7).forEach(v => tr.appendChild(h('td', null, v))); t.appendChild(tr); });
      wrap.appendChild(t);
      return wrap;
    }
    function result() {
      const ev = A.evaluation, box = h('div', 'stack2');
      const big = h('div', 'row2');
      const v = h('div', 'stat'); v.append(h('div', 'v', `${ev.rows.filter(r => r.truth === r.prediction).length} of ${ev.n}`), h('div', 'k', 'patients called right, recomputed'));
      const w = h('div', 'stat'); w.append(h('div', 'v', `${C.fix(100 * ev.computed, 1)}%`), h('div', 'k', 'matches the published accuracy exactly'));
      big.append(v, w); box.appendChild(big);
      const t = h('table', 'mini');
      Object.entries(A.fields).forEach(([k, f]) => { const tr = h('tr'); tr.append(h('th', null, k.replace(/_/g, ' ')), h('td', null, String(f.value).replace(/_/g, ' '))); t.appendChild(tr); });
      box.appendChild(t);
      return box;
    }
    function figure() {
      const box = h('div', 'stack1');
      box.append(h('p', 't1 ink3', `${fig.source} · ${fig.rows.length} organoids transcribed without the target`));
      const holder = h('div'); box.appendChild(holder);
      const rows = fig.rows.map(r => ({ id: r[0], reps: r[1].split(';').map(Number), mean: Number(r[2]), cls: r[3], grade: r[4], ok: r[5] !== 'X' })).sort((a, b) => a.mean - b.mean);
      const run = Charts.mount(holder, (svg, W) => {
        svg.selectAll('*').remove();
        const rh = 18, lab = 56, H = rows.length * rh + 56;
        svg.attr('viewBox', `0 0 ${W} ${H}`).attr('height', H);
        const x = d3.scaleLinear().domain([0.35, 0.85]).range([lab, W - 72]);
        svg.append('g').attr('class', 'axis').attr('transform', `translate(0,${H - 44})`).call(d3.axisBottom(x).ticks(5).tickSize(4).tickPadding(6)).select('.domain').attr('stroke', css('axis'));
        svg.append('text').attr('class', 'axis-title').attr('x', W - 72).attr('y', H - 4).attr('text-anchor', 'end').text('relative AUC of the FLOT dose-response curve');
        svg.append('line').attr('class', 'cutoff').attr('x1', x(0.559)).attr('x2', x(0.559)).attr('y1', 0).attr('y2', H - 44);
        svg.append('text').attr('class', 'tick-label').attr('x', x(0.559) + 6).attr('y', 10).text('paper threshold 0.559');
        rows.forEach((r, i) => {
          const yy = 16 + i * rh;
          svg.append('text').attr('class', 'label').attr('x', lab - 8).attr('y', yy + 4).attr('text-anchor', 'end').text(r.id);
          svg.append('line').attr('stroke', css('line')).attr('stroke-width', 2).attr('x1', x(d3.min(r.reps))).attr('x2', x(d3.max(r.reps))).attr('y1', yy).attr('y2', yy);
          r.reps.forEach(v => svg.append('circle').attr('r', 2.5).attr('cx', x(v)).attr('cy', yy).attr('fill', css('ink-3')));
          svg.append('circle').attr('r', 4.5).attr('cx', x(r.mean)).attr('cy', yy).attr('stroke-width', 2)
            .attr('fill', r.ok ? (r.cls === 'R' ? css('report') : css('surface')) : css('wrong')).attr('stroke', r.ok ? css('report') : css('wrong'));
          svg.append('text').attr('class', 'label').attr('x', W - 64).attr('y', yy + 4).text(`grade ${r.grade}`);
        });
      });
      run(C.state, { init: true });
      return box;
    }
    render();
    return { go: i => { at = i; render(); } };
  };

  /* 11. what the model did, one band */
  Charts.band = function (el) {
    const m = O.model, iv = O.intervals;
    const items = [
      [C.int(m.designs_enumerated.fold1), 'three-concentration layouts enumerated for training'],
      [`${(m.timing.k3_fold1.training_rows / 1e6).toFixed(2)} M`, 'training rows, one model per fold'],
      [`${(m.timing.k3_fold1.seconds / 60).toFixed(1)} min`, 'to train a fold, CPU only'],
      [`${C.fix((1 - iv.width_ratio_learned_over_plain.value) * 100, 1)}%`, 'narrower intervals than plain conformal'],
      [C.pct(iv.learned.coverage), `of ${C.int(iv.wells)} held-out readings inside the 90% interval`]
    ];
    el.textContent = '';
    items.forEach(([v, k]) => { const s = h('div', 'stat'); s.append(h('div', 'v', v), h('div', 'k', k)); el.appendChild(s); });
  };

  /* hover and keyboard focus open the same tip, so the trigger itself stays one line */
  Charts.hoverTip = (el, title, rows, opt) => {
    const show = ev => {
      const r = el.getBoundingClientRect();
      C.tip(ev.clientX !== undefined ? ev : { clientX: r.left, clientY: r.bottom + 8 }, typeof title === 'function' ? title() : title, typeof rows === 'function' ? rows() : rows, opt);
    };
    el.addEventListener('pointermove', show); el.addEventListener('focus', show);
    el.addEventListener('pointerleave', C.untip); el.addEventListener('blur', C.untip);
    return el;
  };

  /* 13. scoreboard: the team stack against every published configuration at one to four measured concentrations */
  const WORDS = ['one', 'two', 'three', 'four'];
  const signed = (x, d = 4) => (x < 0 ? '−' : '+') + Math.abs(x).toFixed(d);
  Charts.scoreboardRows = k => {
    const B = O.final1009.baselines;
    return B.opponents.filter(o => o.k[k]).map(o => ({ o, x: o.k[k] })).sort((a, b) => a.x[0] - b.x[0]);
  };
  Charts.scoreboard = function (el, opt) {
    opt = opt || {};
    const B = O.final1009.baselines, view = { k: 3, all: false };
    const head = h('div', 'sbr sbh');
    ['Predictor', 'Error, lower is better', 'MAE', 'Stack minus row, 95% interval'].forEach(t => head.append(h('span', null, t)));
    Charts.hoverTip(head.lastChild, 'Paired 95% identity-cluster bootstrap', ['Chemicals of one identity resample together', 'Negative favours the stack; an interval that excludes 0 is a win']);
    head.lastChild.tabIndex = 0;
    const body = h('div', 'sb'), more = h('button', 'btn quiet sb-more'); more.type = 'button';
    more.onclick = () => { view.all = !view.all; render(); };
    el.textContent = ''; el.append(head, body, more);
    const row = (name, mae, lo, hi, me, url, x) => {
      const r = h('div', 'sbr' + (me ? ' me' : '')), tr = h('span', 'tr'), bar = h('i'), ref = h('b');
      const pos = v => Math.max(0, Math.min(100, (v - lo) / (hi - lo) * 100));
      bar.style.width = pos(mae) + '%'; ref.style.left = pos(B.team.k[view.k]) + '%'; tr.append(bar, ref);
      const nm = url ? h('a', 'nm', name) : h('span', 'nm', name);
      if (url) { nm.href = url; nm.target = '_blank'; nm.rel = 'noopener'; }
      const d = h('span', 'd');
      if (x) { d.append(h('b', x[4], x[4] === 'win' ? 'Win' : x[4] === 'tie' ? 'Tie' : 'Loss'), `${signed(x[1])} [${signed(x[2])}, ${signed(x[3])}]`); }
      else d.append('reference');
      r.append(nm, tr, h('span', 'val', mae.toFixed(4)), d);
      return r;
    };
    function render() {
      const rows = Charts.scoreboardRows(view.k), team = B.team.k[view.k];
      const maes = rows.map(r => r.x[0]).concat(team), lo = Math.floor(Math.min(...maes) * 10) / 10 - 0.1, hi = Math.max(...maes) * 1.02;
      body.textContent = '';
      body.append(row('AnchorBoost stack (ours)', team, lo, hi, true));
      (view.all ? rows : rows.slice(0, 9)).forEach(({ o, x }) => {
        const r = row(o.name, x[0], lo, hi, false, o.url, x);
        Charts.hoverTip(r, o.name, [`${o.family.replace(/_/g, ' ')} · MAE ${x[0].toFixed(4)} at ${WORDS[view.k - 1]} measured concentration${view.k > 1 ? 's' : ''}`,
          `Stack closer on ${x[5]} of ${x[5] + x[6]} chemicals`, `Stack minus row ${signed(x[1])}, 95% interval ${signed(x[2])} to ${signed(x[3])}`]);
        body.append(r);
      });
      more.hidden = rows.length <= 9;
      more.textContent = view.all ? 'Show the closest 9' : `Show all ${rows.length}`;
      if (opt.onK) opt.onK(view.k, rows.length);
    }
    render();
    return { set: k => { view.k = k; render(); } };
  };

  /* paste input: plate planner and patient table */
  Charts.input = function (el, opt) {
    opt = opt || {};
    const modes = [['series', 'Concentration series'], ['patients', 'Patient table']];
    let mode = opt.mode || 'series';
    const seg = h('div', 'seg'), area = h('textarea', 'field'), go = h('button', 'btn'), out = h('p', 't2 ink2'), alt = h('div', 'row');
    area.rows = opt.rows || 7; area.spellcheck = false;
    const examples = {
      series: '0.03 *\n0.1\n0.3\n1 *\n3\n10\n30 *',
      patients: 'patient,combined,irradiation,response\n' + P.rows.slice(0, 6).map(r => `${r.patient},${r.baseline_readout},${r.readout1},${r.response}`).join('\n')
    };
    const place = { series: 'Paste 7 concentrations in µM, one per line.\nMark the three you will measure with *', patients: 'patient,readout1,readout2,response\nP01,0.60,0.40,1\nP02,1.20,0.80,0\n\nor one combined-regimen readout:\npatient,combined,response' };
    function setMode(m) {
      mode = m;
      seg.querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.m === m)));
      area.placeholder = place[m]; area.value = ''; out.textContent = '';
      go.textContent = m === 'series' ? 'Plan the plate' : 'Call patients';
      alt.textContent = '';
      const a = h('button', 'chip', m === 'series' ? 'Try a 7-point series' : 'Load 43 published patients');
      a.type = 'button';
      a.onclick = () => {
        if (m === 'series') { area.value = examples.series; run(); }
        else { area.value = ''; C.set({ patients: C.publishedPatients(), patientSource: 'published', reveal: false, patient: null }); out.textContent = `Loaded ${P.rows.length} published patients (${P.study.title}).`; }
      };
      alt.appendChild(a);
    }
    modes.forEach(([k, label]) => { const b = h('button', null, label); b.type = 'button'; b.dataset.m = k; b.onclick = () => setMode(k); seg.appendChild(b); });
    function run() {
      try {
        if (mode === 'series') {
          const s = C.parseSeries(area.value);
          if (!s.key) throw Error(`Mark exactly three concentrations with *; ${s.marked} are marked.`);
          const L = C.layouts(), hit = L.find(p => p.key === s.key), rank = L.indexOf(hit) + 1;
          C.set({ layout: s.key });
          const conc = s.pts.filter(p => p.on).map(p => p.c).join(', ');
          out.textContent = `Measuring ${conc} µM: this layout settled ${hit.rep} of ${hit.n} held-out designs (rank ${rank} of 35). At three replicate wells you run 9 of 21 and leave 12 to the forecast.`;
        } else {
          const rows = C.parsePatients(area.value);
          C.set({ patients: rows, patientSource: 'own', reveal: false, patient: null });
          const sens = rows.filter(r => r.call === 1).length, res = rows.filter(r => r.call === 0).length, ret = rows.length - sens - res;
          out.textContent = rows[0].mode === 'two'
            ? `${rows.length} patients called in this browser by the frozen two-readout rule: ${sens} report sensitive, ${res} report resistant, ${ret} retest.`
            : `${rows.length} patients called in this browser: ${sens} sensitive, ${res} resistant at the frozen cutoff ${P.cutoff}.`;
        }
      } catch (e) { out.textContent = e.message; out.setAttribute('role', 'alert'); }
    }
    go.type = 'button'; go.onclick = run;
    const file = h('label', 'btn quiet', 'Open CSV'), pickFile = h('input'); pickFile.type = 'file'; pickFile.accept = '.csv,.tsv,.txt,text/csv'; pickFile.hidden = true;
    file.appendChild(pickFile);
    pickFile.onchange = async () => { const f = pickFile.files[0]; if (!f) return; if (f.size > 4 * 1024 * 1024) { out.textContent = 'Use a file smaller than 4 MB.'; return; } area.value = await f.text(); run(); };
    const row = h('div', 'spread'); row.append(seg, alt);
    const act = h('div', 'row2'); act.append(go, file, out);
    el.textContent = ''; el.classList.add('stack1'); el.append(row, area, act);
    setMode(mode);
    return { setMode, run };
  };

  /* pickers */
  Charts.picker = function (el, opt) {
    opt = opt || {};
    const wrap = h('div', 'picker'), input = h('input', 'field'), list = h('ul', 'picker-list');
    input.type = 'search'; input.placeholder = opt.placeholder || 'Search held-out chemicals'; input.setAttribute('aria-label', 'Chemical');
    input.style.fontFamily = 'var(--sans)'; input.style.fontSize = 'var(--f2)'; input.style.lineHeight = 'var(--l2)';
    let hits = [], idx = 0;
    const show = () => {
      const q = input.value.trim().toLowerCase();
      hits = q ? O.chems.filter(c => c.name.toLowerCase().includes(q)).slice(0, 8) : [];
      list.textContent = '';
      hits.forEach((c, i) => {
        const li = h('li', i === idx ? 'on' : '', c.name);
        li.onpointerdown = e => { e.preventDefault(); pick(c); };
        list.appendChild(li);
      });
      list.hidden = !hits.length;
    };
    const pick = c => { C.set({ chem: c.i }); input.value = ''; hits = []; list.hidden = true; input.blur(); };
    input.oninput = () => { idx = 0; show(); };
    input.onkeydown = e => {
      if (e.key === 'ArrowDown') { idx = Math.min(hits.length - 1, idx + 1); show(); e.preventDefault(); }
      if (e.key === 'ArrowUp') { idx = Math.max(0, idx - 1); show(); e.preventDefault(); }
      if (e.key === 'Enter' && hits[idx]) pick(hits[idx]);
      if (e.key === 'Escape') { input.value = ''; show(); }
    };
    input.onblur = () => setTimeout(() => { list.hidden = true; }, 120);
    list.hidden = true;
    wrap.append(input, list);
    el.appendChild(wrap);
  };
  Charts.examples = function (el) {
    const roles = { 'largest gain over interpolation': 'largest gain', 'median gain over interpolation': 'median gain', 'largest loss': 'hardest case' };
    const chips = O.examples.map(e => {
      const b = h('button', 'chip'); b.type = 'button';
      b.append(document.createTextNode(e.chemical)); b.title = roles[e.role] || e.role;
      const c = C.chemBy.get(e.chemical); b.onclick = () => C.set({ chem: c.i }); b._c = c; return b;
    });
    el.classList.add('row'); el.style.flexWrap = 'wrap'; el.append(...chips);
    C.on(S => chips.forEach(b => b.setAttribute('aria-pressed', String(b._c.i === S.chem))));
  };
  Charts.designChips = function (el) {
    C.on((S, p) => {
      if (p && Object.keys(p).length && !('chem' in p || 'design' in p)) return;
      const c = O.chems[S.chem];
      el.textContent = ''; el.classList.add('row');
      c.d.forEach((d, k) => {
        const b = h('button', 'chip'); b.type = 'button'; b.setAttribute('aria-pressed', String(k === S.design));
        const dot = h('i'); dot.style.cssText = `width:8px;height:8px;border-radius:50%;background:${d.act ? 'var(--report)' : 'var(--retest)'}`;
        b.append(dot, document.createTextNode(String(k + 1)));
        b.title = `Design ${k + 1} measures ${d.m.map(l => C.uM(c.w.levels[l])).join(', ')} µM · ${d.act ? 'report call' : 'measure full series'}`;
        b.setAttribute('aria-label', `Design ${k + 1}`);
        b.onclick = () => C.set({ design: k });
        el.appendChild(b);
      });
    });
  };
})();

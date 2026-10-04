/* Claims: every sentence with a number is built here from window.OOC, so the three layouts say the same thing. */
(function () {
  'use strict';
  const C = window.Core, O = C.O, K = window.Charts;
  const dec = O.decision.anchorboost, v = O.versus.versus, iv = O.intervals;
  const ord = n => ['first', 'second', 'third', 'fourth', 'fifth', 'sixth', 'seventh'][n];
  const Copy = window.Copy = {};

  Copy.vision = 'Run three concentrations. Get the whole curve.';
  Copy.lead = `Tested blind on EPA’s neural network formation screen, the forecast settled the hit call for ${C.pct(dec.coverage)} of three-concentration designs.`;
  Copy.heroNumber = C.pct(dec.wells_saved_fraction);
  Copy.heroLabel = 'fewer wells than running every concentration of the series';
  Copy.hero = (lead, num) => { lead.textContent = Copy.lead; num.textContent = Copy.heroNumber; };

  Copy.curveKeys = [['dot', 'var(--measured)', 'Measured wells'], ['ring', 'var(--ink-3)', 'Held-out wells'], ['line', 'var(--forecast)', 'Forecast'],
    ['box', 'var(--band)', '90% interval'], ['dots', 'var(--compare)', 'Log-linear interpolation'], ['dash', 'var(--cutoff)', 'Cutoff']];
  Copy.curveClaim = S => {
    const c = O.chems[S.chem], d = c.d[S.design], n = c.w.levels.length;
    return d.act ? `${c.name}: hit call settled from 3 of ${n} concentrations` : `${c.name}: the forecast routes this design to the full series of ${n}`;
  };
  Copy.plateClaim = n => `${n.run} wells run, ${n.saved} left to the forecast across ${n.plates} plate${n.plates > 1 ? 's' : ''}`;
  Copy.layoutClaim = () => {
    const t = C.layouts()[0];
    return `Measuring the ${ord(t.pos[0])}, ${ord(t.pos[1])} and ${ord(t.pos[2])} concentrations settled ${t.rep} of ${t.n} held-out designs`;
  };
  Copy.tradeKeys = [['line', 'var(--forecast)', 'With forecast'], ['line', 'var(--measured)', 'Three measured, no forecast'], ['ring', 'var(--forecast)', 'Registered rule'], ['dash', 'var(--cutoff)', 'Budget']];
  Copy.tradeClaim = c => `At a 5% wrong-call budget the forecast leaves ${C.pct(c.a5.saved)} of wells unrun; three measured concentrations alone leave ${C.pct(c.m5.saved)}`;

  const pc = (x, d) => (Number.isFinite(x) ? C.pct(x, x === 1 ? 0 : d) : '—');
  Copy.patientClaim = S => {
    const s = C.patientStats(S.patients);
    if (S.patientSource === 'published') return `${s.correct} of ${s.n} patients called right from one organoid readout`;
    const reported = s.n - s.retest;
    if (S.reveal && s.known) return `${s.correct} of ${s.known} reported calls right` + (s.retest ? `; ${s.retest} sent to retest` : '');
    return `${reported} of your ${s.n} patients reported` + (s.retest ? `, ${s.retest} sent to retest` : '') + ', outcomes still closed';
  };
  Copy.bindPatients = (claim, el) => C.on((S, p) => {
    if (p && Object.keys(p).length && !('patients' in p || 'reveal' in p)) return;
    claim.textContent = Copy.patientClaim(S);
    const s = C.patientStats(S.patients), show = S.patientSource === 'published' || (S.reveal && s.known);
    el.textContent = '';
    el.style.display = show ? '' : 'none';
    if (!show) return;
    [[pc(s.sens, 1), `sensitivity, ${s.tp} of ${s.tp + s.fn} responders`], [pc(s.spec, 1), `specificity, ${s.tn} of ${s.tn + s.fp} non-responders`],
      [pc(s.ppv, 1), `PPV, ${s.tp} of ${s.tp + s.fp} sensitive calls`], [pc(s.npv, 1), `NPV, ${s.tn} of ${s.tn + s.fn} resistant calls`]]
      .forEach(([a, b]) => { const d = K.h('div', 'stat'); d.append(K.h('div', 'v', a), K.h('div', 'k', b)); el.appendChild(d); });
  });

  Copy.versusOptions = [['loglinear_interp', 'Interpolation'], ['analog_knn', 'Analogs'], ['hill_per_endpoint', 'Hill'], ['published_neural_process', 'Neural process']];
  Copy.versus = el => {
    el.textContent = '';
    Copy.versusOptions.forEach(([k, label]) => { const b = K.h('button', null, label); b.type = 'button'; b.onclick = () => C.set({ versus: k }); b.dataset.k = k; el.appendChild(b); });
    C.on(S => el.querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.k === S.versus))));
  };
  Copy.waterfallClaim = (k, x) => (k === 'published_neural_process'
    ? `${C.fix(-x.rel_change_pct, 1)}% lower error than the published neural process, paired interval clear of zero`
    : `Closer than ${K.VERSUS[k]} on ${C.pct(x.frac_chem_improved)} of chemicals`);

  Copy.calKeys = [['dot', 'var(--forecast)', 'Learned width'], ['ring', 'var(--compare)', 'Plain conformal'], ['dash', 'var(--cutoff)', 'Target']];
  Copy.calibrationClaim = () => {
    const r = K.calibrationRows, lo = Math.min(...r.map(x => x.learned)), hi = Math.max(...r.map(x => x.learned));
    return `Every recording day and every feature lands between ${C.pct(lo)} and ${C.pct(hi)} coverage`;
  };
  Copy.forestClaim = () => `Ahead of interpolation on all ${O.forest.rows.length} held-out folds, rat and human screens`;
  Copy.ablationClaim = () => `Take out the analog chemicals and error climbs ${C.fix(O.ablations.ablations.no_analog.minus_full.rel_change_pct, 1)}%; each input pulls weight`;
  Copy.agentClaim = () => { const k = O.agent.cohort; return `Hand it a paper and it rebuilds the clinical headline: ${k.audited_passes} of ${k.eligible} external studies, audited by hand`; };
  Copy.agentSource = () => `${O.agent.title} · ${O.agent.citation.split(';')[0]} · ${O.agent.license}`;
  /* methods footnote: four equal cells on the 12-column grid, one label and one line each; the full text is on hover */
  Copy.methodBlocks = [
    ['Data', 'Public EPA neural MEA screens and organoid cohorts',
      'US EPA network formation assay as packaged by NeuroChip Twin (public-domain data, MIT code); EPA acute MEA and human DNT screens (public domain); rectal-organoid cohort, Cell Reports Medicine 2025 (CC BY 4.0); agent replay paper, Mol Cancer 2024 (CC BY).'],
    ['Model', 'Boosted residuals on log-linear interpolation',
      'Gradient-boosted residuals on log-linear interpolation, one model per held-out fold, trained on every three-concentration layout of the training chemicals. A full retrain of every fold at one to four measured concentrations runs in 65 minutes in one Kaggle notebook session.'],
    ['Validation', 'Held-out folds, conformal 90% intervals',
      'Every chart scores chemicals and patients the model never trained on. Cross-conformal intervals use a learned width model; a call compares the largest DIV-mean response with a cutoff of 3 and is released by conformal risk control at α 0.10.'],
    ['Privacy', 'Runs in this browser; tables stay local',
      'Every number on this page is computed in this browser from the public release files, and pasted tables never leave your machine. Type: Newsreader, Source Sans 3, Source Code Pro (SIL OFL). Charts: D3 (ISC).']
  ];
  Copy.methods = el => {
    el.textContent = '';
    el.classList.add('methods');
    Copy.methodBlocks.forEach(([k, short, full]) => {
      const d = K.h('div', 'cell'); d.tabIndex = 0;
      d.append(K.h('h4', null, k), K.h('p', null, short));
      const show = ev => C.tip(ev.clientX !== undefined ? ev : { clientX: d.getBoundingClientRect().left, clientY: d.getBoundingClientRect().top - 8 }, k, [full]);
      d.addEventListener('pointermove', show); d.addEventListener('focus', show);
      d.addEventListener('pointerleave', C.untip); d.addEventListener('blur', C.untip);
      el.appendChild(d);
    });
  };
  /* hero: the record sits in the hover of the figure, one line */
  Copy.heroRecord = `Tested blind on EPA’s network formation screen: hit call settled for ${C.pct(dec.coverage)} of three-concentration designs`;
  Copy.heroTip = els => els.forEach(el => {
    el.tabIndex = 0;
    const show = ev => C.tip(ev.clientX !== undefined ? ev : { clientX: el.getBoundingClientRect().left, clientY: el.getBoundingClientRect().bottom + 8 }, Copy.heroRecord, [], { line: true });
    el.addEventListener('pointermove', show); el.addEventListener('focus', show);
    el.addEventListener('pointerleave', C.untip); el.addEventListener('blur', C.untip);
  });
})();

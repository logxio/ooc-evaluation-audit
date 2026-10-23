/* Browser claims read the release packet; method panels also link the checked public files. */
(function () {
  'use strict';
  const C = window.Core, O = C.O, K = window.Charts;
  const ord = n => ['first', 'second', 'third', 'fourth', 'fifth', 'sixth', 'seventh'][n];
  const Copy = window.Copy = {};

  /* headline numbers come from the final report packet: the closed-loop replay of 965 designs and the 32-configuration scoreboard */
  const F = O.final1009, cl = F.screening.closedLoop, diff = F.screening.pairedContrasts.model_disagreement__minus__nested_measured_only, bt = F.baselines.stackTotals;
  const mo = { reports: cl.reports - diff.reports_total_difference.estimate, wrong: cl.wrong_reports - diff.wrong_reports_total_difference.estimate, wells: cl.wells_used - diff.wells_used_total_difference.estimate };
  Copy.vision = 'Run three concentrations. Get the whole curve.';
  Copy.heroNumber = F.screening.display.savingVsFull;
  /* top bar: three readings, value then what it counts */
  Copy.bar = [
    [Copy.heroNumber, `fewer exposure wells (${C.int(cl.wells_used)} / ${C.int(cl.wells_full)})`],
    [`${bt.win}W ${bt.tie}T ${bt.loss}L`, `vs ${F.baselines.opponents.length} published models`],
    [String(O.totalPatients), 'published patient assays']
  ];
  /* replay of the 965 designs: the closed loop against three measured concentrations alone, every share with its denominator */
  Copy.replay = [
    [C.pct(cl.reports / cl.designs), `${cl.reports} of ${cl.designs} designs reported: ${cl.stage1_reports} from three concentrations, ${cl.stage2_reports} after one more`],
    [C.pct(mo.reports / cl.designs), `${mo.reports} of ${cl.designs} from three measured concentrations alone`],
    [`${C.pct(cl.wrong_reports / cl.reports)} vs ${C.pct(mo.wrong / mo.reports)}`, `wrong among reported: ${cl.wrong_reports} of ${cl.reports} vs ${mo.wrong} of ${mo.reports}`],
    [C.pct(1 - cl.wells_used / mo.wells), `fewer wells than three measured alone, ${C.int(cl.wells_used)} vs ${C.int(mo.wells)}`]
  ];
  Copy.replayNote = `Closed-loop replay of ${cl.designs} three-concentration designs in ${cl.identity_groups} chemical identity groups of EPA’s network formation screen; training, calibration and test identities are kept apart. Wells are counted per design.`;

  Copy.curveKeys = [['dot', 'var(--measured)', 'Measured wells'], ['ring', 'var(--ink-3)', 'Held-out wells'], ['line', 'var(--forecast)', 'Forecast'],
    ['box', 'var(--band)', '90% interval'], ['dots', 'var(--compare)', 'Log-linear interpolation'], ['dash', 'var(--cutoff)', 'Cutoff']];
  Copy.curveClaim = S => {
    const c = O.chems[S.chem], d = c.d[S.design], n = c.w.levels.length;
    return d.act ? `${c.name}: hit call settled from 3 of ${n} concentrations` : `${c.name}: the forecast routes this design to the full series of ${n}`;
  };
  Copy.plateClaim = n => `${n.run} wells run, ${n.saved} left to the forecast across ${n.plates} plate${n.plates > 1 ? 's' : ''}`;
  Copy.layoutClaim = () => {
    const t = C.layouts()[0];
    return `Measure the ${ord(t.pos[0])}, ${ord(t.pos[1])} and ${ord(t.pos[2])}: ${t.rep} of ${t.n} designs settled`;
  };
  Copy.tradeKeys = [['line', 'var(--forecast)', 'With forecast'], ['line', 'var(--measured)', 'Three measured, no forecast'], ['ring', 'var(--forecast)', 'Release rule fitted on other folds'], ['dash', 'var(--cutoff)', '5% wrong calls']];
  Copy.tradeClaim = c => `At 5% wrong calls the forecast leaves ${C.pct(c.a5.saved)} of wells unrun, three measured alone ${C.pct(c.m5.saved)}`;
  Copy.tradeNote = o => `Retrospective best cut at this retest cost: report ${o.k} of ${C.designsAll.length} designs, leave ${C.pct(o.saved)} of wells unrun, ${C.fix(o.wrong * 100, 1)} wrong calls per 100 designs. Cuts along the curves are read from the replay outcomes; the open circles are rules fitted on other folds.`;

  const pc = (x, d) => (Number.isFinite(x) ? C.pct(x, x === 1 ? 0 : d) : 'n/a');
  /* two rules, named where they act: the combined-regimen cutoff calls the published cohort, the two-readout rule calls pasted readout1/readout2 tables */
  Copy.patientRule = rows => (rows.length && rows[0].mode === 'two' ? 'the two-readout rule' : `the combined-regimen cutoff ${O.patients.cutoff}`);
  Copy.patientClaim = S => {
    const s = C.patientStats(S.patients);
    if (S.patientSource === 'published') return `${window.OOCFinal1009.SHORT_LABELS['rectal-fixed-43']}: ${s.correct} of ${s.n} called right by one combined-regimen cutoff`;
    const reported = s.n - s.retest;
    if (S.patientSource === 'final1009' && S.patientCohort) {
      const name = window.OOCFinal1009.SHORT_LABELS[S.patientCohort.id], ref = S.patients.filter(r => r.reference).length, retest = s.retest - ref;
      if (S.patientCohort.assayOnly) return `${name}: ${S.patients.length} paired gemcitabine and cisplatin AUC records, no clinical outcomes joined`;
      if (ref === s.n) return `${name}: frozen assays that set Tan’s reference medians`;
      return `${name}: ` + (S.reveal && s.known ? `${s.correct} of ${s.known} reported calls right, ${retest} to retest` : `${reported} reported, ${retest} to retest, outcomes still closed`);
    }
    if (S.reveal && s.known) return `${s.correct} of ${s.known} reported calls right` + (s.retest ? `; ${s.retest} sent to retest` : '');
    return `${reported} of your ${s.n} patients reported by ${Copy.patientRule(S.patients)}` + (s.retest ? `, ${s.retest} sent to retest` : '') + ', outcomes still closed';
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
  const np = C.strong.screens[0].total;
  Copy.waterfallClaim = (k, x) => (k === 'published_neural_process'
    ? `Closer than the published neural process on ${np.win} of ${np.n} chemicals, ${C.fix(np.rel, 1)}% lower error`
    : `Closer than ${K.VERSUS[k]} on ${C.pct(x.frac_chem_improved)} of chemicals`);

  Copy.calKeys = [['dot', 'var(--forecast)', 'Learned width'], ['ring', 'var(--compare)', 'Plain conformal'], ['dash', 'var(--cutoff)', 'Target']];
  Copy.calibrationClaim = () => {
    const r = K.calibrationRows, lo = Math.min(...r.map(x => x.learned)), hi = Math.max(...r.map(x => x.learned));
    return `90% intervals cover ${C.fix(lo * 100, 1)} to ${C.pct(hi)} on every day and feature`;
  };
  /* evidence links sit beside the figure they back: the public file in the repository */
  Copy.repo = 'https://github.com/logxio/ooc-evaluation-audit/blob/main/';
  Copy.links = (el, pairs) => {
    el.textContent = ''; el.classList.add('row2');
    pairs.forEach(([label, href]) => { const a = K.h('a', null, label); a.href = href; a.target = '_blank'; a.rel = 'noopener'; el.appendChild(a); });
  };
  Copy.source = (el, path) => Copy.links(el, [['Source', Copy.repo + path]]);
  const SHORT = { nfa: 'chronic rat', acute: 'acute rat', human: 'human' };
  Copy.forestClaim = () => {
    const P = K.forestPanels(), folds = P[0].groups.flatMap(g => g.folds), N = P[1].groups;
    return `Lower error than interpolation in ${folds.filter(f => f.v > 0).length} of ${folds.length} folds and the neural process on ${N.filter(g => g.total.v > 0).length} of ${N.length} screens`;
  };
  Copy.forestNote = () => {
    const ext = C.strong.screens.filter(s => s.key !== 'nfa'), wide = ext.filter(s => s.total.lo2 < 0).map(s => SHORT[s.key]);
    const open = K.forestPanels()[1].groups.filter(g => g.total.lo < 0).map(g => SHORT[g.k]);
    return (open.length ? `The ${open.join(' and ')} 95% interval includes 0. ` : '') +
      `Same five three-concentration contexts per chemical for both models; the neural process keeps its published configuration, refitted per screen with three seeds. ` +
      (C.strong.joint ? 'Both external screens clear 0 at 97.5%.' : `At 97.5% the ${wide.join(' and ')} intervals include 0, so the two external screens are read one by one, not as a joint win.`);
  };
  const CHIP_STATE = rows => (rows.every(r => r.lo < 0 && r.hi > 0) ? 'on par' : rows.every(r => r.hi < 0) ? 'behind' : rows.every(r => r.lo > 0) ? 'ahead' : 'mixed');
  Copy.chipsClaim = () => {
    const R = C.strong.chips, sets = [...new Set(R.map(r => r.dataset))].map(d => ({ d, rows: R.filter(r => r.dataset === d) }));
    return 'Liver chips vs interpolation: ' + sets.map(s => `${CHIP_STATE(s.rows)} on ${K.CHIP[s.d][0]}`).join(', ');
  };
  Copy.chipsNote = () => {
    const leaf = O.model.params.min_samples_leaf, small = C.strong.chips.filter(r => r.rows.every(n => n < leaf));
    return small.map(r => `${r.rows.join(' to ')} ${K.CHIP_END[r.endpoint]}`).join(' and ') + ` training rows per fold in ${K.CHIP[small[0].dataset][0]} sit below the frozen minimum leaf of ${leaf}: the trees cannot split, so that forecast is interpolation plus one constant. ` +
      'Differences keep each endpoint’s published units; drugs are the resampling unit.';
  };
  Copy.ablationClaim = () => `Training on every layout lowers error by ${C.fix(K.ablationRows()[0].v, 3)} at a matched budget`;
  Copy.ablationNote = () => {
    const rest = K.ablationRows().slice(1), hold = rest.filter(r => r.lo > 0), open = rest.filter(r => r.lo <= 0);
    const cap = t => t.charAt(0).toUpperCase() + t.slice(1);
    return cap(hold.map(r => `${r.short} add ${C.fix(r.v, 3)}`).concat(open.length ? [`${open.map(r => r.short).join(' and ')} include 0`] : []).join('; ')) +
      '. The layout comparison is matched on training rows times boosting iterations.';
  };
  Copy.agentClaim = () => { const k = O.agent.cohort; return `Hand it a paper and it rebuilds the clinical headline: ${k.audited_passes} of ${k.eligible} studies`; };
  Copy.agentSource = () => `${O.agent.title} · ${O.agent.citation.split(';')[0]} · ${O.agent.license}`;
  const hoverTip = K.hoverTip;
  /* canvas chain: four numbered steps, each with the reading it proves */
  const ag = O.agent.cohort, outputs = O.features.length * O.divs.length;
  Copy.chain = [
    ['curve', 'Curve', String(outputs), 'outputs', `${outputs} day-by-feature outputs forecast at once from three concentrations`],
    ['plate', 'Plate', Copy.heroNumber, 'fewer wells', `${C.int(cl.wells_used)} of ${C.int(cl.wells_full)} exposure wells across ${C.int(cl.designs)} designs`],
    ['evidence', 'Evidence', `${bt.win}W ${bt.tie}T ${bt.loss}L`, '', `${bt.win} wins, ${bt.tie} tie, ${bt.loss} losses against ${F.baselines.opponents.length} published configurations at one to four concentrations`],
    ['model', 'Model', `${ag.audited_passes}/${ag.eligible}`, 'papers', `The paper agent rebuilds ${ag.audited_passes} of ${ag.eligible} external headlines offline`]
  ];
  const WORDS = ['one', 'two', 'three', 'four'];
  Copy.scoreClaim = k => {
    const c = F.baselines.countsByK.find(x => x.k === k), mae = F.baselines.team.k[k].toFixed(4), at = `${WORDS[k - 1]} measured concentration${k > 1 ? 's' : ''}`;
    return c.win === c.opponents ? `Stack ${mae} beats all ${c.opponents} published configurations at ${at}`
      : `Stack ${mae} at ${at}: ${c.win} wins, ${c.tie} tie${c.tie === 1 ? '' : 's'}, ${c.loss} losses of ${c.opponents}`;
  };
  Copy.scoreKTip = k => { const c = F.baselines.countsByK.find(x => x.k === k); return [`${WORDS[k - 1][0].toUpperCase() + WORDS[k - 1].slice(1)} measured concentration${k > 1 ? 's' : ''}`, [`${c.opponents} published configurations: ${c.win} wins, ${c.tie} tie${c.tie === 1 ? '' : 's'}, ${c.loss} losses`]]; };

  /* reproduce dock: four receipts; every command, ledger line and link is one line, its explanation sits in the tip */
  const REPO = 'https://github.com/logxio/ooc-evaluation-audit', blob = p => `${REPO}/blob/main/${p}`, tree = p => `${REPO}/tree/main/${p}`;
  const R = F.receipts, okN = R.commands.filter(c => c[1] === 0).length, peak = Math.max(...R.commands.map(c => c[3])), longest = Math.max(...R.commands.map(c => c[2]));
  const verifySec = R.commands.find(c => /paper_final_verify/.test(c[0]))[2], k3 = F.baselines.countsByK.find(c => c.k === 3), M = O.model;
  const lockAt = R.lock.created.replace('T', ' ').replace(/:\d\d\+00:00$/, ' UTC');
  const CLONE = [`git clone ${REPO} && cd ooc-evaluation-audit`, '', 'Fresh clone; every command below runs from the repository root'];
  const PIP = ['python -m pip install -r requirements.txt', '', 'Pinned dependencies for the forecast CLI'];
  const PIPF = ['python -m pip install -r requirements-final.txt', '', 'Pinned dependencies for the paper checks'];
  Copy.dockKeys = ['data', 'model', 'validation', 'privacy'];
  /* the receipt that backs each canvas view; the dock follows the canvas */
  Copy.pageDock = { curve: 'data', plate: 'validation', evidence: 'validation', model: 'model', patient: 'validation', yours: 'privacy' };
  Copy.receipts = {
    data: {
      label: 'Data', reading: '13 studies · 12 Cell/Nature',
      tip: ['13 published studies, 12 in Cell or Nature portfolio journals', ['EPA neural screens, liver chips and patient organoids, all public', 'Each study page names its journal, DOI, license, observation unit and download']],
      claim: 'EPA screens download from source and pass SHA-256 before any fit',
      cmds: [CLONE, PIP,
        ['python three_point.py --example epa_dnt', '9.86 s', 'EPA human neural-cell screen: download, SHA-256 check, plate table'],
        ['python chip_forecast.py', '~4 min per fold', 'Network formation screen: two pinned files, SHA-256 check, published baseline errors reproduced, one model per held-out fold on free Kaggle CPU']],
      ledger: [
        ['Locked input', 'epa_dnt_three_point.csv', R.lock.input[1]],
        ['Baseline match', 'log-linear errors within 0.0001, 243 chemicals', null, ['Published log-linear interpolation errors reproduced within 0.0001 for all 243 chemicals at every measured-concentration count']],
        ['Scope', `${O.chems.length} held-out chemicals · ${outputs} outputs · ${O.totalPatients} patients`]],
      pills: [['EPA network formation', 'https://github.com/Agnuxo1/neurochip-twin', 'public domain'], ['EPA acute MEA', 'https://doi.org/10.23719/1504294', 'public domain'],
        ['EPA human neural DNT', 'https://doi.org/10.23719/1407642', 'public domain'], ['Ewart Liver-Chip', 'https://doi.org/10.1038/s43856-022-00209-1', 'CC BY 4.0'],
        ['Yuan liver chip', 'https://doi.org/10.1038/s42003-025-08928-6', 'error statistics'], ['13 study audits', 'audits/index.html', '12 Cell/Nature']],
      jump: ['Open Curve ↑', 'curve']
    },
    model: {
      label: 'Model', reading: 'Boosted residuals',
      tip: ['Gradient-boosted residuals on log-linear interpolation', ['One model per held-out fold, trained on every three-concentration layout of the training chemicals']],
      claim: 'One frozen model per held-out fold, trained on every layout',
      cmds: [CLONE, PIP,
        ['python three_point.py my_plates.csv', '', 'Forecast your own unfinished plate table with the frozen model; writes a SHA-256 lock'],
        PIPF,
        ['python benchmarks/stack/reproduce.py', '0.20 to 0.75 s', 'Stack error at one to four concentrations from saved member predictions'],
        ['python -m contract_agent.replay_agent', 'standard library', `Replay the paper agent offline: ${ag.audited_passes} of ${ag.eligible} headlines rebuilt`]],
      ledger: [
        ['Frozen protocol', 'commit 2b4c20e, before folds 1 to 4 were scored'],
        ['Training', `${C.int(M.designs_enumerated.fold1)} layouts · ${(M.timing.k3_fold1.training_rows / 1e6).toFixed(2)} M rows · ${(M.timing.k3_fold1.seconds / 60).toFixed(1)} min per fold`, null, ['Fold 1 at three measured concentrations, CPU only']],
        ['Paper agent', `${ag.audited_passes} of ${ag.eligible} external headlines rebuilt`, null, [`${ag.correct_refusals} of ${ag.controls} no-headline controls declined`]]],
      pills: [['three_point.py', blob('three_point.py')], ['benchmarks/stack', tree('benchmarks/stack')], ['contract_agent', tree('contract_agent')],
        ['Frozen protocol', `${REPO}/blob/2b4c20e/chip_forecast_protocol.json`], ['Fold 0 weights', blob('results/nested/fold0/outer_model.joblib')]],
      jump: ['Open Model ↑', 'model']
    },
    validation: {
      label: 'Validation', reading: '5-fold blind lock',
      tip: ['Every chart scores chemicals and patients outside their own model’s training', ['Each test fold takes its hit cutoff from two other folds and its release margin from two more, by conformal risk control at α 0.10', 'Forecasts lock by SHA-256 before outcomes are read']],
      claim: 'Forecasts lock by SHA-256 before the plates are read',
      cmds: [CLONE, PIP,
        ['python three_point.py --example epa_dnt', '9.86 s', 'Download the EPA human neural screen and check its SHA-256'],
        ['python three_point.py epa_dnt/epa_dnt_three_point.csv --out epa_dnt/forecast --jobs 9', '26.05 s', 'Lock forecasts for 107 unfinished series; lock.json fixes the SHA-256 of input, output, models, protocol and code'],
        ['python three_point.py epa_dnt/epa_dnt_human_neural.csv --reconcile epa_dnt/forecast', '1.02 s', '2,318 of 2,520 hidden wells (92.0%) fall inside the 90% intervals'],
        PIPF,
        ['python paper_final_baselines.py', '0.54 s', `Rebuild the ${F.baselines.opponents.length}-model scoreboard and every win, tie and loss from per-chemical errors`],
        ['python paper_final_verify.py verify', `${verifySec.toFixed(2)} s`, 'Verify input hashes and 9,168 indexed values, 3,423 of them intervals']],
      ledger: [
        ['Blind lock', `lock.json · ${lockAt}`],
        ['Locked output', 'forecast.csv', R.lock.output[1]],
        ['Locked models', `${R.lock.models} endpoint models in the same lock`],
        ['Clean snapshot', `${okN} of ${R.commands.length} commands exit 0 · peak ${(peak / 1e6).toFixed(1)} MB`, null, [`Longest ${longest.toFixed(2)} s`, `Python ${R.python}, NumPy ${R.numpy}`]]],
      pills: [['lock.json', blob('three_point_example/forecast/lock.json')], ['reconcile.md', blob('three_point_example/forecast/reconcile.md')],
        ['scoreboard.csv', blob('results/final/baselines/scoreboard.csv')], ['verification.json', blob('results/final/verification.json')], ['numbers.json', blob('results/final/numbers.json')]],
      jump: ['Open Evidence ↑', 'evidence']
    },
    privacy: {
      label: 'Privacy', reading: '100% local',
      tip: ['Every number here is computed in this browser from the public release files', ['Pasted tables never leave your machine']],
      claim: 'Every number computes in your browser; pasted tables stay here',
      cmds: [CLONE,
        ["grep -lE 'fetch\\(|XMLHttp[R]equest|send[B]eacon' workbench/runtime.js workbench/assets/*.js", 'instant', 'Prints nothing: the workbench code makes no network call'],
        ['cd workbench && python -m http.server 8000', '', 'Run the same workbench offline at localhost:8000']],
      ledger: [
        ['Data path', 'plain scripts from this site; pasted tables stay in memory'],
        ['Code', 'MIT licence'],
        ['Type and charts', 'SIL OFL 1.1 fonts · D3 ISC', null, ['Newsreader, Source Sans 3, Source Code Pro', 'D3 (ISC) and d3-ease (BSD)']]],
      pills: [['LICENSE', blob('LICENSE'), 'MIT'], ['workbench source', tree('workbench')], ['D3 licence', 'vendor/d3.LICENSE.txt', 'ISC'], ['result.json', 'result.json', 'frozen patient rule', true]],
      jump: ['Paste your table ↑', 'yours']
    }
  };
  const copyText = async text => {
    try { await navigator.clipboard.writeText(text); return true; } catch (_) {
      const back = document.activeElement, ta = document.createElement('textarea'); ta.value = text;
      ta.style.cssText = 'position:fixed;left:-9999px;opacity:0'; document.body.appendChild(ta); ta.select();
      let ok = false; try { ok = document.execCommand('copy'); } catch (__) { ok = false; }
      ta.remove(); if (back && back.focus) back.focus({ preventScroll: true });
      return ok;
    }
  };
  /* a copy control reports what happened: Copied, or that the text needs selecting by hand */
  const copyButton = (cls, label, text) => {
    const b = K.h('button', cls, label); b.type = 'button';
    b.onclick = async ev => {
      ev.stopPropagation();
      const ok = await copyText(text);
      b.classList.remove('ok', 'bad'); b.classList.add(ok ? 'ok' : 'bad'); b.textContent = ok ? 'Copied' : 'Select to copy';
      clearTimeout(b._t); b._t = setTimeout(() => { b.classList.remove('ok', 'bad'); b.textContent = label; }, 1600);
    };
    return b;
  };
  const hashChip = full => {
    const b = K.h('button', 'hash', full.slice(0, 8) + '…' + full.slice(-4)); b.type = 'button';
    hoverTip(b, 'SHA-256', [full, 'Click to copy']);
    b.onclick = async () => { const ok = await copyText(full); b.textContent = ok ? 'copied' : 'select to copy'; setTimeout(() => { b.textContent = full.slice(0, 8) + '…' + full.slice(-4); }, 1400); };
    return b;
  };
  const local = href => !/^https?:/.test(href);
  Copy.dock = (el, actions = {}) => {
    const S = { key: '', open: false };
    el.textContent = '';
    const sheet = K.h('div', 'dsheet'), bar = K.h('div', 'dbar');
    sheet.id = 'dock-sheet';
    const ttl = K.h('button', 'dttl'); ttl.type = 'button';
    ttl.append('Reproduce', K.h('kbd', null, 'R'));
    hoverTip(ttl, 'Reproduce every number', ['R opens and closes, Esc closes', 'The receipt follows the canvas view']);
    const tabs = K.h('div', 'dtabs'); tabs.setAttribute('role', 'tablist'); tabs.setAttribute('aria-label', 'Reproduce');
    const buttons = Copy.dockKeys.map(k => {
      const r = Copy.receipts[k], b = K.h('button'); b.type = 'button'; b.dataset.k = k;
      b.setAttribute('role', 'tab'); b.setAttribute('aria-controls', sheet.id);
      b.append(K.h('b', null, r.label), K.h('span', null, r.reading));
      hoverTip(b, r.tip[0], r.tip[1]);
      b.onclick = () => set(k, !(S.open && S.key === k));
      tabs.appendChild(b); return b;
    });
    const stat = K.h('div', 'dstat');
    [[`${okN}/${R.commands.length}`, 'checks exit 0', 'Clean-snapshot run of the paper checks', [`${okN} of ${R.commands.length} commands exit 0`, `Python ${R.python}, NumPy ${R.numpy}`]],
      [`${k3.win}/${k3.opponents}`, 'at k=3', `${k3.win} of ${k3.opponents} published configurations beaten`, ['Three measured concentrations, paired identity-cluster bootstrap']],
      [R.lock.created.slice(0, 10), '', 'Blind lock', [`lock.json written ${lockAt}`, 'before the finished series was read'], 'lock ']]
      .forEach(([v, k, t, rows, pre]) => { const s = K.h('span'); s.tabIndex = 0; s.append(pre || '', K.h('b', null, v), k ? ' ' + k : ''); stat.appendChild(hoverTip(s, t, rows)); });
    const chev = K.h('button', 'chev', '⌃'); chev.type = 'button'; chev.onclick = () => set(S.key, !S.open);
    bar.append(ttl, tabs, stat, chev);
    ttl.onclick = () => set(S.key, !S.open);
    el.append(sheet, bar);
    function drawer() {
      const r = Copy.receipts[S.key];
      sheet.textContent = '';
      const term = K.h('div', 'term'), th = K.h('div', 'term-h');
      th.append(K.h('span', null, `${r.label} · from a fresh clone, repository root`), copyButton('cpall', 'Copy all', r.cmds.map(c => c[0]).join('\n')));
      const ol = K.h('ol');
      r.cmds.forEach(([code, time, tip]) => {
        const li = K.h('li'), c = K.h('code', null, code);
        c.tabIndex = 0; hoverTip(c, tip, () => (c.scrollWidth > c.clientWidth + 1 ? [code] : []).concat(time ? [`Recorded ${time}`] : []));
        li.append(K.h('i', null, '$'), c, K.h('span', 't', time), copyButton('cp', 'Copy', code));
        ol.appendChild(li);
      });
      term.append(th, ol);
      const top = K.h('div', 'dtop'), claim = K.h('p', 'dclaim', r.claim);
      const ledger = K.h('div', 'ledger');
      r.ledger.forEach(([k, v, hash, tip]) => {
        const row = K.h('div', 'lg'), text = K.h('span', null, v);
        row.append(K.h('i', null, '✓'), K.h('b', null, k), text);
        if (hash) row.appendChild(hashChip(hash));
        if (tip) { text.tabIndex = 0; hoverTip(text, `${k}: ${v}`, tip); }
        ledger.appendChild(row);
      });
      const pills = K.h('div', 'pills');
      r.pills.forEach(([label, href, small, download]) => {
        const a = K.h('a', 'pill' + (download ? ' dl' : ''), label); a.href = href;
        if (download) a.download = ''; else if (!local(href)) { a.target = '_blank'; a.rel = 'noopener'; }
        if (small) a.appendChild(K.h('small', null, small));
        pills.appendChild(a);
      });
      const jump = K.h('button', 'jump', r.jump[0]); jump.type = 'button';
      jump.onclick = () => { set(S.key, false); if (actions.open) actions.open(r.jump[1]); };
      /* claim and jump on top, commands beside the ledger, links along the bottom: every line stays one line */
      top.append(claim, jump);
      sheet.append(top, term, ledger, pills);
    }
    function set(key, open) {
      if (key !== S.key) { S.key = key; drawer(); }
      S.open = open;
      el.dataset.open = String(open);
      buttons.forEach(b => { b.setAttribute('aria-selected', String(b.dataset.k === key)); b.setAttribute('aria-expanded', String(open && b.dataset.k === key)); });
      sheet.inert = !open; sheet.setAttribute('aria-hidden', String(!open));
      chev.setAttribute('aria-label', open ? 'Close the reproduce drawer' : 'Open the reproduce drawer');
    }
    set('data', false);
    return {
      follow: page => { const k = Copy.pageDock[page]; if (k && k !== S.key) set(k, S.open); },
      toggle: () => set(S.key, !S.open),
      close: () => set(S.key, false),
      isOpen: () => S.open
    };
  };
  /* hero: what 56.8% counts sits in the hover of the figure, one line per fact */
  Copy.heroRecord = [`Closed-loop replay of ${cl.designs} three-concentration designs, EPA’s network formation screen`, [
    `${C.int(cl.wells_used)} vs ${C.int(cl.wells_full)} exposure wells across ${cl.designs} designs: ${Copy.heroNumber} fewer than every concentration`,
    `${cl.reports} reports, ${cl.wrong_reports} wrong; ${cl.reports - mo.reports} more reports from ${C.pct(1 - cl.wells_used / mo.wells)} fewer wells than three measured concentrations alone`,
    `${bt.win} wins, ${bt.tie} tie, ${bt.loss} losses against ${F.baselines.opponents.length} published predictor configurations at one to four concentrations`]];
  Copy.heroTip = els => els.forEach(el => { el.tabIndex = 0; hoverTip(el, Copy.heroRecord[0], Copy.heroRecord[1], { line: true }); });
})();

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
    [String(O.totalPatients), 'clinical organoid assays']
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

  const pc = (x, d) => (Number.isFinite(x) ? C.pct(x, x === 1 ? 0 : d) : '—');
  /* two rules, named where they act: the combined-regimen cutoff calls the published cohort, the two-readout rule calls pasted readout1/readout2 tables */
  Copy.patientRule = rows => (rows.length && rows[0].mode === 'two' ? 'the two-readout rule' : `the combined-regimen cutoff ${O.patients.cutoff}`);
  Copy.patientClaim = S => {
    const s = C.patientStats(S.patients);
    if (S.patientSource === 'published') return `${window.OOCFinal1009.SHORT_LABELS['rectal-fixed-43']}: ${s.correct} of ${s.n} called right by one combined-regimen cutoff`;
    const reported = s.n - s.retest;
    if (S.patientSource === 'final1009' && S.patientCohort) {
      const name = window.OOCFinal1009.SHORT_LABELS[S.patientCohort.id], ref = S.patients.filter(r => r.reference).length, retest = s.retest - ref;
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
    return `90% intervals cover ${C.fix(lo * 100, 1)}–${C.pct(hi)} on every day and feature`;
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
    return small.map(r => `${r.rows.join('–')} ${K.CHIP_END[r.endpoint]}`).join(' and ') + ` training rows per fold in ${K.CHIP[small[0].dataset][0]} sit below the frozen minimum leaf of ${leaf}: the trees cannot split, so that forecast is interpolation plus one constant. ` +
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
  /* Method details open from four keyboard accessible tabs. */
  Copy.methodBlocks = [
    ['Data', 'Public EPA neural screens, liver chips, organoid cohorts',
      'US EPA network formation assay as packaged by NeuroChip Twin (public-domain data, MIT code); EPA acute MEA and human DNT screens (public domain); perfused liver chips of Ewart 2022, Communications Medicine (CC BY 4.0) and Yuan 2025, Communications Biology (error statistics only; source under CC BY-NC-ND 4.0 at its DOI); rectal-organoid cohort, Cell Reports Medicine 2025 (CC BY 4.0); agent replay paper, Mol Cancer 2024 (CC BY).'],
    ['Model', 'Boosted residuals on log-linear interpolation',
      'Gradient-boosted residuals on log-linear interpolation, one model per held-out fold, trained on every three-concentration layout of the training chemicals. A full retrain of every fold at one to four measured concentrations runs in 65 minutes in one Kaggle notebook session.'],
    ['Validation', 'Held-out folds, rules fitted on other folds',
      'Every chart scores chemicals and patients outside the training of their own model. Each test fold’s hit-call rule takes its cutoff from two other folds and its release margin from two more by conformal risk control at α 0.10; fold 0 was the development fold. Cross-conformal 90% intervals use a learned width model. Paired intervals resample chemicals, never wells or designs.'],
    ['Privacy', 'Runs in this browser; tables stay local',
      'Every number on this page is computed in this browser from the public release files, and pasted tables never leave your machine. Type: Newsreader, Source Sans 3, Source Code Pro (SIL OFL). Charts: D3 (ISC).']
  ];
  const methodLink = (label, href, local = false) => {
    const a = K.h('a', null, label);
    a.href = href;
    if (!local) { a.target = '_blank'; a.rel = 'noopener'; }
    if (local && label.startsWith('Download')) a.download = '';
    return a;
  };
  const methodSection = (title, note) => {
    const section = K.h('section', 'method-section');
    section.append(K.h('h5', null, title), K.h('p', null, note));
    return section;
  };
  const methodLinks = pairs => {
    const row = K.h('div', 'method-links');
    pairs.forEach(([label, path, local]) => row.appendChild(methodLink(label, local ? path : Copy.repo + path, local)));
    return row;
  };
  const methodTable = (headers, rows) => {
    const wrap = K.h('div', 'method-table-wrap'), table = K.h('table', 'method-table');
    const head = K.h('thead'), headerRow = K.h('tr');
    headers.forEach(label => headerRow.appendChild(K.h('th', null, label)));
    head.appendChild(headerRow);
    const body = K.h('tbody');
    rows.forEach(cells => {
      const tr = K.h('tr');
      cells.forEach(cell => {
        const td = K.h('td');
        if (Array.isArray(cell)) td.appendChild(methodLink(cell[0], cell[1], !!cell[2]));
        else td.textContent = cell;
        tr.appendChild(td);
      });
      body.appendChild(tr);
    });
    table.append(head, body); wrap.appendChild(table);
    return wrap;
  };
  const methodCode = (title, code) => {
    const block = K.h('div', 'method-code'), top = K.h('div', 'method-code-head');
    const button = K.h('button', 'method-copy', 'Copy'); button.type = 'button';
    button.setAttribute('aria-label', `Copy ${title} commands`);
    button.onclick = async () => {
      try {
        const fallback = () => {
          const input = document.createElement('textarea'); input.value = code;
          input.style.position = 'fixed'; input.style.opacity = '0';
          document.body.appendChild(input); input.select();
          const copied = document.execCommand('copy'); input.remove();
          if (!copied) throw new Error('Copy unavailable');
        };
        if (navigator.clipboard && navigator.clipboard.writeText) {
          try { await navigator.clipboard.writeText(code); }
          catch (_) { fallback(); }
        } else fallback();
        button.textContent = 'Copied';
        setTimeout(() => { if (button.isConnected) button.textContent = 'Copy'; }, 1800);
      } catch (_) { button.textContent = 'Select commands'; }
    };
    top.append(K.h('span', null, title), button);
    const pre = K.h('pre'), printed = K.h('code', null, code);
    pre.appendChild(printed); block.append(top, pre);
    return block;
  };
  const methodAction = (label, callback) => {
    const button = K.h('button', 'method-action', label);
    button.type = 'button'; button.onclick = callback;
    return button;
  };
  Copy.methods = (el, actions = {}) => {
    el.textContent = '';
    el.classList.add('methods');
    const row = K.h('div', 'method-tabs');
    row.setAttribute('role', 'tablist');
    row.setAttribute('aria-label', 'Methods and data');
    const detail = K.h('div', 'method-detail');
    detail.id = 'method-detail';
    detail.setAttribute('role', 'tabpanel');
    const tabs = [];
    const select = index => {
      const [name, , full] = Copy.methodBlocks[index];
      tabs.forEach((tab, i) => {
        tab.setAttribute('aria-selected', String(i === index));
        tab.tabIndex = i === index ? 0 : -1;
      });
      detail.setAttribute('aria-labelledby', tabs[index].id);
      detail.textContent = '';
      detail.append(K.h('h4', null, name), K.h('p', null, full));
      if (index === 0) {
        const section = methodSection('Public inputs and study audits', 'Open the original analysis, a local input sample, or a checked result for each source. Source licenses differ by study.');
        section.appendChild(methodTable(['Dataset or paper', 'What is available', 'Open'], [
          ['EPA chronic rat MEA, 194 chemicals', 'Five chemical folds and 35 layouts', ['Result CSV', Copy.repo + 'chip_forecast_result.csv']],
          ['EPA acute rat MEA', 'External screen, per chemical', ['Result CSV', Copy.repo + 'benchmarks/strong_baseline/external/acute/per_chemical.csv']],
          ['Harrill human neural screen, 2,520 hidden wells', 'Locked forecast and reveal', ['Reconcile', Copy.repo + 'three_point_example/forecast/reconcile.md']],
          ['Bircsak perfused liver chips', 'Scored predictions', ['Result CSV', Copy.repo + 'results/capacity/bircsak_run_v1/scored_predictions.csv']],
          ['Ewart, Communications Medicine', 'Normalized liver chip inputs', ['Input CSV', Copy.repo + 'results/capacity/inputs/runs/chip-evidence-s1/expand/ewart/normalized.csv']],
          ['Yuan, Communications Biology', 'Normalized liver chip inputs', ['Input CSV', Copy.repo + 'results/capacity/inputs/runs/chip-evidence-s1/expand/yuan_normalized.csv']],
          ['Xu rectal organoids, Cell Reports Medicine', 'Clinical cohort audit', ['Audit', 'audits/rectal.html', true]],
          ['Dai vascularized chip, Cell Reports Medicine', 'Patient holdout and readout audit', ['Audit', 'audits/dai.html', true]],
          ['Tan colorectal organoids, Cell Reports Medicine', 'Patient action audit', ['Audit', 'audits/tan.html', true]],
          ['Hu lung organoids, Nature Communications', 'Clinical linkage audit', ['Audit', 'audits/hu.html', true]],
          ['Schuster perfused organoids, Nature Communications', 'Schedule horizon audit', ['Audit', 'audits/schuster.html', true]]
        ]));
        section.appendChild(methodLinks([['All study audits', 'audits/index.html', true], ['Download sample input CSV', 'examples/T1_input.csv', true]]));
        detail.appendChild(section);
      } else if (index === 1) {
        const run = methodSection('Run the frozen prediction and reconcile after reveal', 'From the repository root, run the same CLI on an unfinished table, then on its completed counterpart. The forecast directory contains a SHA-256 lock for inputs, outputs, code, protocol and models.');
        run.appendChild(methodCode('Three concentration forecast', 'python three_point.py my_plates.csv\npython three_point.py my_finished_plates.csv --reconcile three_point_my_plates'));
        detail.appendChild(run);
        const audit = methodSection('Recompute the browser and paper checks', 'The first command compares browser calculations with the Python CLI. The published model comparison runs separately. The image audit downloads a larger source archive and resumes by stage.');
        audit.appendChild(methodCode('Verification and full audits', 'python workbench/verify.py --out workbench/verification\npython paper_final_baselines.py\npython run_full_audit.py'));
        detail.appendChild(audit);
        const cards = K.h('div', 'method-metrics');
        [[String(O.model.params.min_samples_leaf), 'frozen minimum leaf size'], [String(C.layouts().length), 'three of seven layouts'], [`${bt.win}W ${bt.tie}T ${bt.loss}L`, `${F.baselines.opponents.length} published models, 98 paired comparisons`], ['about 1 min', 'each screen fold on free Kaggle CPU']].forEach(([value, label]) => {
          const card = K.h('div', 'method-metric'); card.append(K.h('strong', null, value), K.h('span', null, label)); cards.appendChild(card);
        });
        detail.append(cards, methodAction('Open full Model & Agent Replay view ↑', () => actions.openView && actions.openView('model', 'ablation')),
          methodLinks([['Forecast CLI', 'three_point.py'], ['Browser engine', 'workbench/engine.js'], ['32 model benchmark', 'paper_final_baselines.py'], ['Example SHA-256 lock', 'three_point_example/forecast/lock.json']]));
      } else if (index === 2) {
        const section = methodSection('Three checks before a claim leaves the screen', 'Each test chemical or patient is scored outside its own training data. These files let you inspect the heldout rows, frozen receipts and reported totals.');
        section.appendChild(methodTable(['Control', 'Recorded rule', 'Inspect'], [
          ['Chemical identity holdout', 'Five folds; test identities stay out of fitting and cutoff selection', ['Heldout script', Copy.repo + 'paper_final_heldout.py']],
          ['Release risk control', 'Two other folds set the hit cutoff; two more set the release margin at α = 0.10', ['Verification script', Copy.repo + 'paper_final_verify.py']],
          ['Reveal receipt', 'SHA-256 locks the input, predictions, models, protocol and code before outcomes are reconciled', ['Example lock', Copy.repo + 'three_point_example/forecast/lock.json']]
        ]));
        const result = K.h('div', 'method-metrics');
        [[`${bt.win}W ${bt.tie}T ${bt.loss}L`, '98 paired comparisons across 32 models'], ['2,318 / 2,520', 'Harrill hidden wells inside 90% intervals'], [`${cl.reports} / ${cl.designs}`, 'closed loop designs reported']].forEach(([value, label]) => {
          const card = K.h('div', 'method-metric'); card.append(K.h('strong', null, value), K.h('span', null, label)); result.appendChild(card);
        });
        section.appendChild(result);
        section.appendChild(methodLinks([['Paper number check', 'paper_final_verify.py'], ['Heldout decisions', 'paper_final_heldout.py'], ['Image audit', 'audit_report.py'], ['Revealed forecast comparison', 'three_point_example/forecast/reconcile.md']]));
        detail.append(section, methodAction('Open full Evidence & 32-Model Scoreboard ↑', () => actions.openView && actions.openView('evidence', 'replay')));
      } else {
        const section = methodSection('Your table stays in this browser', 'Paste or load a CSV to calculate locally. This page sends no table to a server. The downloadable result.json records the published patient rule, reference rows and checks.');
        section.appendChild(methodTable(['Asset', 'Use', 'Open'], [
          ['Workbench result.json', 'Frozen published patient rule and reference rows', ['Download JSON', 'result.json', true]],
          ['MIT code license', 'Repository source code', ['License', Copy.repo + 'LICENSE']],
          ['EPA public domain inputs', 'Neural screen source and provenance', ['Data guide', Copy.repo + 'README.md']],
          ['CC BY 4.0 study sources', 'Ewart, rectal, Hu and Schuster; follow each source citation', ['Study audits', 'audits/index.html', true]],
          ['Other study licenses', 'Yuan and Dai sources have CC BY-NC-ND terms; only permitted analysis is linked', ['Data guide', Copy.repo + 'README.md']]
        ]));
        section.appendChild(methodLinks([['Sample CSV', 'examples/T1_input.csv', true], ['Chart library licenses', 'vendor/d3.LICENSE.txt', true]]));
        detail.append(section, methodAction('Paste your table ↑', () => actions.openPaste && actions.openPaste()));
      }
    };
    Copy.methodBlocks.forEach(([name, short], index) => {
      const tab = K.h('button', 'cell');
      tab.type = 'button';
      tab.id = `method-tab-${index}`;
      tab.setAttribute('role', 'tab');
      tab.setAttribute('aria-controls', detail.id);
      tab.append(K.h('h4', null, name), K.h('p', null, short));
      tab.addEventListener('click', () => select(index));
      tab.addEventListener('keydown', event => {
        if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
        event.preventDefault();
        const target = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 :
          (index + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
        select(target);
        tabs[target].focus();
      });
      tabs.push(tab);
      row.appendChild(tab);
    });
    el.append(row, detail);
    select(0);
  };
  /* hero: what 56.8% counts sits in the hover of the figure, one line per fact */
  Copy.heroRecord = [`Closed-loop replay of ${cl.designs} three-concentration designs, EPA’s network formation screen`, [
    `${C.int(cl.wells_used)} vs ${C.int(cl.wells_full)} exposure wells across ${cl.designs} designs: ${Copy.heroNumber} fewer than every concentration`,
    `${cl.reports} reports, ${cl.wrong_reports} wrong; ${cl.reports - mo.reports} more reports from ${C.pct(1 - cl.wells_used / mo.wells)} fewer wells than three measured concentrations alone`,
    `${bt.win} wins, ${bt.tie} tie, ${bt.loss} losses against ${F.baselines.opponents.length} published predictor configurations at one to four concentrations`]];
  Copy.heroTip = els => els.forEach(el => {
    el.tabIndex = 0;
    const show = ev => C.tip(ev.clientX !== undefined ? ev : { clientX: el.getBoundingClientRect().left, clientY: el.getBoundingClientRect().bottom + 8 }, Copy.heroRecord[0], Copy.heroRecord[1], { line: true });
    el.addEventListener('pointermove', show); el.addEventListener('focus', show);
    el.addEventListener('pointerleave', C.untip); el.addEventListener('blur', C.untip);
  });
})();

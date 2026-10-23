/* Worksheet: a patient table in, leave-one-patient-out calls, release or retest per patient, a concordance figure,
   validation sizes and a methods paragraph out. Opens on a published cohort so every panel is filled at once. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id), E = WorkbenchEngine, S = WorkbenchStats, start = performance.now(), events = [];
  let result, method = '', figure = '', source = null;
  const esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const log = (type, data = {}) => events.push({ type, elapsed_ms: Math.round(performance.now() - start), at: new Date().toISOString(), ...data });
  const pc = x => x === null ? 'NA' : (100 * x).toFixed(2) + '%';
  const ci = x => x ? `${pc(x.low)}–${pc(x.high)}` : 'NA';
  const readout = k => k.replace(/^readout(\d)$/, 'Readout $1');
  function save(name, body, type) {
    const u = URL.createObjectURL(new Blob([body], { type })), a = document.createElement('a');
    a.href = u; a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(u), 1000); log('download', { kind: name });
  }
  function fail(e) { $('own-error').hidden = false; $('own-error').textContent = e.message; log('error', { message: e.message }); }

  function parse(text) {
    const first = text.trim().split(/[\r\n]/)[0];
    const data = E.csv(text, first.includes('\t') ? '\t' : ','), seen = new Set();
    if (data.length > 2000) throw Error('Use up to 2,000 independent patient rows for this leave-one-out worksheet.');
    return data.map((r, i) => {
      if (!Object.hasOwn(r, 'patient') || !Object.hasOwn(r, 'readout1')) throw Error('Use headers patient,readout1, with optional readout2,response.');
      if (Object.keys(r).some(k => !['patient', 'readout1', 'readout2', 'response'].includes(k))) throw Error('Use only patient,readout1,readout2,response columns. Keep study metadata separately.');
      if (!r.patient || seen.has(r.patient)) throw Error(`Row ${i + 2}: patient IDs must be nonempty and unique. Aggregate replicates within each patient first.`);
      seen.add(r.patient);
      const v = k => { if (!r[k]?.trim()) return null; if (!Number.isFinite(Number(r[k]))) throw Error(`Row ${i + 2}: ${k} must be numeric or empty.`); return Number(r[k]); };
      const a = v('readout1'), b = v('readout2'), y = v('response');
      if (a === null && b === null) throw Error(`Row ${i + 2}: provide at least one readout.`);
      if (y !== null && ![0, 1].includes(y)) throw Error(`Row ${i + 2}: response is 0, 1 or empty.`);
      return { patient: r.patient, readout1: a, readout2: b, response: y };
    });
  }

  const stat = (k, v, tip, tone) => `<div class="stat${tone ? ' ' + tone : ''}"${tip ? ` aria-description="${esc(tip)}"` : ''}><div class="v${/^[\d+>]/.test(v) ? '' : ' text'}">${v}</div><div class="k">${k}</div></div>`;

  /* readout rows: track, 95% interval, observed share; the export adds a title and the interval note */
  function figureSVG(series, full) {
    const W = 760, T = full ? 76 : 8, X0 = 168, X1 = 548, rowH = 46, top = T + 34, last = top + (series.length - 1) * rowH;
    const H = last + (full ? 56 : 20), x = v => X0 + (X1 - X0) * v;
    const ticks = [0, .25, .5, .75, 1].map(t => `<line x1="${x(t)}" x2="${x(t)}" y1="${T + 22}" y2="${last + 16}" stroke="#e1e6ed" stroke-dasharray="2 3"/><text x="${x(t)}" y="${T + 14}" font-size="12" fill="#647084" text-anchor="middle">${100 * t}%</text>`).join('');
    const rows = series.map((m, i) => {
      const y = top + i * rowH, c = m.correct / m.n;
      return `<text x="0" y="${y + 5}" font-size="14" font-weight="600" fill="#1b2430">${esc(m.name)}</text>`
        + `<line x1="${X0}" y1="${y}" x2="${X1}" y2="${y}" stroke="#eef1f5" stroke-width="12" stroke-linecap="round"/>`
        + `<line x1="${x(m.interval.low)}" y1="${y}" x2="${x(m.interval.high)}" y2="${y}" stroke="#00789e" stroke-width="3" stroke-linecap="round"/>`
        + `<circle cx="${x(c)}" cy="${y}" r="6" fill="${m.consensus ? '#1b2430' : '#035a77'}"/>`
        + `<text x="${X1 + 22}" y="${y + 5}" font-size="14" fill="#1b2430"><tspan font-weight="700">${m.correct}/${m.n}</tspan><tspan fill="#647084" dx="8">${(100 * c).toFixed(1)}% · ${ci(m.interval)}</tspan></text>`;
    }).join('');
    const head = full ? `<text x="0" y="30" font-family="Newsreader, Georgia, serif" font-size="22" fill="#1b2430">Patient-level clinical concordance</text><text x="0" y="52" font-size="13" fill="#647084">${esc(result.approach)} · 95% Clopper–Pearson intervals</text>` : '';
    const foot = full ? `<text x="0" y="${H - 10}" font-size="12" fill="#647084">Binomial intervals are descriptive for overlapping leave-one-out fits. ${result.patients} patient rows.</text>` : '';
    return `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}"${full ? '' : ' role="img" aria-label="Clinical concordance per readout with 95% intervals"'}>${full ? '<rect width="100%" height="100%" fill="white"/>' : ''}<g font-family="Source Sans 3, Helvetica Neue, Arial, sans-serif">${head}${ticks}${rows}${foot}</g></svg>`;
  }

  function run() {
    try {
      $('own-error').hidden = true;
      const data = parse($('own-input').value), higher = $('own-direction').value === 'higher';
      result = S.analyse(data, higher);
      log('analysis_complete', { patients: result.patients, labelled: result.scored, readouts: result.models.length, approach: result.approach, source: source?.id || 'own_data' });
      const review = result.patients - result.releases;
      $('own-result-title').textContent = `${result.releases} release candidates · ${review} to review or retest`;
      $('own-result-title').setAttribute('aria-description', `${result.approach}. Clopper–Pearson bounds are exact under a fixed-rule binomial model; for overlapping leave-one-out fits they are descriptive intervals. Release candidates identify concordant readouts for research review.`);
      const main = result.paired ? { n: result.scored_released, correct: result.agreement_correct, interval: result.agreement_interval } : result.models[0];
      $('own-metrics').innerHTML = [
        stat(result.paired ? 'Correct among released' : 'Readout concordance', main.n ? `${main.correct}/${main.n}` : 'Awaiting outcomes', main.n ? `${ci(main.interval)}, 95% binomial interval` : 'Add a response column to score the calls', 'report'),
        stat('Readouts disagree', String(result.conflicts), 'These patients are listed for review or retest in the table', result.conflicts ? 'retest' : ''),
        stat('Wrong / all labelled', result.scored ? `${result.wrong}/${result.scored}` : 'Awaiting outcomes', result.scored ? `${pc(result.overall)} · every labelled patient in the denominator` : '', result.wrong ? 'wrong' : ''),
        stat('Wrong / labelled released', result.scored_released ? `${result.wrong}/${result.scored_released}` : 'NA', result.scored_released ? `${pc(result.conditional)} · released patients in the denominator` : '', result.wrong ? 'wrong' : '')
      ].join('');
      $('own-budget').innerHTML = result.targets.length
        ? result.targets.map(b => stat(`More released cases, ${100 * b.alpha}% target`, b.additional === null ? '>10M' : `+${b.additional}`, `Conditional error target ${100 * b.alpha}%: further released cases with no further errors, at a 95% one-sided binomial bound`)).join('')
        : stat('Labelled released cases', '0', 'Add labelled released validation counts in the sample-size calculator');
      $('own-plan').href = result.scored_released ? `sample.html?n=${result.scored_released}&e=${result.wrong}&alpha=10` : 'sample.html';
      $('own-approach').textContent = result.models.every(m => m.loo) ? 'Leave one patient out' : 'Cohort median for thin readouts';
      $('own-approach').setAttribute('aria-description', result.models.map(m => `${readout(m.key)}: ${m.loo ? 'leave-one-patient-out cutoff' : 'cohort median; exploratory'}`).join(' · '));

      const sens = c => c === null ? '<span class="k3">Missing</span>' : c ? 'Sensitive' : 'Resistant';
      $('own-rows').innerHTML = result.rows.map(r => {
        const released = r.action !== 'retest', known = r.response === 0 || r.response === 1;
        const wrong = released && known && Number(r.action) !== r.response;
        const action = released ? `<span class="badge report">Release ${r.action === '1' ? 'sensitive' : 'resistant'}</span>` : '<span class="badge retest">Review / retest</span>';
        const outcome = known ? (r.response ? 'Responder' : 'Non-responder') + (wrong ? ' · wrong' : '') : '<span class="k3">Not given</span>';
        return `<tr${wrong ? ' class="wrong"' : ''}><td>${esc(r.patient)}</td><td>${sens(r.call1)}</td><td>${sens(r.call2)}</td><td>${action}</td><td${wrong ? ' class="wrong"' : ''}>${outcome}</td><td class="k3">${r.reason}</td></tr>`;
      }).join('');
      $('own-rows-title').textContent = `${result.patients} patients · ${result.releases} released · ${review} to review`;
      $('own-keys').innerHTML = result.wrong ? `<span class="key" style="color:var(--wrong)"><i class="box" style="background:var(--wrong)"></i>${result.wrong} wrong release${result.wrong === 1 ? '' : 's'}</span>` : '';

      const direction = higher ? 'at or above' : 'at or below';
      const procedures = result.models.map(m => m.loo
        ? `${m.key}: for every labelled patient, the cutoff was selected on the remaining labelled patients by maximizing balanced accuracy (ties used the lowest cutoff on the direction-adjusted scale); unlabelled patients used a cutoff fitted on all labelled patients`
        : `${m.key}: insufficient labelled outcome classes for leave-one-out threshold fitting, so the cohort median supplied an exploratory cutoff`).join('. ');
      method = `We analysed ${result.patients} independent patient rows with ${result.scored} recorded binary clinical outcomes (1 = responder, 0 = non-responder). Readout values ${direction} the fitted cutoff were called sensitive. ${procedures}. With two available readouts, concordant calls were marked as release candidates and discordant or incomplete pairs were assigned to review/retest; a single readout remained a review-only prediction. We reported readout-level clinical concordance and, for consensus releases, both wrong releases/all labelled patients and wrong releases/labelled released patients. The current batch had ${result.scored_released} labelled releases and ${result.wrong} wrong releases. Two-sided 95% Clopper–Pearson intervals were computed for the observed binary counts. Because leave-one-out predictions share training data, these binomial intervals describe the counts and do not provide exact cross-validation coverage. Sample-size calculations use a separate fixed-rule, independent-validation model, a one-sided 95% upper bound, and zero additional errors; they are planning minima. Study endpoint definition, assay units, treatment mapping, eligibility and within-patient replicate aggregation should be specified alongside this analysis.`;
      $('own-method-text').textContent = method;

      const series = result.models.filter(m => m.n).map(m => ({ name: readout(m.key), n: m.n, correct: m.correct, interval: m.interval }));
      if (result.paired && main.n) series.push({ name: 'Agreement releases', consensus: true, ...main });
      const plotSeries = series.length ? series : [
        ...result.models.map(m => { const c = m.calls.filter(Boolean), pos = c.filter(x => x.call === 1).length; return { name: `${readout(m.key)} sensitive`, n: c.length, correct: pos, interval: S.interval(pos, c.length) }; }).filter(m => m.n),
        ...(result.paired && result.patients ? [{ name: 'Two-readout agreement', consensus: true, n: result.patients, correct: result.releases, interval: S.interval(result.releases, result.patients) }] : [])
      ];
      $('own-plot-title').textContent = series.length ? 'Clinical concordance per readout' : 'Assay call split and readout agreement';
      figure = plotSeries.length ? figureSVG(plotSeries, true) : '';
      $('own-plot').innerHTML = plotSeries.length ? figureSVG(plotSeries, false) : '<p class="t1 ink3">Add a response column to draw clinical concordance.</p>';
    } catch (e) { fail(e); }
  }

  function setExample(id) {
    const s = PUBLIC_STUDIES.find(s => s.id === id && s.input) || PUBLIC_STUDIES.find(s => s.id === 'rectal');
    source = s; $('own-example').value = s.id;
    if (s.direction) $('own-direction').value = s.direction;
    $('own-input').value = E.toCSV(s.input, ['patient', 'readout1', 'readout2', 'response']);
    log('example_loaded', { id: s.id });
  }
  $('own-run').onclick = run;
  $('own-example').onchange = () => { if ($('own-example').value) { setExample($('own-example').value); run(); } };
  $('own-input').oninput = () => { source = null; $('own-example').value = ''; log('input_edit', { characters: $('own-input').value.length }); };
  $('own-direction').onchange = () => { log('direction_change', { value: $('own-direction').value }); run(); };
  /* the bar's Paste your table lands in this textarea with its contents selected, so a paste replaces the example */
  $('paste-cta').onclick = e => { e.preventDefault(); const t = $('own-input'); t.focus(); t.select(); t.scrollIntoView({ block: 'center', behavior: 'smooth' }); };
  async function openFile(f) {
    if (f.size > 4 * 1024 * 1024) throw Error('Use a CSV smaller than 4 MB.');
    $('own-input').value = await f.text(); source = null; $('own-example').value = '';
    log('file_opened', { bytes: f.size }); run();
  }
  $('own-file').onchange = () => openFile($('own-file').files[0]).catch(fail);
  $('drop-zone').ondragover = e => e.preventDefault();
  $('drop-zone').ondrop = e => { e.preventDefault(); if (e.dataTransfer.files[0]) openFile(e.dataTransfer.files[0]).catch(fail); };
  $('own-csv').onclick = () => save('patient-review-list.csv', E.toCSV(result.rows, ['patient', 'call1', 'call2', 'cutoff1', 'cutoff2', 'action', 'reason', 'response']), 'text/csv');
  $('own-method').onclick = () => save('methods.txt', method, 'text/plain');
  $('own-figure').onclick = () => save('concordance.svg', figure, 'image/svg+xml');
  $('own-record').onclick = () => {
    log('record_export');
    save('local-analysis-record.json', JSON.stringify({ schema: 'workbench.local-analysis.v1', record_type: 'local_analysis', events, summary: { patients: result.patients, scored: result.scored, releases: result.releases, wrong: result.wrong } }, null, 2), 'application/json');
  };
  log('page_open');
  setExample(new URLSearchParams(location.search).get('example') || 'rectal');
  run();
})();

/* Paired observations remain separate throughout search, filtering and display. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const data = window.ChipEvidence;
  if (!data) {
    $('paper-count').textContent = 'Catalogue could not load. Reload this page to retry.';
    $('corpus-count').textContent = 'Catalogue could not load. Reload this page to retry.';
    return;
  }
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));
  const labels = {
    physical_model: 'Physical model', claimed_n: 'Claimed sample n',
    independent_human_donor_n: 'Independent human donors',
    technical_pseudoreplication_ratio: 'Technical repeat ratio',
    raw_multidose_public_level: 'Public multidose data', clinical_attrition: 'Clinical attrition',
    treatment_timing_match: 'Treatment timing match', positive_doses_ge5: 'At least 5 doses',
    positive_doses_ge6: 'At least 6 doses', strict_clinical_eligible: 'Strict clinical eligible',
    cutpoint_in_sample: 'Cutpoint fit in sample', n_distinct_positive_doses: 'Distinct positive doses'
  };
  const phrases = {no_clinical_link: 'No link', fulltext_unavailable: 'No full text', not_applicable: 'N/A'};
  const fmt = value => value === null || value === undefined ? 'Unobserved' :
    Array.isArray(value) ? value.map(fmt).join(', ') : typeof value === 'object' ? JSON.stringify(value) :
    typeof value === 'boolean' ? (value ? 'Yes' : 'No') : phrases[value] || String(value).replaceAll('_', ' ');
  const num = value => value.toLocaleString('en-US');
  const statusTip = pair => `Q status: ${pair.Q_status} | R status: ${pair.R_status}`;
  const valueHTML = (pair, channel) => `<span aria-description="${esc(statusTip(pair))}">${esc(fmt(pair[channel]))}</span>`;
  const paired = pair => ['Q', 'R'].map(c => `<span class="paired-value" aria-description="${esc(statusTip(pair))}">${c}: ${esc(fmt(pair[c]))}</span>`).join('');
  const observed = (paper, field, channel) => paper.coding[field][channel + '_status'] === 'observed' ? paper.coding[field][channel] : null;
  const choices = (id, values) => {
    [...new Set(values.filter(v => v !== null && v !== undefined && v !== ''))]
      .sort((a, b) => String(a).localeCompare(String(b), 'en', {numeric: true}))
      .forEach(value => $(id).add(new Option(String(value).replaceAll('|', ' · ').replaceAll('_', ' '), String(value))));
  };
  choices('paper-year', data.papers.map(p => p.pub_year));
  choices('paper-tier', data.papers.map(p => p.journal_tier));
  choices('paper-journal', data.papers.map(p => p.journal));
  choices('paper-stratum', data.papers.map(p => p.stratum));
  choices('corpus-organ', data.studies.flatMap(s => s.organ_disease));

  function showAgreement() {
    $('agreement-grid').innerHTML = data.agreement[$('agreement-mode').value].map(a => {
      const ci = a.alpha_95_cluster_bootstrap_ci.map(v => v.toFixed(4)).join(', ');
      const tip = `95% CI: [${ci}] · Value agreement: ${(a.raw_agreement_comparable * 100).toFixed(1)}% · Status agreement (399): ${(a.status_agreement_all_pairs * 100).toFixed(1)}% · Status alpha: ${a.status_alpha.toFixed(4)} · IPW alpha: ${a.ipw_alpha_sensitivity.toFixed(4)}`;
      return `<tr aria-description="${esc(tip)}"><td title="${esc(a.field)}">${esc(labels[a.field])}</td><td><details aria-description="${esc(tip)}"><summary aria-description="${esc(tip)}">${a.alpha.toFixed(4)}</summary><div class="alpha-detail">95% CI: [${ci}]<br>Value agreement: ${(a.raw_agreement_comparable * 100).toFixed(1)}%<br>Status agreement (all 399): ${(a.status_agreement_all_pairs * 100).toFixed(1)}%<br>Status alpha: ${a.status_alpha.toFixed(4)}<br>IPW alpha: ${a.ipw_alpha_sensitivity.toFixed(4)}<br>${num(a.valid_bootstrap_replicates)} bootstrap draws</div></details></td><td>${a.comparable_papers}</td></tr>`;
    }).join('');
  }
  $('agreement-mode').addEventListener('change', showAgreement);
  showAgreement();

  const paperSearch = new Map(data.papers.map(p => [p.paper_id, JSON.stringify(p).toLocaleLowerCase()]));
  function filterPapers() {
    const query = $('paper-search').value.trim().toLocaleLowerCase();
    const channel = $('paper-channel').value;
    const channels = channel === 'either' ? ['Q', 'R'] : [channel];
    const eligibility = $('paper-eligibility').value;
    const clinical = $('paper-clinical').value;
    const donors = $('paper-donors').value;
    const papers = data.papers.filter(p => {
      if (query && !paperSearch.get(p.paper_id).includes(query)) return false;
      for (const [control, field] of [['year','pub_year'], ['tier','journal_tier'], ['journal','journal'], ['stratum','stratum']]) {
        if ($('paper-' + control).value && String(p[field]) !== $('paper-' + control).value) return false;
      }
      // Evaluate all coding criteria within one channel, so Q and R never form
      // an artificial hybrid observation when several filters are combined.
      return channels.some(c => {
        if (eligibility && p[c + '_eligibility'] !== eligibility) return false;
        const timing = observed(p, 'treatment_timing_match', c);
        if (clinical === 'linked' && (timing === null || timing === 'no_clinical_link')) return false;
        if (clinical === 'none' && timing !== 'no_clinical_link') return false;
        if (clinical === 'strict' && observed(p, 'strict_clinical_eligible', c) !== true) return false;
        const n = observed(p, 'independent_human_donor_n', c);
        if (donors === 'le3' && !(typeof n === 'number' && n <= 3)) return false;
        if (donors === 'gt3' && !(typeof n === 'number' && n > 3)) return false;
        if (donors === 'unknown' && !channels.every(k => observed(p, 'independent_human_donor_n', k) === null)) return false;
        return true;
      });
    });
    $('paper-count').textContent = `${papers.length} of 399 papers · ${new Set(papers.map(p => p.stratum)).size} of 85 strata · IPW ${num(Number(papers.reduce((s,p) => s + p.weight, 0).toFixed(4)))}`;
    $('paper-grid').innerHTML = papers.map(p => {
      const source = [];
      if (p.pmid) source.push(`<a href="https://pubmed.ncbi.nlm.nih.gov/${encodeURIComponent(p.pmid)}/" target="_blank" rel="noopener">PubMed</a>`);
      if (p.doi) source.push(`<a href="https://doi.org/${esc(encodeURI(p.doi))}" target="_blank" rel="noopener">DOI</a>`);
      if (p.pmcid) source.push(`<a href="https://pmc.ncbi.nlm.nih.gov/articles/${encodeURIComponent(p.pmcid)}/" target="_blank" rel="noopener">PMC</a>`);
      return `<tr data-paper-id="${p.paper_id}"><td><span class="paper-id">${p.paper_id}</span><div class="source-links">${source.join('')}</div></td><td><details data-paper="${p.paper_id}"><summary class="paper-title">${esc(p.title || p.paper_id)}</summary><div class="paper-coding"></div></details></td><td>${esc(p.journal)}<small class="code-status">${esc(p.pub_year)}</small></td><td aria-description="${esc(`Stratum: ${p.stratum} · Inverse probability weight (IPW): ${p.weight.toFixed(6)}`)}">${esc(p.stratum.replaceAll('|', ' · ').replaceAll('_', ' '))}</td><td>${paired({Q: p.Q_eligibility, R: p.R_eligibility, Q_status: p.Q_eligibility, R_status: p.R_eligibility})}</td><td>${paired(p.coding.independent_human_donor_n)}</td><td>${paired(p.coding.treatment_timing_match)}</td></tr>`;
    }).join('') || '<tr><td colspan="7" class="empty-result">No papers match these filters. Reset filters to browse all 399.</td></tr>';
  }
  $('paper-grid').addEventListener('toggle', e => {
    const id = e.target.dataset.paper;
    if (!id || !e.target.open || e.target.dataset.loaded) return;
    const p = data.papers.find(p => p.paper_id === id);
    e.target.querySelector('.paper-coding').innerHTML = `<table class="data paired-coding"><caption>${id}: evidence-aligned paired coding</caption><thead><tr><th>Field</th><th>Q value</th><th>R value</th></tr></thead><tbody>${Object.entries(p.coding).map(([f,v]) => `<tr><td>${esc(labels[f])}</td><td>${valueHTML(v, 'Q')}</td><td>${valueHTML(v, 'R')}</td></tr>`).join('')}</tbody></table>`;
    e.target.dataset.loaded = 'true';
  }, true);
  $('paper-reset-top').addEventListener('click', () => $('paper-filters').reset());
  $('paper-filters').addEventListener('submit', e => e.preventDefault());
  $('paper-filters').addEventListener('input', filterPapers);
  $('paper-filters').addEventListener('change', e => { if (e.target.matches('select')) filterPapers(); });
  $('paper-filters').addEventListener('reset', () => setTimeout(filterPapers, 0));
  filterPapers();

  function filterCorpus() {
    const query = $('corpus-search').value.trim().toLocaleLowerCase();
    const scope = $('corpus-scope').value;
    const system = $('corpus-system').value;
    const organ = $('corpus-organ').value;
    const studies = data.studies.filter(s => (!query || JSON.stringify(s).toLocaleLowerCase().includes(query)) &&
      (!scope || (scope === 'strict' ? s.strict_ge5_curves > 0 : s.strict_ge5_curves === 0)) &&
      (!system || s.system.includes(system)) && (!organ || s.organ_disease.includes(organ)));
    $('corpus-count').textContent = `${studies.length} of 40 studies · ${num(studies.reduce((n,s) => n + s.ge5_curves, 0))} qualified curves · ${num(studies.reduce((n,s) => n + s.observations, 0))} measurement points · ${num(studies.reduce((n,s) => n + s.strict_ge5_curves, 0))} strict PDO curves`;
    $('corpus-grid').innerHTML = studies.map(s => `<tr data-study-id="${s.study_id}"><td><b>${s.study_id}</b><br><a href="https://doi.org/${esc(encodeURI(s.doi))}" target="_blank" rel="noopener">${esc(s.title || s.doi)}</a></td><td>${esc(s.organ_disease.join(', ') || 'Not recorded')}</td><td>${esc(s.origin.join(', ').replaceAll('_', ' '))}<small class="code-status">${esc(s.system.join(', ').replaceAll('_', ' '))}</small></td><td>${num(s.ge5_curves)}</td><td>${num(s.observations)}</td><td>${s.positive_doses_min === s.positive_doses_max ? s.positive_doses_min : s.positive_doses_min + ' to ' + s.positive_doses_max}</td><td>${num(s.strict_ge5_curves)}</td></tr>`).join('') || '<tr><td colspan="7" class="empty-result">No studies match these filters. Reset filters to browse all 40.</td></tr>';
  }
  $('corpus-filters').addEventListener('submit', e => e.preventDefault());
  $('corpus-filters').addEventListener('input', filterCorpus);
  $('corpus-filters').addEventListener('change', e => { if (e.target.matches('select')) filterCorpus(); });
  $('corpus-filters').addEventListener('reset', () => setTimeout(filterCorpus, 0));
  filterCorpus();

  const tabs = [...document.querySelectorAll('.evidence-tabs [role="tab"]')];
  function selectTab(id, updateHash = false) {
    if (!tabs.some(t => t.getAttribute('aria-controls') === id)) id = 'papers399';
    tabs.forEach(tab => {
      const selected = tab.getAttribute('aria-controls') === id;
      tab.setAttribute('aria-selected', String(selected));
      tab.tabIndex = selected ? 0 : -1;
      $(tab.getAttribute('aria-controls')).hidden = !selected;
    });
    if (updateHash) history.replaceState(null, '', '#' + id);
    requestAnimationFrame(() => $('evidence-browser').scrollIntoView({block: 'start'}));
  }
  tabs.forEach((tab, i) => {
    tab.addEventListener('click', () => selectTab(tab.getAttribute('aria-controls'), true));
    tab.addEventListener('keydown', e => {
      let next;
      if (e.key === 'ArrowRight') next = (i+1) % tabs.length;
      if (e.key === 'ArrowLeft') next = (i+tabs.length-1) % tabs.length;
      if (e.key === 'Home') next = 0;
      if (e.key === 'End') next = tabs.length-1;
      if (next !== undefined) { e.preventDefault(); tabs[next].focus(); selectTab(tabs[next].getAttribute('aria-controls'), true); }
    });
  });
  window.addEventListener('hashchange', () => selectTab(location.hash.slice(1)));
  selectTab(location.hash.slice(1));
})();

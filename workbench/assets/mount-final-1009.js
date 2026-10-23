/* Attach saved final-report data.
   Provides cohort switching across the seven clinical organoid cohorts (258 distinct patients, 175 with clinical scores)
   and the final 10/09 screening and 32-baseline metrics. */
(function (root) {
  'use strict';
  const packet = root.OOC_FINAL_1009;
  if (!packet || packet.schema !== 'ooc.final.1009.v1') {
    throw new Error('Load data/ooc-final-1009.js before mount-final-1009.js.');
  }
  const rawCohorts = packet.patients.cohorts, inventory = packet.patients.inventory;
  /* the assay pool supplies reference medians; its rows carry no clinical call */
  const isReference = cohort => cohort.metrics && cohort.metrics.clinicalValidationDenominator === false;

  /* map positions are readouts over the regimen's frozen cutoffs; rows without raw readouts stay off the map and keep their saved call */
  function patientView(cohort) {
    const reference = isReference(cohort);
    return cohort.rows.map((row, index) => {
      const saved = cohort.cases[index];
      const action = saved.action === 'retest' ? null : Number(saved.action);
      const cutoffs = row.cutoffs || cohort.cutoffs;
      const ratios = cutoffs && cutoffs.every(c => Number.isFinite(c) && c > 0);
      return {
        id: `${row.patient}`,
        mode: cohort.mode,
        response: row.response,
        call: action,
        reference,
        reason: saved.reason,
        cohort: cohort.id,
        cohortLabel: cohort.label,
        evaluationUnit: cohort.evaluationUnit,
        combined: row.baseline_readout,
        irr: row.readout1,
        fu: row.readout2,
        readout1: row.readout1,
        readout2: row.readout2,
        r1: ratios && row.readout1 !== null ? row.readout1 / cutoffs[0] : null,
        r2: ratios && row.readout2 !== null ? row.readout2 / cutoffs[1] : null,
        sourceRow: row
      };
    });
  }

  const SHORT_LABELS = {
    'all-258': `All cohorts (${inventory.distinctPatientsIncludingAssayPool})`,
    'rectal-blind-85': 'Rectal blind (85)',
    'rectal-fixed-43': 'Rectal test (43)',
    'crlm-blind-23': 'Liver met blind (23)',
    'rectal-seen-42': 'Rectal pilot (42)',
    'tan-clinical-22': 'Tan clinical (22)',
    'tiriac-primary-7': 'Pancreatic (7)',
    'tan-assay-pool-101': 'Assay pool (101)'
  };
  const shortName = id => SHORT_LABELS[id].replace(/\s*\(\d+\)$/, '');

  /* every cohort row on the two-readout map, named by its cohort: cohort views overlap, so one patient can appear under two cohorts */
  function allRows() {
    return orderedIds.map(id => byId.get(id)).filter(c => c && c.rows.length)
      .flatMap(c => patientView(c).map(item => Object.assign({}, item, { id: `${shortName(c.id)} · ${item.id}`, mode: 'two' })));
  }

  const allCohort = {
    id: 'all-258',
    label: 'All 7 cohorts',
    mode: 'two',
    cutoffs: [1, 1],
    evaluationUnit: 'cohort row',
    patients: inventory.distinctPatientsIncludingAssayPool,
    rows: [],
    cases: []
  };

  const orderedIds = [
    'all-258',
    'rectal-blind-85',
    'rectal-fixed-43',
    'crlm-blind-23',
    'rectal-seen-42',
    'tan-clinical-22',
    'tiriac-primary-7',
    'tan-assay-pool-101'
  ];

  const byId = new Map([[allCohort.id, allCohort], ...rawCohorts.map(c => [c.id, c])]);
  const cohorts = orderedIds.map(id => byId.get(id)).filter(Boolean);
  const published = packet.patients.defaultCohort;

  function mount() {
    if (!root.OOC) throw new Error('Load data/ooc-data.js before mounting final data.');
    root.OOC.final1009 = packet;
    root.OOC.patientCohorts = cohorts;
    root.OOC.totalPatients = inventory.distinctPatientsIncludingAssayPool;
    root.OOC.totalScoredPatients = inventory.distinctClinicallyScoredPatients;
    return packet;
  }

  function getCohort(id) {
    const cohort = byId.get(id);
    if (!cohort) throw new RangeError('Unknown patient cohort: ' + id);
    return cohort;
  }

  /* the cohort on screen is read from the selection store: the published view is the fixed test cohort, a pasted table is none */
  function current(S) {
    if (S.patientSource === 'published') return published;
    return S.patientSource === 'final1009' && S.patientCohort ? S.patientCohort.id : null;
  }

  function selectCohort(id, revealDefault) {
    const cohort = getCohort(id), core = root.Core;
    if (!core || typeof core.set !== 'function') {
      throw new Error('Open the workbench before selecting a patient cohort.');
    }
    const original = id === published;
    const rows = id === allCohort.id ? allRows() : original ? core.publishedPatients() : patientView(cohort);
    const shouldReveal = revealDefault !== undefined ? revealDefault : !isReference(cohort);
    core.set({
      patients: rows,
      patient: rows.length ? rows[0].id : null,
      reveal: shouldReveal,
      patientSource: original ? 'published' : 'final1009',
      patientCohort: original ? null : cohort,
      patientCutoffs: original ? null : [1, 1],
      patientAxisLabels: original ? null : ['readout 1 / frozen cutoff', 'readout 2 / frozen cutoff']
    });
    return cohort;
  }

  let synced = false;
  function sync() {
    if (synced || !root.Core) return;
    synced = true;
    root.Core.on((S, p) => {
      if (p && Object.keys(p).length && !('patients' in p)) return;
      const id = current(S);
      root.document.querySelectorAll('[data-ooc-cohort-select]').forEach(el => { el.value = id || ''; });
      root.document.querySelectorAll('[data-ooc-cohort]').forEach(el => el.setAttribute('aria-pressed', String(el.dataset.oocCohort === id)));
    });
  }

  function bind(scope) {
    scope = scope || root.document;
    if (!scope) return;
    scope.querySelectorAll('[data-ooc-cohort]').forEach(el => {
      if (el.dataset.oocFinalBound) return;
      el.addEventListener('click', () => selectCohort(el.dataset.oocCohort));
      el.dataset.oocFinalBound = 'true';
    });
    scope.querySelectorAll('[data-ooc-cohort-select]').forEach(el => {
      if (el.dataset.oocFinalBound) return;
      if (!el.options.length) {
        cohorts.forEach(cohort => {
          const option = root.document.createElement('option');
          option.value = cohort.id;
          option.textContent = SHORT_LABELS[cohort.id] || cohort.label;
          el.appendChild(option);
        });
      }
      el.addEventListener('change', () => selectCohort(el.value));
      el.dataset.oocFinalBound = 'true';
    });
    sync();
  }

  function renderCohortBar(container) {
    if (!container) return;
    container.textContent = '';
    cohorts.forEach(cohort => {
      const btn = root.document.createElement('button');
      btn.type = 'button';
      btn.className = 'chip';
      btn.dataset.oocCohort = cohort.id;
      btn.textContent = SHORT_LABELS[cohort.id] || cohort.label;
      container.appendChild(btn);
    });
    bind(container);
  }

  root.OOCFinal1009 = Object.freeze({
    mount,
    getCohort,
    patientView,
    selectCohort,
    bind,
    renderCohortBar,
    cohorts,
    SHORT_LABELS,
    get selectedCohort() { return root.Core ? current(root.Core.state) : published; }
  });
  mount();
})(window);

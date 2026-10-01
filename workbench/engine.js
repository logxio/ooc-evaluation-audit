/* Browser adapter of release_calibration.predict/apply. Core Python remains authoritative. */
(function (root) {
  'use strict';
  function csv(text, delimiter=',') {
    const rows = []; let row = [], field = '', quoted = false;
    text = text.replace(/^\uFEFF/, '');
    for (let i = 0; i < text.length; i++) {
      const c = text[i];
      if (quoted) {
        if (c === '"' && text[i + 1] === '"') { field += '"'; i++; }
        else if (c === '"') quoted = false;
        else field += c;
      } else if (c === '"' && !field) quoted = true;
      else if (c === delimiter) { row.push(field.trim()); field = ''; }
      else if (c === '\n' || c === '\r') {
        if (c === '\r' && text[i + 1] === '\n') i++;
        row.push(field.trim()); if (row.some(Boolean)) rows.push(row); row = []; field = '';
      } else field += c;
    }
    if (quoted) throw Error('CSV contains an unfinished quoted field.');
    row.push(field.trim()); if (row.some(Boolean)) rows.push(row);
    if (rows.length < 2) throw Error('Add a header and at least one patient row.');
    const header = rows.shift();
    if (new Set(header).size !== header.length) throw Error('CSV has duplicate column names.');
    return rows.map((r, i) => {
      if (r.length !== header.length) throw Error(`Row ${i + 2}: expected ${header.length} columns, received ${r.length}.`);
      return Object.fromEntries(header.map((h, j) => [h, r[j]]));
    });
  }
  function inputs(text) {
    const rows = csv(text); const seen = new Set();
    if (rows.length > 10000) throw Error('This browser worksheet accepts up to 10,000 patients per batch.');
    for (const [i, r] of rows.entries()) {
      if (Object.keys(r).sort().join(',') !== 'patient,readout1,readout2') throw Error('Input columns: patient,readout1,readout2. Load outcomes separately.');
      if (!/^[A-Za-z0-9_-]{1,24}$/.test(r.patient)) throw Error(`Row ${i + 2}: use a coded patient ID of 1–24 letters, digits, hyphens or underscores.`);
      if (seen.has(r.patient)) throw Error(`Duplicate patient ID: ${r.patient}. Use one row per patient.`);
      seen.add(r.patient);
      for (const k of ['readout1', 'readout2']) {
        if (!r[k] || !Number.isFinite(Number(r[k])) || Number(r[k]) < 0) throw Error(`Row ${i + 2}: ${k} must be a finite nonnegative size ratio.`);
        r[k] = Number(r[k]);
      }
    }
    return rows;
  }
  function outcomes(text, rows) {
    const data = csv(text); const map = {};
    for (const r of data) {
      if (Object.keys(r).sort().join(',') !== 'patient,response') throw Error('Outcome columns: patient,response, with response 0 or 1.');
      if (Object.hasOwn(map, r.patient)) throw Error(`Duplicate outcome ID: ${r.patient}.`);
      if (!['0', '1'].includes(r.response)) throw Error(`Outcome for ${r.patient} must be 0 or 1.`);
      map[r.patient] = Number(r.response);
    }
    if (rows.length !== data.length || rows.some(r => !Object.hasOwn(map, r.patient))) throw Error('Outcomes must match every input patient exactly, with no extra patients.');
    return map;
  }
  function predict(certificate, rows) {
    const model = certificate.model;
    const ecdf = (values, x) => values.reduce((s, v) => s + (v < x ? 1 : v === x ? .5 : 0), 0) / values.length;
    return rows.map(r => {
      const x = r.x || [r.readout1, r.readout2];
      const calls = x.map((v, j) => Number(v <= model.cutoffs[j]));
      const margin = Math.min(...x.map((v, j) => Math.abs(ecdf(model.reference[j], v) - ecdf(model.reference[j], model.cutoffs[j]))));
      const agree = calls[0] === calls[1], released = agree && margin > certificate.margin;
      return {patient:r.patient, calls, agree, margin, prediction:calls[0], released};
    });
  }
  const action = a => a.released ? String(a.prediction) : 'retest';
  const names = {readout1:'Readout 1 alone',readout2:'Readout 2 alone',both_sensitive:'Both sensitive → sensitive',either_sensitive:'Either sensitive → sensitive',all_retest:'Retest everyone'};
  function baseline(predictions, key) {
    return predictions.map(p => key === 'all_retest' ? 'retest' : String(key === 'readout1' ? p.calls[0] : key === 'readout2' ? p.calls[1] : key === 'both_sensitive' ? Math.min(...p.calls) : Math.max(...p.calls)));
  }
  function metrics(rows, actions, truth, cost) {
    if (actions.some(a => !['0','1','retest'].includes(a))) throw Error('Choose an action for every patient.');
    const n = rows.length, released = actions.filter(a => a !== 'retest').length, retests = n - released;
    const wrong = truth ? rows.reduce((s,r,i) => s + Number(actions[i] !== 'retest' && Number(actions[i]) !== truth[r.patient]), 0) : null;
    return {patients:n,released,retests,wrong_released:wrong,overall_wrong_release:wrong === null ? null : wrong/n,
      released_error_rate:wrong === null || !released ? null : wrong/released,
      retest_cost:cost*retests,total_cost:wrong === null ? null : wrong+cost*retests,
      loss:wrong === null ? null : (wrong+cost*retests)/n};
  }
  function compare(rows, predictions, truth, cost) {
    return Object.keys(names).map(key => ({key,name:names[key],...metrics(rows,baseline(predictions,key),truth,cost)})).sort((a,b) => a.loss-b.loss || a.key.localeCompare(b.key));
  }
  function toCSV(rows, fields) {
    const quote = v => {let s = String(v ?? ''); if (typeof v==='string' && /^[=+@-]/.test(s)) s = "'"+s; return /[,"\r\n]/.test(s) ? '"'+s.replaceAll('"','""')+'"' : s;};
    return [fields.join(','),...rows.map(r=>fields.map(k=>quote(r[k])).join(','))].join('\r\n')+'\r\n';
  }
  const api = {csv,inputs,outcomes,predict,action,baseline,metrics,compare,names,toCSV};
  if (typeof module !== 'undefined') module.exports = api;
  root.WorkbenchEngine = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);

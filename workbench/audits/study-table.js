/* Published-study tables: each [data-study-table] section reads its rows (already in the page, or from its CSV),
   filters on every keystroke and sorts on a header click. data-kind="actions" is a release / retest list:
   calls, actions and outcomes read as words, wrong releases turn red, and [data-split] draws the release split. */
(function () {
  'use strict';
  function parseCSV(source) {
    const records = [];
    let row = [], cell = '', quoted = false;
    for (let i = 0; i < source.length; i++) {
      const ch = source[i];
      if (ch === '"') {
        if (quoted && source[i + 1] === '"') { cell += '"'; i++; }
        else quoted = !quoted;
      } else if (ch === ',' && !quoted) {
        row.push(cell); cell = '';
      } else if ((ch === '\n' || ch === '\r') && !quoted) {
        if (ch === '\r' && source[i + 1] === '\n') i++;
        row.push(cell); cell = '';
        if (row.some(value => value !== '')) records.push(row);
        row = [];
      } else cell += ch;
    }
    if (cell || row.length) { row.push(cell); records.push(row); }
    const [head, ...body] = records;
    return { head, body };
  }

  const WORDS = { id: 'ID', ic50: 'IC50', auc: 'AUC', sd: 'SD', pdf: 'PDF', doi: 'DOI', um: 'µM', percent: '%', '24h': '24 h', '72h': '72 h' };
  const NAMES = { call1: 'Call 1', call2: 'Call 2', response: 'Outcome', cutoff1: 'Cutoff 1', cutoff2: 'Cutoff 2', source_locator: 'Source', mean_grayscale_0_255: 'Mean grayscale 0 to 255', grayscale_0_255: 'Grayscale 0 to 255' };
  const name = k => NAMES[k] || k.split('_').map(w => WORDS[w.toLowerCase()] || w).join(' ').replace(/^./, c => c.toUpperCase());
  const isNum = v => v !== '' && Number.isFinite(Number(v));
  /* long decimals show four significant digits; the cell's tip keeps the source value */
  const short = v => (/\.\d{5,}|e-?\d+$/i.test(v) && isNum(v)) ? String(+Number(v).toPrecision(4)) : v;
  const ACTION = { '1': ['report', 'Release sensitive'], '0': ['report', 'Release resistant'], retest: ['retest', 'Retest'] };

  function split(el, body, col) {
    const n = body.length, retest = body.filter(r => r[col.action] === 'retest').length;
    const wrong = body.filter(r => r[col.action] !== 'retest' && r[col.response] !== '' && r[col.action] !== r[col.response]).length;
    const right = n - retest - wrong;
    const part = (k, c, label) => k ? `<i style="width:${100 * k / n}%;background:var(--${c})" aria-description="${k} of ${n} patients: ${label}"></i>` : '';
    el.innerHTML = `<div class="bar-track">${part(right, 'report', 'released, call matches the outcome')}${part(wrong, 'wrong', 'released, call differs from the outcome')}${part(retest, 'retest', 'readouts disagree, sent to retest')}</div>`
      + `<div class="keys"><span class="key"><i class="box" style="background:var(--report)"></i>${right} correct releases</span><span class="key"><i class="box" style="background:var(--wrong)"></i>${wrong} wrong</span><span class="key"><i class="box" style="background:var(--retest)"></i>${retest} retests</span><span class="key">of ${n} patients</span></div>`;
  }

  document.querySelectorAll('[data-study-table]').forEach(async section => {
    const status = section.querySelector('[data-table-status]'), filter = section.querySelector('input[type="search"]');
    const table = section.querySelector('table'), thead = table.querySelector('thead'), tbody = table.querySelector('tbody');
    const actions = section.dataset.kind === 'actions', hide = new Set((section.dataset.hide || '').split(' ').filter(Boolean));
    let data, keep, numeric, col = {}, column = -1, ascending = true;
    function cell(value, i, row) {
      const td = document.createElement('td'), key = data.head[i];
      if (numeric[i]) td.className = 'n';
      if (actions && (key === 'call1' || key === 'call2')) td.textContent = value === '1' ? 'Sensitive' : value === '0' ? 'Resistant' : 'Missing';
      else if (actions && key === 'action' && ACTION[value]) td.innerHTML = `<span class="badge ${ACTION[value][0]}">${ACTION[value][1]}</span>`;
      else if (actions && key === 'response') {
        const wrong = row[col.action] !== 'retest' && value !== '' && row[col.action] !== value;
        td.textContent = (value === '1' ? 'Responder' : value === '0' ? 'Non-responder' : 'Not given') + (wrong ? ' · wrong' : '');
        if (wrong) td.classList.add('wrong');
      } else if (value === 'True' || value === 'true' || value === 'False' || value === 'false') td.textContent = /^t/i.test(value) ? 'Yes' : 'No';
      else if (/^[a-z]+(_[a-z]+)+$/.test(value)) td.textContent = value.replace(/^non_/, 'non-').replace(/_/g, ' ');
      else {
        td.textContent = short(value);
        if (td.textContent !== value) td.title = value;
      }
      return td;
    }
    function render() {
      const query = filter ? filter.value.trim().toLocaleLowerCase() : '';
      const rows = data.body.filter(row => row.join(' ').toLocaleLowerCase().includes(query));
      if (column >= 0) rows.sort((a, b) => {
        const x = a[column], y = b[column];
        const result = isNum(x) && isNum(y) ? Number(x) - Number(y) : x.localeCompare(y, undefined, { numeric: true });
        return ascending ? result : -result;
      });
      tbody.replaceChildren(...rows.map(row => {
        const tr = document.createElement('tr');
        keep.forEach(i => tr.appendChild(cell(row[i], i, row)));
        if (actions && tr.querySelector('td.wrong')) tr.className = 'wrong';
        return tr;
      }));
      thead.querySelectorAll('button').forEach(b => { if (Number(b.dataset.i) === column) b.dataset.dir = ascending ? '↑' : '↓'; else delete b.dataset.dir; });
      if (status) status.textContent = rows.length === data.body.length ? `${data.body.length} rows` : `${rows.length} of ${data.body.length} rows`;
    }
    try {
      if (tbody.rows.length) {
        data = { head: [...thead.querySelectorAll('th')].map(th => th.textContent.trim()), body: [...tbody.rows].map(tr => [...tr.cells].map(td => td.textContent.trim())) };
      } else {
        const response = await fetch(section.dataset.studyTable);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        data = parseCSV(await response.text());
      }
      data.head.forEach((k, i) => { col[k] = i; });
      keep = data.head.map((k, i) => i).filter(i => !hide.has(data.head[i]));
      numeric = data.head.map((k, i) => !(actions && /^(call|action|response)/.test(k)) && data.body.every(r => r[i] === '' || isNum(r[i])) && data.body.some(r => r[i] !== ''));
      const tr = document.createElement('tr');
      keep.forEach(i => {
        const th = document.createElement('th'), button = document.createElement('button');
        if (numeric[i]) th.className = 'n';
        button.type = 'button'; button.dataset.i = i; button.textContent = name(data.head[i]); button.title = `Sort by ${name(data.head[i]).toLowerCase()}`;
        button.onclick = () => { ascending = column === i ? !ascending : true; column = i; render(); };
        th.appendChild(button); tr.appendChild(th);
      });
      thead.replaceChildren(tr);
      if (filter) { filter.placeholder = `Filter ${data.body.length} rows`; filter.oninput = render; }
      const bar = actions && document.querySelector('[data-split]');
      if (bar) split(bar, data.body, col);
      render();
    } catch (error) { if (status) status.textContent = `Table unavailable: ${error.message}`; }
  });
})();

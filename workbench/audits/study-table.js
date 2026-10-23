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

  document.querySelectorAll('[data-study-table]').forEach(async section => {
    const file = section.dataset.studyTable;
    const status = section.querySelector('[data-table-status]');
    const filter = section.querySelector('input[type="search"]');
    const table = section.querySelector('table');
    const thead = table.querySelector('thead');
    const tbody = table.querySelector('tbody');
    const previous = section.querySelector('[data-previous]');
    const next = section.querySelector('[data-next]');
    let data, column = -1, ascending = true, page = 0;
    const pageSize = 50;
    function render() {
      const query = filter.value.trim().toLocaleLowerCase();
      const rows = data.body.filter(row => row.join(' ').toLocaleLowerCase().includes(query));
      if (column >= 0) rows.sort((a, b) => {
        const x = a[column], y = b[column], nx = Number(x), ny = Number(y);
        const result = x !== '' && y !== '' && Number.isFinite(nx) && Number.isFinite(ny)
          ? nx - ny : x.localeCompare(y, undefined, { numeric: true });
        return ascending ? result : -result;
      });
      const pages = Math.max(1, Math.ceil(rows.length / pageSize));
      page = Math.min(page, pages - 1);
      tbody.replaceChildren(...rows.slice(page * pageSize, (page + 1) * pageSize).map(row => {
        const tr = document.createElement('tr');
        row.forEach(value => { const td = document.createElement('td'); td.textContent = value; tr.appendChild(td); });
        return tr;
      }));
      status.textContent = `${rows.length} of ${data.body.length} records, page ${page + 1} of ${pages}`;
      previous.disabled = page === 0;
      next.disabled = page >= pages - 1;
    }
    try {
      const response = await fetch(file);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      data = parseCSV(await response.text());
      thead.replaceChildren();
      const tr = document.createElement('tr');
      data.head.forEach((name, i) => {
        const th = document.createElement('th');
        const button = document.createElement('button');
        button.type = 'button'; button.textContent = name; button.title = `Sort by ${name}`;
        button.onclick = () => { ascending = column === i ? !ascending : true; column = i; page = 0; render(); };
        th.appendChild(button); tr.appendChild(th);
      });
      thead.appendChild(tr);
      filter.oninput = () => { page = 0; render(); };
      previous.onclick = () => { page--; render(); };
      next.onclick = () => { page++; render(); };
      render();
    } catch (error) { status.textContent = `Table unavailable: ${error.message}`; }
  });
})();

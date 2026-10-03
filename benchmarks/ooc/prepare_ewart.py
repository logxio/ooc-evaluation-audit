"""Rebuild Ewart's CSV from the committed, checksum-pinned source workbook."""
import csv
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent


def main():
    manifest = json.loads((ROOT / 'sources.json').read_text())
    spec = next(item for item in manifest['downloads'] if item['id'] == 'ewart')
    source = ROOT / 'raw' / spec['file']
    assert hashlib.sha256(source.read_bytes()).hexdigest() == spec['sha256']
    book = openpyxl.load_workbook(source, read_only=True, data_only=True)
    rows = []
    for sheet in book:
        replicate = Counter()
        for number, (compound, dose, value) in enumerate(list(sheet.values)[1:], 2):
            if value in ('NaN', 'NA', None):
                value = None
            assert isinstance(compound, str) and isinstance(dose, (int, float)) and math.isfinite(dose)
            assert value is None or (isinstance(value, (int, float)) and math.isfinite(value))
            replicate[(compound, dose)] += 1
            rows.append(dict(sheet=sheet.title, source_row=number, compound=compound,
                             concentration_as_published=dose, replicate_within_endpoint=replicate[(compound, dose)],
                             value_as_published=value))
    book.close()
    assert len(rows) == 210 and sum(row['value_as_published'] is not None for row in rows) == 204
    output = ROOT / 'ewart_readings.csv'
    with output.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    assert hashlib.sha256(output.read_bytes()).hexdigest() == '326c494f0ebdae41bd7ea5b425d3697d5e48b5685ac033bb719ff1e7713f3b8c'
    print('Ewart source replay: 210 positions, 204 numeric readings, pinned CSV matched')


if __name__ == '__main__':
    main()

"""Text/cell normalization; PDF layout, figures and spreadsheet styles are not retained."""
import csv
import hashlib
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile


def digest(data):
    return hashlib.sha256(data).hexdigest()


def words(node):
    return " ".join("".join(node.itertext()).split())


def normalize(path, name):
    path = Path(path)
    cells = {}
    text = []
    if path.suffix == '.xml':
        root = ET.parse(path).getroot()
        # Include the full article narrative, references and all captions.
        for i, node in enumerate(root.iter('p'), 1):
            text.append(f'{name}:p{i} {words(node)}')
        for i, node in enumerate(root.iter('article-title'), 1):
            text.insert(0, f'{name}:title{i} {words(node)}')
        for i, node in enumerate(root.iter('table-wrap'), 1):
            label = node.find('label')
            table = words(label) if label is not None else f'Table {i}'
            text.append(f'{name}/{table} {words(node.find("caption")) if node.find("caption") is not None else ""}')
            for r, tr in enumerate(node.iter('tr'), 1):
                for c, cell in enumerate(tr, 1):
                    ref = f'{name}/{table}/R{r}C{c}'
                    cells[ref] = words(cell)
        license_nodes = list(root.iter('license'))
        license_text = '\n'.join(words(n) for n in license_nodes)
    elif path.suffix == '.xlsx':
        ns = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
        rel = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'
        with ZipFile(path) as z:
            strings = []
            if 'xl/sharedStrings.xml' in z.namelist():
                strings = [words(n) for n in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('s:si', ns)]
            targets = {n.attrib['Id']: n.attrib['Target'] for n in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
            for sheet in ET.fromstring(z.read('xl/workbook.xml')).findall('s:sheets/s:sheet', ns):
                target = targets[sheet.attrib[rel]]
                target = target.lstrip('/') if target.startswith('/') else 'xl/' + target
                for cell in ET.fromstring(z.read(target)).findall('.//s:sheetData/s:row/s:c', ns):
                    value = cell.find('s:v', ns)
                    value = value.text if value is not None else ''
                    if cell.attrib.get('t') == 's':
                        value = strings[int(value)]
                    elif cell.attrib.get('t') == 'inlineStr':
                        value = words(cell.find('s:is', ns))
                    if value != '':
                        cells[f'{name}/{sheet.attrib["name"]}/{cell.attrib["r"]}'] = value
        license_text = ''
    elif path.suffix == '.xls':
        import xlrd
        book = xlrd.open_workbook(path)
        for sheet in book.sheets():
            for r in range(sheet.nrows):
                for c in range(sheet.ncols):
                    v = sheet.cell_value(r, c)
                    if v != '':
                        cells[f'{name}/{sheet.name}/R{r+1}C{c+1}'] = str(v)
        license_text = ''
    elif path.suffix == '.pdf':
        result = subprocess.run(['pdftotext', '-layout', str(path), '-'], capture_output=True, check=True)
        for page, body in enumerate(result.stdout.decode().split('\f'), 1):
            for line, value in enumerate(body.splitlines(), 1):
                if value.strip():
                    ref = f'{name}/page{page}/line{line}'
                    cells[ref] = value.strip()
        license_text = ''
    else:
        raise ValueError(f'Unsupported original: {path.suffix}')
    return {'name': name, 'sha256': digest(path.read_bytes()), 'narrative': text,
            'cells': cells, 'license_text': license_text}


def render(document):
    lines = [f'DOCUMENT {document["name"]}', *document['narrative']]
    lines.extend(f'[{k}] {v}' for k, v in document['cells'].items())
    return '\n'.join(lines)

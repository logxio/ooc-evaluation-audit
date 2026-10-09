"""Verify the final bundle hashes and every numeric citation without fitting."""
import sys
sys.dont_write_bytecode = True
from paper_final_common import *
import re

def resolve(obj, field):
    if field.startswith('sum(') and field.endswith(')'):
        values = resolve(obj, field[4:-1])
        return sum(values) if isinstance(values, list) else values
    if field.startswith('/'):
        parts = [p.replace('~1', '/').replace('~0', '~') for p in field[1:].split('/')]
    else:
        parts = [a or b for a, b in re.findall(r'([^\.\[\]]+)|\[([^\]]+)\]', field)]
    def visit(current, remaining):
        if not remaining:
            return current
        part, rest = remaining[0], remaining[1:]
        if isinstance(current, list):
            if '=' in part:
                selected = current
                for condition in part.split(','):
                    key, value = condition.split('=', 1)
                    selected = [r for r in selected if str(r[key]) == value]
                if len(selected) == 1:
                    return visit(selected[0], rest)
                return [visit(r, rest) for r in selected]
            if ':' in part:
                start, end = part.split(':')
                return visit(current[int(start):int(end)], rest)
            if part.isdigit():
                return visit(current[int(part)], rest)
            return [visit(r, remaining) for r in current]
        return visit(current[part], rest)
    return visit(obj, parts)

def csv_value(rows, field):
    match = re.search(r'row\((.*?)\)(?:\.([a-zA-Z0-9_]+))?', field)
    if not match:
        raise ValueError('Unsupported table selector: ' + field)
    predicates, column = match.groups()
    selected = rows
    for predicate in predicates.split(';'):
        key, op, value = re.fullmatch(r'([^<>=]+)(>=|<=|=)(.+)', predicate).groups()
        if op == '=':
            selected = [r for r in selected if r[key] == value]
        elif op == '>=':
            selected = [r for r in selected if float(r[key]) >= float(value)]
        else:
            selected = [r for r in selected if float(r[key]) <= float(value)]
    if field.startswith('count('):
        return len(selected)
    values = [float(r[column]) for r in selected]
    if field.startswith('max('):
        return max(values)
    if len(values) != 1:
        raise ValueError('Citation must select one row: ' + field)
    return values[0]

def run():
    manifest = load(FINAL / 'manifest.json')
    for path, expected in manifest['sha256'].items():
        if sha(ROOT / path) != expected:
            raise ValueError('Bundle hash mismatch: ' + path)
    ledger = load(ROOT / 'results/REDACTIONS.json')['files']
    for record in ledger:
        if record['path'].startswith('results/final/'):
            same(frozen_sha(ROOT / record['path']), record['original_sha256'])
    numbers = load(FINAL / 'numbers.json')
    keys = [r['key'] for r in numbers]
    if len(keys) != len(set(keys)):
        raise ValueError('Duplicate numeric key')
    cache = {}
    for row in numbers:
        path = row['source_file']
        if path not in cache:
            cache[path] = rcsv(ROOT / path) if path.endswith('.csv') else load(ROOT / path)
        source = cache[path]
        if path.endswith('.csv'):
            value = csv_value(source, row['field'])
        else:
            value = resolve(source, row['field'])
        target = value.get('estimate', value.get('point')) if isinstance(value, dict) else value
        same(row['value'], target, row['key'])
        if 'ci95' in row:
            if 'ci95_fields' in row:
                bounds = [resolve(source, field) for field in row['ci95_fields']]
            elif 'ci95_field' in row:
                bounds = resolve(source, row['ci95_field'])
            elif isinstance(value, dict):
                bounds = value['ci95']
            elif row['field'].startswith('/'):
                parent = resolve(source, row['field'].rsplit('/', 1)[0])
                bounds = parent['ci95']
            else:
                parent = resolve(source, row['field'].rsplit('.', 1)[0])
                bounds = parent['ci95']
            same(row['ci95'], bounds, row['key'] + '/ci95')
    return dict(status='verified', input_files=len(manifest['sha256']), numeric_citations=len(numbers),
                analysis_groups=len({r['group'] for r in numbers}), new_fits=0)

if __name__ == '__main__':
    if sys.argv[1:] != ['verify']:
        raise SystemExit('Use: python paper_final_verify.py verify')
    print(json.dumps(run(), indent=2))

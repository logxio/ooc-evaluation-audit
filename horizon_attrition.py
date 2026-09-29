#!/usr/bin/env python3
"""Audit an observed decision horizon and missing-value sensitivity in chip data."""

import argparse
import hashlib
import io
import json
import random
import statistics
import xml.etree.ElementTree as ET
import urllib.request
import zipfile
from pathlib import Path


SOURCE_URL = ('https://media.springernature.com/original/springer-static/esm/'
              'art%3A10.1038%2Fs42003-021-02526-y/MediaObjects/'
              '42003_2021_2526_MOESM4_ESM.zip')
SOURCE_SHA256 = '2c662942b871ff10420cf186fb3a45090a76d0ab7bf6044b06f2f6731c73b220'
X = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
ARMS = ('mono', 'gap24', 'gap72')
FILE_MAP = {
    'chip_day7': 'figure raw data Excel/fig 5a raw data.xlsx',
    'mouse_day7': 'figure raw data Excel/fig 5b 01 raw data.xlsx',
    'mouse_day15': 'figure raw data Excel/fig 5b 02 raw data.xlsx',
    'mouse_day35': 'figure raw data Excel/fig 5b 03 raw data.xlsx',
}


def column(ref):
    number = 0
    for letter in ref.rstrip('0123456789'):
        number = number * 26 + ord(letter) - 64
    return number


def sheet_path(archive, sheet_name):
    rel = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'
    book = ET.fromstring(archive.read('xl/workbook.xml'))
    rid = next(s.attrib[rel] for s in book.iter(X+'sheet') if s.attrib['name'] == sheet_name)
    rels = ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))
    target = next(r.attrib['Target'] for r in rels if r.attrib['Id'] == rid)
    return target.lstrip('/') if target.startswith('/xl/') else 'xl/' + target


def cells(xlsx_bytes, sheet_name=None):
    with zipfile.ZipFile(io.BytesIO(xlsx_bytes)) as archive:
        strings = []
        if 'xl/sharedStrings.xml' in archive.namelist():
            root = ET.fromstring(archive.read('xl/sharedStrings.xml'))
            strings = [''.join(t.text or '' for t in node.iter(X+'t'))
                       for node in root.iter(X+'si')]
        path = sheet_path(archive, sheet_name) if sheet_name else 'xl/worksheets/sheet1.xml'
        root = ET.fromstring(archive.read(path))
        output = []
        for cell in root.iter(X+'c'):
            ref = cell.attrib['r']
            value = cell.find(X+'v')
            text = value.text if value is not None else ''
            if cell.attrib.get('t') == 's' and text:
                text = strings[int(text)]
            if text:
                output.append((ref, column(ref), text))
        return output


def mouse_groups(all_cells):
    headers = sorted((col, value) for ref, col, value in all_cells
                     if ref.endswith('1') and value != 'Tumour size')
    groups = {}
    for index, (start, label) in enumerate(headers):
        end = headers[index+1][0] if index+1 < len(headers) else 10**6
        lower = label.lower()
        if 'azd0156' in lower:
            arm = 'gap72' if '72h gap' in lower else 'gap24'
        elif 'dmso' in lower:
            arm = 'mono'
        else:
            continue
        values = []
        for ref, col, value in all_cells:
            if col < start or col >= end or ref.endswith('1'):
                continue
            try:
                values.append(float(value))
            except ValueError:
                pass
        groups[arm] = values
    assert set(groups) == set(ARMS), (headers, groups)
    return groups


def chip_groups(all_cells):
    mapping = {'D': 'gap72', 'E': 'gap24', 'F': 'mono'}
    groups = {arm: [] for arm in ARMS}
    for ref, _, value in all_cells:
        arm = mapping.get(ref[0])
        if arm and not ref.endswith('1'):
            try:
                groups[arm].append(float(value))
            except ValueError:
                pass
    assert all(groups.values())
    return groups


def interval(a, b, seed):
    rng = random.Random(seed)
    differences = []
    for _ in range(10000):
        av = statistics.mean(rng.choice(a) for _ in a)
        bv = statistics.mean(rng.choice(b) for _ in b)
        differences.append(av-bv)
    differences.sort()
    return [round(differences[249], 6), round(differences[9749], 6)]


def analyze(groups, day):
    means = {arm: statistics.mean(groups[arm]) for arm in ARMS}
    ordering = sorted(ARMS, key=means.get)
    pairs = {}
    for i, a in enumerate(ARMS):
        for b in ARMS[i+1:]:
            pairs[a+'_minus_'+b] = {
                'mean_difference': round(means[a]-means[b], 6),
                'bootstrap_95': interval(groups[a], groups[b], 52+day*10+i),
            }
    return {'n': {arm: len(groups[arm]) for arm in ARMS},
            'means': {arm: round(means[arm], 6) for arm in ARMS},
            'best_to_worst': ordering, 'pairwise': pairs}


def adjusted_interval(a, b, seed):
    rng = random.Random(seed)
    differences = []
    for _ in range(10000):
        av = statistics.mean(rng.choice(a) for _ in a)
        bv = statistics.mean(rng.choice(b) for _ in b)
        differences.append(av-bv)
    differences.sort()
    return [round(differences[124], 6), round(differences[9874], 6)]


def certificate(groups, day):
    comparisons = {}
    for j, other in enumerate(('mono', 'gap72')):
        ci = adjusted_interval(groups['gap24'], groups[other], 53+day*10+j)
        comparisons[other] = {
            'gap24_minus_other': round(statistics.mean(groups['gap24'])-
                                       statistics.mean(groups[other]), 6),
            'bonferroni_97_5_two_sided': ci,
            'observed_advantage': ci[1] < 0,
        }
    result = {'n_of_15': {arm: len(values) for arm, values in groups.items()},
              'comparisons': comparisons,
              'observed_double_advantage': all(v['observed_advantage']
                                               for v in comparisons.values())}
    if day == 35:
        low = min(v for values in groups.values() for v in values)
        high = max(v for values in groups.values() for v in values)
        bounds = {}
        for arm, values in groups.items():
            missing = 15-len(values)
            bounds[arm] = {
                'missing': missing,
                'mean_if_missing_at_observed_min': round((sum(values)+missing*low)/15, 6),
                'mean_if_missing_at_observed_max': round((sum(values)+missing*high)/15, 6),
            }
        result['observed_global_range'] = [low, high]
        result['full_15_mean_bounds'] = bounds
        result['missingness_robust_advantage'] = all(
            bounds['gap24']['mean_if_missing_at_observed_max'] <
            bounds[other]['mean_if_missing_at_observed_min']
            for other in ('mono', 'gap72'))
    return result


ZHAI_URL = ('https://media.springernature.com/original/springer-static/esm/'
            'art%3A10.1038%2Fs41467-024-48616-3/MediaObjects/'
            '41467_2024_48616_MOESM13_ESM.xlsx')
ZHAI_SHA256 = 'd09231a19108faf96f89973a565b02e5115de1f98a744b1b751168f5b56f8ee8'
ZHAI_DESIGNS = {
    'figure_3d': {'sheet': 'figure 3', 'preferred': ('effective',), 'rejected': 'ineffective',
                  'arms': (('Pos', 'effective'), ('Neg', 'ineffective'), ('Ctrl', 'control'))},
    'figure_4c': {'sheet': 'figure 4', 'preferred': ('single_effective', 'combination_effective'),
                  'rejected': 'ineffective',
                  'arms': (('Single effective', 'single_effective'), ('Negative', 'ineffective'),
                           ('Combinational Effective', 'combination_effective'), ('Ctrl', 'control'))},
}


def fetch(path, url, expected):
    if path:
        data = path.read_bytes()
    else:
        with urllib.request.urlopen(url, timeout=60) as response:
            data = response.read()
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        raise ValueError(f'Source SHA256 mismatch: {actual}')
    return data


def bonferroni_interval(a, b, seed, comparisons):
    rng = random.Random(seed)
    differences = sorted(statistics.mean(rng.choice(a) for _ in a) -
                         statistics.mean(rng.choice(b) for _ in b) for _ in range(10000))
    tail = int(10000 * 0.05 / comparisons / 2)
    return [round(differences[tail-1], 6), round(differences[10000-tail-1], 6)]


def tumour_block(table, design):
    """Per-mouse tumour volumes from the first tumour-volume block of a sheet."""
    rows = {}
    for ref, col, value in table:
        rows.setdefault(int(ref[len(ref.rstrip('0123456789')):]), {})[col] = value
    header = next(r for r in sorted(rows) if any(str(v).startswith(design['arms'][0][0]) for v in rows[r].values()))
    stop = min([r for r in rows if r > header and any(str(v).startswith('Original data') for v in rows[r].values())] + [10**6])
    mice = {}
    for col, label in rows[header].items():
        for prefix, arm in design['arms']:
            if str(label).startswith(prefix):
                mice[col] = (arm, str(label).strip())
    series = {col: {} for col in mice}
    tcol = min(mice) - 1
    for r in sorted(rows):
        if header < r < stop and tcol in rows[r]:
            try:
                time = int(float(rows[r][tcol]))
            except ValueError:
                continue
            for col in mice:
                if col in rows[r]:
                    series[col][time] = float(rows[r][col])
    return mice, series


def zhai_certificate(design, mice, series, relative, seed_base):
    arms = {}
    for col, (arm, _) in mice.items():
        arms.setdefault(arm, []).append(col)
    compared = list(design['preferred']) + [design['rejected']]
    times = sorted({t for s in series.values() for t in s})
    per_time = {}
    for t in times:
        value = {col: series[col][t] / series[col][1] if relative else series[col][t]
                 for col in mice if t in series[col] and (not relative or 1 in series[col])}
        groups = {arm: [value[c] for c in cols if c in value] for arm, cols in arms.items()}
        comparisons = {}
        for j, arm in enumerate(design['preferred']):
            a, b = groups[arm], groups[design['rejected']]
            ci = bonferroni_interval(a, b, seed_base + t*10 + j, len(design['preferred']))
            pairs = [1.0 if x < y else 0.5 if x == y else 0.0 for x in a for y in b]
            comparisons[arm] = {'difference': round(statistics.mean(a) - statistics.mean(b), 6),
                                'adjusted_interval': ci, 'confirmed': ci[1] < 0,
                                'per_mouse_concordance': round(sum(pairs) / len(pairs), 6)}
        low = min(v for arm in compared for v in groups[arm])
        high = max(v for arm in compared for v in groups[arm])
        bounds = {arm: {'nominal': len(arms[arm]), 'observed': len(groups[arm]),
                        'lower': round((sum(groups[arm]) + (len(arms[arm])-len(groups[arm]))*low)/len(arms[arm]), 6),
                        'upper': round((sum(groups[arm]) + (len(arms[arm])-len(groups[arm]))*high)/len(arms[arm]), 6)}
                  for arm in compared}
        control = bonferroni_interval(groups[design['rejected']], groups['control'], seed_base + 5000 + t, 1)
        per_time[t] = {
            'observed': {arm: len(g) for arm, g in groups.items()},
            'comparisons': comparisons,
            'confirmed_among_observed': all(c['confirmed'] for c in comparisons.values()),
            'full_n_bounds': bounds,
            'attrition_robust': all(bounds[arm]['upper'] < bounds[design['rejected']]['lower']
                                    for arm in design['preferred']),
            'rejected_minus_control': {'difference': round(statistics.mean(groups[design['rejected']]) -
                                                           statistics.mean(groups['control']), 6),
                                       'interval_95': control},
        }
    confirmed = [t for t in times if per_time[t]['confirmed_among_observed']]
    onset = next((t for t in times if all(per_time[u]['confirmed_among_observed'] for u in times if u >= t)), None)
    complete = [t for t in times if all(per_time[t]['full_n_bounds'][arm]['observed'] ==
                                        per_time[t]['full_n_bounds'][arm]['nominal'] for arm in compared)]
    return {'administrations': times, 'first_confirmed': confirmed[0] if confirmed else None,
            'stable_confirmation_from': onset, 'last_complete_administration': max(complete) if complete else None,
            'by_administration': {str(t): per_time[t] for t in times}}


def zhai(data):
    output = {}
    for key, design in ZHAI_DESIGNS.items():
        mice, series = tumour_block(cells(data, design['sheet']), design)
        seed = 55000 + (1000 if key == 'figure_4c' else 0)
        output[key] = {'mice': {arm: sum(1 for a, _ in mice.values() if a == arm)
                                for arm in dict.fromkeys(a for a, _ in mice.values())},
                       'relative_volume': zhai_certificate(design, mice, series, True, seed),
                       'absolute_volume': zhai_certificate(design, mice, series, False, seed + 500)}
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-zip', type=Path, help='Optional original Petreus source ZIP')
    parser.add_argument('--zhai-xlsx', type=Path, help='Optional original Zhai source XLSX')
    parser.add_argument('--out', type=Path, help='Optional aggregate JSON output')
    args = parser.parse_args()
    data = fetch(args.source_zip, SOURCE_URL, SOURCE_SHA256)
    actual = hashlib.sha256(data).hexdigest()
    results, certificates = {}, {}
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for timepoint, name in FILE_MAP.items():
            table = cells(archive.read(name))
            groups = chip_groups(table) if timepoint == 'chip_day7' else mouse_groups(table)
            results[timepoint] = analyze(groups, int(timepoint.rsplit('day', 1)[1]))
            if timepoint.startswith('mouse_'):
                certificates[timepoint] = certificate(groups, int(timepoint.rsplit('day', 1)[1]))
    chip_order = results['chip_day7']['best_to_worst']
    for key in ('mouse_day7', 'mouse_day15', 'mouse_day35'):
        mouse_order = results[key]['best_to_worst']
        inversions = sum((chip_order.index(a)-chip_order.index(b)) *
                         (mouse_order.index(a)-mouse_order.index(b)) < 0
                         for i, a in enumerate(ARMS) for b in ARMS[i+1:])
        results[key]['inversions_vs_chip'] = inversions
        results[key]['kendall_tau_vs_chip'] = round(1-2*inversions/3, 6)
    payload = {
        'schema': 'horizon.attrition.decision.certificate.v1',
        'source_sha256': actual,
        'source': 'https://www.nature.com/articles/s42003-021-02526-y',
        'results': results,
        'certificates': certificates,
        'limits': ['One SW620 cell line; no patient outcome.',
                   'Schedules are matched, observations are not paired across assay systems or timepoints.',
                   'Numeric mouse cells in the source tables are fewer than the nominal 15 per arm; missing mechanism and mouse identities are unknown.',
                   'The observed day-35 range is a sensitivity scenario, not a biologically justified bound.',
                   'The authors already reported the main 24-hour efficacy trend.'],
    }
    zhai_bytes = fetch(args.zhai_xlsx, ZHAI_URL, ZHAI_SHA256)
    payload['schema'] = 'horizon.attrition.decision.certificate.v2'
    payload['zhai2024'] = {
        'source': 'https://doi.org/10.1038/s41467-024-48616-3',
        'source_sha256': ZHAI_SHA256,
        **zhai(zhai_bytes),
        'limits': ['MDA-MB-231 xenografts; each mouse was treated according to a chip screen of its own tumour cells.',
                   'Chip readouts and the tumour table share no published per-mouse key; arms are the authors\' chip-assigned treatment groups.',
                   'Later administrations have missing tumour volumes without a stated mechanism.',
                   'The authors already reported suppression in chip-effective groups.'],
    }
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, indent=2) + '\n')
    print(json.dumps(payload, indent=2))


if __name__ == '__main__':
    main()

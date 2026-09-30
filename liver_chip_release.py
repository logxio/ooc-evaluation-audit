#!/usr/bin/env python3
"""Run the two-readout release contract on a commercial perfused Liver-Chip.

Source: Ewart et al. 2022, Communications Medicine (CC BY 4.0), the NCBI open-access XML.
Table 1 gives each drug's Garside clinical liver-injury rank (1 severe ... 5 none); Table 4
gives each drug's margin-of-safety-like value (free IC50 over total human Cmax) for chips
from hepatocyte donor 1, donor 2, both donors combined, and 3D spheroids. As in the paper's
Table 6, a chip value below 375 (spheroid: 2250) calls the drug toxic, and a censored value
('>x', no IC50 reached) calls it safe; ranks 1-3 are hepatotoxic.

The two readouts are the two donors' chips, on the drugs run in both. A call is released
when the donors agree and sent to a third-donor retest when they disagree. The script
checks the transcription against the paper's own counts, then reports releases, the
break-even retest cost against each alternative (the share of disagreements that
alternative gets wrong), and the released-accuracy forecast from each donor's accuracy,
under independence and with the error correlation carried over from the patient settings.
"""

import argparse
import hashlib
import json
import math
import re
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ARTICLE = 'https://doi.org/10.1038/s43856-022-00209-1'
SOURCE_URL = 'https://pmc-oa-opendata.s3.amazonaws.com/PMC9727064.1/PMC9727064.1.xml'
SOURCE_SHA256 = 'f7209ddfd62008ef853fd18946c5162f6581ced639f3f8891945a4eb8a00ac5c'
CHIP_CUT, SPHEROID_CUT = 375.0, 2250.0
COSTS = (0.10, 0.25, 0.50)
# Mean correlation between the two readouts' right/wrong indicators over the six patient
# settings in release_certificate.py (colorectal chips, osteosarcoma and blind organoids).
RHO_PATIENT_SETTINGS = 0.3124


def source(path):
    if path:
        data = path.read_bytes()
    else:
        with urllib.request.urlopen(SOURCE_URL, timeout=60) as response:
            data = response.read()
    actual = hashlib.sha256(data).hexdigest()
    if actual != SOURCE_SHA256:
        raise ValueError(f'{SOURCE_URL} SHA256 mismatch: {actual}')
    return data


def tables(root):
    out = []
    for wrap in root.iter('table-wrap'):
        caption = ' '.join(''.join(wrap.find('caption').itertext()).split())
        foot = wrap.find('table-wrap-foot')
        rows = [[' '.join(''.join(c.itertext()).split()) for c in tr if c.tag in ('td', 'th')]
                for tr in wrap.iter('tr')]
        out.append({'caption': caption, 'rows': rows,
                    'foot': ' '.join(''.join(foot.itertext()).split()) if foot is not None else ''})
    return out


def value(text):
    """Return (number, censored) or None when the drug was not tested."""
    text = text.replace(',', '').strip()
    if text in ('–', '-', ''):
        return None
    censored = text.startswith('>')
    return float(text.lstrip('>').strip()), censored


def call(entry, cut):
    if entry is None:
        return None
    number, censored = entry
    return int(not censored and number < cut)


def counts(calls, truth):
    pairs = [(c, t) for c, t in zip(calls, truth) if c is not None]
    return {'tp': sum(c and t for c, t in pairs), 'tn': sum(not c and not t for c, t in pairs),
            'fp': sum(c and not t for c, t in pairs), 'fn': sum(not c and t for c, t in pairs)}


def published(table):
    out = {}
    for row in table['rows'][1:]:
        out[row[0]] = dict(zip(('tp', 'tn', 'fp', 'fn'), map(int, row[1:5])))
    return out


def forecast(p1, p2, rho):
    k = rho * math.sqrt(p1 * (1 - p1) * p2 * (1 - p2))
    right, wrong = p1 * p2 + k, (1 - p1) * (1 - p2) + k
    return round(right / (right + wrong), 4), round(right + wrong, 4)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--xml', type=Path, help='local copy of the NCBI open-access XML')
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    root = ET.fromstring(source(args.xml))
    license_text = ' '.join(''.join(root.find('.//license').itertext()).split())
    found = tables(root)
    drugs_t = next(t for t in found if t['caption'].startswith('Small-molecule drugs used'))
    mos_t = next(t for t in found if t['caption'].startswith('Calculation of margin of safety'))
    perf_t = next(t for t in found if t['caption'].startswith('Sensitivity and specificity') and '375' in t['foot'])
    drug_rows, mos_rows = drugs_t['rows'][1:], mos_t['rows'][1:]
    assert len(drug_rows) == len(mos_rows) == 27
    rows = []
    for d, m in zip(drug_rows, mos_rows):
        name = d[0] or m[0]
        # Table 1 leaves one name cell empty in the XML; row order and its pair
        # ('matched with Clozapine') identify it as the drug Table 4 names in that row.
        assert name == m[0], (d, m)
        rows.append({'drug': name, 'garside_rank': int(d[4]), 'hepatotoxic': int(int(d[4]) <= 3),
                     'donor1': call(value(m[1]), CHIP_CUT), 'donor2': call(value(m[2]), CHIP_CUT),
                     'both_donors': call(value(m[3]), CHIP_CUT), 'spheroid': call(value(m[4]), SPHEROID_CUT)})
    truth = [r['hepatotoxic'] for r in rows]
    recomputed = {name: counts([r[key] for r in rows], truth)
                  for name, key in (('Chip donor 1', 'donor1'), ('Chip donor 2', 'donor2'),
                                    ('Chip both donors', 'both_donors'), ('Spheroid', 'spheroid'))}
    printed = published(perf_t)
    check = {name: {'published': printed[name], 'recomputed': recomputed[name],
                    'match': printed[name] == recomputed[name]} for name in printed}
    assert check['Chip donor 1']['match'] and check['Chip both donors']['match'], check

    both = [r for r in rows if r['donor1'] is not None and r['donor2'] is not None]
    n = len(both)
    t = [r['hepatotoxic'] for r in both]
    d1, d2 = [r['donor1'] for r in both], [r['donor2'] for r in both]
    either = [int(a or b) for a, b in zip(d1, d2)]
    agree = [a == b for a, b in zip(d1, d2)]
    released = sum(agree)
    wrong = sum(g and a != y for g, a, y in zip(agree, d1, t))
    disagree = [r for r, g in zip(both, agree) if not g]
    right1 = [a == y for a, y in zip(d1, t)]
    right2 = [b == y for b, y in zip(d2, t)]
    p1, p2 = sum(right1) / n, sum(right2) / n
    errors = {'donor 1 alone': n - sum(right1), 'donor 2 alone': n - sum(right2),
              'either donor flags': sum(e != y for e, y in zip(either, t))}
    retests = n - released
    shared = [r for r, a, b in zip(both, right1, right2) if not a and not b]
    observed = (released - wrong) / released
    result = {
        'schema': 'liver_chip.release.v1', 'article': ARTICLE, 'source_url': SOURCE_URL,
        'source_sha256': SOURCE_SHA256, 'license': license_text,
        'rule': 'chip toxic if MOS-like value < 375 (spheroid < 2250), censored > value = safe; Garside rank 1-3 hepatotoxic',
        'transcription_check_vs_table6': check,
        'drugs': len(rows), 'hepatotoxic': sum(truth),
        'two_donor_setting': {
            'drugs': n, 'hepatotoxic': sum(t), 'safe': n - sum(t),
            'readout_accuracy': [round(p1, 4), round(p2, 4)],
            'released': released, 'released_correct': released - wrong, 'released_wrong': wrong, 'retests': retests,
            'disagreements': [{'drug': r['drug'], 'hepatotoxic': r['hepatotoxic'], 'donor1': r['donor1'], 'donor2': r['donor2']} for r in disagree],
            'shared_misses': [{'drug': r['drug'], 'garside_rank': r['garside_rank']} for r in shared],
            'full_call_errors': errors,
            'break_even_retest_cost': {
                'vs donor 1 alone': round(sum(not a for r, a in zip(both, right1) if r in disagree) / len(disagree), 4),
                'vs donor 2 alone': round(sum(not b for r, b in zip(both, right2) if r in disagree) / len(disagree), 4),
                'vs either donor flags': round(sum(not r['hepatotoxic'] for r in disagree) / len(disagree), 4)},
            'cost_per_drug': {str(c): {'release_or_retest': round((wrong + c * retests) / n, 4),
                                       **{k: round(v / n, 4) for k, v in errors.items()}} for c in COSTS},
            'released_accuracy': round(observed, 4),
            'forecast_independent': dict(zip(('released_accuracy', 'released_share'), forecast(p1, p2, 0.0))),
            'forecast_rho_from_patient_settings': dict(zip(('released_accuracy', 'released_share'), forecast(p1, p2, RHO_PATIENT_SETTINGS))),
            'rho_carried': RHO_PATIENT_SETTINGS,
            'observed_released_share': round(released / n, 4)},
        'rows': rows}
    if args.out:
        args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'rows'}, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()

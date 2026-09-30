#!/usr/bin/env python3
"""Freeze a third blind test of the two-readout release rule on a metastatic colorectal cancer cohort.

Wang et al., Cell Reports Medicine 2023 (doi:10.1016/j.xcrm.2023.101335, CC BY-NC-ND 4.0): tumour
organoids from 82 community-cohort patients and 19 patients of the FORECAST-1 study, each tested
with single-agent 5-FU, oxaliplatin and SN-38 (the active metabolite of irinotecan) and with the
5-FU-oxaliplatin and 5-FU-SN-38 combinations (Table S4: AUC for single agents, mean pan-matrix
viability for combinations; lower means a stronger response).

The rule is the one already public in blind_consensus.py and blind2_predict.py, unchanged: a readout
calls a patient sensitive when the value is at or below the cohort median, a patient's organoid
lines are averaged first, and a regimen call is released only when its two drugs agree; otherwise
the patient is sent to retest. Because the regimens appear only in the clinical tables, a call is
frozen here for both regimen pairs and both combination readouts of every patient, and the scoring
script later takes the pair that matches each treatment.

Only Table S4 is read here. The treatment and outcome tables (Tables S5 and S8 in Document S1, and
Figures 4B and 5C) have not been opened. The source file is downloaded at run time and never
redistributed; the output holds calls and cohort medians, not the organoid values.
"""

import argparse
import hashlib
import io
import json
import urllib.request

import openpyxl

from blind_consensus import OBJECTIVE_RESPONSE, DISEASE_CONTROL, calls
from blind2_predict import CRLM_REGIMENS, pair_calls

ARTICLE = 'https://doi.org/10.1016/j.xcrm.2023.101335'
READOUT_URL = 'https://pmc-oa-opendata.s3.amazonaws.com/PMC10783557.1/mmc4.xlsx'
READOUT_SHA256 = 'c769732edc1ef21bdf8981bbf6ffa141c390a1a5af839a908a63e86ed1b165a9'
CLINICAL_URL = 'https://pmc-oa-opendata.s3.amazonaws.com/PMC10783557.1/mmc1.pdf'
CLINICAL_SHA256 = 'b2357dfaf12ea45aafa7b0250751ed510af59793e53258ed4c3ff1852b166a00'
COLUMNS = {'5-FU': 'AUC_5FU', 'Oxaliplatin': 'AUC_Oxaliplatin', 'Irinotecan': 'AUC_SN38',
           'FOLFOX combination': 'Pan-matrix viability_FOLFOX', 'FOLFIRI combination': 'Pan-matrix viability_FOLFIRI'}
PAIRS = (('5-FU', 'Oxaliplatin'), ('5-FU', 'Irinotecan'))
COMBINATION_FOR_PAIR = {'5-FU+Oxaliplatin': 'FOLFOX combination', '5-FU+Irinotecan': 'FOLFIRI combination'}
ENDPOINTS = {
    'unit': 'treatment (patient x regimen line) listed in Table S5 (community cohort) or Table S8 (FORECAST-1); '
            'a patient with two eligible regimens contributes two treatments, reported also as first eligible treatment per patient',
    'eligible_regimens': {k: list(v) for k, v in CRLM_REGIMENS.items()},
    'regimen_rule': 'antibodies added to a backbone are ignored; single-agent regimens (5-FU or capecitabine alone, '
                    'irinotecan or oxaliplatin alone, TAS-102, regorafenib and others) and regimens outside the map are not evaluable; '
                    'capecitabine counts as 5-FU',
    'clinical_benefit_primary': 'the authors\' clinical benefit: complete response, partial response, or stable disease for '
                                'more than 24 weeks = responder; otherwise non-responder. Where the table gives best response '
                                'and duration instead of the benefit label, the same definition is applied to them',
    'disease_control_secondary': DISEASE_CONTROL,
    'objective_response_secondary': OBJECTIVE_RESPONSE,
    'other_entries': 'not evaluable',
}
PRIMARY = ('all eligible treatments of both cohorts pooled, patient-level mean of organoid lines, calls from the '
           'median of all 101 patients in Table S4, the regimen\'s two drugs, clinical benefit endpoint')
SECONDARY = ('medians taken within each cohort (82 community, 19 FORECAST-1); each cohort alone; first eligible '
             'treatment per patient; disease control and objective response endpoints')
ASSERTIONS = [
    'P1. In the primary analysis the two single readouts share more wrong calls than independence predicts, '
    'n(1-p1)(1-p2), where p1 and p2 are the readouts\' observed accuracies on the same treatments.',
    'P2. In the primary analysis the observed accuracy of released calls is within 0.09 of p1*p2 / (p1*p2 + (1-p1)*(1-p2)).',
    'P3. In any analysis where the weaker readout is not better than a coin flip (min(p1, p2) <= 0.5), released '
    'calls are not more accurate than the better readout alone.',
    'P4. In the primary analysis the organoid readout of the matching combination, split at its own median, '
    'classifies at least as many treatments correctly as the better single readout.',
    'Checked, not predicted: when p1 + p2 > 1, released accuracy falls below the formula exactly when shared wrong '
    'calls exceed the independence count; the two break-even retest costs sum to 1.',
]


def fetch():
    with urllib.request.urlopen(READOUT_URL, timeout=120) as response:
        blob = response.read()
    digest = hashlib.sha256(blob).hexdigest()
    if digest != READOUT_SHA256:
        raise ValueError(f'Table S4 changed: {digest}')
    return blob


def read_table(blob):
    sheet = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True).worksheets[0]
    rows = list(sheet.iter_rows(values_only=True))
    header = list(rows[0])
    col = {name: header.index(name) for name in ('PDTO ID', 'Cohort', *COLUMNS.values())}
    lines = {}
    for row in rows[1:]:
        if row[col['PDTO ID']] is None:
            continue
        lines[row[col['PDTO ID']]] = {'cohort': row[col['Cohort']],
                                      'values': {k: float(row[col[v]]) for k, v in COLUMNS.items()}}
    return lines


def patient_of(line):
    """WCB015LM and WCB015T are two organoid lines of patient WCB015."""
    digits = ''.join(ch for ch in line[3:] if ch.isdigit())
    return line[:3] + digits[:3]


def by_patient(lines):
    grouped = {}
    for line, rec in lines.items():
        grouped.setdefault(patient_of(line), []).append(rec)
    values, cohort = {}, {}
    for patient, recs in grouped.items():
        assert len({r['cohort'] for r in recs}) == 1, patient
        cohort[patient] = recs[0]['cohort']
        values[patient] = {k: sum(r['values'][k] for r in recs) / len(recs) for k in COLUMNS}
    return values, cohort, {p: sorted(l for l in lines if patient_of(l) == p) for p in grouped}


def freeze(values):
    sensitive, medians = calls(values)
    out = {}
    for patient in sorted(values):
        s = sensitive[patient]
        pairs = pair_calls(s, PAIRS)
        for key, combo in COMBINATION_FOR_PAIR.items():
            pairs[key]['combination_readout'] = 'responder' if s[combo] else 'non_responder'
        out[patient] = {'sensitive': {k: s[k] for k in COLUMNS}, 'pairs': pairs}
    return {'medians': {k: round(m, 6) for k, m in medians.items()}, 'patients': out}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--out', default='blind3_predictions.json')
    args = parser.parse_args()
    lines = read_table(fetch())
    values, cohort, line_map = by_patient(lines)
    assert len(lines) == 103 and len(values) == 101, (len(lines), len(values))
    whole = freeze(values)
    within = {c: freeze({p: v for p, v in values.items() if cohort[p] == c}) for c in sorted(set(cohort.values()))}
    result = {'schema': 'blind3.consensus.predictions.v1', 'rule_source': 'blind_consensus.calls, blind2_predict.pair_calls',
              'rule': 'per readout, sensitive if value <= cohort median; release only when the two readouts agree',
              'source': {'article': ARTICLE, 'license': 'CC BY-NC-ND 4.0', 'readout_file': READOUT_URL,
                         'readout_sha256': READOUT_SHA256, 'readout_table': 'Table S4 (processed drug sensitivity)',
                         'clinical_file': CLINICAL_URL, 'clinical_sha256': CLINICAL_SHA256,
                         'clinical_tables': 'Tables S5 and S8 (Document S1) and Figures 4B and 5C, not opened before this file'},
              'endpoints': ENDPOINTS, 'primary_analysis': PRIMARY, 'secondary_analyses': SECONDARY, 'assertions': ASSERTIONS,
              'patients': {p: {'cohort': cohort[p], 'organoid_lines': line_map[p]} for p in sorted(values)},
              'calls': {'whole_table_median': whole, 'within_cohort_median': within}}
    with open(args.out, 'w') as handle:
        json.dump(result, handle, indent=1, sort_keys=True)
        handle.write('\n')
    released = {k: sum(v['pairs'][k]['release'] for v in whole['patients'].values()) for k in COMBINATION_FOR_PAIR}
    print(json.dumps({'patients': len(values), 'cohorts': {c: sum(1 for p in cohort if cohort[p] == c) for c in within},
                      'whole_table_medians': whole['medians'], 'released_of_101': released}, indent=1))


if __name__ == '__main__':
    main()

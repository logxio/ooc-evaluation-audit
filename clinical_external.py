#!/usr/bin/env python3
"""Freeze and score a source-specific external clinical action list.

Cartry et al. (2023), doi:10.1186/s13046-023-02853-4, CC BY 4.0.
prepare reads only Supplementary Table 3 columns A/B/D/E/F. score opens
clinical column C only after checking the immutable prediction manifest.
This is a literature replay with known aggregate results, not a clinical trial.
"""
import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parent
URL = 'https://media.springernature.com/original/springer-static/esm/art%3A10.1186%2Fs13046-023-02853-4/MediaObjects/13046_2023_2853_MOESM1_ESM.xlsx'
SOURCE_SHA = '3f9159f9d644e89274c25b95e321ffbefbaa98dfaa98a86c660c32e11b559ffc'
NS = {'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}

def sha(data):
    return hashlib.sha256(data).hexdigest()

def read_cells(data, columns):
    """Return selected columns only; outcome cells never enter prepare output."""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        strings = []
        if 'xl/sharedStrings.xml' in z.namelist():
            strings = [''.join(n.itertext()) for n in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('s:si', NS)]
        book = ET.fromstring(z.read('xl/workbook.xml'))
        sheet = next(s for s in book.findall('s:sheets/s:sheet', NS) if s.attrib['name'] == 'Sup Table 3')
        rel = sheet.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']
        links = ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
        target = next(x.attrib['Target'] for x in links if x.attrib['Id'] == rel)
        path = target.lstrip('/') if target.startswith('/') else 'xl/' + target
        cells = {}
        for c in ET.fromstring(z.read(path)).findall('.//s:c', NS):
            address = c.attrib['r']
            col = ''.join(x for x in address if x.isalpha())
            if col not in columns:
                continue
            v = c.findtext('s:v', default='', namespaces=NS)
            if c.attrib.get('t') == 's':
                v = strings[int(v)]
            elif c.attrib.get('t') == 'inlineStr':
                v = ''.join(c.find('s:is', NS).itertext())
            cells[address] = v
        return cells

def prepare(data):
    cells = read_cells(data, {'A','B','D','E','F'})
    cases = []
    for row in range(4, 15):
        patient, setting = cells[f'A{row}'], cells[f'B{row}'].strip().lower()
        scores = [float(cells[f'{col}{row}']) for col in ['E','F'] if cells.get(f'{col}{row}', '').strip() not in ('','NA')]
        eligible = setting == 'metastasis' and bool(scores)
        cases.append(dict(patient=patient, source_row=row, setting=setting,
                          regimen=cells[f'D{row}'], scores=scores,
                          proxy=('capecitabine' in cells[f'D{row}'].lower() or 'SN-38' in cells[f'D{row}']),
                          eligible=eligible, prediction=int(max(scores) > 1.9) if eligible else None,
                          action='report_for_research' if eligible else 'clinical_linkage_review',
                          reason='Metastatic setting with measured regimen components' if eligible else 'Adjuvant outcome mixes drug response with surgical disease removal'))
    return dict(schema='external.clinical.freeze.v1', study='Cartry2023',
                source_url=URL, source_sha256=sha(data),
                rule=dict(score='maximum of reported component scores', threshold=1.9, comparison='strictly greater',
                          origin='Published hit threshold; no target outcome used to fit or select a threshold',
                          transfer='Source-specific scores; rectal size-ratio cutoff 0.31875 is not applied here'),
                primary=dict(eligibility='Every Sup Table 3 metastatic patient with measured regimen scores; one row per patient',
                             endpoint='Clinical benefit: partial response or stable disease versus progression',
                             comparator='Always predict no clinical benefit at identical patient coverage',
                             statistics='Accuracy, paired correctness difference, exact McNemar test, Wilson 95% accuracy interval',
                             exclusions='All six adjuvant rows, frozen using setting before clinical outcome column is opened',
                             prediction= '3 benefit / 2 no-benefit reports in 5 patients; expected 3-4 correct; all 6 adjuvant rows need linkage review'),
                sensitivity='Remove the two explicitly marked pharmacological-proxy regimens; preserve primary result',
                exposure=dict(aggregate='Published 75% sensitivity/specificity in eight evaluable patients was read before this freeze',
                              concealed='Individual outcome and remarks columns C/G unread before the public prediction freeze',
                              design='Retrospective publication selected for available numerical scores; outcome-value concealment by the same analyst; no independent custodian'),
                independence='Separate French STING/MATCH-R colorectal publication from prior Chinese/Australian/US clinical datasets; no patient-level identity linkage across institutions is available',
                license='CC BY 4.0; source spreadsheet attributed to Cartry et al. 2023', cases=cases)

def wilson(correct, n):
    if not n:
        return None
    z = 1.959963984540054
    p = correct/n
    center = (p+z*z/(2*n))/(1+z*z/n)
    half = z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/(1+z*z/n)
    return [center-half, center+half]

def metrics(cases):
    n = len(cases)
    correct = sum(c['prediction'] == c['response'] for c in cases)
    baseline = sum(c['response'] == 0 for c in cases)
    wins = sum(c['prediction'] == c['response'] and c['response'] != 0 for c in cases)
    losses = sum(c['prediction'] != c['response'] and c['response'] == 0 for c in cases)
    d = wins+losses
    p = min(1, 2*sum(math.comb(d,k) for k in range(min(wins,losses)+1))/(2**d)) if d else 1
    return dict(patients=n, reports=n, correct=correct, wrong=n-correct, accuracy=correct/n if n else None,
                accuracy_wilson95=wilson(correct,n), baseline_correct=baseline,
                accuracy_difference=(correct-baseline)/n if n else None,
                paired_wins=wins, paired_losses=losses, exact_mcnemar_p=p)

def score(data, frozen):
    if prepare(data) != frozen:
        raise ValueError('Source, eligibility, rule or predictions differ from the frozen manifest')
    labels = read_cells(data, {'C'})
    mapping = {'partial response':1, 'stable disease':1, 'progressive disease':0,
               'progression':0, 'PR':1, 'SD':1, 'PD':0}
    cases = []
    for c in frozen['cases']:
        if not c['eligible']:
            continue
        text = labels[f'C{c["source_row"]}'].strip()
        if text not in mapping:
            raise ValueError(f'Unmapped clinical response for {c["patient"]}: {text!r}; keep frozen endpoint')
        cases.append(dict(c, source_outcome=text, response=mapping[text]))
    return dict(schema='external.clinical.result.v1', source_sha256=sha(data),
                prediction_sha256=sha((json.dumps(frozen,indent=2,ensure_ascii=False)+'\n').encode()),
                primary=metrics(cases), exact_drug_sensitivity=metrics([c for c in cases if not c['proxy']]),
                source_table_rows=len(frozen['cases']), linkage_review=sum(not c['eligible'] for c in frozen['cases']),
                cases=cases,
                scope='Validation of source-specific research calls, not a new calibration method or validation of the rectal combined assay',
                risk_certificate='No independent labelled calibration set; certified 10% conditional-risk coverage remains zero')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['prepare','score'])
    p.add_argument('--input',type=Path)
    p.add_argument('--out',type=Path)
    p.add_argument('--freeze',type=Path,default=ROOT/'clinical_external_frozen.json')
    a=p.parse_args()
    data=a.input.read_bytes() if a.input else urllib.request.urlopen(URL,timeout=40).read()
    if sha(data) != SOURCE_SHA:
        raise ValueError('Publisher source checksum differs')
    out=a.out or (a.freeze if a.mode=='prepare' else ROOT/'clinical_external_result.json')
    result=prepare(data) if a.mode=='prepare' else score(data,json.loads(a.freeze.read_text()))
    content=json.dumps(result,indent=2,ensure_ascii=False)+'\n'
    if a.mode=='prepare' and out.exists() and out.read_text()!=content:
        raise ValueError('Preserve the existing freeze; write a distinct manifest for changed inputs')
    out.write_text(content)
    if a.mode=='score':
        dest=out.with_suffix('.csv')
        with dest.open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=['patient','regimen','prediction','response','action','next_action'])
            writer.writeheader()
            for c in result['cases']:
                writer.writerow({**{k:c[k] for k in writer.fieldnames if k!='next_action'},
                                 'next_action':'Review discordance before a new independently enrolled batch' if c['prediction']!=c['response'] else 'Retain as an auditable research report'})
    print(json.dumps(result.get('primary',dict(cases=len(result['cases']))),indent=2))

if __name__=='__main__':
    main()

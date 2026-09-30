#!/usr/bin/env python3
"""Count registered clinical studies that test each patient's own organoids or chips
against drugs, from the public ClinicalTrials.gov API (v2).

The API query is broad; a study is kept only when its own title, summaries, outcome
measures, interventions or keywords name both a patient-derived model (organoid, organ- or
tumour-on-chip, microfluidic culture) and a drug-response test (drug sensitivity, drug
screen, chemosensitivity, drug response, drug test). For kept studies the script reports
counts by start year, type and status, planned enrollment, how many name a multi-drug
regimen (each patient then carries one readout per drug of the regimen), and what the
release certificate's pilot-size rule, (released errors + 1) / (n + 1) <= alpha, allows at
each study's planned size. Registry rows are plans, not results; the keyword rule is not a
systematic review. Rows and the run date are written out so the count can be re-audited.
"""

import argparse
import datetime
import json
import re
import statistics
import time
import urllib.parse
import urllib.request
from pathlib import Path

API = 'https://clinicaltrials.gov/api/v2/studies'
QUERY = ('(organoid OR organoids OR "organ-on-a-chip" OR "organ on a chip" OR "organ-on-chip" OR '
         '"tumor-on-a-chip" OR "tumour-on-a-chip" OR "tumor on a chip" OR microfluidic) AND '
         '("drug sensitivity" OR "drug screening" OR "drug screen" OR chemosensitivity OR '
         '"drug response" OR "drug test" OR "drug testing" OR "sensitivity test" OR "sensitivity testing")')
FIELDS = ('NCTId,BriefTitle,OfficialTitle,BriefSummary,DetailedDescription,Condition,Keyword,'
          'InterventionName,InterventionDescription,PrimaryOutcomeMeasure,PrimaryOutcomeDescription,'
          'SecondaryOutcomeMeasure,EnrollmentCount,EnrollmentType,StudyType,OverallStatus,StartDate,Phase')
MODEL = re.compile(r'organoid|on[- ]a[- ]chip|on[- ]chip|microfluidic', re.I)
TEST = re.compile(r'drug[- ]sensitiv|drug[- ]screen|chemosensitiv|chemo[- ]sensitiv|drug[- ]response|drug[- ]test|sensitivity[- ]test', re.I)
CANCER = re.compile(r'cancer|carcinoma|tumou?r|neoplasm|sarcoma|glioma|glioblastoma|lymphoma|leukemia|leukaemia|melanoma|myeloma|blastoma|mesothelioma|malignan', re.I)
CONFLICT = re.compile(r'\bre-?test|repeat(ed)? (test|assay|screen)|inconclusive|indeterminate|discordan|disagree|conflicting', re.I)
# conservative: named multi-drug regimens or the words combination/doublet/triplet; short
# two-letter acronyms are left out because they collide with disease abbreviations
REGIMEN = re.compile(r'\b(FOLFOX\w*|mFOLFOX6|FOLFIRI\w*|FOLFIRINOX|XELOX|CAPOX|CAPEOX|SOX|XELIRI|GEMOX|GEMCIS|FLOT|DCF|ECF|TCbH)\b|combination|doublet|triplet', re.I)


def fetch(query, page_size=100, pause=0.4):
    rows, token = [], None
    while True:
        params = {'query.term': query, 'fields': FIELDS, 'pageSize': page_size, 'countTotal': 'true', 'format': 'json'}
        if token:
            params['pageToken'] = token
        url = API + '?' + urllib.parse.urlencode(params)
        with urllib.request.urlopen(url, timeout=60) as response:
            page = json.load(response)
        total = page.get('totalCount', total if token else None)
        rows += page.get('studies', [])
        token = page.get('nextPageToken')
        if not token:
            return rows, total
        time.sleep(pause)


def flat(study):
    p = study['protocolSection']
    ident, status, design = p.get('identificationModule', {}), p.get('statusModule', {}), p.get('designModule', {})
    desc, cond = p.get('descriptionModule', {}), p.get('conditionsModule', {})
    arms, outcomes = p.get('armsInterventionsModule', {}), p.get('outcomesModule', {})
    interventions = arms.get('interventions', [])
    outcome_text = ' '.join(o.get('measure', '') + ' ' + o.get('description', '')
                            for key in ('primaryOutcomes', 'secondaryOutcomes') for o in outcomes.get(key, []))
    text = ' '.join([ident.get('briefTitle', ''), ident.get('officialTitle', ''), desc.get('briefSummary', ''),
                     desc.get('detailedDescription', ''), ' '.join(cond.get('keywords', [])), outcome_text,
                     ' '.join(i.get('name', '') + ' ' + i.get('description', '') for i in interventions)])
    enrollment = design.get('enrollmentInfo', {})
    start = status.get('startDateStruct', {}).get('date', '')
    return {'nct': ident.get('nctId'), 'title': ident.get('briefTitle', ''),
            'type': design.get('studyType'), 'status': status.get('overallStatus'),
            'start_year': int(start[:4]) if start[:4].isdigit() else None,
            'enrollment': enrollment.get('count'), 'enrollment_type': enrollment.get('type'),
            'cancer': bool(CANCER.search(' '.join(cond.get('conditions', [])) + ' ' + ident.get('briefTitle', ''))),
            'model_and_test_in_own_text': bool(MODEL.search(text) and TEST.search(text)),
            'model_in_title': bool(MODEL.search(ident.get('briefTitle', '') + ' ' + ident.get('officialTitle', ''))),
            'mentions_conflicting_or_repeat_readouts': bool(CONFLICT.search(text)),
            'multi_drug': bool(REGIMEN.search(' '.join(i.get('name', '') + ' ' + i.get('description', '') for i in interventions)
                                              + ' ' + desc.get('briefSummary', '')))}


def pilot_alpha(n, errors):
    return round((errors + 1) / (n + 1), 4)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    raw, total = fetch(QUERY)
    rows = [flat(s) for s in raw]
    kept = [r for r in rows if r['model_and_test_in_own_text']]
    sizes = [r['enrollment'] for r in kept if isinstance(r['enrollment'], int) and r['enrollment'] > 0]
    years = {}
    for r in kept:
        years[r['start_year']] = years.get(r['start_year'], 0) + 1
    count = lambda key: {k: sum(r[key] == k for r in kept) for k in sorted({r[key] for r in kept}, key=str)}
    result = {
        'schema': 'registry.fingerprint.v1', 'api': API, 'query': QUERY,
        'run_date_utc': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d'),
        'api_total': total, 'fetched': len(rows), 'kept': len(kept),
        'kept_rule': 'own title, summaries, outcomes, interventions or keywords name both a patient-derived model and a drug-response test',
        'by_start_year': {str(k): v for k, v in sorted(years.items(), key=lambda kv: (kv[0] is None, kv[0]))},
        'by_type': count('type'), 'by_status': count('status'),
        'cancer': sum(r['cancer'] for r in kept), 'multi_drug_named': sum(r['multi_drug'] for r in kept),
        'model_named_in_title': sum(r['model_in_title'] for r in kept),
        'model_in_title_interventional': sum(r['model_in_title'] and r['type'] == 'INTERVENTIONAL' for r in kept),
        'mentions_conflicting_or_repeat_readouts': sum(r['mentions_conflicting_or_repeat_readouts'] for r in kept),
        'conflict_mentions': [r['nct'] for r in kept if r['mentions_conflicting_or_repeat_readouts']],
        'planned_enrollment': {'studies_with_size': len(sizes), 'sum': sum(sizes),
                               'median': statistics.median(sizes) if sizes else None,
                               'at_least_9': sum(s >= 9 for s in sizes), 'at_least_19': sum(s >= 19 for s in sizes),
                               'at_least_39': sum(s >= 39 for s in sizes)},
        'certificate_at_median_size': {'no_released_error': pilot_alpha(int(statistics.median(sizes)), 0),
                                       'one_released_error': pilot_alpha(int(statistics.median(sizes)), 1)} if sizes else None,
        'rows': kept}
    if args.out:
        args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'rows'}, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()

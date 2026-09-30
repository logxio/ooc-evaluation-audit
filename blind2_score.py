#!/usr/bin/env python3
"""Score the second blind release test against the two clinical tables.

blind2_predictions.json was public (commit cc63238) before either clinical table was parsed; this
script refuses to run if that file changed. The rows below are transcribed from the rectal cohort's
Supplementary Table 1 (Treatments, TRG) and the liver-metastasis cohort's Table S7 (Regimen,
Treatment Response); the source files and their hashes are listed in the prediction file. The
forecast is release_theory.setting, unchanged. A patient counts for a readout pair only when the
regimen contains both treatments, the rule blind_consensus_score.py already used.
"""

import hashlib
import json
from pathlib import Path

from blind_consensus_score import outcome
from release_theory import setting

PREDICTIONS_SHA256 = 'b12709fda79eda677d90c0eb8a3ec90614a701827c4845dbd998cb55e83980f0'
COSTS = (0.10, 0.25, 0.50)
TOLERANCE = 0.09
RECTAL_TREATMENT = {'radiation': 'Irradiation', 'capecitabine': '5-FU', 'irinotecan': 'Irinotecan'}
# Patient number -> (Treatments, TRG) from the rectal Supplementary Table 1.
RECTAL_CLINICAL = {
    1: ('radiation/irinotecan/Capecitabine', '0'), 2: ('radiation/irinotecan/Capecitabine', '3'), 3: ('radiation/irinotecan/Capecitabine', '2'),
    4: ('radiation/irinotecan/Capecitabine', '1'), 5: ('radiation/Capecitabine', '2'), 6: ('radiation/irinotecan/Capecitabine', '1'),
    7: ('radiation/irinotecan/Capecitabine', '3'), 8: ('radiation/irinotecan/Capecitabine', '1'), 9: ('radiation/Capecitabine', '3'),
    10: ('radiation/irinotecan/Capecitabine', '2'), 11: ('radiation/irinotecan/Capecitabine', '2'), 12: ('radiation/irinotecan/Capecitabine', '0'),
    13: ('radiation/irinotecan/Capecitabine', '2'), 14: ('radiation/irinotecan/Capecitabine', '2'), 15: ('radiation/irinotecan/Capecitabine', '2'),
    16: ('radiation/Capecitabine', 'ccr'), 17: ('radiation/irinotecan/Capecitabine', '0'), 18: ('radiation/irinotecan/Capecitabine', '1'),
    19: ('radiation/irinotecan/Capecitabine', '1'), 20: ('radiation/irinotecan/Capecitabine', '3'), 21: ('radiation/Capecitabine', '3'),
    22: ('radiation/Capecitabine', '0'), 23: ('radiation/irinotecan/Capecitabine', '1'), 24: ('radiation/Capecitabine', '0'),
    25: ('radiation/Capecitabine', '2'), 26: ('radiation/irinotecan/Capecitabine', '0'), 27: ('radiation/irinotecan/Capecitabine', '2'),
    28: ('radiation/irinotecan/Capecitabine', '2'), 29: ('radiation/irinotecan/Capecitabine', '2'), 30: ('radiation/irinotecan/Capecitabine', '0'),
    31: ('radiation/irinotecan/Capecitabine', '1'), 32: ('radiation/Capecitabine', '0'), 33: ('radiation/Capecitabine', '0'),
    34: ('radiation/irinotecan/Capecitabine', '2'), 35: ('radiation/irinotecan/Capecitabine', '0'), 36: ('radiation/irinotecan/Capecitabine', '0'),
    37: ('radiation/irinotecan/Capecitabine', '2'), 38: ('radiation/irinotecan/Capecitabine', 'ccr'), 39: ('radiation/irinotecan/Capecitabine', 'ccr'),
    40: ('radiation/irinotecan/Capecitabine', 'ccr'), 41: ('radiation/irinotecan/Capecitabine', '2'), 42: ('radiation/irinotecan/Capecitabine', 'ccr'),
    43: ('radiation/irinotecan/Capecitabine', '0'), 44: ('radiation/irinotecan/Capecitabine', '0'), 45: ('radiation/irinotecan/Capecitabine', '1'),
    46: ('radiation/irinotecan/Capecitabine', '2'), 47: ('radiation/Capecitabine', '3'), 48: ('radiation/irinotecan/Capecitabine', '3'),
    49: ('radiation/irinotecan/Capecitabine', '0'), 50: ('radiation/irinotecan/Capecitabine', '3'), 51: ('radiation/irinotecan/Capecitabine', '0'),
    52: ('radiation/irinotecan/Capecitabine', '0'), 53: ('radiation/irinotecan/Capecitabine', '2'), 54: ('radiation/irinotecan/Capecitabine', '1'),
    55: ('radiation/irinotecan/Capecitabine', '2'), 56: ('radiation/Capecitabine', '2'), 57: ('radiation/irinotecan/Capecitabine', '0'),
    58: ('radiation/Capecitabine', '2'), 59: ('radiation/irinotecan/Capecitabine', '3'), 60: ('radiation/irinotecan/Capecitabine', '0'),
    61: ('radiation/irinotecan/Capecitabine', '2'), 62: ('radiation/irinotecan/Capecitabine', '2'), 63: ('radiation/Capecitabine', '2'),
    64: ('radiation/irinotecan/Capecitabine', '1'), 65: ('radiation/irinotecan/Capecitabine', '2'), 66: ('radiation/irinotecan/Capecitabine', '2'),
    67: ('radiation/irinotecan/Capecitabine', '2'), 68: ('radiation/irinotecan/Capecitabine', '0'), 69: ('radiation/irinotecan/Capecitabine', '1'),
    70: ('radiation/irinotecan/Capecitabine', '2'), 71: ('radiation/irinotecan/Capecitabine', '2'), 72: ('radiation/irinotecan/Capecitabine', '3'),
    73: ('radiation/irinotecan/Capecitabine', '3'), 74: ('radiation/irinotecan/Capecitabine', '2'), 75: ('radiation/irinotecan/Capecitabine', '1'),
    76: ('radiation/irinotecan/Capecitabine', '2'), 77: ('radiation/Capecitabine', '1'), 78: ('radiation/irinotecan/Capecitabine', '2'),
    79: ('radiation/irinotecan/Capecitabine', '2'), 80: ('radiation/Capecitabine', '3'), 81: ('radiation/irinotecan/Capecitabine', '0'),
    82: ('radiation/irinotecan/Capecitabine', '0'), 83: ('radiation/Capecitabine', '2'), 84: ('radiation/irinotecan/Capecitabine', '0'),
    85: ('radiation/irinotecan/Capecitabine', '2'), 86: ('radiation/Capecitabine', 'ccr'), 87: ('radiation/irinotecan/Capecitabine', 'ccr'),
    88: ('radiation/Capecitabine', '2'), 89: ('radiation/irinotecan/Capecitabine', 'ccr'), 90: ('radiation/irinotecan/Capecitabine', '2'),
    91: ('radiation/irinotecan/Capecitabine', '3'), 92: ('radiation/irinotecan/Capecitabine', '2'), 93: ('radiation/Capecitabine', '2'),
    94: ('radiation/irinotecan/Capecitabine', '3'), 95: ('radiation/irinotecan/Capecitabine', 'ccr'), 96: ('radiation/irinotecan/Capecitabine', '0'),
    97: ('radiation/irinotecan/Capecitabine', '1'), 98: ('radiation/irinotecan/Capecitabine', '0'), 99: ('radiation/irinotecan/Capecitabine', '0'),
    100: ('radiation/irinotecan/Capecitabine', '0'), 101: ('radiation/irinotecan/Capecitabine', '0'), 102: ('radiation/irinotecan/Capecitabine', 'ccr'),
    103: ('radiation/irinotecan/Capecitabine', '2'), 104: ('radiation/irinotecan/Capecitabine', '2'), 105: ('radiation/irinotecan/Capecitabine', 'ccr'),
    106: ('radiation/irinotecan/Capecitabine', '2'), 107: ('radiation/irinotecan/Capecitabine', 'ccr'), 108: ('radiation/irinotecan/Capecitabine', 'ccr'),
    109: ('irinotecan/Capecitabine', '2'), 110: ('radiation/irinotecan/Capecitabine', '2'), 111: ('radiation/irinotecan/Capecitabine', '2'),
    112: ('radiation/irinotecan/Capecitabine', '2'), 113: ('radiation/irinotecan/Capecitabine', '2'), 114: ('radiation/irinotecan/Capecitabine', '1'),
    115: ('radiation/Capecitabine', '2'), 116: ('radiation/irinotecan/Capecitabine', '2'), 117: ('radiation/Capecitabine', '2'),
    118: ('radiation/irinotecan/Capecitabine', '3'), 119: ('radiation/irinotecan/Capecitabine', '1'), 120: ('radiation/Capecitabine', '0'),
    121: ('radiation/irinotecan/Capecitabine', '2'), 122: ('radiation/Capecitabine', '2'), 123: ('radiation/irinotecan/Capecitabine', '2'),
    124: ('radiation/irinotecan/Capecitabine', '0'), 125: ('radiation/irinotecan/Capecitabine', '3'), 126: ('radiation/irinotecan/Capecitabine', '2'),
    127: ('radiation/irinotecan/Capecitabine', '2'), 128: ('radiation/irinotecan/Capecitabine', '2'),
}
# Patient -> (Regimen, Treatment Response) from the liver-metastasis Table S7.
CRLM_CLINICAL = {
    'P2': ('FOLFIRI', 'SD/PR'), 'P3': ('FOLFOX', 'PD'), 'P4': ('FOLFOX', 'SD/PR'), 'P5': ('FOLFOX', 'SD/PR'),
    'P6': ('FOLFOX', 'PD'), 'P7': ('FOLFIRI', 'PD'), 'P8': ('FOLFIRI', 'SD/PR'), 'P9': ('FOLFOX', 'PD'),
    'P10': ('FOLFIRI', 'PD'), 'P11': ('FOLFOX', 'SD/PR'), 'P12': ('FOLFOX', 'SD/PR'), 'P13': ('FOLFOX', 'SD/PR'),
    'P14': ('FOLFOX', 'SD/PR'), 'P15': ('FOLFIRI', 'SD/PR'), 'P16': ('FOLFIRI', 'SD/PR'), 'P17': ('FOLFIRI', 'PD'),
    'P18': ('FOLFOX', 'PD'), 'P19': ('FOLFOX', 'PD'), 'P21': ('FOLFIRI', 'PD'), 'P22': ('FOLFIRI', 'PD'),
    'P23': ('FOLFOX', 'SD/PR'), 'P24': ('FOLFIRI', 'SD/PR'), 'P25': ('FOLFOX', 'SD/PR'),
}


def rectal_truth(trg, endpoint):
    for label in ('responder', 'non_responder'):
        if trg.lower() in endpoint[label]:
            return label
    return None


def analyse(name, rows):
    """rows: (patient, call_a, call_b, truth) with calls and truth as 'responder'/'non_responder'."""
    a = [int(r[1] == 'responder') for r in rows]
    b = [int(r[2] == 'responder') for r in rows]
    t = [int(r[3] == 'responder') for r in rows]
    s = setting(name, a, b, t)
    n = len(rows)
    released_wrong = s['released'] - s['released_correct']
    retests = n - s['released']
    s['responders'] = sum(t)
    s['loss_per_patient'] = {str(c): round((released_wrong + c * retests) / n, 4) for c in COSTS}
    s['single_readout_loss'] = [round(1 - p, 4) for p in s['readout_accuracy']]
    s['forecast_gap'] = round(s['released_accuracy'] - s['released_accuracy_forecast'], 4)
    s['rows'] = [{'patient': p, 'calls': [x, y], 'truth': z} for p, x, y, z in rows]
    return s


def assertions(primary, every):
    out = []
    for s in primary:
        out.append({'assertion': 'P1', 'analysis': s['setting'],
                    'holds': s['shared_errors'] > s['shared_errors_if_independent'],
                    'observed': [s['shared_errors'], s['shared_errors_if_independent']]})
        out.append({'assertion': 'P2', 'analysis': s['setting'],
                    'holds': abs(s['forecast_gap']) <= TOLERANCE, 'observed': s['forecast_gap']})
    for s in every:
        if min(s['readout_accuracy']) <= 0.5:
            out.append({'assertion': 'P3', 'analysis': s['setting'],
                        'holds': s['released_accuracy'] <= max(s['readout_accuracy']),
                        'observed': [s['released_accuracy'], max(s['readout_accuracy'])]})
    return out


def rectal(frozen):
    cohort = frozen['cohorts']['rectal']
    endpoints = frozen['endpoints']['rectal']
    blind = set(cohort['blind_patients'])
    result, singles = {}, {}

    def rows(pair, patients, endpoint, require_regimen=True):
        out = []
        for p in patients:
            treatments, trg = RECTAL_CLINICAL[int(p[7:])]
            received = {RECTAL_TREATMENT[x.lower()] for x in treatments.split('/')}
            truth = rectal_truth(trg, endpoint)
            calls = cohort['patients'][p]['readout_sensitive']
            if truth is None or (require_regimen and not set(pair) <= received):
                continue
            out.append((p, *('responder' if calls[d] else 'non_responder' for d in pair), truth))
        return out

    good, complete = endpoints['good_response_primary'], endpoints['complete_response_secondary']
    blind_list = [p for p in cohort['patients'] if p in blind]
    seen_list = [p for p in cohort['patients'] if p not in blind]
    main = ('Irradiation', '5-FU')
    result['primary_blind_43_128'] = analyse('rectal blind 43-128, irradiation + 5-FU, TRG 0-1/cCR', rows(main, blind_list, good))
    result['blind_complete_response'] = analyse('rectal blind 43-128, irradiation + 5-FU, TRG 0/cCR', rows(main, blind_list, complete))
    result['blind_regimen_ignored'] = analyse('rectal blind 43-128, irradiation + 5-FU, all patients', rows(main, blind_list, good, False))
    result['seen_1_42'] = analyse('rectal 1-42 (outcomes seen before freeze), irradiation + 5-FU', rows(main, seen_list, good))
    result['all_128'] = analyse('rectal 1-128, irradiation + 5-FU', rows(main, list(cohort['patients']), good))
    for pair in (('Irradiation', 'Irinotecan'), ('5-FU', 'Irinotecan')):
        result['blind_' + '+'.join(pair)] = analyse('rectal blind 43-128, ' + ' + '.join(pair), rows(pair, blind_list, good))
    for channel in ('Irradiation', '5-FU', 'Irinotecan', 'Combined'):
        r = rows((channel, channel), blind_list, good, False)
        singles[channel] = {'patients': len(r), 'correct': sum(x[1] == x[3] for x in r),
                            'accuracy': round(sum(x[1] == x[3] for x in r) / len(r), 4)}
    result['blind_single_readouts'] = singles
    return result


def crlm(frozen):
    words = {k: tuple(v) for k, v in frozen['endpoints']['crlm']['disease_control_primary'].items()}
    pairs = frozen['endpoints']['crlm']['regimen_pairs']
    result = {}
    for variant in ('mean_of_both_organoids', 'liver_metastasis_organoid', 'primary_tumour_organoid'):
        patients = frozen['cohorts']['crlm'][variant]['patients']
        rows = []
        for p, (regimen, response) in CRLM_CLINICAL.items():
            pair = pairs[regimen.upper()]
            truth = outcome(response, words)
            calls = patients[p]['readout_sensitive']
            rows.append((p, *('responder' if calls[d] else 'non_responder' for d in pair), truth))
        result[variant] = analyse(f'liver metastasis, {variant.replace("_", " ")}, regimen pair, disease control', rows)
    result['objective_response_secondary'] = 'not computable: Table S7 reports SD and PR in one class (SD/PR)'
    return result


def main():
    blob = Path('blind2_predictions.json').read_bytes()
    actual = hashlib.sha256(blob).hexdigest()
    if actual != PREDICTIONS_SHA256:
        raise ValueError(f'blind2_predictions.json changed: {actual}')
    frozen = json.loads(blob)
    rect, liver = rectal(frozen), crlm(frozen)
    primary = [rect['primary_blind_43_128'], liver['mean_of_both_organoids']]
    every = [v for v in list(rect.values()) + list(liver.values()) if isinstance(v, dict) and 'setting' in v]
    result = {'schema': 'blind2.consensus.score.v1', 'predictions_sha256': actual,
              'rectal': rect, 'crlm': liver, 'assertions': assertions(primary, every)}
    Path('blind2_score.json').write_text(json.dumps(result, indent=1) + '\n')
    brief = {k: {x: v[x] for x in ('patients', 'responders', 'readout_accuracy', 'released', 'released_correct',
                                   'released_accuracy', 'released_accuracy_forecast', 'forecast_gap', 'shared_errors',
                                   'shared_errors_if_independent', 'loss_per_patient')}
             for k, v in [*rect.items(), *liver.items()] if isinstance(v, dict) and 'setting' in v}
    print(json.dumps({'analyses': brief, 'single_readouts': rect['blind_single_readouts'],
                      'assertions': result['assertions']}, indent=1))


if __name__ == '__main__':
    main()

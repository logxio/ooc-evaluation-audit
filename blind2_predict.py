#!/usr/bin/env python3
"""Freeze a second blind test of the two-readout release rule on two new patient-organoid cohorts.

The rule is the one already public in blind_consensus.py: a readout calls a patient sensitive when
the value is at or below the cohort median (lower = stronger response), a patient's organoids are
averaged first, and a call is released only when the two readouts agree; otherwise the patient is
sent to retest. Predictions are made from the organoid readout tables only, for every readout pair,
before the clinical tables are read. Run blind2_score.py after this file and its output are public.

Rectal cohort: 128 locally advanced rectal cancer patients, organoid size ratio day 24 / day 0 after
irradiation, 5-FU, irinotecan or the combination (Supplementary Table 2). The clinical table rows of
patients 1-42 were displayed while its column headers were being checked, before this file was
written, so the blind analysis covers patients 43-128 and patients 1-42 are reported separately.

Colorectal liver-metastasis cohort: 25 patients, one organoid from the primary tumour and one from
the liver metastasis, IC50 for 5-FU, irinotecan and oxaliplatin (Table S6). Its clinical table was
not opened.
"""

import argparse
import json

from blind_consensus import OBJECTIVE_RESPONSE, DISEASE_CONTROL, calls

SOURCES = {
    'rectal': {
        'article': 'https://doi.org/10.1016/j.xcrm.2025.102397',
        'license': 'CC BY 4.0',
        'readout_file': 'https://pmc-oa-opendata.s3.amazonaws.com/PMC12629783.1/mmc1.pdf',
        'readout_sha256': 'cdab09edc26e223bcc436d698570e587e44d48237608b7d844b9f0fe1485bf07',
        'readout_table': 'Supplementary Table 2, organoid size ratio day 24 / day 0',
        'clinical_table': 'Supplementary Table 1, Treatments and TRG columns (same file)',
    },
    'crlm': {
        'article': 'https://doi.org/10.1002/advs.202204097',
        'license': 'CC BY 4.0',
        'readout_file': 'https://pmc-oa-opendata.s3.amazonaws.com/PMC9631073.1/ADVS-9-2204097-s002.xls',
        'readout_sha256': '9e217844434fb72e9d379770b7072fa6fd93de5cc87c685d1ae867e0e6784d4c',
        'readout_table': 'Table S6, IC50 (uM)',
        'clinical_table': 'Table S7, Regimen and Treatment Response columns (same file)',
    },
}
RECTAL_CHANNELS = ('Irradiation', '5-FU', 'Irinotecan', 'Combined')
# Patient number -> size ratio after irradiation, 5-FU, irinotecan, combined chemoradiation.
RECTAL = {
    1: [0.1732, 0.1245, 0.1796, 0.0779], 2: [1.602, 0.9826, 1.1959, 0.4014], 3: [1.0596, 0.5233, 0.1737, 0.6521], 4: [1.3869, 0.0449, 0.0947, 0.0426],
    5: [0.9694, 0.7991, 0.7702, 0.5579], 6: [0.082, 0.6799, 0.3706, 0.0892], 7: [1.1961, 4.6461, 0.3839, 0.4358], 8: [0.5862, 0.1408, 0.3961, 0.1292],
    9: [1.7505, 1.9983, 1.7603, 1.1668], 10: [1.0941, 3.4739, 2.1068, 0.55627], 11: [1.0694, 1.2971, 1.2187, 1.2265], 12: [0.1331, 0.3925, 0.1256, 0.0406],
    13: [0.6687, 0.8629, 1.6675, 0.3573], 14: [1.3953, 0.646, 1.0329, 0.6052], 15: [2.6321, 1.6992, 0.9797, 0.6007], 16: [0.0615, 0.4441, 0.0553, 0.2211],
    17: [0.0674, 0.0763, 0.0763, 0.0301], 18: [0.1946, 0.8631, 0.6485, 0.1989], 19: [1.2079, 1.1885, 0.2629, 0.2374], 20: [2.021, 1.8163, 1.1856, 0.5838],
    21: [0.3915, 0.6838, 0.4642, 0.4927], 22: [1.7514, 0.9472, 0.112, 0.0259], 23: [2.7133, 0.1318, 0.2942, 0.0666], 24: [2.223, 0.3833, 1.1384, 0.5263],
    25: [0.9302, 0.7154, 0.8771, 0.48], 26: [0.0134, 0.5752, 0.0419, 0.0316], 27: [1.6408, 1.5948, 1.0612, 0.7979], 28: [0.6528, 0.6274, 0.1055, 1.1741],
    29: [0.8309, 0.9402, 0.9843, 1.2334], 30: [0.0828, 0.0539, 0.0663, 0.0227], 31: [0.8513, 0.0474, 0.5182, 0.0091], 32: [0.0092, 0.1414, 0.0248, 0.0203],
    33: [1.222, 0.0974, 1.7817, 0.0579], 34: [1.0433, 1.9676, 0.7693, 0.6068], 35: [0.247, 0.9842, 0.3182, 0.0291], 36: [0.1601, 0.7266, 0.0941, 0.0733],
    37: [2.9111, 0.3449, 0.3988, 0.3476], 38: [0.0891, 0.0583, 0.0301, 0.0111], 39: [4.3328, 0.1484, 0.2274, 0.1635], 40: [3.5075, 0.1324, 0.0245, 0.0486],
    41: [8.9479, 1.5382, 3.0217, 0.9244], 42: [1.8199, 0.1501, 0.0666, 0.0541], 43: [0.0964, 0.0417, 0.0275, 0.041], 44: [10.7701, 0.1794, 2.9778, 0.1885],
    45: [1.3001, 0.6362, 0.6196, 0.0196], 46: [0.5568, 1.0107, 0.5072, 0.7091], 47: [1.5233, 0.7623, 0.0781, 0.6767], 48: [2.9192, 0.5027, 3.0001, 0.4926],
    49: [7.943, 1.3261, 0.107, 0.1197], 50: [3.7136, 0.101, 0.0824, 0.0451], 51: [0.5136, 0.0354, 0.0139, 0.0229], 52: [1.6379, 0.6386, 0.0624, 0.2814],
    53: [1.6725, 0.6802, 1.025, 0.5789], 54: [0.4593, 0.7663, 0.2726, 0.2157], 55: [1.9776, 1.0877, 1.9224, 0.7161], 56: [3.029, 1.2754, 1.2302, 1.3519],
    57: [4.2972, 0.1825, 0.1209, 0.2077], 58: [2.7879, 1.128, 0.2522, 0.9556], 59: [2.477, 1.2204, 0.8038, 0.5341], 60: [1.1626, 0.1873, 0.1441, 0.1017],
    61: [4.7457, 0.3593, 5.9216, 0.4942], 62: [0.0888, 1.1369, 0.175, 1.0093], 63: [3.3909, 0.7168, 1.8737, 0.6753], 64: [0.7278, 0.456, 0.6503, 0.2921],
    65: [3.6419, 1.1073, 2.0594, 0.5112], 66: [3.8453, 1.229, 3.6988, 1.1679], 67: [1.401, 0.9609, 0.3735, 0.3429], 68: [0.2383, 0.0604, 0.0667, 0.057],
    69: [6.3307, 0.1623, 1.4695, 0.1182], 70: [3.5791, 0.9575, 0.8799, 0.4298], 71: [4.9398, 0.6673, 3.5636, 0.5014], 72: [1.8227, 1.2946, 0.6457, 0.9127],
    73: [5.7599, 0.1081, 0.0762, 0.0954], 74: [1.1349, 0.4632, 0.7727, 0.4683], 75: [0.0741, 0.1051, 0.1271, 0.1206], 76: [7.2763, 0.3065, 0.0427, 0.1015],
    77: [0.7775, 0.16, 0.0163, 0.024], 78: [3.0112, 0.9331, 1.8804, 1.1438], 79: [8.8329, 1.2211, 1.0192, 0.5536], 80: [2.5331, 0.613, 0.909, 0.5916],
    81: [0.2354, 0.3641, 0.2227, 0.1352], 82: [2.2886, 0.5901, 0.1026, 0.0972], 83: [1.0349, 1.0459, 0.517, 0.7846], 84: [9.1641, 0.0696, 0.0469, 0.0373],
    85: [1.7749, 0.7071, 0.5082, 0.5723], 86: [0.0487, 0.0761, 0.0952, 0.032], 87: [0.2364, 0.1724, 0.1803, 0.0547], 88: [0.4267, 1.8225, 2.6342, 0.5005],
    89: [2.5151, 1.914, 0.3362, 0.2828], 90: [1.2311, 0.8607, 0.5343, 0.7652], 91: [19.8914, 2.1416, 5.7191, 1.0986], 92: [1.3194, 0.5599, 0.9099, 0.7524],
    93: [0.3965, 2.2952, 1.6997, 0.6381], 94: [2.5292, 1.8019, 1.735, 1.5187], 95: [1.5039, 0.0563, 0.619, 0.0097], 96: [1.6662, 0.0703, 0.0222, 0.029],
    97: [7.8834, 3.7457, 2.5245, 0.0314], 98: [0.043, 0.2199, 0.0239, 0.0135], 99: [0.0602, 0.0663, 0.0363, 0.0105], 100: [0.0792, 0.1155, 0.0645, 0.0308],
    101: [1.0608, 0.3499, 0.3253, 0.0576], 102: [0.0111, 0.023, 0.016, 0.0057], 103: [5.0088, 3.8364, 0.1415, 1.0696], 104: [2.8429, 0.3234, 0.7362, 0.3454],
    105: [0.602, 0.5201, 0.5798, 0.6035], 106: [1.6517, 0.6862, 0.7521, 0.4515], 107: [0.7926, 1.2499, 1.8746, 0.1785], 108: [4.5186, 0.0901, 0.0209, 0.0304],
    109: [0.8927, 0.8919, 0.8277, 0.7425], 110: [1.5705, 1.3677, 0.626, 0.7442], 111: [0.7304, 0.7564, 0.4828, 0.9134], 112: [2.0702, 0.781, 0.8651, 0.8276],
    113: [1.2093, 1.0782, 1.0998, 0.7589], 114: [5.5238, 0.1418, 0.0447, 0.0308], 115: [6.1799, 2.9776, 4.3813, 1.1169], 116: [0.7552, 0.9322, 0.8107, 0.6934],
    117: [0.9604, 0.6514, 1.142, 0.7548], 118: [2.4642, 0.3975, 0.6116, 0.3857], 119: [2.4711, 0.7668, 0.0667, 0.3415], 120: [0.1434, 0.181, 0.6209, 0.0592],
    121: [2.5753, 0.8419, 1.0003, 0.498], 122: [4.2256, 3.8528, 1.0073, 1.7538], 123: [1.9527, 0.4455, 0.0888, 0.6037], 124: [1.7715, 0.6291, 0.7631, 0.4641],
    125: [0.4327, 1.4518, 0.4895, 0.4951], 126: [7.7413, 0.8003, 0.3873, 0.9186], 127: [0.3488, 0.8148, 0.229, 0.6516], 128: [2.8906, 0.5223, 0.3577, 0.4272],
}
CRLM_CHANNELS = ('5-FU', 'Irinotecan', 'Oxaliplatin')
# Organoid -> IC50 (uM) for 5-FU, irinotecan (CPT11), oxaliplatin. CRCn and LMn come from patient Pn,
# the naming used in the same file's Table S4 (P3_CRC organoid, P3_LM organoid).
CRLM = {
    'CRC1': [0.7971, 1.175, 19.33], 'LM1': [0.6087, 1.422, 19.92], 'CRC2': [1.185, 0.7517, 14.79], 'LM2': [2.285, 1.117, 14.54],
    'CRC3': [30.46, 8.805, 63.79], 'LM3': [34.42, 0.7507, 13.96], 'CRC4': [4.408, 2.867, 9.081], 'LM4': [0.9708, 1.853, 10.0],
    'CRC5': [8.115, 4.424, 48.23], 'LM5': [1.116, 2.271, 25.17], 'CRC6': [5.143, 8.757, 37.76], 'LM6': [8.054, 8.698, 41.24],
    'CRC7': [32.75, 19.02, 63.06], 'LM7': [34.61, 22.57, 85.61], 'CRC8': [10.49, 5.385, 39.3], 'LM8': [14.31, 2.852, 60.75],
    'CRC9': [13.14, 8.226, 47.22], 'LM9': [14.25, 7.087, 59.59], 'CRC10': [38.66, 25.93, 74.83], 'LM10': [82.28, 43.46, 80.57],
    'CRC11': [2.884, 1.851, 60.3], 'LM11': [3.845, 3.557, 47.42], 'CRC12': [1.194, 0.7556, 15.72], 'LM12': [3.299, 0.5608, 23.72],
    'CRC13': [0.3582, 2.101, 13.16], 'LM13': [0.4726, 2.755, 13.95], 'CRC14': [2.106, 4.912, 87.89], 'LM14': [3.264, 7.265, 68.97],
    'CRC15': [7.139, 3.5, 37.24], 'LM15': [4.002, 4.083, 27.41], 'CRC16': [8.1, 4.537, 34.16], 'LM16': [4.98, 4.117, 36.96],
    'CRC17': [46.81, 18.57, 89.68], 'LM17': [44.03, 40.45, 101.3], 'CRC18': [0.8403, 0.622, 38.28], 'LM18': [3.124, 2.033, 36.68],
    'CRC19': [6.485, 5.582, 14.31], 'LM19': [21.51, 14.28, 16.62], 'CRC20': [12.92, 5.918, 23.16], 'LM20': [11.37, 6.903, 16.98],
    'CRC21': [28.5, 17.83, 70.52], 'LM21': [19.29, 21.1, 52.61], 'CRC22': [9.096, 4.776, 29.84], 'LM22': [8.303, 4.778, 23.1],
    'CRC23': [6.027, 4.243, 47.29], 'LM23': [6.455, 4.219, 45.34], 'CRC24': [11.99, 3.22, 52.72], 'LM24': [8.893, 3.478, 40.47],
    'CRC25': [8.213, 4.801, 39.6], 'LM25': [8.313, 5.201, 32.07],
}
RECTAL_BLIND = tuple(range(43, 129))
RECTAL_SEEN = tuple(range(1, 43))
RECTAL_PAIRS = (('Irradiation', '5-FU'), ('Irradiation', 'Irinotecan'), ('5-FU', 'Irinotecan'))
CRLM_PAIRS = (('5-FU', 'Oxaliplatin'), ('5-FU', 'Irinotecan'))
CRLM_REGIMENS = {'FOLFOX': ('5-FU', 'Oxaliplatin'), 'MFOLFOX6': ('5-FU', 'Oxaliplatin'),
                 'CAPOX': ('5-FU', 'Oxaliplatin'), 'XELOX': ('5-FU', 'Oxaliplatin'),
                 'FOLFOXIRI': ('5-FU', 'Oxaliplatin'), 'FOLFIRI': ('5-FU', 'Irinotecan'),
                 'XELIRI': ('5-FU', 'Irinotecan'), 'CAPIRI': ('5-FU', 'Irinotecan')}
ENDPOINTS = {
    'rectal': {
        'column': 'TRG (tumour regression grade, 0-3) with cCR for clinical complete response',
        'good_response_primary': {'responder': ['0', '1', 'ccr', 'pcr'], 'non_responder': ['2', '3']},
        'complete_response_secondary': {'responder': ['0', 'ccr', 'pcr'], 'non_responder': ['1', '2', '3']},
        'other_entries': 'not evaluable',
    },
    'crlm': {
        'column': 'Treatment Response',
        'disease_control_primary': DISEASE_CONTROL,
        'objective_response_secondary': OBJECTIVE_RESPONSE,
        'regimen_pairs': {k: list(v) for k, v in CRLM_REGIMENS.items()},
        'regimen_rule': 'antibodies added to a backbone are ignored; the organoids were tested with chemotherapy only',
        'other_entries': 'not evaluable',
    },
}
ASSERTIONS = [
    'P1. In each primary analysis the two single readouts share more wrong calls than independence '
    'predicts, n(1-p1)(1-p2), where p1 and p2 are the readouts\' observed accuracies on the same patients.',
    'P2. In each primary analysis the observed accuracy of released calls is within 0.09 of '
    'p1*p2 / (p1*p2 + (1-p1)*(1-p2)).',
    'P3. In any analysis where the weaker readout is not better than a coin flip (min(p1, p2) <= 0.5), '
    'released calls are not more accurate than the better readout alone.',
    'Checked, not predicted: when p1 + p2 > 1, released accuracy falls below the formula exactly when shared '
    'wrong calls exceed the independence count; the two break-even retest costs sum to 1.',
]
PRIMARY = {
    'rectal': 'patients 43-128, Irradiation + 5-FU (every patient received radiation with capecitabine), '
              'good response = TRG 0-1 or cCR',
    'crlm': 'patients with a Table S7 regimen, mean of the two organoids, the regimen\'s two drugs, '
            'disease control = CR, PR or SD',
}


def pair_calls(sensitive, pairs):
    out = {}
    for a, b in pairs:
        if a in sensitive and b in sensitive:
            agree = sensitive[a] == sensitive[b]
            out[a + '+' + b] = {'release': agree,
                                'predicted': ('responder' if sensitive[a] else 'non_responder') if agree else 'retest'}
    return out


def cohort(values, pairs):
    sensitive, medians = calls(values)
    return {'medians': {d: round(m, 6) for d, m in medians.items()},
            'patients': {p: {'readout_sensitive': sensitive[p], 'pairs': pair_calls(sensitive[p], pairs)}
                         for p in values}}


def crlm_values(which):
    prefixes = ('CRC', 'LM') if which == 'both' else (which,)
    out = {}
    for n in range(1, 26):
        organoids = [f'{p}{n}' for p in prefixes]
        out[f'P{n}'] = {d: sum(CRLM[o][i] for o in organoids) / len(organoids) for i, d in enumerate(CRLM_CHANNELS)}
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--out', default='blind2_predictions.json')
    args = parser.parse_args()
    rectal_values = {f'Patient{n}': dict(zip(RECTAL_CHANNELS, v)) for n, v in RECTAL.items()}
    rectal = cohort(rectal_values, RECTAL_PAIRS)
    rectal.update({'blind_patients': [f'Patient{n}' for n in RECTAL_BLIND],
                   'seen_before_freeze': [f'Patient{n}' for n in RECTAL_SEEN],
                   'primary_pair': 'Irradiation+5-FU', 'single_readout_comparator': 'Combined'})
    crlm = {'mean_of_both_organoids': cohort(crlm_values('both'), CRLM_PAIRS),
            'liver_metastasis_organoid': cohort(crlm_values('LM'), CRLM_PAIRS),
            'primary_tumour_organoid': cohort(crlm_values('CRC'), CRLM_PAIRS),
            'primary_variant': 'mean_of_both_organoids'}
    result = {'schema': 'blind2.consensus.predictions.v1', 'rule_source': 'blind_consensus.calls',
              'rule': 'per readout, sensitive if value <= cohort median; release only when the two readouts agree',
              'sources': SOURCES, 'endpoints': ENDPOINTS, 'primary_analyses': PRIMARY,
              'assertions': ASSERTIONS, 'cohorts': {'rectal': rectal, 'crlm': crlm}}
    with open(args.out, 'w') as handle:
        json.dump(result, handle, indent=1, sort_keys=True)
        handle.write('\n')
    blind = [rectal['patients'][p]['pairs']['Irradiation+5-FU']['release'] for p in rectal['blind_patients']]
    print(json.dumps({'rectal_medians': rectal['medians'],
                      'rectal_blind_released': f'{sum(blind)}/{len(blind)}',
                      'crlm_medians': crlm['mean_of_both_organoids']['medians']}, indent=1))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Freeze blind two-readout release predictions for two patient-organoid cohorts.

Predictions are made from organoid drug-response readouts only (each article's Table S3).
The clinical-response tables are not read by this script. Run `blind_consensus_score.py`
after this file and its output have been committed publicly.
"""

import argparse
import json
import statistics

SOURCES = {
    'gastric': {
        'article': 'https://doi.org/10.1016/j.xcrm.2024.101627',
        'readout_file': 'https://pmc-oa-opendata.s3.amazonaws.com/PMC11293329.1/mmc1.pdf',
        'readout_sha256': '19ef08717917c1e4a7db8c7f6648bb7b8f9ef11e6b68f323bc50b2a9b689a994',
        'readout_table': 'Table S3, replicate 1 AUC',
    },
    'biliary': {
        'article': 'https://doi.org/10.1016/j.xcrm.2023.101277',
        'readout_file': 'https://pmc-oa-opendata.s3.amazonaws.com/PMC10694672.1/mmc1.pdf',
        'readout_sha256': '26f16d49884c88fabebb102df888787f8356c0c88f94dd6dc1c79ab7440f6537',
        'readout_table': 'Table S3, AUC (%) and author class',
        'patient_map_file': 'https://pmc-oa-opendata.s3.amazonaws.com/PMC10694672.1/mmc2.xlsx',
        'patient_map_sha256': '54d64c61a4ed935b04fa23b014d3874db2f152b6d3b583a0c915bd0921d55d8e',
    },
}
# Table S3 values extracted from the publisher PDFs above (lower AUC = more sensitive).
GASTRIC_AUC = {"G20T":{"5-FU":18.38,"Oxaliplatin":27.77,"Cisplatin":32.67,"Paclitaxel":8.07,"SN-38":7.86,"Doxorubicin":55.73},"G23T":{"5-FU":34.01,"Oxaliplatin":41.74,"Cisplatin":31.75,"Paclitaxel":14.94,"SN-38":19.65,"Doxorubicin":17.25},"G24T":{"5-FU":22.46,"Oxaliplatin":48.19,"Cisplatin":36.94,"Paclitaxel":1.7,"SN-38":10.38,"Doxorubicin":24.28},"G27T":{"5-FU":28.71,"Oxaliplatin":29.79,"Cisplatin":30.03,"Paclitaxel":10.89,"SN-38":13.2,"Doxorubicin":17.23},"G28T":{"5-FU":46.39,"Oxaliplatin":97.62,"Cisplatin":81.12,"Paclitaxel":50.71,"SN-38":62.53,"Doxorubicin":19.08},"G30T":{"5-FU":53.91,"Oxaliplatin":40.78,"Cisplatin":36.18,"Paclitaxel":17.86,"SN-38":17.69,"Doxorubicin":35.88},"G31T":{"5-FU":16.1,"Oxaliplatin":28.87,"Cisplatin":47.17,"Paclitaxel":8.12,"SN-38":11.81,"Doxorubicin":18.81},"G32T":{"5-FU":21.38,"Oxaliplatin":26.05,"Cisplatin":23.54,"Paclitaxel":9.02,"SN-38":10.33,"Doxorubicin":10.33},"G33T":{"5-FU":30.39,"Oxaliplatin":38.22,"Cisplatin":33.65,"Paclitaxel":3.28,"SN-38":11.2,"Doxorubicin":11.2},"G34T":{"5-FU":39.12,"Oxaliplatin":52.55,"Cisplatin":47.53,"Paclitaxel":6.47,"SN-38":21.3,"Doxorubicin":21.3},"G36T":{"5-FU":56.24,"Oxaliplatin":76.36,"Cisplatin":58.56,"Paclitaxel":3.94,"SN-38":30.11,"Doxorubicin":34.5},"G37T":{"5-FU":15.51,"Oxaliplatin":30.33,"Cisplatin":29.23,"Paclitaxel":3.17,"SN-38":6.79,"Doxorubicin":14.07},"G38T":{"5-FU":61.64,"Oxaliplatin":40.92,"Cisplatin":18.75,"Paclitaxel":5.9,"SN-38":13.54,"Doxorubicin":14.04},"G39T":{"5-FU":30.73,"Oxaliplatin":60.94,"Cisplatin":43.58,"Paclitaxel":5.62,"SN-38":17.18,"Doxorubicin":16.15},"G41T":{"5-FU":23.8,"Oxaliplatin":51.13,"Cisplatin":27.71,"Paclitaxel":1.41,"SN-38":10.6,"Doxorubicin":12.87},"G42T":{"5-FU":15.57,"Oxaliplatin":46.37,"Cisplatin":22.6,"Paclitaxel":3.18,"SN-38":8.05,"Doxorubicin":6.1},"G43T":{"5-FU":35.6,"Oxaliplatin":59.7,"Cisplatin":25.37,"Paclitaxel":4.31,"SN-38":11.54,"Doxorubicin":17.13},"G44T":{"5-FU":30.15,"Oxaliplatin":59.12,"Cisplatin":37.68,"Paclitaxel":7.57,"SN-38":21.73,"Doxorubicin":20.64},"G47T":{"5-FU":23.52,"Oxaliplatin":29.63,"Cisplatin":14.87,"Paclitaxel":8.89,"SN-38":16.04,"Doxorubicin":5.92},"G48T":{"5-FU":45.35,"Oxaliplatin":59.26,"Cisplatin":20.2,"Paclitaxel":43.92,"SN-38":46.67,"Doxorubicin":34.21},"G50T":{"5-FU":14.87,"Oxaliplatin":19.84,"Cisplatin":7.93,"Paclitaxel":0.49,"SN-38":4.97,"Doxorubicin":6.19},"G55T":{"5-FU":36.1,"Oxaliplatin":66.03,"Cisplatin":35.06,"Paclitaxel":15.81,"SN-38":22.25,"Doxorubicin":19.69},"G56T":{"5-FU":22.08,"Oxaliplatin":46.95,"Cisplatin":24.16,"Paclitaxel":3.83,"SN-38":10.38,"Doxorubicin":14.54},"G58T":{"5-FU":50.31,"Oxaliplatin":52.75,"Cisplatin":23.92,"Paclitaxel":23.26,"SN-38":20.61,"Doxorubicin":24.65},"G59T":{"5-FU":8.73,"Oxaliplatin":49.35,"Cisplatin":6.98,"Paclitaxel":1.61,"SN-38":5.23,"Doxorubicin":9.44},"G5T":{"5-FU":68.61,"Oxaliplatin":17.53,"Cisplatin":25.75,"Paclitaxel":4.32,"SN-38":5.45,"Doxorubicin":12.4},"G61T":{"5-FU":49.79,"Oxaliplatin":77.68,"Cisplatin":48.13,"Paclitaxel":29.75,"SN-38":40.46,"Doxorubicin":40.59},"G62T":{"5-FU":30.65,"Oxaliplatin":56.34,"Cisplatin":28.79,"Paclitaxel":7.25,"SN-38":15.92,"Doxorubicin":21.59},"G63T":{"5-FU":60.5,"Oxaliplatin":85.97,"Cisplatin":33.37,"Paclitaxel":12.9,"SN-38":36.11,"Doxorubicin":25.04},"G65T":{"5-FU":44.26,"Oxaliplatin":98.74,"Cisplatin":25.69,"Paclitaxel":5.34,"SN-38":8.99,"Doxorubicin":17.53},"G72T":{"5-FU":9.7,"Oxaliplatin":12.45,"Cisplatin":9.99,"Paclitaxel":3.85,"SN-38":1.52,"Doxorubicin":1.88},"G73T":{"5-FU":27.03,"Oxaliplatin":56.74,"Cisplatin":25.27,"Paclitaxel":9.63,"SN-38":11.55,"Doxorubicin":19.32},"G74T":{"5-FU":31.27,"Oxaliplatin":60.0,"Cisplatin":23.5,"Paclitaxel":20.31,"SN-38":24.12,"Doxorubicin":12.5},"G78T":{"5-FU":24.4,"Oxaliplatin":33.67,"Cisplatin":21.44,"Paclitaxel":15.18,"SN-38":13.48,"Doxorubicin":13.32},"G80T":{"5-FU":10.86,"Oxaliplatin":15.47,"Cisplatin":15.75,"Paclitaxel":5.85,"SN-38":12.43,"Doxorubicin":10.61},"G82T":{"5-FU":37.86,"Oxaliplatin":53.77,"Cisplatin":45.97,"Paclitaxel":9.03,"SN-38":14.77,"Doxorubicin":26.85},"G83T":{"5-FU":52.57,"Oxaliplatin":70.73,"Cisplatin":41.44,"Paclitaxel":28.36,"SN-38":52.26,"Doxorubicin":51.37},"G84T":{"5-FU":50.03,"Oxaliplatin":54.37,"Cisplatin":72.19,"Paclitaxel":36.53,"SN-38":32.02,"Doxorubicin":18.02},"G86T":{"5-FU":31.53,"Oxaliplatin":69.65,"Cisplatin":22.84,"Paclitaxel":7.77,"SN-38":18.13,"Doxorubicin":18.82},"G87T":{"5-FU":57.48,"Oxaliplatin":61.66,"Cisplatin":17.67,"Paclitaxel":31.49,"SN-38":46.44,"Doxorubicin":39.62},"G9T":{"5-FU":31.13,"Oxaliplatin":47.37,"Cisplatin":38.98,"Paclitaxel":5.26,"SN-38":7.92,"Doxorubicin":25.52}}
BILIARY_AUC = {"ECC-14T":{"Gemcitabine":[0.58,"Sensitive"],"Cisplatin":[2.3,"Sensitive"],"5-FU":[7.25,"Sensitive"],"SN-38":[0.3,"Sensitive"],"Oxaliplatin":[27.58,"Sensitive"],"Mitomycin C":[4.32,"Sensitive"],"Paclitaxel":[3.58,"Sensitive"]},"ECC-15T":{"Gemcitabine":[1.48,"Sensitive"],"Cisplatin":[2.21,"Sensitive"],"5-FU":[10.28,"Sensitive"],"SN-38":[0.45,"Sensitive"],"Oxaliplatin":[40.43,"Intermediate"],"Mitomycin C":[7.19,"Sensitive"],"Paclitaxel":[3.0,"Sensitive"]},"ECC-16T":{"Gemcitabine":[2.75,"Sensitive"],"Cisplatin":[17.63,"Sensitive"],"5-FU":[21.85,"Sensitive"],"SN-38":[0.59,"Sensitive"],"Oxaliplatin":[61.34,"Intermediate"],"Mitomycin C":[12.45,"Sensitive"],"Paclitaxel":[16.06,"Sensitive"]},"ECC-19T":{"Gemcitabine":[3.32,"Sensitive"],"Cisplatin":[17.87,"Sensitive"],"5-FU":[15.52,"Sensitive"],"SN-38":[0.74,"Sensitive"],"Oxaliplatin":[72.1,"Resistant"],"Mitomycin C":[22.9,"Sensitive"],"Paclitaxel":[81.02,"Resistant"]},"ECC-1T":{"Gemcitabine":[2.99,"Sensitive"],"Cisplatin":[34.38,"Intermediate"],"5-FU":[28.03,"Sensitive"],"SN-38":[2.95,"Sensitive"],"Oxaliplatin":[40.3,"Intermediate"],"Mitomycin C":[7.61,"Sensitive"],"Paclitaxel":[1.62,"Sensitive"]},"ECC-20T":{"Gemcitabine":[1.27,"Sensitive"],"Cisplatin":[8.41,"Sensitive"],"5-FU":[20.6,"Sensitive"],"SN-38":[1.23,"Sensitive"],"Oxaliplatin":[31.92,"Sensitive"],"Mitomycin C":[6.99,"Sensitive"],"Paclitaxel":[32.72,"Sensitive"]},"ECC-21T":{"Gemcitabine":[3.85,"Sensitive"],"Cisplatin":[31.64,"Sensitive"],"5-FU":[50.53,"Intermediate"],"SN-38":[1.52,"Sensitive"],"Oxaliplatin":[100.0,"Resistant"],"Mitomycin C":[12.27,"Sensitive"],"Paclitaxel":[63.13,"Intermediate"]},"ECC-26T":{"Gemcitabine":[0.8,"Sensitive"],"Cisplatin":[13.05,"Sensitive"],"5-FU":[8.34,"Sensitive"],"SN-38":[0.25,"Sensitive"],"Oxaliplatin":[47.98,"Intermediate"],"Mitomycin C":[2.66,"Sensitive"],"Paclitaxel":[13.58,"Sensitive"]},"ECC-27T":{"Gemcitabine":[1.07,"Sensitive"],"Cisplatin":[12.04,"Sensitive"],"5-FU":[13.2,"Sensitive"],"SN-38":[0.29,"Sensitive"],"Oxaliplatin":[26.21,"Sensitive"],"Mitomycin C":[3.36,"Sensitive"],"Paclitaxel":[10.83,"Sensitive"]},"ECC-2T":{"Gemcitabine":[0.25,"Sensitive"],"Cisplatin":[22.66,"Sensitive"],"5-FU":[17.59,"Sensitive"],"SN-38":[0.64,"Sensitive"],"Oxaliplatin":[39.99,"Intermediate"],"Mitomycin C":[3.26,"Sensitive"],"Paclitaxel":[7.42,"Sensitive"]},"ECC-4T":{"Gemcitabine":[5.1,"Sensitive"],"Cisplatin":[37.2,"Intermediate"],"5-FU":[30.73,"Sensitive"],"SN-38":[1.17,"Sensitive"],"Oxaliplatin":[49.63,"Intermediate"],"Mitomycin C":[4.68,"Sensitive"],"Paclitaxel":[1.68,"Sensitive"]},"ECC-8T":{"Gemcitabine":[23.1,"Sensitive"],"Cisplatin":[19.25,"Sensitive"],"5-FU":[61.07,"Sensitive"],"SN-38":[1.53,"Sensitive"],"Oxaliplatin":[89.51,"Resistant"],"Mitomycin C":[15.86,"Sensitive"],"Paclitaxel":[83.43,"Resistant"]},"GBC-10T":{"Gemcitabine":[10.02,"Sensitive"],"Cisplatin":[48.23,"Intermediate"]},"GBC-11T":{"Gemcitabine":[8.42,"Sensitive"],"Cisplatin":[66.51,"Intermediate"],"5-FU":[45.17,"Intermediate"],"SN-38":[2.43,"Sensitive"],"Oxaliplatin":[90.98,"Resistant"],"Mitomycin C":[15.14,"Sensitive"],"Paclitaxel":[64.8,"Intermediate"]},"GBC-16T":{"Cisplatin":[35.94,"Intermediate"]},"GBC-4T":{"Gemcitabine":[7.8,"Sensitive"],"Cisplatin":[27.58,"Sensitive"],"5-FU":[33.79,"Intermediate"],"SN-38":[2.05,"Sensitive"],"Oxaliplatin":[70.39,"Resistant"],"Mitomycin C":[9.05,"Sensitive"],"Paclitaxel":[2.57,"Sensitive"]},"GBC-9T":{"Gemcitabine":[5.42,"Sensitive"],"Cisplatin":[15.58,"Sensitive"],"5-FU":[18.16,"Sensitive"],"SN-38":[1.48,"Sensitive"],"Oxaliplatin":[48.77,"Intermediate"],"Mitomycin C":[6.79,"Sensitive"],"Paclitaxel":[1.35,"Sensitive"]},"ICC-14T":{"Gemcitabine":[19.44,"Sensitive"],"Cisplatin":[30.83,"Sensitive"],"5-FU":[31.52,"Sensitive"],"SN-38":[7.86,"Sensitive"],"Oxaliplatin":[63.97,"Intermediate"],"Mitomycin C":[30.77,"Sensitive"],"Paclitaxel":[46.67,"Intermediate"]},"ICC-16T":{"Cisplatin":[31.27,"Sensitive"]},"ICC-17T":{"Gemcitabine":[2.58,"Sensitive"],"Cisplatin":[35.21,"Intermediate"],"5-FU":[0.82,"Sensitive"],"SN-38":[30.09,"Sensitive"],"Oxaliplatin":[33.55,"Intermediate"],"Mitomycin C":[7.38,"Sensitive"],"Paclitaxel":[29.68,"Sensitive"]},"ICC-19T":{"Cisplatin":[41.81,"Intermediate"]},"ICC-20T":{"Gemcitabine":[6.93,"Sensitive"],"Cisplatin":[28.22,"Sensitive"]},"ICC-21T":{"Gemcitabine":[7.95,"Sensitive"],"Cisplatin":[52.4,"Intermediate"],"5-FU":[31.72,"Sensitive"],"SN-38":[1.21,"Sensitive"],"Oxaliplatin":[51.7,"Intermediate"],"Mitomycin C":[11.07,"Sensitive"],"Paclitaxel":[3.2,"Sensitive"]},"ICC-22T":{"Cisplatin":[17.47,"Sensitive"]},"ICC-23T":{"Gemcitabine":[11.68,"Sensitive"],"Cisplatin":[56.34,"Intermediate"],"5-FU":[42.67,"Intermediate"],"SN-38":[1.61,"Sensitive"],"Oxaliplatin":[79.91,"Resistant"],"Mitomycin C":[19.4,"Sensitive"],"Paclitaxel":[1.92,"Sensitive"]},"ICC-26T":{"Cisplatin":[23.86,"Sensitive"]},"ICC-28T":{"Gemcitabine":[3.43,"Sensitive"],"Cisplatin":[20.97,"Sensitive"],"5-FU":[23.3,"Sensitive"],"SN-38":[0.58,"Sensitive"],"Oxaliplatin":[45.78,"Intermediate"],"Mitomycin C":[7.41,"Sensitive"],"Paclitaxel":[6.9,"Sensitive"]},"ICC-29T":{"Gemcitabine":[4.99,"Sensitive"],"Cisplatin":[34.14,"Intermediate"],"5-FU":[28.67,"Sensitive"],"SN-38":[0.81,"Sensitive"],"Oxaliplatin":[70.61,"Resistant"],"Mitomycin C":[14.35,"Sensitive"],"Paclitaxel":[33.08,"Intermediate"]},"ICC-31T":{"Gemcitabine":[1.64,"Sensitive"],"Cisplatin":[9.62,"Sensitive"],"5-FU":[22.72,"Sensitive"],"SN-38":[1.33,"Sensitive"],"Oxaliplatin":[48.08,"Intermediate"],"Mitomycin C":[7.87,"Sensitive"],"Paclitaxel":[11.8,"Sensitive"]},"ICC-33T1":{"Gemcitabine":[4.09,"Sensitive"],"Cisplatin":[35.52,"Intermediate"]},"ICC-33T2":{"Gemcitabine":[3.52,"Sensitive"],"Cisplatin":[40.03,"Intermediate"]},"ICC-33T3":{"Gemcitabine":[8.76,"Sensitive"],"Cisplatin":[38.44,"Intermediate"]},"ICC-34T":{"Cisplatin":[23.01,"Sensitive"]},"ICC-36T":{"Gemcitabine":[5.4,"Sensitive"],"Cisplatin":[44.2,"Intermediate"],"5-FU":[22.91,"Sensitive"],"SN-38":[1.01,"Sensitive"],"Oxaliplatin":[100.0,"Resistant"],"Mitomycin C":[8.18,"Sensitive"],"Paclitaxel":[15.5,"Sensitive"]},"ICC-37T1":{"Gemcitabine":[4.55,"Sensitive"],"Cisplatin":[17.21,"Sensitive"],"5-FU":[10.31,"Sensitive"],"SN-38":[1.18,"Sensitive"],"Oxaliplatin":[32.29,"Sensitive"],"Mitomycin C":[10.43,"Sensitive"],"Paclitaxel":[12.63,"Sensitive"]},"ICC-37T2":{"Gemcitabine":[5.54,"Sensitive"],"Cisplatin":[19.1,"Sensitive"],"5-FU":[22.89,"Sensitive"],"SN-38":[1.08,"Sensitive"],"Oxaliplatin":[45.93,"Intermediate"],"Mitomycin C":[12.46,"Sensitive"],"Paclitaxel":[15.57,"Sensitive"]},"ICC-37T3":{"Gemcitabine":[20.79,"Sensitive"],"Cisplatin":[37.22,"Intermediate"],"5-FU":[67.97,"Resistant"],"SN-38":[2.93,"Sensitive"],"Oxaliplatin":[77.55,"Resistant"],"Mitomycin C":[25.8,"Sensitive"],"Paclitaxel":[85.83,"Resistant"]},"ICC-38T":{"Gemcitabine":[1.6,"Sensitive"],"Cisplatin":[2.91,"Sensitive"],"5-FU":[22.91,"Sensitive"],"SN-38":[25.05,"Sensitive"],"Oxaliplatin":[35.36,"Intermediate"],"Mitomycin C":[8.4,"Sensitive"],"Paclitaxel":[16.86,"Sensitive"]},"ICC-45T":{"Gemcitabine":[26.04,"Sensitive"],"Cisplatin":[16.64,"Sensitive"],"5-FU":[52.01,"Intermediate"],"SN-38":[9.41,"Sensitive"],"Oxaliplatin":[56.17,"Intermediate"],"Mitomycin C":[18.32,"Sensitive"],"Paclitaxel":[50.09,"Intermediate"]},"ICC-46T":{"Gemcitabine":[4.75,"Sensitive"],"Cisplatin":[28.88,"Sensitive"],"5-FU":[22.73,"Sensitive"],"SN-38":[0.37,"Sensitive"],"Oxaliplatin":[34.4,"Intermediate"],"Mitomycin C":[6.37,"Sensitive"],"Paclitaxel":[10.72,"Sensitive"]},"ICC-46T-MA":{"Gemcitabine":[2.52,"Sensitive"],"Cisplatin":[8.39,"Sensitive"],"5-FU":[6.05,"Sensitive"],"SN-38":[0.25,"Sensitive"],"Oxaliplatin":[39.17,"Intermediate"],"Mitomycin C":[4.31,"Sensitive"],"Paclitaxel":[5.84,"Sensitive"]},"ICC-47T":{"Gemcitabine":[7.43,"Sensitive"],"Cisplatin":[20.71,"Sensitive"],"5-FU":[15.69,"Sensitive"],"SN-38":[5.12,"Sensitive"],"Oxaliplatin":[100.0,"Resistant"],"Mitomycin C":[8.76,"Sensitive"],"Paclitaxel":[20.95,"Sensitive"]},"ICC-49T":{"Gemcitabine":[6.61,"Sensitive"],"Cisplatin":[82.08,"Resistant"],"5-FU":[53.12,"Intermediate"],"SN-38":[2.28,"Sensitive"],"Oxaliplatin":[100.0,"Resistant"],"Mitomycin C":[11.89,"Sensitive"],"Paclitaxel":[31.35,"Sensitive"]},"ICC-4T":{"Gemcitabine":[10.86,"Sensitive"],"Cisplatin":[22.57,"Sensitive"]},"ICC-50T1":{"Gemcitabine":[4.06,"Sensitive"],"Cisplatin":[100.0,"Resistant"],"5-FU":[41.77,"Intermediate"],"SN-38":[1.6,"Sensitive"],"Oxaliplatin":[100.0,"Resistant"],"Mitomycin C":[26.82,"Sensitive"],"Paclitaxel":[26.69,"Sensitive"]},"ICC-50T2":{"Gemcitabine":[1.45,"Sensitive"],"Cisplatin":[53.75,"Intermediate"],"5-FU":[16.72,"Sensitive"],"SN-38":[0.9,"Sensitive"],"Oxaliplatin":[79.37,"Resistant"],"Mitomycin C":[7.21,"Sensitive"],"Paclitaxel":[8.95,"Sensitive"]},"ICC-53T":{"Gemcitabine":[2.85,"Sensitive"],"Cisplatin":[26.19,"Sensitive"],"5-FU":[14.81,"Sensitive"],"SN-38":[1.35,"Sensitive"],"Oxaliplatin":[35.55,"Intermediate"],"Mitomycin C":[9.0,"Sensitive"],"Paclitaxel":[4.98,"Sensitive"]},"ICC-57T":{"Gemcitabine":[3.08,"Sensitive"],"Cisplatin":[40.42,"Intermediate"],"5-FU":[31.27,"Sensitive"],"SN-38":[1.25,"Sensitive"],"Oxaliplatin":[88.22,"Resistant"],"Mitomycin C":[23.01,"Sensitive"],"Paclitaxel":[41.81,"Intermediate"]},"ICC-58T":{"Gemcitabine":[5.61,"Sensitive"],"Cisplatin":[49.31,"Intermediate"],"5-FU":[14.81,"Sensitive"],"SN-38":[3.77,"Sensitive"],"Oxaliplatin":[55.87,"Intermediate"],"Mitomycin C":[7.5,"Sensitive"],"Paclitaxel":[30.29,"Sensitive"]},"ICC-5T":{"Gemcitabine":[3.08,"Sensitive"],"Cisplatin":[40.42,"Intermediate"]},"ICC-62T1":{"Gemcitabine":[28.82,"Sensitive"],"Cisplatin":[12.86,"Sensitive"],"5-FU":[30.45,"Sensitive"],"SN-38":[17.41,"Sensitive"],"Oxaliplatin":[60.01,"Intermediate"],"Mitomycin C":[11.65,"Sensitive"],"Paclitaxel":[34.34,"Intermediate"]},"ICC-62T2":{"Gemcitabine":[26.64,"Sensitive"],"Cisplatin":[14.53,"Sensitive"]},"ICC-63T":{"Gemcitabine":[0.76,"Sensitive"],"Cisplatin":[6.68,"Sensitive"],"5-FU":[9.77,"Sensitive"],"SN-38":[0.3,"Sensitive"],"Oxaliplatin":[34.68,"Intermediate"],"Mitomycin C":[10.88,"Sensitive"],"Paclitaxel":[0.98,"Sensitive"]},"ICC-65T":{"Gemcitabine":[3.17,"Sensitive"],"Cisplatin":[35.04,"Intermediate"],"5-FU":[4.57,"Sensitive"],"SN-38":[0.32,"Sensitive"],"Oxaliplatin":[41.76,"Intermediate"],"Mitomycin C":[4.64,"Sensitive"],"Paclitaxel":[13.64,"Sensitive"]},"ICC-67T":{"Gemcitabine":[9.53,"Sensitive"],"Cisplatin":[100.0,"Resistant"],"5-FU":[68.36,"Resistant"],"SN-38":[1.72,"Sensitive"],"Oxaliplatin":[95.46,"Resistant"],"Mitomycin C":[7.12,"Sensitive"],"Paclitaxel":[54.64,"Intermediate"]},"ICC-69T":{"Gemcitabine":[23.46,"Sensitive"],"Cisplatin":[44.19,"Intermediate"],"5-FU":[45.51,"Intermediate"],"SN-38":[2.85,"Sensitive"],"Oxaliplatin":[72.1,"Resistant"],"Mitomycin C":[22.9,"Sensitive"],"Paclitaxel":[75.24,"Resistant"]},"ICC-71T":{"Gemcitabine":[2.98,"Sensitive"],"Cisplatin":[18.78,"Sensitive"],"5-FU":[10.86,"Sensitive"],"SN-38":[0.63,"Sensitive"],"Oxaliplatin":[40.52,"Intermediate"],"Mitomycin C":[5.82,"Sensitive"],"Paclitaxel":[9.08,"Sensitive"]},"ICC-72T":{"Gemcitabine":[2.44,"Sensitive"],"Cisplatin":[13.24,"Sensitive"],"5-FU":[19.06,"Sensitive"],"SN-38":[1.74,"Sensitive"],"Oxaliplatin":[39.11,"Intermediate"],"Mitomycin C":[11.98,"Sensitive"],"Paclitaxel":[6.45,"Sensitive"]},"ICC-73T-MA":{"Gemcitabine":[54.45,"Intermediate"],"Cisplatin":[54.36,"Intermediate"],"5-FU":[93.09,"Resistant"],"SN-38":[11.05,"Sensitive"],"Oxaliplatin":[67.53,"Resistant"],"Mitomycin C":[7.94,"Sensitive"],"Paclitaxel":[39.98,"Intermediate"]},"ICC-7T":{"Gemcitabine":[3.26,"Sensitive"],"Cisplatin":[29.11,"Sensitive"],"5-FU":[26.63,"Sensitive"],"SN-38":[0.55,"Sensitive"],"Oxaliplatin":[35.16,"Intermediate"],"Mitomycin C":[6.87,"Sensitive"],"Paclitaxel":[17.98,"Sensitive"]},"ICC-8T":{"Gemcitabine":[2.12,"Sensitive"],"Cisplatin":[12.36,"Sensitive"],"5-FU":[26.18,"Sensitive"],"SN-38":[1.08,"Sensitive"],"Oxaliplatin":[43.83,"Intermediate"],"Mitomycin C":[10.37,"Sensitive"],"Paclitaxel":[16.84,"Sensitive"]}}
# Organoid ID -> patient ID from the biliary Table S1; unlisted organoids use their own ID.
BILIARY_PATIENT = {"ECC-14T":"ECC-14T-P","ECC-15T":"ECC-15T-P","ECC-16T":"ECC-16T-P","ECC-19T":"ECC-19T-P","ECC-1T":"ECC-1T-P","ECC-20T":"ECC-20T-P","ECC-21T":"ECC-21T-P","ECC-26T":"ECC-26T-P","ECC-27T":"ECC-27T-P","ECC-2T":"ECC-2T-P","ECC-4T":"ECC-4T-P","ECC-8T":"ECC-8T-P","GBC-10T":"GBC-10T-P","GBC-11T":"GBC-11T-P","GBC-16T":"GBC-16T-P","GBC-4T":"GBC-4T-P","GBC-9T":"GBC-9T-P","ICC-14T":"ICC-14T-P","ICC-16T":"ICC-16T-P","ICC-17T":"ICC-17T-P","ICC-19T":"ICC-19T-P","ICC-20T":"ICC-20T-P","ICC-21T":"ICC-21T-P","ICC-22T":"ICC-22T-P","ICC-23T":"ICC-23T-P","ICC-26T":"ICC-26T-P","ICC-28T":"ICC-28T-P","ICC-29T":"ICC-29T-P","ICC-31T":"ICC-31T-P","ICC-33T1":"ICC-33T-P","ICC-33T2":"ICC-33T-P","ICC-33T3":"ICC-33T-P","ICC-34T":"ICC-34T-P","ICC-37T1":"ICC-37T-P","ICC-37T2":"ICC-37T-P","ICC-37T3":"ICC-37T-P","ICC-38T":"ICC-38T-P","ICC-45T":"ICC-45T-P","ICC-46T":"ICC-46T-P","ICC-46T-MA":"ICC-46T-P","ICC-47T":"ICC-47T-P","ICC-49T":"ICC-49T-P","ICC-4T":"ICC-4T-P","ICC-50T1":"ICC-50T-P","ICC-50T2":"ICC-50T-P","ICC-53T":"ICC-53T-P","ICC-58T":"ICC-58T-P","ICC-5T":"ICC-5T-P","ICC-62T1":"ICC-62T-P","ICC-62T2":"ICC-62T-P","ICC-63T":"ICC-63T-P","ICC-65T":"ICC-65T-P","ICC-67T":"ICC-67T-P","ICC-69T":"ICC-69T-P","ICC-71T":"ICC-71T-P","ICC-72T":"ICC-72T-P","ICC-73T-MA":"ICC-73T-P","ICC-7T":"ICC-7T-P","ICC-8T":"ICC-8T-P"}
# Regimen acronym -> the two drugs whose organoid readouts form the two channels.
REGIMEN_PAIRS = {
    'SOX': ('5-FU', 'Oxaliplatin'), 'XELOX': ('5-FU', 'Oxaliplatin'), 'CAPOX': ('5-FU', 'Oxaliplatin'),
    'FOLFOX': ('5-FU', 'Oxaliplatin'), 'MFOLFOX6': ('5-FU', 'Oxaliplatin'), 'FLOT': ('5-FU', 'Oxaliplatin'),
    'GEMOX': ('Gemcitabine', 'Oxaliplatin'), 'GP': ('Gemcitabine', 'Cisplatin'), 'GC': ('Gemcitabine', 'Cisplatin'),
    'GEMCIS': ('Gemcitabine', 'Cisplatin'), 'SP': ('5-FU', 'Cisplatin'), 'FP': ('5-FU', 'Cisplatin'),
    'XP': ('5-FU', 'Cisplatin'), 'FOLFIRI': ('5-FU', 'SN-38'), 'XELIRI': ('5-FU', 'SN-38'),
    'IRIS': ('5-FU', 'SN-38'), 'GS': ('Gemcitabine', '5-FU'), 'GX': ('Gemcitabine', '5-FU'),
    'DS': ('5-FU', 'Paclitaxel'), 'PS': ('5-FU', 'Paclitaxel'), 'AG': ('Gemcitabine', 'Paclitaxel'),
    'GNP': ('Gemcitabine', 'Paclitaxel'),
}
# Drug names that map a free-text regimen onto a readout, and the pair priority when two appear.
DRUG_WORDS = {
    'Oxaliplatin': ('oxaliplatin',), 'Cisplatin': ('cisplatin', 'ddp'), 'Gemcitabine': ('gemcitabine', 'gemzar'),
    '5-FU': ('5-fu', '5fu', 'fluorouracil', 'capecitabine', 'xeloda', 's-1', 's1', 'tegafur', 'tegio'),
    'SN-38': ('irinotecan', 'cpt-11'), 'Paclitaxel': ('paclitaxel', 'docetaxel', 'taxol', 'nab-paclitaxel'),
}
PAIR_PRIORITY = (('5-FU', 'Oxaliplatin'), ('Gemcitabine', 'Oxaliplatin'), ('Gemcitabine', 'Cisplatin'),
                 ('5-FU', 'Cisplatin'), ('5-FU', 'SN-38'), ('5-FU', 'Paclitaxel'),
                 ('Gemcitabine', '5-FU'), ('Gemcitabine', 'Paclitaxel'))
# Clinical-response words -> outcome class, used only by the scoring script.
DISEASE_CONTROL = {'responder': ('cr', 'pr', 'sd', 'complete response', 'partial response', 'stable disease',
                                 'sensitive', 'effective', 'no recurrence', 'disease-free', 'no relapse', 'ned'),
                   'non_responder': ('pd', 'progressive disease', 'progression', 'resistant', 'ineffective',
                                     'recurrence', 'relapse')}
OBJECTIVE_RESPONSE = {'responder': ('cr', 'pr', 'complete response', 'partial response'),
                      'non_responder': ('sd', 'pd', 'stable disease', 'progressive disease', 'progression')}


def patient_auc():
    cohorts = {'gastric': {o: dict(v) for o, v in GASTRIC_AUC.items()}, 'biliary': {}}
    grouped = {}
    for organoid, drugs in BILIARY_AUC.items():
        grouped.setdefault(BILIARY_PATIENT.get(organoid, organoid), []).append(drugs)
    for patient, organoids in grouped.items():
        cohorts['biliary'][patient] = {
            drug: statistics.mean(o[drug][0] for o in organoids if drug in o)
            for drug in {d for o in organoids for d in o}}
    return cohorts


def calls(cohort_auc, author_class=False):
    drugs = sorted({d for v in cohort_auc.values() for d in v})
    medians = {d: statistics.median(v[d] for v in cohort_auc.values() if d in v) for d in drugs}
    out = {}
    for patient, values in cohort_auc.items():
        out[patient] = {d: (values[d] < 33.0 if author_class else values[d] <= medians[d]) for d in values}
    return out, medians


def predictions(cohort_calls):
    out = {}
    for patient, c in sorted(cohort_calls.items()):
        pairs = {}
        for a, b in PAIR_PRIORITY:
            if a in c and b in c:
                agree = c[a] == c[b]
                pairs[a + '+' + b] = {'release': agree,
                                      'predicted': ('responder' if c[a] else 'non_responder') if agree else 'retest'}
        out[patient] = {'drug_sensitive': c, 'pairs': pairs}
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', default='blind_predictions.json')
    args = parser.parse_args()
    auc = patient_auc()
    result = {'schema': 'blind.consensus.predictions.v1', 'sources': SOURCES,
              'rule': 'per drug, sensitive if patient AUC <= cohort median; release a regimen call only when its two drugs agree',
              'regimen_pairs': {k: list(v) for k, v in REGIMEN_PAIRS.items()},
              'pair_priority': ['+'.join(p) for p in PAIR_PRIORITY],
              'drug_words': {k: list(v) for k, v in DRUG_WORDS.items()},
              'outcome_words': {'disease_control_primary': DISEASE_CONTROL, 'objective_response_secondary': OBJECTIVE_RESPONSE},
              'cohorts': {}}
    for name, cohort_auc in auc.items():
        median_calls, medians = calls(cohort_auc)
        entry = {'patients': len(cohort_auc), 'medians': {d: round(m, 4) for d, m in medians.items()},
                 'primary_median_split': predictions(median_calls)}
        if name == 'biliary':
            entry['secondary_author_class'] = predictions(calls(cohort_auc, author_class=True)[0])
        result['cohorts'][name] = entry
    with open(args.out, 'w') as handle:
        json.dump(result, handle, indent=1, sort_keys=True)
        handle.write('\n')
    print(json.dumps({n: {'patients': c['patients'], 'medians': c['medians']} for n, c in result['cohorts'].items()}, indent=1))


if __name__ == '__main__':
    main()

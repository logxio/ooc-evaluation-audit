# Human PDO Acquisition and Physical Plate Drift

## Two wave acquisition

The JCI evaluation contains 240 human pancreatic cancer 3D PDO curves at 10 concentrations, with 7,200 reference wells, three material lines and eight passage clusters. The MODEL policy uses 3,096 wells and saves 57.00% [54.00%, 60.00%]. The measured only policy (MO) uses 3,300 wells and saves 54.17% [50.67%, 57.50%]. MODEL saves 204 additional wells [144, 264], equivalent to 2.83 percentage points [2.00, 3.67]. Intervals use 10,000 paired stratified passage cluster bootstrap draws, seed 55.

MODEL completes acquisition in a mean of 1.32 waves, with 163 curves completed in wave one and 77 in wave two. It misses 1 of 240 curves. MO misses 0 of 240. MODEL issues 215 ranking certificates, with 215 correct certificates. Its top 20% selection overlap is 44/48, or 0.9167, and mean within drug AUC Spearman correlation is 0.8851. The binary two wave policy uses 1,629 wells, saves 77.38% and misses 0 of 240 curves.

## Material line results

| Material | Curves | Reference wells | MODEL wells | MODEL saving | MO wells | MO saving | Net wells saved | MODEL misses | MO misses |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| hF24 | 90 | 2700 | 1278 | 52.67% | 1290 | 52.22% | 12 | 0 | 0 |
| hM1F | 90 | 2700 | 1098 | 59.33% | 1218 | 54.89% | 120 | 0 | 0 |
| hT1 | 60 | 1800 | 720 | 60.00% | 792 | 56.00% | 72 | 1 | 0 |

## Drug results

| Drug | Curves | Reference wells | MODEL wells | MODEL saving | MO wells | MO saving | Net wells saved | MODEL misses | MO misses |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 5-fluorouracil | 40 | 1200 | 384 | 68.00% | 492 | 59.00% | 108 | 0 | 0 |
| SN-38 | 40 | 1200 | 576 | 52.00% | 552 | 54.00% | -24 | 0 | 0 |
| gemcitabine | 40 | 1200 | 600 | 50.00% | 612 | 49.00% | 12 | 0 | 0 |
| oxaliplatin | 40 | 1200 | 528 | 56.00% | 600 | 50.00% | 72 | 1 | 0 |
| paclitaxel | 40 | 1200 | 480 | 60.00% | 480 | 60.00% | 0 | 0 | 0 |
| trametinib | 40 | 1200 | 528 | 56.00% | 564 | 53.00% | 36 | 0 | 0 |

## Physical cross plate drift sensitivity

ToxCast contributes 273 endpoint specific physical drift pairs from 91 physical sample plate pairs and 88 compounds across three endpoints. The replay evaluates 77 empirical assignments per endpoint and calibration mode, for 924 scenarios. It transports the measured H9 physical drift to the fixed PDO acquisition masks and applies disturbances in wave two. Wave one calls stay fixed. Each table row summarizes 77 scenarios. Percentile ranges in the artifact describe empirical reassignment sensitivity.

| Endpoint | Calibration | Policy | Scenarios | Wells | Saving | Misses | Top K | AUC Spearman | IC50 Spearman |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| STM_H9_CystineISnorm_perc | unbridged | MODEL | 77 | 3096 | 57.00% | 1/240 | 0.6415 | 0.6102 | 0.5167 |
| STM_H9_CystineISnorm_perc | unbridged | MO | 77 | 3300 | 54.17% | 0/240 | 0.5904 | 0.5719 | 0.4989 |
| STM_H9_CystineISnorm_perc | reference_translation | MODEL | 77 | 3096 | 57.00% | 1/240 | 0.6434 | 0.6102 | 0.5166 |
| STM_H9_CystineISnorm_perc | reference_translation | MO | 77 | 3300 | 54.17% | 0/240 | 0.5912 | 0.5716 | 0.4987 |
| STM_H9_CystineISnorm_perc | reference_ratio | MODEL | 77 | 3096 | 57.00% | 1/240 | 0.6399 | 0.6097 | 0.5161 |
| STM_H9_CystineISnorm_perc | reference_ratio | MO | 77 | 3300 | 54.17% | 0/240 | 0.5898 | 0.5714 | 0.4982 |
| STM_H9_CystineISnorm_perc | two_control_affine_diagnostic | MODEL | 77 | 3327 | 53.79% | 1/240 | 0.6767 | 0.6764 | 0.5671 |
| STM_H9_CystineISnorm_perc | two_control_affine_diagnostic | MO | 77 | 3576 | 50.33% | 0/240 | 0.6502 | 0.6618 | 0.5514 |
| STM_H9_OrnithineISnorm_perc | unbridged | MODEL | 77 | 3096 | 57.00% | 1/240 | 0.7416 | 0.7600 | 0.6326 |
| STM_H9_OrnithineISnorm_perc | unbridged | MO | 77 | 3300 | 54.17% | 0/240 | 0.7389 | 0.7625 | 0.6383 |
| STM_H9_OrnithineISnorm_perc | reference_translation | MODEL | 77 | 3096 | 57.00% | 1/240 | 0.7378 | 0.7581 | 0.6313 |
| STM_H9_OrnithineISnorm_perc | reference_translation | MO | 77 | 3300 | 54.17% | 0/240 | 0.7319 | 0.7579 | 0.6356 |
| STM_H9_OrnithineISnorm_perc | reference_ratio | MODEL | 77 | 3096 | 57.00% | 1/240 | 0.7403 | 0.7589 | 0.6321 |
| STM_H9_OrnithineISnorm_perc | reference_ratio | MO | 77 | 3300 | 54.17% | 0/240 | 0.7354 | 0.7587 | 0.6372 |
| STM_H9_OrnithineISnorm_perc | two_control_affine_diagnostic | MODEL | 77 | 3327 | 53.79% | 1/240 | 0.7321 | 0.7527 | 0.6301 |
| STM_H9_OrnithineISnorm_perc | two_control_affine_diagnostic | MO | 77 | 3576 | 50.33% | 1/240 | 0.7381 | 0.7494 | 0.6281 |
| STM_H9_OrnCyssISnorm_ratio | unbridged | MODEL | 77 | 3096 | 57.00% | 1/240 | 0.7143 | 0.7494 | 0.6140 |
| STM_H9_OrnCyssISnorm_ratio | unbridged | MO | 77 | 3300 | 54.17% | 0/240 | 0.6935 | 0.7429 | 0.6146 |
| STM_H9_OrnCyssISnorm_ratio | reference_translation | MODEL | 77 | 3096 | 57.00% | 1/240 | 0.7132 | 0.7467 | 0.6119 |
| STM_H9_OrnCyssISnorm_ratio | reference_translation | MO | 77 | 3300 | 54.17% | 0/240 | 0.6870 | 0.7410 | 0.6125 |
| STM_H9_OrnCyssISnorm_ratio | reference_ratio | MODEL | 77 | 3096 | 57.00% | 1/240 | 0.7178 | 0.7476 | 0.6133 |
| STM_H9_OrnCyssISnorm_ratio | reference_ratio | MO | 77 | 3300 | 54.17% | 0/240 | 0.6929 | 0.7422 | 0.6144 |
| STM_H9_OrnCyssISnorm_ratio | two_control_affine_diagnostic | MODEL | 77 | 3327 | 53.79% | 1/240 | 0.7067 | 0.7305 | 0.6124 |
| STM_H9_OrnCyssISnorm_ratio | two_control_affine_diagnostic | MO | 77 | 3576 | 50.33% | 0/240 | 0.7054 | 0.7305 | 0.6058 |

The three primary calibration modes retain MODEL saving of 57.00% and 1/240 missed curves. The two control affine diagnostic charges an additional control group per wave two curve, uses 3,327 wells and saves 53.79%. Its Cystine AUC Spearman correlation is 0.6764. The second control supplies the distinct response reference needed to identify translation and gain.

## Data and recalculation

[Curve level records](artifacts/final_v3_jci.rows.json), [acquisition summary](artifacts/final_v3_jci.json) and [physical drift scenarios](artifacts/final_v3_jci_drift_sensitivity.json) contain the released numerical evidence. The verifier recomputes acquisition totals, within drug ranking, paired bootstrap intervals and every drift summary from those records, and checks their SHA256 digests.

```sh
python workbench/audits/axis_a_v3_s56/verify_receipt.py
```

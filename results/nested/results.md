# Retrospective drug-disjoint release evaluation

Primary folds 1–4 contain 188 drug groups, 193 substances and 965 alternative three-point designs. All five outer folds were completed; historical development fold 0 is reported separately.

| Method | Released/designs | Wrong/all designs | Wrong/released | Full-coverage wrong/designs | Drug-mean wrong-release loss | Exposed wells used | Savings vs full | Savings vs three-point calibrated fallback |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| AnchorBoost + group CRC | 946/965 (98.03%) | 77/965 (7.98%) | 77/946 (8.14%) | 88/965 (9.12%) | 8.09% | 11588 | 58.73% | 15.24% |
| Log-linear + group CRC | 789/965 (81.76%) | 76/965 (7.88%) | 76/789 (9.63%) | 132/965 (13.68%) | 8.09% | 13923 | 50.42% | -1.84% |
| Three measured points + group CRC | 806/965 (83.52%) | 75/965 (7.77%) | 75/806 (9.31%) | 131/965 (13.58%) | 7.98% | 13671 | 51.31% | 0.00% |
| Observed-active release; otherwise full measurement | 626/965 (64.87%) | 0/965 (0.00%) | 0/626 (0.00%) | 134/965 (13.89%) | 0.00% | 17017 | 39.40% | -24.48% |

The full-series baseline uses 28080 exposed wells across these alternative designs. Agreement with its own reference equals one by construction. Controls, repeats and overhead are outside all exposed-well counts.

| Outer fold | Test drug groups | Test designs | AB release | AB wrong/all | AB wrong/released | AB drug loss | Measured-only release | Measured-only wrong/all |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 49 | 250 | 90.40% | 10.00% | 11.06% | 10.20% | 61.60% | 3.60% |
| 1 | 48 | 250 | 92.40% | 6.40% | 6.93% | 6.67% | 66.80% | 4.80% |
| 2 | 49 | 255 | 100.00% | 7.06% | 7.06% | 6.94% | 91.76% | 5.10% |
| 3 | 45 | 230 | 100.00% | 10.00% | 10.00% | 10.22% | 81.30% | 10.00% |
| 4 | 46 | 230 | 100.00% | 8.70% | 8.70% | 8.70% | 94.78% | 11.74% |

| Outer fold | Calibration drugs | AB margin | Corrected calibration loss | Feasible grid value |
|---|---:|---:|---:|---|
| 0 | 91 | 0.05 | 8.91% | True |
| 1 | 91 | 0.05 | 9.35% | True |
| 2 | 91 | -1.0 | 9.78% | True |
| 3 | 95 | -1.0 | 9.17% | True |
| 4 | 94 | -1.0 | 8.63% | True |

Margin −1 releases every design. Folds 2–4 selected it from calibration data. Every fitted fold had a feasible margin; the insufficient-calibration all-fallback branch is covered by the arithmetic check. Realized drug loss in fold 3 is 10.22%; in historical development fold 0 it is 10.20%.

## Paired primary comparisons

Differences are AnchorBoost minus comparator, with 4,000 drug bootstrap resamples at fixed fitted decisions. Intervals do not include refitting uncertainty.

| Comparator | Drug loss difference [95% interval] | Release difference [95% interval] | Full-coverage error difference [95% interval] |
|---|---:|---:|---:|
| Log-linear + group CRC | +0.00 pp [-1.91, +2.02] | +16.31 pp [+12.64, +20.16] | -4.56 pp [-6.81, -2.34] |
| Three measured points + group CRC | +0.11 pp [-1.81, +2.02] | +14.56 pp [+11.05, +18.39] | -4.45 pp [-6.76, -2.29] |
| Observed-active release; otherwise full measurement | +8.09 pp [+5.85, +10.64] | +33.28 pp [+27.80, +39.15] | -4.77 pp [-7.20, -2.50] |

## Historical replay, separate experiment

| Method | Designs | Released | Wrong releases | Error/all | Error/released | Exposed wells used | Savings vs full |
|---|---:|---:|---:|---:|---:|---:|---:|
| anchorboost | 970 | 905 | 79 | 8.14% | 8.73% | 12240 | 56.57% |
| measured_only | 970 | 711 | 79 | 8.14% | 11.11% | 15373 | 45.46% |

## Claim scope

Observed primary drug loss at alpha=0.10: True. Positive release gain with a bootstrap lower bound above zero: True. Lower full-coverage error with an upper bound below zero: True.

The primary drug-loss bootstrap interval at fixed decisions is [5.85%, 10.64%]. Its upper end exceeds 10%. The supported empirical claim is increased release and lower exposed-well replay cost, with the observed risk and its uncertainty reported alongside the benefit.

These are retrospective empirical comparisons. The mathematical CRC statement concerns expected marginal drug loss under exchangeability. Error among released designs, each realized batch risk, prospective laboratory savings, donor generalization and independent batch generalization remain different claims. Normalization and conservative identity grouping changed relative to the historical replay, so the difference between old and new totals does not isolate the effect of correcting a single leak.

Implementation and artifacts: `protocol.json`, `splits.json`, `identities.json`, per-fold `pretest_freeze.json` and `prediction_freeze.json`, `point_predictions.csv.gz`, `drug_decisions.csv`, `design_decisions.csv`, `summary.json`, `verification.json`, and `data_flow.md`.

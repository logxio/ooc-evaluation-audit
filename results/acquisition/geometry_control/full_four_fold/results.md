# Post hoc highest-unobserved geometry control

Completed folds: [1, 2, 3, 4]; 194 drugs / 970 designs.

This control was added after the original acquisition results. All forecasts, initial designs, 
targets and update rules are reused from the frozen experiment. The rule selects the maximum 
original unobserved log concentration. The two strata use only original concentration geometry.

Differences are highest minus comparator; negative favors highest. Drug means average the 
available designs within each stratum. Intervals are 10,000 paired drug bootstrap replicates 
(seed 0); sign tests are exact and two-sided. The same drug can occur in both strata. 
Intervals condition on fitted models; comparisons are exploratory without multiplicity correction.

The all-recorded CNP rows retain the original identity overlap. Use the common identity-clean population for four-predictor inference. Excluded there: ['Phenobarbital'].

## all_recorded / all

194 drugs, 970 designs.

| Predictor | Comparator | Highest MAE | Comparator MAE | Difference [95% CI] | Win/tie/loss | Sign p |
|---|---|---:|---:|---|---|---:|
| interpolation | model_disagreement | 0.935643 | 0.857766 | +0.077877 [+0.054216, +0.104105] | 38/57/99 | 1.87794e-07 |
| interpolation | uniform_random | 0.935643 | 0.956180 | -0.020537 [-0.046893, +0.007677] | 126/0/68 | 3.7732e-05 |
| interpolation | fixed_maximin | 0.935643 | 0.902627 | +0.033017 [+0.002127, +0.065333] | 89/0/105 | 0.281477 |
| anchorboost_all | model_disagreement | 0.806681 | 0.764657 | +0.042024 [+0.025069, +0.061132] | 61/57/76 | 0.231537 |
| anchorboost_all | uniform_random | 0.806681 | 0.840219 | -0.033538 [-0.054435, -0.011947] | 135/0/59 | 4.94637e-08 |
| anchorboost_all | fixed_maximin | 0.806681 | 0.816776 | -0.010095 [-0.032863, +0.013447] | 118/0/76 | 0.00314216 |
| anchorboost_five | model_disagreement | 0.808475 | 0.769386 | +0.039089 [+0.023206, +0.057149] | 61/57/76 | 0.231537 |
| anchorboost_five | uniform_random | 0.808475 | 0.843757 | -0.035281 [-0.055088, -0.014279] | 135/0/59 | 4.94637e-08 |
| anchorboost_five | fixed_maximin | 0.808475 | 0.819802 | -0.011327 [-0.033387, +0.011692] | 120/0/74 | 0.00117794 |
| cnp | model_disagreement | 0.817592 | 0.775954 | +0.041638 [+0.019495, +0.069056] | 69/57/68 | 1 |
| cnp | uniform_random | 0.817592 | 0.864735 | -0.047143 [-0.069631, -0.023972] | 136/0/58 | 2.10883e-08 |
| cnp | fixed_maximin | 0.817592 | 0.837865 | -0.020272 [-0.046227, +0.008398] | 119/0/75 | 0.00194348 |

| Choices | Matches / designs | Overlap |
|---|---:|---:|
| highest_unobserved / model_disagreement | 635.000 / 970 | 65.46% |
| highest_unobserved / uniform_random | 231.020 / 970 | 23.82% |
| highest_unobserved / fixed_maximin | 252.000 / 970 | 25.98% |
| model_disagreement / uniform_random | 231.020 / 970 | 23.82% |
| model_disagreement / fixed_maximin | 353.000 / 970 | 36.39% |
| uniform_random / fixed_maximin | 231.020 / 970 | 23.82% |

## all_recorded / top_dose_initially_measured=True

181 drugs, 406 designs.

| Predictor | Comparator | Highest MAE | Comparator MAE | Difference [95% CI] | Win/tie/loss | Sign p |
|---|---|---:|---:|---|---|---:|
| interpolation | model_disagreement | 0.914912 | 0.820597 | +0.094315 [+0.059070, +0.136979] | 32/67/82 | 3.13852e-06 |
| interpolation | uniform_random | 0.914912 | 0.888401 | +0.026511 [-0.005124, +0.061537] | 83/0/98 | 0.298039 |
| interpolation | fixed_maximin | 0.914912 | 0.853938 | +0.060974 [+0.017744, +0.108036] | 79/0/102 | 0.101733 |
| anchorboost_all | model_disagreement | 0.777564 | 0.739061 | +0.038502 [+0.019546, +0.059033] | 52/67/62 | 0.399373 |
| anchorboost_all | uniform_random | 0.777564 | 0.785203 | -0.007640 [-0.028944, +0.013992] | 97/0/84 | 0.372465 |
| anchorboost_all | fixed_maximin | 0.777564 | 0.779087 | -0.001523 [-0.033421, +0.029782] | 95/0/86 | 0.552207 |
| anchorboost_five | model_disagreement | 0.778512 | 0.745518 | +0.032995 [+0.015230, +0.052648] | 52/67/62 | 0.399373 |
| anchorboost_five | uniform_random | 0.778512 | 0.789342 | -0.010829 [-0.032013, +0.010013] | 99/0/82 | 0.234245 |
| anchorboost_five | fixed_maximin | 0.778512 | 0.785438 | -0.006925 [-0.038719, +0.024028] | 100/0/81 | 0.180762 |
| cnp | model_disagreement | 0.784556 | 0.747955 | +0.036601 [+0.011751, +0.069130] | 62/67/52 | 0.399373 |
| cnp | uniform_random | 0.784556 | 0.805246 | -0.020689 [-0.043538, +0.004645] | 111/0/70 | 0.00284416 |
| cnp | fixed_maximin | 0.784556 | 0.795829 | -0.011272 [-0.047439, +0.029920] | 108/0/73 | 0.0112915 |

| Choices | Matches / designs | Overlap |
|---|---:|---:|
| highest_unobserved / model_disagreement | 205.000 / 406 | 50.49% |
| highest_unobserved / uniform_random | 98.299 / 406 | 24.21% |
| highest_unobserved / fixed_maximin | 0.000 / 406 | 0.00% |
| model_disagreement / uniform_random | 98.299 / 406 | 24.21% |
| model_disagreement / fixed_maximin | 90.000 / 406 | 22.17% |
| uniform_random / fixed_maximin | 98.299 / 406 | 24.21% |

## all_recorded / top_dose_initially_measured=False

191 drugs, 564 designs.

| Predictor | Comparator | Highest MAE | Comparator MAE | Difference [95% CI] | Win/tie/loss | Sign p |
|---|---|---:|---:|---|---|---:|
| interpolation | model_disagreement | 0.955277 | 0.879226 | +0.076051 [+0.049839, +0.105603] | 18/115/58 | 4.71324e-06 |
| interpolation | uniform_random | 0.955277 | 0.998442 | -0.043165 [-0.073864, -0.011161] | 138/0/53 | 6.38014e-10 |
| interpolation | fixed_maximin | 0.955277 | 0.933542 | +0.021735 [-0.013080, +0.056942] | 84/21/86 | 0.938895 |
| anchorboost_all | model_disagreement | 0.822367 | 0.774586 | +0.047782 [+0.025591, +0.073387] | 26/115/50 | 0.00790518 |
| anchorboost_all | uniform_random | 0.822367 | 0.871713 | -0.049346 [-0.075776, -0.022253] | 135/0/56 | 1.03516e-08 |
| anchorboost_all | fixed_maximin | 0.822367 | 0.838654 | -0.016286 [-0.043203, +0.011254] | 108/21/62 | 0.000519907 |
| anchorboost_five | model_disagreement | 0.825445 | 0.779866 | +0.045579 [+0.026236, +0.067843] | 25/115/51 | 0.00383624 |
| anchorboost_five | uniform_random | 0.825445 | 0.874932 | -0.049486 [-0.074507, -0.023943] | 137/0/54 | 1.65618e-09 |
| anchorboost_five | fixed_maximin | 0.825445 | 0.842046 | -0.016601 [-0.042718, +0.010275] | 104/21/66 | 0.00440297 |
| cnp | model_disagreement | 0.834609 | 0.787078 | +0.047531 [+0.021786, +0.078539] | 29/115/47 | 0.0504524 |
| cnp | uniform_random | 0.834609 | 0.902441 | -0.067831 [-0.098936, -0.037404] | 125/0/66 | 2.35554e-05 |
| cnp | fixed_maximin | 0.834609 | 0.869016 | -0.034406 [-0.066239, -0.001591] | 105/21/65 | 0.00267298 |

| Choices | Matches / designs | Overlap |
|---|---:|---:|
| highest_unobserved / model_disagreement | 430.000 / 564 | 76.24% |
| highest_unobserved / uniform_random | 132.721 / 564 | 23.53% |
| highest_unobserved / fixed_maximin | 252.000 / 564 | 44.68% |
| model_disagreement / uniform_random | 132.721 / 564 | 23.53% |
| model_disagreement / fixed_maximin | 263.000 / 564 | 46.63% |
| uniform_random / fixed_maximin | 132.721 / 564 | 23.53% |

## common_identity_clean / all

193 drugs, 965 designs.

| Predictor | Comparator | Highest MAE | Comparator MAE | Difference [95% CI] | Win/tie/loss | Sign p |
|---|---|---:|---:|---|---|---:|
| interpolation | model_disagreement | 0.936894 | 0.858613 | +0.078281 [+0.054525, +0.104207] | 38/56/99 | 1.87794e-07 |
| interpolation | uniform_random | 0.936894 | 0.957636 | -0.020742 [-0.047529, +0.007040] | 126/0/67 | 2.60435e-05 |
| interpolation | fixed_maximin | 0.936894 | 0.904011 | +0.032882 [+0.001365, +0.065248] | 89/0/104 | 0.313576 |
| anchorboost_all | model_disagreement | 0.807778 | 0.765536 | +0.042242 [+0.024617, +0.061329] | 61/56/76 | 0.231537 |
| anchorboost_all | uniform_random | 0.807778 | 0.841156 | -0.033379 [-0.054253, -0.012006] | 134/0/59 | 6.92095e-08 |
| anchorboost_all | fixed_maximin | 0.807778 | 0.817798 | -0.010020 [-0.033429, +0.013857] | 117/0/76 | 0.00387126 |
| anchorboost_five | model_disagreement | 0.809539 | 0.770248 | +0.039292 [+0.022916, +0.057059] | 61/56/76 | 0.231537 |
| anchorboost_five | uniform_random | 0.809539 | 0.844788 | -0.035249 [-0.055297, -0.014302] | 134/0/59 | 6.92095e-08 |
| anchorboost_five | fixed_maximin | 0.809539 | 0.821015 | -0.011475 [-0.034262, +0.011829] | 120/0/73 | 0.000881982 |
| cnp | model_disagreement | 0.818474 | 0.776620 | +0.041854 [+0.019728, +0.069385] | 69/56/68 | 1 |
| cnp | uniform_random | 0.818474 | 0.863891 | -0.045416 [-0.067986, -0.021879] | 135/0/58 | 2.97179e-08 |
| cnp | fixed_maximin | 0.818474 | 0.837427 | -0.018952 [-0.045238, +0.010040] | 118/0/75 | 0.00241307 |

| Choices | Matches / designs | Overlap |
|---|---:|---:|
| highest_unobserved / model_disagreement | 630.000 / 965 | 65.28% |
| highest_unobserved / uniform_random | 229.770 / 965 | 23.81% |
| highest_unobserved / fixed_maximin | 251.000 / 965 | 26.01% |
| model_disagreement / uniform_random | 229.770 / 965 | 23.81% |
| model_disagreement / fixed_maximin | 352.000 / 965 | 36.48% |
| uniform_random / fixed_maximin | 229.770 / 965 | 23.81% |

## common_identity_clean / top_dose_initially_measured=True

181 drugs, 406 designs.

| Predictor | Comparator | Highest MAE | Comparator MAE | Difference [95% CI] | Win/tie/loss | Sign p |
|---|---|---:|---:|---|---|---:|
| interpolation | model_disagreement | 0.914912 | 0.820597 | +0.094315 [+0.059070, +0.136979] | 32/67/82 | 3.13852e-06 |
| interpolation | uniform_random | 0.914912 | 0.888401 | +0.026511 [-0.005124, +0.061537] | 83/0/98 | 0.298039 |
| interpolation | fixed_maximin | 0.914912 | 0.853938 | +0.060974 [+0.017744, +0.108036] | 79/0/102 | 0.101733 |
| anchorboost_all | model_disagreement | 0.777564 | 0.739061 | +0.038502 [+0.019546, +0.059033] | 52/67/62 | 0.399373 |
| anchorboost_all | uniform_random | 0.777564 | 0.785203 | -0.007640 [-0.028944, +0.013992] | 97/0/84 | 0.372465 |
| anchorboost_all | fixed_maximin | 0.777564 | 0.779087 | -0.001523 [-0.033421, +0.029782] | 95/0/86 | 0.552207 |
| anchorboost_five | model_disagreement | 0.778512 | 0.745518 | +0.032995 [+0.015230, +0.052648] | 52/67/62 | 0.399373 |
| anchorboost_five | uniform_random | 0.778512 | 0.789342 | -0.010829 [-0.032013, +0.010013] | 99/0/82 | 0.234245 |
| anchorboost_five | fixed_maximin | 0.778512 | 0.785438 | -0.006925 [-0.038719, +0.024028] | 100/0/81 | 0.180762 |
| cnp | model_disagreement | 0.784556 | 0.747955 | +0.036601 [+0.011751, +0.069130] | 62/67/52 | 0.399373 |
| cnp | uniform_random | 0.784556 | 0.805246 | -0.020689 [-0.043538, +0.004645] | 111/0/70 | 0.00284416 |
| cnp | fixed_maximin | 0.784556 | 0.795829 | -0.011272 [-0.047439, +0.029920] | 108/0/73 | 0.0112915 |

| Choices | Matches / designs | Overlap |
|---|---:|---:|
| highest_unobserved / model_disagreement | 205.000 / 406 | 50.49% |
| highest_unobserved / uniform_random | 98.299 / 406 | 24.21% |
| highest_unobserved / fixed_maximin | 0.000 / 406 | 0.00% |
| model_disagreement / uniform_random | 98.299 / 406 | 24.21% |
| model_disagreement / fixed_maximin | 90.000 / 406 | 22.17% |
| uniform_random / fixed_maximin | 98.299 / 406 | 24.21% |

## common_identity_clean / top_dose_initially_measured=False

190 drugs, 559 designs.

| Predictor | Comparator | Highest MAE | Comparator MAE | Difference [95% CI] | Win/tie/loss | Sign p |
|---|---|---:|---:|---|---|---:|
| interpolation | model_disagreement | 0.956650 | 0.880199 | +0.076451 [+0.049716, +0.106219] | 18/114/58 | 4.71324e-06 |
| interpolation | uniform_random | 0.956650 | 1.000143 | -0.043493 [-0.074052, -0.011668] | 138/0/52 | 3.50156e-10 |
| interpolation | fixed_maximin | 0.956650 | 0.935111 | +0.021539 [-0.013049, +0.056917] | 84/21/85 | 1 |
| anchorboost_all | model_disagreement | 0.823564 | 0.775531 | +0.048033 [+0.025690, +0.073603] | 26/114/50 | 0.00790518 |
| anchorboost_all | uniform_random | 0.823564 | 0.872831 | -0.049267 [-0.075893, -0.021493] | 134/0/56 | 1.4705e-08 |
| anchorboost_all | fixed_maximin | 0.823564 | 0.839807 | -0.016243 [-0.042906, +0.011757] | 107/21/62 | 0.000667714 |
| anchorboost_five | model_disagreement | 0.826615 | 0.780796 | +0.045819 [+0.026170, +0.067988] | 25/114/51 | 0.00383624 |
| anchorboost_five | uniform_random | 0.826615 | 0.876143 | -0.049528 [-0.074080, -0.023897] | 136/0/54 | 2.38648e-09 |
| anchorboost_five | fixed_maximin | 0.826615 | 0.843394 | -0.016779 [-0.043041, +0.010111] | 104/21/65 | 0.00334463 |
| cnp | model_disagreement | 0.835595 | 0.787814 | +0.047781 [+0.021923, +0.078895] | 29/114/47 | 0.0504524 |
| cnp | uniform_random | 0.835595 | 0.901782 | -0.066187 [-0.097189, -0.035411] | 124/0/66 | 3.10794e-05 |
| cnp | fixed_maximin | 0.835595 | 0.868735 | -0.033140 [-0.065110, -0.000725] | 104/21/65 | 0.00334463 |

| Choices | Matches / designs | Overlap |
|---|---:|---:|
| highest_unobserved / model_disagreement | 425.000 / 559 | 76.03% |
| highest_unobserved / uniform_random | 131.471 / 559 | 23.52% |
| highest_unobserved / fixed_maximin | 251.000 / 559 | 44.90% |
| model_disagreement / uniform_random | 131.471 / 559 | 23.52% |
| model_disagreement / fixed_maximin | 262.000 / 559 | 46.87% |
| uniform_random / fixed_maximin | 131.471 / 559 | 23.52% |

## Data and computation

All policies add one concentration, including its recorded replicate wells, to initial K3. 
The common target is all valid cells outside initial K3; the acquired cells have zero error. 
Random is the exact uniform expectation over complete candidate branches. Measurements are 
retrospective scenario counts; overlapping designs reuse recorded wells. Real wet-lab savings 
remain a separate prospective question. Per-policy well budgets are in measurement_budgets.csv.

drug_differences.csv preserves each signed paired effect. contrasts.csv also decomposes the 
difference into measurement-only replacement and context reconditioning. Their sum equals 
the total difference. This diagnostic describes forecast errors on this source.

highest_point_predictions.npz copies the original saved highest branches, including true 
responses, masks, forecasts and raw model outputs. choices.jsonl explicitly marks post hoc 
selection; it makes no pre-reveal commitment claim for this newly added rule.

Candidate-count distribution: {4: 850, 9: 20, 5: 40, 8: 30, 6: 20, 7: 5, 10: 5}.
Extra training: 0; extra measurements: 0; elapsed 2.934s; peak RSS 286851072 bytes.

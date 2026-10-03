# Ewart perfused Liver-Chip transfer experiment

Frozen before fitting on 2026-10-03T06:04:49Z. Series1 task2 authorizes a new preparation and split rule. This is a six-drug transfer experiment; the unchanged-protocol fourth-benchmark availability result remains a separate result.

## Question and reporting decision

Measure whether the frozen AnchorBoost algorithm improves sparse-concentration prediction on these perfused liver-chip response curves. Report both preparations and all three endpoints whatever their signs. An endpoint has evidence of lower error when its primary paired bootstrap upper bound is below zero. Forecast before fitting: effects may vary by endpoint, with 0–4 wins of six and intervals crossing zero; this forecast changes no execution or reporting rule.

## Fixed inputs and model

- Input: `ewart_readings.csv`, SHA-256 `326c494f0ebdae41bd7ea5b425d3697d5e48b5685ac033bb719ff1e7713f3b8c`; six compounds, three endpoints, 210 source positions, 204 numeric observations, six blank observations. Source: Ewart et al., https://www.nature.com/articles/s43856-022-00209-1, Supplementary Data 8, CC BY 4.0.
- Frozen source: https://github.com/logxio/ooc-evaluation-audit/blob/dbddd7437b9f1643ef2872bd5de86de0779b209b/chip_forecast.py, SHA-256 `3d02dd3a1bc57e8c53f701a6005c8d5e9d8ad6a15a57cdec3f22b27066015897`. Import its functions and classes; keep its bytes unchanged. Use `AnchorBoost(train, 3)` with the original features, 600 iterations, absolute-error loss and all other `MODEL` parameters unchanged. The algorithm is frozen; each fold fits weights using its five training drugs.
- Fit one single-output model per endpoint and held-out drug. Set the imported module's output dimensions to ND=NF=D=1, as a data-shape adapter. No endpoint pairing or shared chip identity is inferred. Concentration coordinates are log10 of the positive values as published, stored as float32; original GRID, AC50 and HILL grids stay unchanged.

## Preparations, fixed before outcomes

1. **Primary `author_units`:** use published values as supplied, with no scaling, clipping or inferred vehicle correction. Albumin retains author-normalized units; ALT and morphology retain their published units.
2. **Sensitivity `lowest_centered`:** subtract the mean of available readings at the lowest observed positive concentration of each drug and endpoint. Keep the same units; use subtraction rather than division, so zero-valued ALT references remain defined. The reference concentration is always one of the three test context concentrations. No held-out concentration contributes to this reference. Restore the reference for exported predictions in published units.

The source CSV preserves blank cells. Computational arrays use the original model's explicit mask; no missing value becomes an observed zero. A dose with no observed response for this endpoint is excluded from that endpoint's task, including the highest Troglitazone ALT and morphology dose. Other available replicates are retained. Means use only observed replicates; concentration means, not individual readings, are evaluation targets. All 204 numeric observations participate in their endpoint's available curve.

## Designs and splits

- Six leave-one-drug-out folds, ordered alphabetically by compound name, separately for ALBUMIN, ALT and Morphology. Every training fold contains five compounds. Exclude every row of the held-out drug from model fitting, analog profiles and learned summaries.
- Training uses unchanged `all_designs`: all C(L,3) context sets for each training drug.
- Evaluation uses five distinct three-concentration contexts for each drug and endpoint. Each contains the lowest available dose plus two other doses. Enumerate those pairs in ascending concentration order; select five via a permutation from numpy default_rng seeded by the first eight hex digits of SHA-256(`ewart-transfer-v1|` + endpoint + `|` + compound). Use the same contexts in both preparations and both methods.
- Every test context predicts all remaining observed dose levels, two or three per design. Endpoint-local missingness determines L. There is no tuning, drug exclusion based on performance or selection of a preferred design after evaluation.

## Comparators and statistics

- Baseline: unchanged `predict_interp` from the same frozen source, linear between means in log concentration and flat outside the selected range.
- For each design, calculate mean absolute error against remaining concentration means using unchanged `errors`. Average the five design errors within each drug. Endpoint MAE is the equal-weight mean across six drugs.
- For each endpoint and preparation, compare matched drug MAEs using unchanged `paired`: 4,000 chemical bootstrap resamples with replacement, seed 0, percentile 95% interval, difference = AnchorBoost minus interpolation. Lower error percent = minus the returned relative change. Positive lower-error percent means improvement; negative means higher error.
- Report all six fold MAEs, paired differences and win/loss/tie counts (strict numerical comparison), and endpoint summaries. The resampling denominator is six drugs, not 68 endpoint readings or 30 designs. The interval is descriptive for these six curves. No cross-endpoint raw-unit pooled MAE is reported because units differ; no multiplicity-adjusted claim is made.

## Execution

Run one primary ALBUMIN fold as the minimal resource probe after this file is saved. Reuse its declared parameters in the complete finite run of 36 fits (2 preparations × 3 endpoints × 6 folds); the probe is separate from the result. Cap each process at 4 GB and 5 minutes through `comp job`; single-thread numerical libraries keep this small workload bounded. The full run writes `result.json.ewart_transfer`, per-fold CSV and per-concentration predictions. Preserve the earlier availability audit fields. Reproduction checks the source/model/protocol hashes and both preparations; timing belongs in a separate resource file.

# Chip Forecast Workbench

Open `index.html`. Measure three of seven concentrations of a neural MEA screen and the page shows the whole concentration-response series: the forecast at the four unmeasured concentrations with 90% intervals, the hit call against the cutoff, and whether to report the call or measure the full series. The same page calls organoid patients sensitive, resistant or retest. The browser computes each result locally from the files in this folder and keeps pasted tables on the machine.

Live: https://logxio.github.io/ooc-evaluation-audit/workbench/

## Frozen four-axis evidence, 25 October 2026

All four axes are FROZEN. Corpus totals, clinical patients and selectable demonstration cohorts retain their own denominators.

| Axis | Frozen result |
| :--- | :--- |
| A: sparse acquisition | EPA neural screen: **56.8% fewer exposure wells**, 12,119 / 28,080 wells, 925 calls and 69 wrong. AnchorBoost Stack: **97W 1T 0L** versus 32 published models at k=1 to 4, across 98 paired comparisons; k=3 wins 32/32, MAE 1.1170 versus CNP 1.1920. JCI: **240 human 3D PDO curves**, 10 concentrations, 7,200 wells, prelocked single-reveal two-wave acquisition. MODEL uses 3,096 wells: **57.00% saving [54.00%, 60.00%]**, 1/240 missed, mean 1.32 waves. Measured-only uses 3,300 wells (54.17% saving); MODEL saves **204 additional wells**, +2.83 percentage points [2.00, 3.67]. Across 273 ToxCast physical two-wave drift pairs (91 sample plate pairs, 88 compounds, 924 scenarios), saving remains 57.00% and missed count 1/240. Bircsak perfused human liver: 46/46 hidden responses inside frozen envelopes, all curves settled with 25 points, 0 early errors. Harrill human neural screen: 2,318/2,520 hidden wells (92.0%) inside locked 90% intervals, 35.6% next-action well saving. |
| B: human 3D corpus | At least 5 positive concentrations: **34 strict direct-patient PDO studies, 13,444 curves**, 202,498 measurement points, 181 resolved deduplicated donor groups. At least 6: 29 studies, 12,908 curves, 197,293 points. All qualified human 3D models, including PDO and chips: **40 studies, 13,585 curves**, 206,113 points at the 5-concentration threshold. Full master table: 13,780 curves, 208,824 observations. |
| C: clinical matching and design | **248 matched cancer patients across 8 eligible study clusters**, 243 with numerical sensitivity. Within-study weighted AUC **0.9502 [0.6849, 0.9775]**. Complete-exposure sensitivity: 185 patients, 5 clusters, AUC 0.9615 [0.7453, 0.9844]. LOSO calibration slopes span **0.27 to 30.42**. Same-budget design leverage (10,000 paired Monte Carlo draws in the nonsaturated study cohort): reallocating from 30 wells per donor to 9 wells per donor across more donors increases clinical responder AUC by **+0.0286, +0.0577 and +0.0994** at 96, 192 and 384 wells. |
| D: stratified literature survey | **17,386 PubMed records**, 2019 to 2026, 85 strata; **399 randomly sampled papers** audited by Q and R, with **12,144 original quotation and image-hash evidence checks**. Evidence aligned coding across 12 fields has Krippendorff alpha **0.8054 to 1.0000**. Weighted prevalence across channels: **94.84% to 96.29%** lack clinical outcome linkage; **53.66% to 65.36%** have at most 3 independent human donors; **5.28% to 15.10%** publish raw multidose tables. |

The [audit index](audits/index.html) pairs these totals with the original 13 searchable examples that load directly into the worksheet. Frozen source readouts: [A](audits/axis_a_v3_s56/public_readout.md), [B](audits/corpus/public_s18/readout_s18.md), [C](audits/clinical_match_s54/protocol_s55/readout_s56.md) and [D](audits/survey400_s54/public_s58/readout_s58_full400.md).

## What is on the page

- **Chemicals.** 194 chemicals of the EPA network formation assay, each held out from training, with five three-concentration designs each (970 designs). Pages: *Curve* (measured wells, forecast, 90% interval, log-linear interpolation, and a call track of the largest DIV-mean response against the cutoff of 3; a 17 feature × 4 recording-day error matrix picks the output), *Plate* (the chemical's 48-well plates with run and unrun wells, the 35 possible three-of-seven layouts and how often each settled the call, and the retrospective wells-against-wrong-calls curve with a retest-cost slider), *Evidence* (the 970-design replay against three measured concentrations alone; per-chemical error against log-linear interpolation, analog chemicals, Hill fits and the published neural process; every held-out fold of three neural screens against interpolation and against the published neural process given the same contexts; five perfused liver-chip endpoints from Ewart 2022 and Yuan 2025; interval coverage by day and feature) and *Model* (what was trained, the matched-budget ablation, and a call-by-call replay of the contract agent rebuilding a published clinical headline from a paper's own table and figure).
- **Download actions** under the chemical list saves the listed chemicals at the open design, one row each: `chemical,design,measured_uM,action,hit_call,epa_label,reason`, with `design` numbered 1 to 5 as on the page. Type several names separated by `;` or by a comma and a space, or paste a column from a spreadsheet; the list and the file keep your order.
- **Patients.** 43 held-out rectal-organoid patients called from one combined-regimen readout at a frozen training cutoff. *Reveal outcomes* opens the clinical response; a wrong call turns red on the map and on the plate.
- **Your data.** Paste or open a table:
  * seven concentrations with the three you will measure marked `*`: the page returns how often that layout settled the call among the held-out designs and how many wells it saves;
  * `patient,readout1,readout2[,baseline_readout,response]`: the frozen two-readout release rule in `result.json` reports agreeing calls and sends the rest to retest (try `examples/T1_input.csv`);
  * `patient,combined[,irradiation,response]`: the frozen combined-regimen cutoff.
  Outcomes can arrive later through *Add outcomes* (`patient,response`); *Download actions* saves one row per patient. A different assay goes through `worksheet.html`.

`sample.html` (validation sample size) and `audits/index.html` (published studies) are linked from the header.

## Files

- `index.html` with `assets/` (design system, charts, claims) and `vendor/` (D3 7.9.0 under ISC; Newsreader, Source Sans 3 and Source Code Pro as woff2 under the SIL Open Font License, licence texts alongside).
- `data/ooc-data.js`: every number the page draws, built from the repository's results by `build_data.py`. The builder re-runs the repository's own code and stops unless the decision chain reproduces `chip_forecast_decision.json`, the action list matches `chip_forecast_actions.csv`, per-chemical comparisons match `chip_forecast_result.json`, the example forecasts match `chip_forecast_examples.json`, plain interval coverage matches `chip_forecast_intervals.json` exactly and learned interval coverage lands within 0.002 of it:

  ```sh
  for f in 1 2 3 4; do python workbench/build_data.py widths --fold $f; done
  python workbench/build_data.py export
  ```

  `python workbench/build_data.py evidence` refreshes the comparison figures from `benchmarks/strong_baseline` in about a second without refitting: it re-aggregates the saved errors at their chemical denominators and stops unless every mean, interval and win count matches the released results.

- `engine.js`, `stats.js`, `chain-engine.js`, `result.json` / `result.js`: the frozen two-readout release rule used for pasted tables; `verify.py` checks the browser engine against `chip_release.py` and `matched_regimen.py`.

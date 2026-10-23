# Chip Forecast Workbench

Open `index.html`. Measure three of seven concentrations of a neural MEA screen and the page shows the whole concentration-response series: the forecast at the four unmeasured concentrations with 90% intervals, the hit call against the cutoff, and whether to report the call or measure the full series. The same page calls organoid patients sensitive, resistant or retest. Everything is computed in the browser from files in this folder; pasted tables never leave the machine, and the page makes no network request.

Live: https://logxio.github.io/ooc-evaluation-audit/workbench/

## What is on the page

- **Chemicals.** 194 chemicals of the EPA network formation assay, each held out from training, with five three-concentration designs each (970 designs). Pages: *Curve* (measured wells, forecast, 90% interval, log-linear interpolation, and a call track of the largest DIV-mean response against the cutoff of 3; a 17 feature × 4 recording-day error matrix picks the output), *Plate* (the chemical's 48-well plates with run and unrun wells, the 35 possible three-of-seven layouts and how often each settled the call, and the retrospective wells-against-wrong-calls curve with a retest-cost slider), *Evidence* (the 970-design replay against three measured concentrations alone; per-chemical error against log-linear interpolation, analog chemicals, Hill fits and the published neural process; every held-out fold of three neural screens against interpolation and against the published neural process given the same contexts; five perfused liver-chip endpoints from Ewart 2022 and Yuan 2025; interval coverage by day and feature) and *Model* (what was trained, the matched-budget ablation, and a call-by-call replay of the contract agent rebuilding a published clinical headline from a paper's own table and figure).
- **Download actions** under the chemical list saves the listed chemicals at the open design, one row each: `chemical,design,measured_uM,action,hit_call,epa_label,reason`, with `design` numbered 1–5 as on the page. Type several names separated by `;` or by a comma and a space, or paste a column from a spreadsheet; the list and the file keep your order.
- **Patients.** 43 held-out rectal-organoid patients called from one combined-regimen readout at a frozen training cutoff. *Reveal outcomes* opens the clinical response; a wrong call turns red on the map and on the plate.
- **Your data.** Paste or open a table:
  - seven concentrations with the three you will measure marked `*`: the page returns how often that layout settled the call among the held-out designs and how many wells it saves;
  - `patient,readout1,readout2[,baseline_readout,response]`: the frozen two-readout release rule in `result.json` reports agreeing calls and sends the rest to retest (try `examples/T1_input.csv`);
  - `patient,combined[,irradiation,response]`: the frozen combined-regimen cutoff.
  Outcomes can arrive later through *Add outcomes* (`patient,response`); *Download actions* saves one row per patient. A different assay goes through `worksheet.html`.

`sample.html` (validation sample size) and `audits/index.html` (published studies) are linked from the header.

## Final report data

`data/ooc-final-1009.js` exports `window.OOC_FINAL_1009`: the 965-design
reporting and closed-loop results, all 32 comparable predictor configurations at
k=1–4, twelve Bircsak curves, the locked Harrill human-cell example, and patient
cohort views. The `screening`, `baselines`, `bircsak`, `harrill` and `patients`
properties keep their source-specific units and denominators. `sources` records
relative paths and SHA-256 hashes. `report` identifies the exact report bytes;
the current report's date field reads 10 October 2026.

From the repository root, using Python 3 with its standard library:

```sh
python build_final_1009_webdata.py
python build_final_1009_webdata.py --check
node -c workbench/data/ooc-final-1009.js
```

The builder checks report Tables 4, 6 and 7 against saved results, including the
paired intervals and outcomes. Unrun predictor cells contain `mae: null`,
`status: "not_run"` and an explicit missing-value label. The report-matched
Harrill run is preserved in `results/final/harrill_1009/`, with its original
lock and forecasts, from the commit recorded in `snapshot.json`. Its
2,244/3,483-well account belongs to that lock; the current `three_point_example/`
directory holds a later run.

`assets/mount-final-1009.js` attaches the packet as `OOC.final1009` and the
cohort array as `OOC.patientCohorts`. The existing page loads both scripts and
keeps its original default view. Select a saved cohort through the browser API:

```js
OOCFinal1009.selectCohort('rectal-fixed-43');
OOCFinal1009.selectCohort('rectal-blind-85');
OOCFinal1009.selectCohort('crlm-blind-23');
OOCFinal1009.selectCohort('tiriac-primary-7');
```

Each cohort retains the existing `patients.rows`, `cases`, `rule` and `study`
shape. The selector reads saved actions, resets outcome reveal and updates the
existing patient map, plate and export. The two-readout map uses ratios to each
regimen's frozen cutoffs; tooltips and patient details retain the raw values.
Source artifacts that preserve calls without raw readouts have `null` readouts
and remain inspectable in the patient plate and exports.

For a control supplied by an embedding page, set
`data-ooc-cohort="rectal-blind-85"` on a button or `data-ooc-cohort-select` on
a select, then call `OOCFinal1009.bind()`. Binding reuses those controls; the
mount script creates no default interface elements or styles.

The inventory contains 323 cohort-view rows and 258 distinct source patients
including the assay pool; 175 distinct patients have clinical scores. The
43-patient fixed view overlaps the 85-patient blind view. Tan contributes 22
scored treatments in 18 patients and a separate 101-patient assay pool; that
pool supplies reference medians. Rectal and liver-metastasis formula checks
use a frozen formula with single-readout accuracies observed after outcome
access, as described in report Appendix C.1.

## Files

- `index.html` with `assets/` (design system, charts, claims) and `vendor/` (D3 7.9.0 under ISC; Newsreader, Source Sans 3 and Source Code Pro as woff2 under the SIL Open Font License, licence texts alongside).
- `data/ooc-data.js`: every number the page draws, built from the repository's results by `build_data.py`. The builder re-runs the repository's own code and stops unless the decision chain reproduces `chip_forecast_decision.json`, the action list matches `chip_forecast_actions.csv`, per-chemical comparisons match `chip_forecast_result.json`, the example forecasts match `chip_forecast_examples.json`, plain interval coverage matches `chip_forecast_intervals.json` exactly and learned interval coverage lands within 0.002 of it:

  ```sh
  for f in 1 2 3 4; do python workbench/build_data.py widths --fold $f; done
  python workbench/build_data.py export
  ```

  `python workbench/build_data.py evidence` refreshes the comparison figures from `benchmarks/strong_baseline` in about a second without refitting: it re-aggregates the saved errors at their chemical denominators and stops unless every mean, interval and win count matches the released results.

- `engine.js`, `stats.js`, `chain-engine.js`, `result.json` / `result.js`: the frozen two-readout release rule used for pasted tables; `verify.py` checks the browser engine against `chip_release.py` and `matched_regimen.py`.

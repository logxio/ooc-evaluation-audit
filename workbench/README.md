# Chip Forecast Workbench

Open `index.html`. Measure three of seven concentrations of a neural MEA screen and the page shows the whole concentration-response series: the forecast at the four unmeasured concentrations with 90% intervals, the hit call against the cutoff, and whether to report the call or measure the full series. The same page calls organoid patients sensitive, resistant or retest. Everything is computed in the browser from files in this folder; pasted tables never leave the machine, and the page makes no network request.

Live: https://logxio.github.io/ooc-evaluation-audit/workbench/

## What is on the page

- **Chemicals.** 194 chemicals of the EPA network formation assay, each held out from training, with five three-concentration designs each (970 designs). Pages: *Curve* (measured wells, forecast, 90% interval, log-linear interpolation, and a call track of the largest DIV-mean response against the cutoff of 3; a 17 feature × 4 recording-day error matrix picks the output), *Plate* (the chemical's 48-well plates with run and unrun wells, the 35 possible three-of-seven layouts and how often each settled the call, and the wells-against-wrong-calls frontier with a retest-cost slider), *Evidence* (per-chemical error against log-linear interpolation, analog chemicals, Hill fits and the published neural process; every held-out fold of three screens; interval coverage by day and feature; ablations) and *Model* (what was trained, and a call-by-call replay of the contract agent rebuilding a published clinical headline from a paper's own table and figure).
- **Patients.** 43 held-out rectal-organoid patients called from one combined-regimen readout at a frozen training cutoff. *Reveal outcomes* opens the clinical response; a wrong call turns red on the map and on the plate.
- **Your data.** Paste or open a table:
  - seven concentrations with the three you will measure marked `*`: the page returns how often that layout settled the call among the held-out designs and how many wells it saves;
  - `patient,readout1,readout2[,baseline_readout,response]`: the frozen two-readout release rule in `result.json` reports agreeing calls and sends the rest to retest (try `examples/T1_input.csv`);
  - `patient,combined[,irradiation,response]`: the frozen combined-regimen cutoff.
  Outcomes can arrive later through *Add outcomes* (`patient,response`); *Download actions* saves one row per patient. A different assay goes through `worksheet.html`.

`sample.html` (validation sample size) and `audits/index.html` (published studies) are linked from the header.

## Files

- `index.html` with `assets/` (design system, charts, claims) and `vendor/` (D3 7.9.0 under ISC; Newsreader, Source Sans 3 and Source Code Pro as woff2 under the SIL Open Font License, licence texts alongside).
- `data/ooc-data.js`: every number the page draws, built from the repository's results by `build_data.py`. The builder re-runs the repository's own code and stops unless the decision chain reproduces `chip_forecast_decision.json`, the action list matches `chip_forecast_actions.csv`, per-chemical comparisons match `chip_forecast_result.json`, the example forecasts match `chip_forecast_examples.json`, plain interval coverage matches `chip_forecast_intervals.json` exactly and learned interval coverage lands within 0.002 of it:

  ```sh
  for f in 1 2 3 4; do python workbench/build_data.py widths --fold $f; done
  python workbench/build_data.py export
  ```

- `engine.js`, `stats.js`, `chain-engine.js`, `result.json` / `result.js`: the frozen two-readout release rule used for pasted tables; `verify.py` checks the browser engine against `chip_release.py` and `matched_regimen.py`.

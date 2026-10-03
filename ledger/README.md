# Recompute the well and error counts

From the repository root, install NumPy into your Python environment and run:

```sh
python -m pip install -r ledger/requirements.txt
python ledger/run.py
```

The command rebuilds [wells.csv](wells.csv) (970 designs), [risk.csv](risk.csv) (970 decisions), and [lineage.csv](lineage.csv) (43 patients), then checks every row against the saved results. It uses the committed forecasts in `chip_forecast_runs/`, downloads two public files with pinned SHA-256 hashes into `ledger/.cache/` on its first run, and works offline with that cache afterward. It trains zero models and requires NumPy plus the Python standard library. Outputs stay in this directory. Python 3.13.14 and NumPy 2.5.3 were used for the publication replay.

| Quantity | Numerator | Denominator | Result |
|---|---:|---:|---:|
| Exposed-well equivalents saved | 28,185 − 12,240 = 15,945 | 28,185 full-series wells | 56.5726% |
| Forecast wrong releases, all designs | 79 | 970 | 8.1443% |
| Forecast wrong releases, released designs | 79 | 905 | 8.7293% |
| Measured-only wrong releases, all designs | 79 | 970 | 8.1443% |
| Measured-only wrong releases, released designs | 79 | 711 | 11.1111% |
| Forecast / measured-only errors at forced full coverage | 102 / 145 | 970 each | 10.5155% / 14.9485% |

These are retrospective static rat cortical MEA screens: five alternative designs for each of 194 held-out chemicals, sharing 5,637 retained physical-well trajectories. Each design measures three concentrations with their actual replicate counts. Its fallback reuses those wells and adds the remaining exposed wells: 11,395 first-round + 845 additional = 12,240 strategy wells. Controls, quality-control wells, reruns and prospective validation overhead are excluded from both cost totals. Designs are alternatives, not 970 independently executed experiments. `wells.csv` records all accounting rules and weights; `well_records.csv` and `observation_map.csv.gz` link retained wells to the 964,187 design × well × day × feature targets.

At a uniform seven concentrations × three replicates, with nine initial wells reused on fallback, the same decisions save 53.3137%. The sequential decomposition in [well_cost_decomposition.csv](well_cost_decomposition.csv) adds concentration count (+2.25743 percentage points), mean-replicate weighting (+1.04736), then within-chemical replicate imbalance (−0.04584), totaling +3.25895 points. Individual increments depend on this stated order.

The 10% calibration budget divides smoothed wrong releases by **all calibration designs**. The held-out conditional error is 79/905, separate from that budget; its chemical-bootstrap 95% interval is 6.1450–11.4630%. [calibration.csv](calibration.csv) gives fold-specific counts. The five designs share a chemical, and other-fold forecasts used for calibration can have trained on the current test fold. These are replay estimates, with prospective independent validation remaining a separate experiment.

The 43-patient lineage compares two different policies on the same inputs: the built-in two-readout agreement rule releases 27 with four errors; the measured combined-regimen rule releases 43 with one error. The command independently recomputes the cutoffs, margins and actions and checks committed browser exports. [browser/receipt.json](browser/receipt.json) records the original real-browser run. To refresh that run with an installed Chrome: `npm install --prefix ledger`, then `node ledger/browser_replay.mjs` (set `CHROME_PATH` for a custom executable), then `python ledger/lineage.py`. All browser HTTP requests are blocked during replay.

[fold_results.csv](fold_results.csv) and [environments.csv](environments.csv) reproduce archived Linux folds 1–4 and macOS folds 1–2 from committed references. Historical macOS dependency versions and folds 3–4 are absent from the archive; the current replay rebuilds statistics from saved runs. [headline_numbers.csv](headline_numbers.csv) maps each displayed number to its numerator, denominator, platform and stage.

Source: US EPA network-formation data (US Government work), packaged with published comparator results by [NeuroChip Twin](https://github.com/Agnuxo1/neurochip-twin/tree/f9848800dfab66a8bc005e6b3087153eeaabe9ac) (MIT). Patient source attribution and licenses are in the repository [technical report](../technical_report.md). Repository code is MIT licensed.

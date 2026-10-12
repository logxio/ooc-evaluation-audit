# Replay of three-concentration designs from epa_dnt_human_neural.csv

Each completed series was replayed from five three-concentration designs. Compounds were dealt into five folds; for each test fold, two folds trained the model and two calibrated the release margin, so no test compound informed its own forecast or call. Calls are compared with the call from the full series.

| Endpoint | Compounds | Designs | Calls from three | After one more | Wrong calls | Wells used | Saved against the full series | Measured concentrations only: calls, wrong | Saved against measured-only |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| hN2_NOG_NeuriteLength | 68 | 340 | 219 | 64 | 18 | 4,626 of 11,110 | 58.4% | 250, 32 | 10.4% |
| hNP1_CellTiter_Lum | 41 | 205 | 58 | 41 | 2 | 4,512 of 6,660 | 32.2% | 64, 7 | 13.5% |

| Endpoint | Forecast error, AnchorBoost | Interpolation | Difference, paired 95% interval | Hidden wells inside the 90% interval |
|:--|--:|--:|--:|--:|
| hN2_NOG_NeuriteLength | 0.758 | 0.757 | +0.001 [-0.062, +0.072] | 91.5% of 8,012 |
| hNP1_CellTiter_Lum | 0.988 | 1.138 | -0.150 [-0.298, -0.010] | 90.8% of 4,815 |

Forecast error is the mean absolute difference from the measured concentration means, in baseline SDs (the spread of responses at the two lowest concentrations of training and calibration compounds, after centring each plate on its vehicle wells when the table has them), per compound over its designs. A call is active when the largest absolute concentration mean reaches 3 baseline SDs; the release margin keeps the expected share of wrong early calls per compound at or below 10% on the calibration compounds. Activity is called only from measured concentrations at that line; the forecast reports inactive calls or names the concentration to add. "Measured concentrations only" is the calibrated three-concentration rule reading the measured concentrations without a forecast, with the same direct report of measured activity. Wells count exposed wells; vehicle wells are shared and not counted.

**Inputs and code (SHA-256)**

- input epa_dnt_human_neural.csv: `42c148324c762ec486ee34306ea44e72377d87b817c4ca97c3005e4fa1ff6e47`
- replay.csv: `ca21d5d793c4f0b34d452898b4ef3b2191f4457f0c2c9ce69b9d360fdff87e29`
- protocol.json: `c95f19e2dc1977a79ba856f5ad883b3a3bc31864529355822376b5a7f82193c2`
- code three_point.py: `bb01fa2b20c2d432c01cffe7acc3fbe6dfd9b5c4eb17e7dad8fe43b68a795e25`
- code chip_forecast.py: `3d02dd3a1bc57e8c53f701a6005c8d5e9d8ad6a15a57cdec3f22b27066015897`
- code chip_forecast_intervals.py: `ad4825c2d0f1f6ccd5698cfe8b21e1d8fb31847f41338ef0ad1bf055fada05d4`
- code chip_forecast_selfcheck.py: `5c16d9cd82513c876ce3b98132338fb4b40bb9b7322c3b05e62ad1be96c23818`
- code paper_nested_decision.py: `22de67e35239a390a03e93d1df2c557671837944afc341e1eb2f5d46a9c094d7`

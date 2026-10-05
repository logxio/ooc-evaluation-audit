# Replay of three-concentration designs from epa_dnt_human_neural.csv

Each completed series was replayed from five three-concentration designs. Compounds were dealt into five folds; for each test fold, two folds trained the model and two calibrated the release margin, so no test compound informed its own forecast or call. Calls are compared with the call from the full series.

| Endpoint | Compounds | Designs | Calls from three | After one more | Wrong calls | Wells used | Saved against the full series | Measured concentrations only: calls, wrong | Saved against measured-only |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| hN2_NOG_NeuriteLength | 68 | 340 | 125 | 32 | 14 | 7,458 of 11,110 | 32.9% | 212, 32 | -24.4% |
| hNP1_CellTiter_Lum | 41 | 205 | 8 | 7 | 2 | 6,321 of 6,660 | 5.1% | 16, 7 | -0.7% |

| Endpoint | Forecast error, AnchorBoost | Interpolation | Difference, paired 95% interval | Hidden wells inside the 90% interval |
|:--|--:|--:|--:|--:|
| hN2_NOG_NeuriteLength | 0.758 | 0.757 | +0.001 [-0.062, +0.072] | 91.5% of 8,012 |
| hNP1_CellTiter_Lum | 0.988 | 1.138 | -0.150 [-0.298, -0.010] | 90.8% of 4,815 |

Forecast error is the mean absolute difference from the measured concentration means, in baseline SDs (the spread of responses at the two lowest concentrations of training and calibration compounds, after centring each plate on its vehicle wells when the table has them), per compound over its designs. A call is active when the largest absolute concentration mean reaches 3 baseline SDs; the release margin keeps the expected share of wrong early calls per compound at or below 10% on the calibration compounds. "Measured concentrations only" is the same calibrated rule reading the three measured concentrations without a forecast. Wells count exposed wells; vehicle wells are shared and not counted.

**Inputs and code (SHA-256)**

- input epa_dnt_human_neural.csv: `42c148324c762ec486ee34306ea44e72377d87b817c4ca97c3005e4fa1ff6e47`
- replay.csv: `4b93fb3daf942ca87799f55a51099f576f0154e68cd0df47ba3adc82e93f9e50`
- protocol.json: `97456d313dc1fceca2edf75c47a2885b24bab9fd8ea111bfa843ad4f39990187`
- code three_point.py: `91a327c5bdc8f8a083fe767086f0fdd9bf801d4cb074de78304f979c41fb1064`
- code chip_forecast.py: `3d02dd3a1bc57e8c53f701a6005c8d5e9d8ad6a15a57cdec3f22b27066015897`
- code chip_forecast_intervals.py: `ad4825c2d0f1f6ccd5698cfe8b21e1d8fb31847f41338ef0ad1bf055fada05d4`
- code chip_forecast_selfcheck.py: `5c16d9cd82513c876ce3b98132338fb4b40bb9b7322c3b05e62ad1be96c23818`
- code paper_nested_decision.py: `22de67e35239a390a03e93d1df2c557671837944afc341e1eb2f5d46a9c094d7`

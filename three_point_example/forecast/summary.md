# Next steps for epa_dnt_three_point.csv

107 series: 51 can be called now, 56 need one more concentration, 0 need the full series. Fixed at 2026-10-05T19:27:33+00:00 (UTC); send lock.json, or the SHA-256 the command prints, to the laboratory before the remaining concentrations are read. `forecast.csv` holds the forecast and the 90% interval for one well at every concentration still to measure; `--reconcile` checks them against the finished series concentration by concentration.

## Call now

| Compound | Endpoint | Call | Measured |
|:--|:--|:--|:--|
| Aminonicotinimide | hN2_NOG_NeuronCount | inactive | 0.001, 0.3, 100 uM |
| Amphetamine | hN2_NOG_NeuronCount | inactive | 0.001, 0.3, 100 uM |
| Amphetamine | hNP1_Pro_MeanAvgInten | inactive | 0.001, 0.3, 100 uM |
| Amphetamine | hNP1_Pro_ResponderAvgInten | inactive | 0.001, 0.3, 100 uM |
| Caffeine | hN2_NOG_BPCount | inactive | 0.001, 0.3, 100 uM |
| Caffeine | hN2_NOG_NeuriteLength | inactive | 0.001, 0.3, 100 uM |
| Caffeine | hNP1_Pro_MeanAvgInten | inactive | 0.001, 0.3, 100 uM |
| Caffeine | hNP1_Pro_ObjectCount | inactive | 0.001, 0.3, 100 uM |
| Caffeine | hNP1_Pro_ResponderAvgInten | inactive | 0.001, 0.3, 100 uM |
| Chlorpyrifos | hN2_NOG_NeuriteCount | active | 0.001, 0.3, 100 uM |
| Chlorpyrifos | hN2_NOG_NeuriteLength | active | 0.001, 0.3, 100 uM |
| Chlorpyrifos | hNP1_Pro_ObjectCount | active | 0.001, 0.3, 100 uM |
| Dexamethasone | hN2_NOG_BPCount | inactive | 0.001, 0.3, 100 uM |
| Dexamethasone | hN2_NOG_NeuriteCount | inactive | 0.001, 0.3, 100 uM |
| Dexamethasone | hN2_NOG_NeuriteLength | inactive | 0.001, 0.3, 100 uM |
| Dexamethasone | hN2_NOG_NeuronCount | inactive | 0.001, 0.3, 100 uM |
| Dexamethasone | hNP1_Caspase_Apop | inactive | 0.001, 0.3, 100 uM |
| Dexamethasone | hNP1_Pro_ObjectCount | inactive | 0.001, 0.3, 100 uM |
| Dicrotophos | hNP1_CellTiter_Lum | inactive | 0.001, 0.3, 100 uM |
| Dieldrin | hN2_NOG_NeuronCount | active | 0.001, 0.3, 100 uM |
| Dieldrin | hNP1_Pro_ObjectCount | inactive | 0.001, 0.3, 100 uM |
| Dimethoate | hNP1_CellTiter_Lum | inactive | 0.001, 0.3, 100 uM |
| Glyphosate | hN2_NOG_BPCount | inactive | 0.001, 0.1, 30 uM |
| Glyphosate | hN2_NOG_NeuriteCount | inactive | 0.001, 0.1, 30 uM |
| Glyphosate | hNP1_Caspase_Apop | inactive | 0.001, 0.1, 30 uM |
| Glyphosate | hNP1_Pro_ObjectCount | inactive | 0.001, 0.1, 30 uM |
| Glyphosate | hNP1_Pro_ResponderAvgInten | inactive | 0.001, 0.1, 30 uM |
| Isoniazid | hN2_NOG_NeuriteCount | inactive | 0.001, 0.3, 100 uM |
| Isoniazid | hN2_NOG_NeuronCount | inactive | 0.001, 0.3, 100 uM |
| Isoniazid | hNP1_Caspase_Apop | active | 0.001, 0.3, 100 uM |
| Isoniazid | hNP1_Pro_MeanAvgInten | inactive | 0.001, 0.3, 100 uM |
| Isoniazid | hNP1_Pro_ResponderAvgInten | inactive | 0.001, 0.3, 100 uM |
| Sorbitol | hN2_NOG_BPCount | inactive | 0.001, 0.3, 100 uM |
| Sorbitol | hN2_NOG_NeuriteCount | inactive | 0.001, 0.3, 100 uM |
| Sorbitol | hN2_NOG_NeuriteLength | inactive | 0.001, 0.3, 100 uM |
| Sorbitol | hNP1_Caspase_Apop | inactive | 0.001, 0.3, 100 uM |
| Sorbitol | hNP1_Pro_MeanAvgInten | inactive | 0.001, 0.3, 100 uM |
| Sorbitol | hNP1_Pro_ObjectCount | inactive | 0.001, 0.3, 100 uM |
| Thiouracil | hN2_NOG_BPCount | inactive | 0.001, 0.3, 100 uM |
| Thiouracil | hN2_NOG_NeuriteCount | inactive | 0.001, 0.3, 100 uM |
| Thiouracil | hN2_NOG_NeuronCount | inactive | 0.001, 0.3, 100 uM |
| Thiouracil | hNP1_Caspase_Apop | inactive | 0.001, 0.3, 100 uM |
| Thiouracil | hNP1_Pro_ObjectCount | inactive | 0.001, 0.3, 100 uM |
| Valproate | hN2_NOG_BPCount | inactive | 0.03, 10, 3000 uM |
| Valproate | hN2_NOG_NeuriteCount | inactive | 0.03, 10, 3000 uM |
| Valproate | hN2_NOG_NeuriteLength | inactive | 0.03, 10, 3000 uM |
| Valproate | hNP1_Caspase_Apop | active | 0.03, 10, 3000 uM |
| trans-Retinoic Acid | hN2_NOG_NeuriteCount | active | 0.001, 0.1, 30 uM |
| trans-Retinoic Acid | hN2_NOG_NeuriteLength | active | 0.001, 0.1, 30 uM |
| trans-Retinoic Acid | hNP1_Caspase_Apop | inactive | 0.001, 0.1, 30 uM |
| trans-Retinoic Acid | hNP1_Pro_ObjectCount | inactive | 0.001, 0.1, 30 uM |

## Add one concentration, then run again with its readings

| Compound | Endpoint | Add | Measured |
|:--|:--|:--|:--|
| Aminonicotinimide | hN2_NOG_BPCount | 10 uM | 0.001, 0.3, 100 uM |
| Aminonicotinimide | hN2_NOG_NeuriteCount | 30 uM | 0.001, 0.3, 100 uM |
| Aminonicotinimide | hN2_NOG_NeuriteLength | 30 uM | 0.001, 0.3, 100 uM |
| Aminonicotinimide | hNP1_Caspase_Apop | 30 uM | 0.001, 0.3, 100 uM |
| Aminonicotinimide | hNP1_CellTiter_Lum | 10 uM | 0.001, 0.3, 100 uM |
| Aminonicotinimide | hNP1_Pro_MeanAvgInten | 10 uM | 0.001, 0.3, 100 uM |
| Aminonicotinimide | hNP1_Pro_ObjectCount | 30 uM | 0.001, 0.3, 100 uM |
| Aminonicotinimide | hNP1_Pro_ResponderAvgInten | 10 uM | 0.001, 0.3, 100 uM |
| Amphetamine | hN2_NOG_BPCount | 1 uM | 0.001, 0.3, 100 uM |
| Amphetamine | hN2_NOG_NeuriteCount | 30 uM | 0.001, 0.3, 100 uM |
| Amphetamine | hN2_NOG_NeuriteLength | 30 uM | 0.001, 0.3, 100 uM |
| Amphetamine | hNP1_Caspase_Apop | 0.003 uM | 0.001, 0.3, 100 uM |
| Amphetamine | hNP1_CellTiter_Lum | 10 uM | 0.001, 0.3, 100 uM |
| Amphetamine | hNP1_Pro_ObjectCount | 10 uM | 0.001, 0.3, 100 uM |
| Caffeine | hN2_NOG_NeuriteCount | 30 uM | 0.001, 0.3, 100 uM |
| Caffeine | hN2_NOG_NeuronCount | 1 uM | 0.001, 0.3, 100 uM |
| Caffeine | hNP1_Caspase_Apop | 10 uM | 0.001, 0.3, 100 uM |
| Caffeine | hNP1_CellTiter_Lum | 10 uM | 0.001, 0.3, 100 uM |
| Chlorpyrifos | hN2_NOG_BPCount | 30 uM | 0.001, 0.3, 100 uM |
| Chlorpyrifos | hN2_NOG_NeuronCount | 30 uM | 0.001, 0.3, 100 uM |
| Chlorpyrifos | hNP1_Caspase_Apop | 30 uM | 0.001, 0.3, 100 uM |
| Chlorpyrifos | hNP1_Pro_MeanAvgInten | 3 uM | 0.001, 0.3, 100 uM |
| Chlorpyrifos | hNP1_Pro_ResponderAvgInten | 10 uM | 0.001, 0.3, 100 uM |
| Dexamethasone | hNP1_Pro_MeanAvgInten | 3 uM | 0.001, 0.3, 100 uM |
| Dexamethasone | hNP1_Pro_ResponderAvgInten | 1 uM | 0.001, 0.3, 100 uM |
| Diazinon | hNP1_Caspase_Apop | 30 uM | 0.001, 0.3, 100 uM |
| Diazinon | hNP1_CellTiter_Lum | 1 uM | 0.001, 0.3, 100 uM |
| Dicrotophos | hNP1_Caspase_Apop | 10 uM | 0.001, 0.3, 100 uM |
| Dieldrin | hN2_NOG_BPCount | 30 uM | 0.001, 0.3, 100 uM |
| Dieldrin | hN2_NOG_NeuriteCount | 30 uM | 0.001, 0.3, 100 uM |
| Dieldrin | hN2_NOG_NeuriteLength | 3 uM | 0.001, 0.3, 100 uM |
| Dieldrin | hNP1_Caspase_Apop | 30 uM | 0.001, 0.3, 100 uM |
| Dieldrin | hNP1_Pro_MeanAvgInten | 30 uM | 0.001, 0.3, 100 uM |
| Dieldrin | hNP1_Pro_ResponderAvgInten | 10 uM | 0.001, 0.3, 100 uM |
| Dimethoate | hNP1_Caspase_Apop | 0.1 uM | 0.001, 0.3, 100 uM |
| Glyphosate | hN2_NOG_NeuriteLength | 0.01 uM | 0.001, 0.1, 30 uM |
| Glyphosate | hN2_NOG_NeuronCount | 10 uM | 0.001, 0.1, 30 uM |
| Glyphosate | hNP1_Pro_MeanAvgInten | 0.003 uM | 0.001, 0.1, 30 uM |
| Isoniazid | hN2_NOG_BPCount | 0.003 uM | 0.001, 0.3, 100 uM |
| Isoniazid | hN2_NOG_NeuriteLength | 10 uM | 0.001, 0.3, 100 uM |
| Isoniazid | hNP1_CellTiter_Lum | 0.01 uM | 0.001, 0.3, 100 uM |
| Isoniazid | hNP1_Pro_ObjectCount | 10 uM | 0.001, 0.3, 100 uM |
| Sorbitol | hN2_NOG_NeuronCount | 0.1 uM | 0.001, 0.3, 100 uM |
| Sorbitol | hNP1_Pro_ResponderAvgInten | 1 uM | 0.001, 0.3, 100 uM |
| Thiouracil | hN2_NOG_NeuriteLength | 0.1 uM | 0.001, 0.3, 100 uM |
| Thiouracil | hNP1_Pro_MeanAvgInten | 30 uM | 0.001, 0.3, 100 uM |
| Thiouracil | hNP1_Pro_ResponderAvgInten | 0.03 uM | 0.001, 0.3, 100 uM |
| Valproate | hN2_NOG_NeuronCount | 100 uM | 0.03, 10, 3000 uM |
| Valproate | hNP1_CellTiter_Lum | 100 uM | 0.03, 10, 3000 uM |
| Valproate | hNP1_Pro_MeanAvgInten | 100 uM | 0.03, 10, 3000 uM |
| Valproate | hNP1_Pro_ObjectCount | 30 uM | 0.03, 10, 3000 uM |
| Valproate | hNP1_Pro_ResponderAvgInten | 30 uM | 0.03, 10, 3000 uM |
| trans-Retinoic Acid | hN2_NOG_BPCount | 3 uM | 0.001, 0.1, 30 uM |
| trans-Retinoic Acid | hN2_NOG_NeuronCount | 0.3 uM | 0.001, 0.1, 30 uM |
| trans-Retinoic Acid | hNP1_Pro_MeanAvgInten | 0.03 uM | 0.001, 0.1, 30 uM |
| trans-Retinoic Acid | hNP1_Pro_ResponderAvgInten | 3 uM | 0.001, 0.1, 30 uM |

**How the next step is chosen.** Values are in the table's own units. The model works in baseline SDs: the spread of responses at the two lowest concentrations of the completed compounds, after centring each plate on its vehicle wells when the table has them. A call is active when the largest absolute concentration mean of the full series reaches 3 baseline SDs. The call is reported when its rank margin clears the release margin, set on calibration compounds so that the expected share of wrong early calls per compound stays at or below 10% whichever fourth concentration is added; otherwise the concentration where the forecasters disagree most is added, and after four measured concentrations the series is reported or completed.

- hN2_NOG_BPCount: trained on 27 completed compounds (31,868 design rows), calibrated on 27; baseline 0.11 ± 0.1779 from 330 wells; release margin 0.42.
- hN2_NOG_NeuriteCount: trained on 27 completed compounds (33,528 design rows), calibrated on 27; baseline 0.06 ± 0.215 from 330 wells; release margin 0.35.
- hN2_NOG_NeuriteLength: trained on 28 completed compounds (34,484 design rows), calibrated on 28; baseline 3.215 ± 12.74 from 342 wells; release margin 0.33.
- hN2_NOG_NeuronCount: trained on 28 completed compounds (34,848 design rows), calibrated on 28; baseline 7.04 ± 12.46 from 342 wells; release margin 0.24.
- hNP1_Caspase_Apop: trained on 28 completed compounds (32,372 design rows), calibrated on 28; baseline 393 ± 5193 from 336 wells; release margin 0.23.
- hNP1_CellTiter_Lum: trained on 17 completed compounds (22,440 design rows), calibrated on 16; baseline 5.435e+04 ± 3.856e+04 from 198 wells; release margin 0.4.
- hNP1_Pro_MeanAvgInten: trained on 28 completed compounds (33,524 design rows), calibrated on 28; baseline 15.66 ± 26.11 from 336 wells; release margin 0.47.
- hNP1_Pro_ObjectCount: trained on 28 completed compounds (35,184 design rows), calibrated on 28; baseline 26.75 ± 35.21 from 336 wells; release margin 0.2.
- hNP1_Pro_ResponderAvgInten: trained on 28 completed compounds (34,848 design rows), calibrated on 28; baseline 5.55 ± 7.302 from 336 wells; release margin 0.35.

**Lock.** SHA-256 of what produced this forecast:

- input epa_dnt_three_point.csv: `8d07ccbf0084f7f21e94521d07a5f59b82648bb73463d1c2fa200bcd5ab484b6`
- forecast.csv: `4b05b47ce641fae587421f543eac3c6fc6ad960393e78986057bba7aa376305a`
- model hN2_NOG_BPCount (model_hN2_NOG_BPCount.pkl): `d66b5ebd9e1ec4d607c593aea3e9aff294db544492b8badf2d3b77423ccaadad`
- model hN2_NOG_NeuriteCount (model_hN2_NOG_NeuriteCount.pkl): `0dec41fed92ca9f8ecffbf8dff018e6ff11fb74cd8cda4ae9a60eadbc0fb5da3`
- model hN2_NOG_NeuriteLength (model_hN2_NOG_NeuriteLength.pkl): `5335aeefbe23a47ce0585babf41c546e8ec5e8f90ff884ca63baf19aedaeb000`
- model hN2_NOG_NeuronCount (model_hN2_NOG_NeuronCount.pkl): `3e500794abc1e562bbef3904d72410e2e5c5614bda9286fee0006144fbd92ea0`
- model hNP1_Caspase_Apop (model_hNP1_Caspase_Apop.pkl): `0e60f79226042bb1b7e82783f3764326d66a7d417154df50875d5d3aad8c0fc1`
- model hNP1_CellTiter_Lum (model_hNP1_CellTiter_Lum.pkl): `d3c15121687ae3cc8b0195e4d74e424881ec58a34d36b9d22cd547b181be701a`
- model hNP1_Pro_MeanAvgInten (model_hNP1_Pro_MeanAvgInten.pkl): `598cbfa281eb645ead63947d73991df732911726f498a3f5ec2056b01cc18fcb`
- model hNP1_Pro_ObjectCount (model_hNP1_Pro_ObjectCount.pkl): `c53798f49670e1403d129ddfd046d75050102f8d4a61de6d315f162a881d3424`
- model hNP1_Pro_ResponderAvgInten (model_hNP1_Pro_ResponderAvgInten.pkl): `3257f42e5a671e54edb18306cb74c1a1630a1278d6ba09bdb1d38d51fb33c140`
- protocol.json: `59090cd92c6f604c01c12225ec6c1b7b670b0936669b3af72d18f166730ef712`
- code three_point.py: `91a327c5bdc8f8a083fe767086f0fdd9bf801d4cb074de78304f979c41fb1064`
- code chip_forecast.py: `3d02dd3a1bc57e8c53f701a6005c8d5e9d8ad6a15a57cdec3f22b27066015897`
- code chip_forecast_intervals.py: `ad4825c2d0f1f6ccd5698cfe8b21e1d8fb31847f41338ef0ad1bf055fada05d4`
- code chip_forecast_selfcheck.py: `5c16d9cd82513c876ce3b98132338fb4b40bb9b7322c3b05e62ad1be96c23818`
- code paper_nested_decision.py: `22de67e35239a390a03e93d1df2c557671837944afc341e1eb2f5d46a9c094d7`

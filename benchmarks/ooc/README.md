# Ewart perfused Liver-Chip transfer

Reproduce the six-drug, three-endpoint transfer experiment on a free CPU:

```sh
python -m pip install -r benchmarks/ooc/requirements.txt
sh benchmarks/ooc/reproduce.sh --probe
sh benchmarks/ooc/reproduce.sh
```

Set `OOC_PYTHON` to choose another Python executable. The first command checks one albumin fold; the full run fits 36 models (two preparations × three endpoints × six held-out drugs). The committed source workbooks, frozen model and extracted CSV make the experiment runnable offline after installing dependencies.

[ewart_protocol.md](ewart_protocol.md) fixes preprocessing, splits, design selection, model parameters and reporting before fitting. [ewart_readings.csv](ewart_readings.csv) contains 210 source positions, 204 numeric observations and six blanks. [sources.json](sources.json) gives publisher URLs, licenses and hashes. The script verifies the original workbook and reproduces the CSV byte for byte before fitting. The frozen model source and protocol retain their original bytes.

[result.json](result.json), field `ewart_transfer`, reports the transfer results. [ewart_folds.csv](ewart_folds.csv) gives the 36 drug-level comparisons; [ewart_predictions.csv](ewart_predictions.csv) gives every held-out concentration prediction. In the primary published-unit preparation, AnchorBoost has lower error in four of six albumin folds and three of six ALT and morphology folds. All three paired 95% intervals span zero. The bootstrap samples six drugs; the 204 readings are not 204 independent test compounds. Each fold fits weights on its five training drugs using the frozen algorithm.

`result.json` also preserves the earlier nine-source availability audit, which applies the distinct unchanged vehicle-normalization protocol. The reproduction command rebuilds the Ewart transfer; the historical availability audit remains a source record. `sources.json` lists downloads for that earlier audit, while `raw/` includes only the Ewart workbooks and frozen model needed here.

Data attribution: Lorna Ewart et al., *Performance assessment and economic analysis of a human Liver-Chip for predictive toxicology*, Communications Medicine 2, 154 (2022), [article and supplementary data](https://doi.org/10.1038/s43856-022-00209-1), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The CSV extracts Supplementary Data 8 and preserves its row order, values and blanks. Supplementary Data 1 documents the study design. Code is covered by the repository MIT license; `raw/chip_forecast.py` is pinned to repository commit `dbddd7437b9f1643ef2872bd5de86de0779b209b`.

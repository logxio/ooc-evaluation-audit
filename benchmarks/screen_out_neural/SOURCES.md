# Sources and reuse terms

The archive contains prepared numerical measurements, predictions, derived errors,
model weights and analysis code. It contains no original EPA spreadsheets, R scripts
or article PDFs. `input_hashes.json` records upstream bytes; `checksums.json` records
the distributed files. Prepared matrices are the frozen training inputs.

| Material | Primary source | Terms and attribution |
|---|---|---|
| Analysis, shared network, AnchorBoost implementation and Ewart context helper | This repository; `run_experiment.py`, `aggregate.py`, `source/` | MIT, [LICENSE](LICENSE). The original repository copyright notice is retained. |
| NFA task representation, evaluation protocol port, published neural-process chemical errors (`published_np.csv`) | [NeuroChip Twin at f9848800dfab66a8bc005e6b3087153eeaabe9ac](https://github.com/Agnuxo1/neurochip-twin/tree/f9848800dfab66a8bc005e6b3087153eeaabe9ac) | MIT, copyright 2026 Francisco Angulo de Lafuente. [Pinned upstream license](https://github.com/Agnuxo1/neurochip-twin/blob/f9848800dfab66a8bc005e6b3087153eeaabe9ac/LICENSE), reproduced in [licenses/neurochip-twin-MIT.txt](licenses/neurochip-twin-MIT.txt). This is the published comparator identified as C in the benchmark audit. |
| NFA experimental measurements and chemical annotations | [US EPA CompTox DNT NFA Refinement, 01adf3e1a0068c87fe221d60df36b9f96c4b4b1d](https://github.com/USEPA/CompTox-DNT-NFA-Refinement/tree/01adf3e1a0068c87fe221d60df36b9f96c4b4b1d) | Publicly accessible EPA numerical data. The pinned repository has no dataset-specific license file. The MIT license above applies to the comparator code and distribution, not an independently established blanket license for every underlying EPA document. |
| Acute MEA measurements, Kosnik et al. (2020) | [EPA ScienceHub DOI 10.23719/1504294](https://doi.org/10.23719/1504294), [source archive](https://pasteur.epa.gov/uploads/10.23719/1504294/MEA_All_Data_Scripts.zip) | Public EPA scientific measurements. The original benchmark protocol labels these US public domain; a separate dataset-specific license was not captured with this experiment. Only derived numerical matrices are distributed here. |
| Human hNP1/hN2 measurements, Harrill et al. (2018) | [EPA ScienceHub DOI 10.23719/1407642](https://doi.org/10.23719/1407642), [source workbook](https://pasteur.epa.gov/uploads/10.23719/1407642/Harrill%20et%20al%20DNT_Assay%20Dataset.xlsx) | Public EPA scientific measurements; the same original-protocol license qualification as acute MEA applies. |
| Six-drug Liver-Chip measurements, Ewart et al. (2022) | [Performance assessment and economic analysis of a human Liver-Chip for predictive toxicology](https://www.nature.com/articles/s43856-022-00209-1), Supplementary Data 8 | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), The Author(s), 2022. Numeric ALBUMIN, ALT and Morphology values were extracted, missing entries masked, concentrations log-transformed and replicates averaged for evaluation. Author response units are retained. |

EPA's [disclaimers page](https://www.epa.gov/web-policies-and-procedures/epa-disclaimers)
describes scientific and educational use and document-specific copyright conditions;
it also says its catalogue of disclaimers requires incorporation to apply to a
particular work. Thus public access is documented separately from a dataset-specific
redistribution license. `licenses/source_evidence.json` records the checked sources
and this qualification. The software MIT license grants no additional rights in
third-party documents. This package uses derived factual numerical measurements.

`published_np.csv` is the unmodified upstream
[`results/trajectory_cv_per_chemical.csv`](https://github.com/Agnuxo1/neurochip-twin/blob/f9848800dfab66a8bc005e6b3087153eeaabe9ac/results/trajectory_cv_per_chemical.csv),
SHA-256 `0d013127aef781ca5e1de04088532e2e19223364173a198e0686941c04f93abc`.
Aggregation selects `method=neurotrajectory`, `k=3`, and the evaluated NFA chemicals.
These are published per-chemical errors, not new neural-process predictions or
neural-process retraining. Its original folds/designs and representation are
retained. Published NP results for the other three screens were unavailable in the
frozen experiment.

`comparator_errors.csv` contains the actual AnchorBoost references used in both
regimes. Harrill was refitted after removing the training alias `Valproate` of held-out
`Valproic Acid`; the other original references were reused. `baseline_audit.json`
records that correction. `baseline_*.csv` are the original references used by the
training entry before this correction, and therefore are not substituted for the
frozen corrected comparison in `aggregate.py`.

The immutable representation and original source-code hashes are recorded in
`input_hashes.json`. Public packaging changes, original artifact hashes and the
Kaggle experiment location are recorded in `provenance.json`. The package ships all
prepared inputs, so neither offline aggregation nor retraining requires access to
the private experiment notebook or dataset.

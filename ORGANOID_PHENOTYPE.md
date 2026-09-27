# Neural organoid phenotype audit

Find biological sample keys whose predicted NPC, Neuron, and Glioblast composition needs a closer look. The report ranks Bhaduri samples by Glioblast false positives so a researcher can check marker genes and original annotations before using the composition estimate.

On a free Kaggle Linux CPU with Python 3.12, enable Internet, leave GPU and TPU off, add `organoid_phenotype.py` as the script, and run:

```sh
python organoid_phenotype.py
```

The command downloads HNOCA v1 directly from [Zenodo](https://zenodo.org/records/15004818), verifies the original file is exactly **2,880,860,613 bytes** with MD5 `078675d6108e93cebc99676b6b0626aa`, and removes the temporary source copy after extracting the selected cells. Open `organoid_audit/audit.html`. `audit.json` contains all scores, denominators, 34 group confusion matrices, and resource readings; `groups.csv` is a compact per-sample review queue. No original data, per-cell predictions, or model weights are written to the report directory. The free Kaggle CPU run downloads 2.88 GB, so use a remote CPU with enough scratch space and time. If the Kaggle image changes, install the versions in `requirements-organoid.txt` before running.

The fixed evaluation uses `publication` to train on all Velasco 2019 NPC, Neuron, and Glioblast cells and test once on all Bhaduri 2020 cells in those classes. The HNOCA 3,000-gene count panel is normalized per cell to 10,000 counts and transformed with `log1p`. A balanced linear `SGDClassifier` uses log loss, L2, alpha `1e-4`, at most 30 iterations, averaging, and seed 26. Velasco also has a stratified 20% random cell holdout and a 20% `bio_sample` group holdout, each with its own fit. Prespecified baselines are Velasco's majority class and cosine nearest centroid. On the same Bhaduri cells, 2,000 seed-26 resamples of all 34 biological sample keys give the main macro-F1 interval and a paired difference interval against the better prespecified baseline. The report retains class scores, confusion matrices, all test denominators, and each group's composition gap and confusion matrix.

The better baseline is selected using Bhaduri's score, so its paired interval is conditional on that selection. The random, group, and external scores use different test cells and training sizes; gaps between those rows do not isolate a leakage effect.

This extends the repository's [image evaluation audit](audit_report.py): it exposes the source boundary, group definition, test denominators, false positives, and same-record paired comparison. `bio_sample` is a biological sample key, not a verified physical organoid ID. HNOCA selected the gene panel and assigned coarse labels across the shared atlas, including Bhaduri. This is a cross-laboratory acquisition-source test **under a shared panel and annotation**, not independently blind labeling. The predicted proportions are a review queue, not clinical, drug-toxicity, or unbiased composition truth. Astrocyte stays outside the three-class score and is reported only with descriptive denominators.

HNOCA v1 is [CC BY 4.0](https://zenodo.org/records/15004818). This repository's code is [MIT](LICENSE). NumPy, SciPy, scikit-learn, and h5py use BSD-3-Clause licenses; Requests uses Apache-2.0. The source file remains on Zenodo and is not distributed with this code.

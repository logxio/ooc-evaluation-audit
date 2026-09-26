# Organ-on-Chip Image Quality Gate

A researcher can use this baseline to flag organ-on-chip brightfield images that may need review before a culture is used for downstream analysis. It predicts the source dataset's expert **good/bad image-quality** label. It does not measure drug toxicity, neural connectivity, or whether a chip will succeed clinically.

The key question is whether image evidence still helps when images with the same date-like filename prefix are kept together during evaluation. The prefix is a proxy for acquisition context; the source does not provide independent chip IDs.

## Data and license

The source is the [Organ-on-a-Chip Image Dataset](https://zenodo.org/records/10203721) by Movčana et al., DOI [10.5281/zenodo.10203721](https://doi.org/10.5281/zenodo.10203721), with 3,072 PNGs, six cell types, and an XLSX datasheet. The [data description](https://www.mdpi.com/2306-5729/9/2/28), DOI [10.3390/data9020028](https://doi.org/10.3390/data9020028), explains how experts assigned quality labels. Label `1` is good; label `2` is bad, confirmed against the ZIP folder names.

Zenodo's record metadata lists **CC BY 4.0** for the two source files. The description paper calls the **dataset license CC-BY-SA** without a version. We record both statements rather than silently choosing one. This repository is **MIT licensed code only**. It downloads source files from Zenodo, attributes their creators, and does not rehost images or adapted image data. Resolve the license discrepancy before redistributing adapted data. [Zenodo record/API](https://zenodo.org/api/records/10203721), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).

## First measured baseline

The fixed split uses the first six digits of each image ID, which look like a date. Compute `int(sha256(utf8("26" + prefix)).hexdigest(), 16) % 100`; buckets 0–19 are test, 20–29 validation, and 30–99 training. There are 38/6/15 prefix groups and 2,084/252/736 images in train/validation/test. The test set has 376 good and 360 bad images.

The metadata-only logistic baseline uses cell type, seeding density, time after seeding, day, and flow rate. Missing-value medians and feature scaling are fitted on **training rows only**. A threshold is chosen on validation rows only. On the held-out test set, the actual script output is:

| Baseline | Balanced accuracy | Bad recall | Test confusion matrix, true rows good/bad |
| --- | ---: | ---: | --- |
| Always good | 0.5000 | 0.0000 | `[[376, 0], [360, 0]]` |
| Metadata only | **0.5233** | **0.4722** | `[[216, 160], [190, 170]]` |

The image-feature result is pending a full source-image run. The metadata score alone is not evidence that the quality gate generalizes well.

## Reproduce

Use Python 3.10 or later. [NumPy](https://numpy.org/doc/stable/license) is BSD-3-Clause licensed; [Pillow](https://pillow.readthedocs.io/en/stable/about.html#license) describes its license as MIT-CMU. This code uses no paid API, proprietary model, or GPU.

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python ooc_qc.py prepare --limit 64
python ooc_qc.py metadata
```

The script downloads and SHA-256 checks the 119,712-byte datasheet into `.cache/`. For the image baseline, the source ZIP is 6,710,767,405 bytes. Each `download-images` call saves progress and stops after 200 seconds so it can run within a short local process budget. Repeat the download and extraction commands until they report `"complete": true`.

```sh
python ooc_qc.py download-images
python ooc_qc.py verify-images
python ooc_qc.py extract-images --count 64
python ooc_qc.py image-evaluate
```

`verify-images` checks the source ZIP against Zenodo's MD5. `extract-images` computes 29 low-cost grayscale features per image; it writes only local, ignored cache entries. The image model uses the same split, train-only scaling, training-only fitting, and validation-only threshold selection. The test set is read once for the reported score. The split is stricter than the source's original image-level split, but it cannot establish chip-level independence without chip identifiers.

To run the complete image calculation on a private Kaggle CPU notebook with internet enabled:

```sh
python make_kaggle_job.py --owner YOUR_KAGGLE_USERNAME
kaggle kernels push -p .cache/kaggle_f1
```

The generated job is private and downloads the ZIP directly from Zenodo. `f1_image_result.json` is its evaluation artifact. Do not treat it as a public submission or publish it without reviewing the source license and competition sharing rules.

# Organ-on-Chip Image Evaluation Audit

A researcher can use this audit to see how an organ-on-chip image-quality score changes when images sharing an acquisition context are held out together. It compares two fixed evaluations of the source dataset's expert **good/bad image-quality** labels and shows which images change from correct to incorrect.

The first evaluation follows the source ZIP's image-level train/validation/test folders. The second keeps images with the same date-like filename prefix together. That prefix is a proxy for acquisition context; the source does not provide independent chip IDs. The image-quality models are baselines for the audit, not measures of drug toxicity or neural connectivity.

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
| Image features only | **0.6088** | **0.8028** | `[[156, 220], [71, 289]]` |

The image result comes from all 3,072 source PNGs. The downloaded ZIP matched Zenodo's MD5 `8f7e058996203d48eb03b2d86c0a2e4d`; all 3,072 extracted feature IDs matched the datasheet. The image model improves balanced accuracy by 0.0855 over metadata, but incorrectly flags 220 of 376 good test images (58.5%). A prefix-group bootstrap with 2,000 resamples gives a wide approximate 95% interval of 0.492–0.719 for image balanced accuracy; the prefixes are not confirmed chip IDs. The image score is below our predefined 0.65 continuation target. These results support a review queue for potentially bad images, not automatic rejection of a culture. A549 and HSAEC remain weak; HUVEC and NHBE have only bad examples in this test split, so per-cell balanced accuracy is undefined for them.

## F2: one preregistered nonlinear comparison

After seeing the F1 test score, we preregistered one F2 random forest using the **same 29 image features, labels, and prefix split**. It fits only on train: `RandomForestClassifier(n_estimators=300, min_samples_leaf=8, max_features='sqrt', class_weight='balanced_subsample', random_state=26)` with all other scikit-learn defaults. There is no additional feature engineering or test-set tuning. This is an **adaptive iteration after viewing F1 test**, so the reused 736-image test is not a fresh blind holdout.

Threshold selection uses validation probabilities only. Candidates are each distinct probability, adjacent midpoints, and 0, 0.5, 1. Among candidates with bad recall at least 0.60 **and** good recall at least 0.55, maximize balanced accuracy. If none qualify, use those with bad recall at least 0.60; if none qualify, maximize balanced accuracy without a recall constraint. Ties go to the threshold closest to 0.5, then the higher threshold. The first tier contained 44 of 506 candidates, and selected `0.31713680975737424`.

Before the fit, our target for continuing this direction was **all three** test conditions: balanced accuracy at least 0.65, bad recall at least 0.60, and good false-positive rate at most 0.45. Our expected ranges were test balanced accuracy 0.63–0.71 (center 0.67), bad recall 0.60–0.80, and good false-positive rate 0.35–0.50. The actual measurements are:

| F2 split | Good / bad | Balanced accuracy | Good recall | Bad recall | Good false-positive rate | Confusion matrix, true rows good/bad |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Validation | 179 / 73 | 0.6464 | 0.5531 | 0.7397 | 80/179 = 0.4469 | `[[99, 80], [19, 54]]` |
| Test | 376 / 360 | **0.6578** | 0.5239 | **0.7917** | **179/376 = 0.4761** | `[[197, 179], [75, 285]]` |

Against the F1 image baseline, F2 increases test balanced accuracy by 0.0490 and reduces good false positives from 220 to 179, while bad recall changes from 0.8028 to 0.7917. A 2,000-draw bootstrap resampling the 15 date-like test prefix groups gives an approximate 95% balanced-accuracy interval of 0.577–0.733. **F2 misses the preregistered joint continuation target** because 47.61% of good images are still falsely flagged, above the 45% ceiling. The next decision is to change the primary direction, not tune a third model on this test set. This result may help prioritize human review; it does not justify automatic culture rejection.

| Test cell type | Good / bad | Balanced accuracy | Good recall | Bad recall | Good false-positive rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| A549 | 151 / 81 | 0.5684 | 0.4702 | 0.6667 | 0.5298 |
| CACO | 27 / 55 | 0.6774 | 0.5185 | 0.8364 | 0.4815 |
| HPMEC | 187 / 152 | 0.6960 | 0.5829 | 0.8092 | 0.4171 |
| HSAEC | 11 / 24 | 0.4280 | 0.2727 | 0.5833 | 0.7273 |
| HUVEC | 0 / 39 | undefined | undefined | 1.0000 | undefined |
| NHBE | 0 / 9 | undefined | undefined | 1.0000 | undefined |

The F2 script also prints per-cell validation denominators, recalls, false-positive rates, and confusion matrices. A missing class makes that cell's balanced accuracy undefined. Neither the split nor the bootstrap proves independence across physical chips, because chip IDs are unavailable.

## How the source split changes the score

The source ZIP assigns images to train, validation, and test folders. The `source_split_audit.py` command reads that assignment from the ZIP64 central directory with byte-range requests, then checks every image ID and good/bad folder against the datasheet. It reads about 0.5 MB of ZIP metadata and does not download the 6.7 GB image archive. The source split has 2,130/286/656 images; all 57 date-like prefixes in its test set also appear in its training set. That is acquisition-context overlap, not proof that the same physical chip appears on both sides.

F3 fits the same 300-tree random-forest specification on the source training images using the frozen 29 features. It selects a threshold from the source validation images with the exact F2 rule. The source validation set selects `0.4984234764442013`; the F2 prefix-split validation set selected `0.31713680975737424`.

| Split and model | Good / bad test images | Test balanced accuracy | Good recall | Bad recall | Good false-positive rate | Test confusion matrix |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Source ZIP folders, F3 RF | 365 / 291 | **0.7979** | 0.8329 | 0.7629 | 61/365 = 0.1671 | `[[304, 61], [69, 222]]` |
| Date-like prefix groups, F2 RF | 376 / 360 | **0.6578** | 0.5239 | 0.7917 | 179/376 = 0.4761 | `[[197, 179], [75, 285]]` |

F3 source validation balanced accuracy is 0.7850, with good/bad recall 0.8221/0.7480, good false-positive rate 29/163 = 0.1779, and confusion matrix `[[134, 29], [31, 92]]`. Source test balanced accuracy exceeds the prefix-split result by **0.1401**. A 2,000-draw bootstrap over the source test's 57 prefixes gives an approximate 95% balanced-accuracy interval of **0.744–0.847**; it does not remove train/test prefix overlap. The comparison passes our preregistered audit-direction screen: source test accuracy at least 0.75 and a gap of at least 0.10. A second dataset is needed before treating split sensitivity as a general finding.

Only 151 images are in both test sets; 505 are unique to the source test and 585 to the prefix-group test. The score gap combines changes in training rows, validation rows and threshold, and test composition. It is a diagnostic comparison, not a same-image causal estimate of leakage. This experiment does not reproduce the published InceptionV3 study.

| F3 source test cell type | Good / bad | Balanced accuracy | Good recall | Bad recall | Good false-positive rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| A549 | 112 / 52 | 0.7754 | 0.8393 | 0.7115 | 0.1607 |
| CACO | 25 / 50 | 0.8000 | 0.8000 | 0.8000 | 0.2000 |
| HPMEC | 163 / 138 | 0.8018 | 0.8282 | 0.7754 | 0.1718 |
| HSAEC | 37 / 20 | 0.6595 | 0.9189 | 0.4000 | 0.0811 |
| HUVEC | 4 / 21 | 0.9762 | 1.0000 | 0.9524 | 0.0000 |
| NHBE | 24 / 10 | 0.8542 | 0.7083 | 1.0000 | 0.2917 |

## F4: the same 151 test images

The two original test sets share 151 images: 68 good, 83 bad, across 14 date-like prefixes. F4 refits each frozen 300-tree forest on its original training rows, chooses its threshold on its original validation rows, and scores both on those same 151 images. The 29 features, model parameters, and threshold rule are unchanged. F4 does not select or tune a model on the 151-image subset. Both models' full test summaries were already seen before F4, so this is a diagnostic comparison, not a fresh blind test.

| Model on shared images | Balanced accuracy | Good recall | Bad recall | Good false-positive rate | Confusion matrix, true rows good/bad |
| --- | ---: | ---: | ---: | ---: | --- |
| Source ZIP split, F3 | **0.762491** | 0.838235 | 0.686747 | 11/68 = 0.161765 | `[[57, 11], [26, 57]]` |
| Prefix-group split, F2 | **0.691708** | 0.588235 | 0.795181 | 28/68 = 0.411765 | `[[40, 28], [17, 66]]` |

The paired balanced-accuracy difference is **+0.070783** for the source-split model. Its good-image recall is higher by 0.25, while its bad-image recall is lower by 0.108434. Resampling the same 14 prefixes for both models 2,000 times gives a paired percentile bootstrap 95% difference interval of **−0.031747 to +0.127527**. Our preregistered stronger-evidence screen required a difference of at least 0.08 and a bootstrap lower bound above zero. Neither condition passed. This is a split-sensitivity diagnostic on one dataset, with a second data source needed before a general platform claim.

| True label | Both correct | Source only correct | Prefix only correct | Both wrong |
| --- | ---: | ---: | ---: | ---: |
| Good, 68 images | 40 | 17 | 0 | 11 |
| Bad, 83 images | 54 | 3 | 12 | 14 |
| All 151 images | **94** | **20** | **12** | **25** |

Per-cell scores use the same shared images in both models. A cell with no good images has undefined balanced accuracy, good recall, and good false-positive rate.

| Cell type, good/bad | Source BA | Good recall | Bad recall | Good FPR | Source confusion matrix |
| --- | ---: | ---: | ---: | ---: | --- |
| A549, 28/20 | 0.725000 | 0.750000 | 0.700000 | 0.250000 | `[[21,7],[6,14]]` |
| CACO, 5/9 | 0.577778 | 0.600000 | 0.555556 | 0.400000 | `[[3,2],[4,5]]` |
| HPMEC, 31/33 | 0.847507 | 0.967742 | 0.727273 | 0.032258 | `[[30,1],[9,24]]` |
| HSAEC, 4/9 | 0.486111 | 0.750000 | 0.222222 | 0.250000 | `[[3,1],[7,2]]` |
| HUVEC, 0/9 | undefined | undefined | 1.000000 | undefined | `[[0,0],[0,9]]` |
| NHBE, 0/3 | undefined | undefined | 1.000000 | undefined | `[[0,0],[0,3]]` |

| Cell type, good/bad | Prefix BA | Good recall | Bad recall | Good FPR | Prefix confusion matrix |
| --- | ---: | ---: | ---: | ---: | --- |
| A549, 28/20 | 0.592857 | 0.535714 | 0.650000 | 0.464286 | `[[15,13],[7,13]]` |
| CACO, 5/9 | 0.688889 | 0.600000 | 0.777778 | 0.400000 | `[[3,2],[2,7]]` |
| HPMEC, 31/33 | 0.747801 | 0.677419 | 0.818182 | 0.322581 | `[[21,10],[6,27]]` |
| HSAEC, 4/9 | 0.513889 | 0.250000 | 0.777778 | 0.750000 | `[[1,3],[2,7]]` |
| HUVEC, 0/9 | undefined | undefined | 1.000000 | undefined | `[[0,0],[0,9]]` |
| NHBE, 0/3 | undefined | undefined | 1.000000 | undefined | `[[0,0],[0,3]]` |

F4 reproduced every stored full-test metric field for F2 and F3, including each cell type and the full-test bootstrap interval; it also matched their split summaries, validation metrics, threshold choices, parameters, and feature names. Keeping test images fixed removes test-composition differences. The models still have different training rows and validation thresholds, so the paired difference cannot be attributed entirely to prefix overlap and does not prove that a physical chip leaked across splits.

## Reproduce

Use Python 3.11 or later. [NumPy](https://numpy.org/doc/stable/license) is BSD-3-Clause licensed; [Pillow](https://pillow.readthedocs.io/en/stable/about.html#license) describes its license as MIT-CMU. [scikit-learn 1.9.1 on official PyPI](https://pypi.org/project/scikit-learn/1.9.1/) is BSD-3-Clause licensed. This code uses no paid API, proprietary model, or GPU.

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

`verify-images` checks the source ZIP against Zenodo's MD5. `extract-images` computes 29 low-cost grayscale features per image; it writes only local, ignored cache entries. The F1 image model uses the same split, train-only scaling, training-only fitting, and validation-only threshold selection. Its test labels did not guide F1 feature design, model fitting, or threshold selection. F2 was specified after the F1 test score was known. The split is stricter than the source's original image-level split, but it cannot establish chip-level independence without chip identifiers.

With the **existing** `.cache/image_features.jsonl` from that F1 extraction, F2 needs no ZIP download. Supply another path with `--features` if the cache is elsewhere. `probe` fits 300 trees on only 64 training rows and reports time/memory, without reporting a score. `evaluate` runs the one full train fit and prints the complete validation/test result as JSON, including per-cell counts, confusion matrices, the prefix-group bootstrap, and F1-to-F2 changes.

```sh
python f2_rf.py probe --features .cache/image_features.jsonl
python f2_rf.py evaluate --features .cache/image_features.jsonl > .cache/f2_rf_result.json
```

The measured local F2 fit took 0.97 seconds; the full process took 2.22 seconds and reached 147 MB maximum resident memory on a Mac. The 64-row resource probe reached 135 MB. Feature cache SHA-256: `ba4406c3671d5d859b6ff58a66a7d05ff4bbd95ed4d58700de18533e362b5f57`. The cache and result JSON are ignored by git; they contain no redistributed source images.

To reproduce F3 with the same feature cache, read the ZIP metadata and evaluate the frozen RF specification:

```sh
python source_split_audit.py probe
python source_split_audit.py map
python source_split_audit.py evaluate --features .cache/image_features.jsonl > .cache/f3_source_result.json
```

`map` saves `.cache/source_split.json` after verifying 3,072 unique IDs, source-folder labels, cell types, and split counts. Both mapping and result are ignored by git. The measured mapping process took 5.01 seconds and peaked at 61 MB; the F3 evaluation took 2.74 seconds and peaked at 149 MB. The central-directory SHA-256 is `82125825d36ecca86496fe7d64a2b6169f4ffa940ffa3d98b9fce91bb97f27b8`.

After F2 and F3 have written their local result JSON files, reproduce the paired F4 audit without downloading images again:

```sh
python f4_paired.py probe --features .cache/image_features.jsonl
python f4_paired.py evaluate --features .cache/image_features.jsonl > .cache/f4_paired_result.json
```

The script stops if any stored F2 or F3 deterministic field differs from its refit, then reports the shared-image matrices, per-cell scores, correctness transitions, and paired prefix-group interval. The 64-row-per-model resource probe prints no score. The local F4 evaluation took 2.91 seconds including process startup and peaked at 149 MB; its ignored JSON stores the unrounded values. The feature-cache SHA-256 was `ba4406c3671d5d859b6ff58a66a7d05ff4bbd95ed4d58700de18533e362b5f57`.

To run the complete image calculation on a private Kaggle CPU notebook with internet enabled:

```sh
python make_kaggle_job.py --owner YOUR_KAGGLE_USERNAME
kaggle kernels push -p .cache/kaggle_f1
```

The generated job is private and downloads the ZIP directly from Zenodo. `f1_image_result.json` is its evaluation artifact. Do not treat it as a public submission or publish it without reviewing the source license and competition sharing rules.

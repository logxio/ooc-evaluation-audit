# Phenotype Transfer Maps: cross-study organoid cell typing with sample review priorities

A **Phenotype Transfer Map** pairs a cell-type model's cross-acquisition-source score with a score-based sample review order and a separate label-backed error audit. It makes visible what one aggregate metric hides: a model can transfer well overall while rare-class calls and particular sample keys still need review. The fixed three-class model trained on [Velasco's neural organoids](https://doi.org/10.1038/s41586-019-1289-x) reached **0.9078 macro-F1** on **207,871 cells** from [Bhaduri's separate laboratory](https://doi.org/10.1038/s41586-020-1962-0). Resampling **34 biological-sample keys** gives a 95% interval of **0.8423–0.9372**. A source-trained nearest-centroid comparator scored **0.8068** on those same cells; the paired difference is **+0.1010** with a group interval of **+0.0705 to +0.1205**.

Within the HNOCA cohort already selected by its three class labels, the report ranks sample keys by mean uncertainty from the model's decision-score margins; the **ranking calculation** uses no target labels. In a **retrospective** check on the same 34 Bhaduri keys, this rank correlated with observed key error rate (equal-key Spearman **0.7791**, 2,000-draw key interval **0.5546–0.9010**). The highest-ranked eight keys had **1.721 times** the equal-key mean error rate. After observing this ratio, we kept the top-eight ranks fixed and shuffled the 34 observed group error rates 10,000 times; none matched it (one-sided, plus-one Monte Carlo **p=0.00010**). This conditional, post hoc check does not supply independent labels or a prospective test. Cohort selection did use HNOCA labels, so this is not an end-to-end test on a wholly unannotated batch; the score is not an error probability.

When reference labels are available, a separate error audit shows what to check. Glioblast, HNOCA's neural progenitor cell-type label rather than a tumor diagnosis, is the sharpest example: the model found 2,862 of 3,071 consensus-labeled cells, while **1,353** other cells were incorrectly flagged. One 3,030-cell sample has **8** consensus Glioblast labels and **96** model calls. That example ranks sixth by known-label Glioblast false positives but 27th by the score-only uncertainty queue. Inspect those cells before using a predicted composition as a research result.

A secondary label-and-endpoint check exposes another limit of a single headline score. The [Bhaduri author labels preserved in HNOCA's CC BY cleaned archive](https://zenodo.org/records/14161275) classify **175,160** of the selected test cells unambiguously as Neuron or Radial Glia. On this different two-class endpoint, the fixed model scored **0.9412 macro-F1** (34-key interval **0.9224–0.9566**), while the prespecified nearest-centroid comparator scored **0.9472**. The paired model-minus-centroid interval was **−0.0101 to −0.0025**. The comparator ordering reverses when both the label convention and class endpoint change; this does not isolate which change caused it, and the 0.9412 score is not a new model advantage. These labels come from the same Bhaduri collection and may have informed atlas harmonization, so this is a sensitivity check, not independently blind validation.

The two experiments were collected independently, but the [HNOCA atlas](https://www.nature.com/articles/s41586-024-08172-8) selected its 3,000-gene panel across studies and harmonized their labels. This is a cross-laboratory **acquisition-source** test under a shared panel and annotation, not a blind independent-label validation. `bio_sample` is an atlas key, not a verified physical organoid or donor ID. These organoids are not perfused organ-on-chip cultures; the image audit below uses actual chip images. The [organoid run guide](ORGANOID_PHENOTYPE.md) covers the free-CPU source-to-report route; the [technical report](technical_report.pdf) gives the full protocol, class errors, license attribution, and limits ([source](technical_report.md)).

[HNOCA-tools](https://devsystemslab.github.io/HNOCA-tools/api/mapping/AtlasMapper/) already supports atlas mapping and label transfer, and [Khatri and Bonn](https://proceedings.mlr.press/v179/khatri22a.html) studied uncertainty for single-cell label transfer. This map does not invent those methods or calibrate its margin score as an error probability. Its measured output joins one whole-study holdout, a review order on the same 34 sample keys, and their known-label errors in one reproducible record. A future independently labeled cohort is still needed to test whether this review order transfers.

**Reproduce the main result:** On a free Kaggle Linux CPU with Internet enabled, install [`requirements-organoid.txt`](requirements-organoid.txt) if needed, then run `python organoid_phenotype.py`. The command checks the 2,880,860,613-byte HNOCA original against its published MD5 and writes `organoid_audit/audit.html`, `audit.json`, `groups.csv`, and `review_queue.csv`. The earlier F17 CLI ran cleanly in **675 seconds** at **2.56 GB** peak resident memory. The expanded F18 CLI ran cleanly from the original in **1,164 seconds** at **2.55 GB** in a private free CPU run; its old metrics and score-based rank matched the prior reads. The [public competition notebook](https://www.kaggle.com/code/loxigicck/neural-organoid-phenotype-audit-across-labs) v3 completed from the original with script exit **0** in **869.831 seconds**, at **2,548,330,496 bytes** peak resident memory. An independent output check matched the original file MD5, the exact source SHA-256, all F17/F18 metrics, and the new permutation count. That v3 notebook preserves the earlier source for the primary route; the optional author-label command below is a later addition and is undergoing a separate source-matched rerun. The [run guide](ORGANOID_PHENOTYPE.md) states the full protocol and limits. Source transfer may take longer than computation and requires temporary scratch space.

To include the Bhaduri author-label sensitivity check in the same source-to-report run, use `python organoid_phenotype.py --author-label-sensitivity`. It reads only needed metadata byte ranges of the separate CC BY cleaned archive, verifies that all **223,453** Bhaduri HNOCA row keys match the scoring archive in order, and adds `author_label_sensitivity.json` with class totals, per-key confusion matrices, fixed comparators, and 2,000-draw key intervals. The ordinary command above remains the shorter primary run.

## Organ-on-chip image audit

Give the audit per-image labels, acquisition groups, train/validation/test splits, and test predictions. It gives you an offline report showing group overlap, each test set's good/bad errors, and what changes when both evaluations score the same images.

The image case examines a different task and dataset. Its full method and exact denominators are in the same [technical report](technical_report.pdf).

To reproduce the [Zenodo image-quality example](https://zenodo.org/records/10203721) from the original files, install `requirements.txt`, then run:

```sh
python run_full_audit.py
```

The first run downloads a **6,710,767,405-byte (6.71 GB) image ZIP** and a 119,712-byte datasheet from Zenodo. It verifies their published hashes, extracts 29 features from all 3,072 images, recomputes F1–F4, checks the Linux reference, and writes `.cache/audit_report/audit.html`, `audit.json`, and `run_evidence.json`. Open the HTML offline; the JSON includes scored records and input hashes. The default command stops after about four minutes on a local machine. Run the **same command again** to resume the ZIP download or feature extraction. On a remote CPU with a longer process allowance, use `python run_full_audit.py --time-budget 0` for one uninterrupted invocation. No source images or cached features are included in this repository.

A clean Kaggle Linux x86-64 run from the original Zenodo files supplies the frozen reference. Linux ARM64 independently reproduced its F2–F4 deterministic fields from the same real feature file. On Linux, matching source files and features lead to a verified report and exit 0. On macOS, the same feature file yields different random-forest trees and scores; the report marks the platform mismatch and exits 3. The original macOS measurements remain below as historical results.

For another image dataset, use `python audit_report.py records --source-records SOURCE.jsonl --grouped-records GROUPED.jsonl --output OUTPUT_DIR`. Each JSONL file needs one record per image with `id`, `group`, `label` (`0` good, `1` bad), `split` (`train`, `val`, or `test`), and `prediction` (`0` or `1` on test, `null` elsewhere). `subgroup` is optional. The two files must use the same labels and groups for shared IDs. A group should identify the acquisition unit you want to keep together; it is only a chip ID if your data actually supplies one.

For this OoC dataset, the date-like prefix is an acquisition-context proxy. The source does not supply independent physical chip IDs. These image-quality scores do not measure toxicity or neural connectivity.

### Data and license

The source is the [Organ-on-a-Chip Image Dataset](https://zenodo.org/records/10203721) by Movčana et al., DOI [10.5281/zenodo.10203721](https://doi.org/10.5281/zenodo.10203721), with 3,072 PNGs, six cell types, and an XLSX datasheet. The [data description](https://www.mdpi.com/2306-5729/9/2/28), DOI [10.3390/data9020028](https://doi.org/10.3390/data9020028), explains how experts assigned quality labels. Label `1` is good; label `2` is bad, confirmed against the ZIP folder names.

Zenodo's record metadata lists **CC BY 4.0** for the two source files. The description paper calls the **dataset license CC-BY-SA** without a version. We record both statements rather than silently choosing one. This repository is **MIT licensed code only**. It downloads source files from Zenodo, attributes their creators, and does not rehost images or adapted image data. Resolve the license discrepancy before redistributing adapted data. [Zenodo record/API](https://zenodo.org/api/records/10203721), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).

### First measured baseline

The fixed split uses the first six digits of each image ID, which look like a date. Compute `int(sha256(utf8("26" + prefix)).hexdigest(), 16) % 100`; buckets 0–19 are test, 20–29 validation, and 30–99 training. There are 38/6/15 prefix groups and 2,084/252/736 images in train/validation/test. The test set has 376 good and 360 bad images.

The metadata-only logistic baseline uses cell type, seeding density, time after seeding, day, and flow rate. Missing-value medians and feature scaling are fitted on **training rows only**. A threshold is chosen on validation rows only. On the held-out test set, the actual script output is:

| Baseline | Balanced accuracy | Bad recall | Test confusion matrix, true rows good/bad |
| --- | ---: | ---: | --- |
| Always good | 0.5000 | 0.0000 | `[[376, 0], [360, 0]]` |
| Metadata only | **0.5233** | **0.4722** | `[[216, 160], [190, 170]]` |
| Image features only | **0.6088** | **0.8028** | `[[156, 220], [71, 289]]` |

The image result comes from all 3,072 source PNGs. The downloaded ZIP matched Zenodo's MD5 `8f7e058996203d48eb03b2d86c0a2e4d`; all 3,072 extracted feature IDs matched the datasheet. The image model improves balanced accuracy by 0.0855 over metadata, but incorrectly flags 220 of 376 good test images (58.5%). A prefix-group bootstrap with 2,000 resamples gives a wide approximate 95% interval of 0.492–0.719 for image balanced accuracy; the prefixes are not confirmed chip IDs. The image score is below our predefined 0.65 continuation target. These results support a review queue for potentially bad images, not automatic rejection of a culture. A549 and HSAEC remain weak; HUVEC and NHBE have only bad examples in this test split, so per-cell balanced accuracy is undefined for them.

### What the example shows

The source ZIP's test folder contains 57 date-like image-ID prefixes; all 57 also occur in its training folder. The alternative holdout keeps all images with a prefix in one split. A prefix is an acquisition-context proxy, not a verified physical chip ID.

The same frozen 29-feature, 300-tree random-forest specification is fitted separately to each training split, with each threshold selected on that split's validation images. The test sets share only 151 IDs. The scores below are from the Linux reference built from the original Zenodo files.

| Evaluation | Test good/bad | Balanced accuracy | Good images flagged bad | Confusion matrix, true rows good/bad |
| --- | ---: | ---: | ---: | --- |
| Source ZIP folders, F3 | 365/291 | 0.799925 | 57/365 | `[[308,57],[71,220]]` |
| Prefix-group holdout, F2 | 376/360 | 0.657920 | 181/376 | `[[195,181],[73,287]]` |

The full-test difference is +0.142005. It compares different test images and separately fitted models, so it cannot measure the causal effect of prefix overlap. F2 also flags 48.14% of expert-good test images, above the prespecified 45% ceiling for an automatic quality gate. F2 follows the viewed F1 test and is not a fresh blind test.

### The 151 shared test images

The intersection contains 68 good and 83 bad images from 14 date-like prefixes. Scoring these exact IDs with both models removes test-composition differences. Training rows, validation rows, and thresholds still differ.

| Model on shared images | Balanced accuracy | Good images flagged bad | Confusion matrix |
| --- | ---: | ---: | --- |
| Source ZIP split, F3 | 0.756467 | 11/68 | `[[57,11],[27,56]]` |
| Prefix-group split, F2 | 0.690379 | 29/68 | `[[39,29],[16,67]]` |

The paired balanced-accuracy difference is +0.066088. Of the 151 images, both models classify 92 correctly, only the source model 21, only the grouped model 14, and neither 24. A 2,000-draw paired bootstrap over the 14 prefixes gives an approximate 95% difference interval of −0.042091 to +0.122483. It crosses zero and does not support a general claim that image-level splits are optimistic. The report also lists each test set's class denominators, subgroup scores, transitions, and input hashes.

### Platform history and reproducibility

The original macOS run used the same source data, feature SHA-256, model specification, and validation rule. The first divergent random-forest node appears in tree 3 with 2,084 training rows, before validation probabilities and threshold selection. A single-tree fit agrees across macOS and Linux. The underlying platform operation causing the tree split is not established.

| Measure | Linux reference | Earlier macOS result |
| --- | ---: | ---: |
| F2 full-test balanced accuracy | 0.657920 | 0.657801 |
| F3 full-test balanced accuracy | 0.799925 | 0.797882 |
| Same-151-image difference | +0.066088 | +0.070783 |
| Paired 95% interval | −0.042091 to +0.122483 | −0.031747 to +0.127527 |

`frozen_reference.json` retains both records and checks the Linux run's feature SHA-256, full validation/test summaries, confusion matrices, thresholds, overlap, and paired results. Numeric comparisons use an absolute tolerance of `1e-12`; class counts and other discrete fields must match exactly. This tolerance is below the observed cross-platform differences. A changed source or feature file is a mismatch, not an accepted variation.

### Reproduce

Use Python 3.12 and install the pinned CPU dependencies:

```sh
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python run_full_audit.py
```

The command uses ignored `.cache/` files. Its default local process budget is 240 seconds, so run the **same command again** to resume the 6.71 GB ZIP download or feature extraction. On a remote CPU with a longer allowance, `python run_full_audit.py --time-budget 0` runs the complete route in one invocation. Open `.cache/audit_report/audit.html` offline; `audit.json` holds scored image records and `run_evidence.json` holds source hashes, reference status, elapsed time, and peak memory. The source images are downloaded under the source's license and are never distributed with this code.

For the individual stages, run `python ooc_qc.py --help`, `python f2_rf.py --help`, `python source_split_audit.py --help`, and `python f4_paired.py --help`. F3 reads the F2 result from the **same** run so its full-test gap compares two scores from one environment. The generic `audit_report.py records` command above accepts another dataset's own predictions without using our image model.

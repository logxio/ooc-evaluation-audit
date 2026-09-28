# Decision Contract Map: what a chip readout can support

A chip readout can look decisive until the patient, time point, or assay channel changes. **Decision Contract Map** records what was measured, what decision it might support, and what later result challenges it. Its new **Assay Discordance Contract** asks whether an image-derived area change and a viability assay even agree before anyone projects either into a treatment claim. In a published patient-derived spheroid source table, they disagree on **14/49** patient-treatment pairs; in **12/40** pairs with reduced viability, area fails to shrink. The paper's Figure 5 caption says n=48, while its downloadable source table has 49 complete numeric pairs. The patient spheroid method does not clearly state that these particular rows were measured under chip perfusion, so this is an adjacent assay check, not another physical-chip validation.

In a separate published 22-patient colorectal chip study, our patient-held-out threshold audit classified **17/22** clinical responses with a prespecified two-channel average. An exploratory vessel-only channel reached **21/22**; averaging it with the tumoroid channel lost four correct classifications. An outer patient holdout with channel selection inside the other 21 patients classified **20/22**. That nested procedure was designed after seeing the six readouts, so it remains exploratory and needs a new registered cohort before clinical use. The original authors built the chips and established the underlying clinical correlation; our contribution is the held-out audit, the channel-combination failure case, and the explicit selection check.

In separate published programmable pancreatic organoid-chip traces, **8/48** temporal-versus-static drug contrasts changed direction between 24 and 72 hours. An early forecast failed: its 72-hour MAE was **0.4071**, compared with **0.1526** for simply carrying the 24-hour value forward. Those 48 contrasts came from only three patients. The [technical report](technical_report.pdf) keeps these chip results separate from the cell-review audit below and states what each can and cannot establish.

A **Review Contract Map** records which organoid cells are eligible for a review queue, the score-only sample-key order, how later reference labels define findings, and what a fixed review budget misses. A fixed model trained on [Velasco's neural organoids](https://doi.org/10.1038/s41586-019-1289-x) reached **0.9078 macro-F1** on **207,871 Bhaduri cells** and **0.9374** on **236,453 HNOCA-selected Uzquiano cells**. These are different acquisition publications within one harmonized atlas, not independently adjudicated biological results. A 20% whole-key budget on **all 263,827 Uzquiano cells** exposed **17,046/34,656** later HNOCA-label findings and missed **17,610**; the full result and its negative Bhaduri contrast are below.

Within the HNOCA cohort already selected by its three class labels, the report ranks sample keys by mean uncertainty from the model's decision-score margins; the **ranking calculation** uses no target labels. In a **retrospective** check on the same 34 Bhaduri keys, this rank correlated with observed key error rate (equal-key Spearman **0.7791**, 2,000-draw key interval **0.5546–0.9010**). The highest-ranked eight keys had **1.721 times** the equal-key mean error rate. After observing this ratio, we kept the top-eight ranks fixed and shuffled the 34 observed group error rates 10,000 times; none matched it (one-sided, plus-one Monte Carlo **p=0.00010**). This conditional, post hoc check does not supply independent labels or a prospective test. Cohort selection did use HNOCA labels, so this is not an end-to-end test on a wholly unannotated batch; the score is not an error probability.

When reference labels are available, a separate error audit shows what to check. Glioblast, HNOCA's neural progenitor cell-type label rather than a tumor diagnosis, is the sharpest example: the model found 2,862 of 3,071 consensus-labeled cells, while **1,353** other cells were incorrectly flagged. One 3,030-cell sample has **8** consensus Glioblast labels and **96** model calls. That example ranks sixth by known-label Glioblast false positives but 27th by the score-only uncertainty queue. Inspect those cells before using a predicted composition as a research result.

A secondary label-and-endpoint check exposes another limit of a single headline score. The [Bhaduri author labels preserved in HNOCA's CC BY cleaned archive](https://zenodo.org/records/14161275) classify **175,160** of the selected test cells unambiguously as Neuron or Radial Glia. On this different two-class endpoint, the fixed model scored **0.9412 macro-F1** (34-key interval **0.9224–0.9566**), while the prespecified nearest-centroid comparator scored **0.9472**. The paired model-minus-centroid interval was **−0.0101 to −0.0025**. The comparator ordering reverses when both the label convention and class endpoint change; this does not isolate which change caused it, and the 0.9412 score is not a new model advantage. These labels come from the same Bhaduri collection and may have informed atlas harmonization, so this is a sensitivity check, not independently blind validation.

The two experiments were collected independently, but the [HNOCA atlas](https://www.nature.com/articles/s41586-024-08172-8) selected its 3,000-gene panel across studies and harmonized their labels. This is a cross-laboratory **acquisition-source** test under a shared panel and annotation, not a blind independent-label validation. `bio_sample` is an atlas key, not a verified physical organoid or donor ID. These neural organoids are not perfused organ-on-chip cultures; the distinct physical-chip and chip-image audits appear below. The [organoid run guide](ORGANOID_PHENOTYPE.md) covers the free-CPU source-to-report route; the [technical report](technical_report.pdf) gives the full protocol, class errors, license attribution, and limits ([source](technical_report.md)).

[HNOCA-tools](https://devsystemslab.github.io/HNOCA-tools/api/mapping/AtlasMapper/) already supports atlas mapping and label transfer, and [Khatri and Bonn](https://proceedings.mlr.press/v179/khatri22a.html) studied uncertainty for single-cell label transfer. This map does not invent those methods or calibrate its margin score as an error probability. Its measured output joins one whole-study holdout, a review order on the same 34 sample keys, and their known-label errors in one reproducible record. A future independently labeled cohort is still needed to test whether this review order transfers.

**Reproduce the main result:** On a free Kaggle Linux CPU with Internet enabled, install [`requirements-organoid.txt`](requirements-organoid.txt) if needed, then run `python organoid_phenotype.py`. The command checks the 2,880,860,613-byte HNOCA original against its published MD5 and writes `organoid_audit/audit.html`, `audit.json`, `groups.csv`, and `review_queue.csv`. The [competition-linked public notebook](https://www.kaggle.com/code/loxigicck/neural-organoid-phenotype-audit-across-labs) v4 ran the optional two-archive route on free Kaggle Linux CPU to script exit **0** in **921.345 seconds**, at **2,550,792,192 bytes** peak resident memory. Its source SHA-256 matches this repository's main script `936fef80…` and original-author module `8cd0e89f…`. An independent output check confirmed the minimal original's MD5, every earlier three-class field and rank result, the 175,160-cell author-label endpoint, and all 34 paired group matrices. The cleaned archive was read by byte ranges and its full published MD5 was **not** recomputed. The [run guide](ORGANOID_PHENOTYPE.md) states the protocol and limits. Source transfer may take longer than computation and requires temporary scratch space.

To include the Bhaduri author-label sensitivity check in the same source-to-report run, use `python organoid_phenotype.py --author-label-sensitivity`. It reads only needed metadata byte ranges of the separate CC BY cleaned archive, verifies that all **223,453** Bhaduri HNOCA row keys match the scoring archive in order, and adds `author_label_sensitivity.json` with class totals, per-key confusion matrices, fixed comparators, and 2,000-draw key intervals. The ordinary command above remains the shorter primary run.

## Fixed-budget review results and reproduction

The selected Bhaduri queue ranked 34 HNOCA-selected sample keys without consulting their labels during ranking. Its top eight had 1.721 times the equal-key mean later disagreement rate. This selected-cohort result did **not** transfer to all Bhaduri rows: after rescoring all 223,453 cells, a 20% whole-key cap reviewed 44,543 cells, exposed **6,881/22,721** later findings, and missed **15,840**. A random key order found at least as many in **19.33%** of 10,000 draws. The [five-contract map and fixed-budget outputs](review_reference/) preserve the changed row and endpoint definitions; run `python review_contract_map.py` and `python fixed_budget.py` to regenerate them from the included small source summaries.

The third publication was selected *before model outcomes* by a fixed HNOCA metadata rule: exclude Velasco and Bhaduri, require 10,000–250,000 selected three-class rows, at least 100 per class, five sample keys, and no key overlap with training; choose the largest eligible publication. This chose **Uzquiano 2022** with 236,453 selected cells and 47 keys. The unchanged Velasco-trained model reached **0.937418 macro-F1** (whole-key interval **0.918595–0.952664**), versus **0.815074** for source-trained nearest centroid; the paired difference was **+0.122344** (interval **+0.099082 to +0.147403**).

On those selected three classes, a separately frozen score-margin queue reviewed 47,228 cells under a 47,290-cell cap, exposed **2,989/7,282** HNOCA disagreements, and missed **4,293**. None of 10,000 random whole-key orders reached its count; a source-trained centroid-distance order exposed 1,759 while reviewing 47,048 cells. A later predeclared replay removed the three-class row filter from the **same Uzquiano publication**, admitting all 263,827 cells. Its 52,765-cell cap let the margin queue review 51,993 cells and expose **17,046/34,656** later findings, including 14,442 outside the three-class endpoint, while missing **17,610**. Only three of 10,000 random whole-key orders reached its total (**0.03% high tail**); centroid distance exposed 9,181 findings while reviewing 51,954 cells. The margin queue found 7,865 more while reviewing 39 more cells. The frozen all-row gates required a random total high tail below 5%, more total findings than distance, and more outside-endpoint findings than the random median; all passed.

These are retrospective disagreements against HNOCA's harmonized labels. HNOCA metadata and class labels helped choose the publication; the same labels define later findings. The full-row result is not an independent cohort relative to the selected-row result, an expert-confirmed error count, a prospective trial, or measured researcher time. The Bhaduri all-row failure remains visible. The metadata gate in `review_contract_gate.py` rejects declared changes to publication, eligibility, score, group, label scheme, or endpoint; matching fields do not prove useful ranking, and the current gate does not verify actual row membership. The real organ-on-chip image audit below is a separate experiment.

The code and [small reference JSON files](review_reference/) let readers inspect each key and rebuild the counts. Use a free Linux CPU with Internet access and the attributed [HNOCA v1 archive](https://zenodo.org/records/15004818). Each script checks its published 2,880,860,613-byte size and MD5; to avoid repeated downloads, pass one verified local file to all three runs in this order:

```sh
python f32_third_source.py --input hnoca_minimal_for_mapping.h5ad
python f36_third_review.py --input hnoca_minimal_for_mapping.h5ad --f32-reference f32_third_source/third_source.json
python f38_full_intake.py --input hnoca_minimal_for_mapping.h5ad --f32-reference f32_third_source/third_source.json
```

The later scripts assert the selected publication, training-row identity, and all 47 selected-key confusion matrices against the first run. The [competition-linked Notebook](https://www.kaggle.com/code/loxigicck/neural-organoid-phenotype-audit-across-labs) embeds these scripts and the Bhaduri map on free CPU. The [technical report](technical_report.pdf) describes the protocol, data permissions and limitations. No raw atlas or chip-image files are redistributed here.

## Physical-chip readout audits

The [competition-linked chip Notebook](https://www.kaggle.com/code/loxigicck/chip-decision-contract-map) runs both analyses on free Kaggle CPU. It downloads and checks the original files, prints aggregate numbers, and does not publish 22 patient-level measurements or clinical labels.

**Schedule Decision Horizon** uses [Schuster et al.'s Figure 5a-b source workbook](https://www.nature.com/articles/s41467-020-19058-4#Sec25). Run `python schedule_horizon.py --source original-source.xlsx --out schedule_horizon.json` after installing `requirements-schedule.txt`; the script verifies the original workbook SHA256 and writes a 48-row CSV beside the JSON. There are **8/48** sign reversals between 24 and 72 hours and **13/48** retrospective stability horizons later than 24 hours. The three-patient leave-one-out forecast loses to 24-hour persistence (MAE **0.407105** versus **0.152629**). The horizon uses future data, so it cannot authorize an early stop or treatment decision. The original article is CC BY 4.0 and developed the chip and drug schedules.

**Clinical Holdout Contract** uses [Dai et al.'s published Figure 5 source files](https://doi.org/10.1016/j.xcrm.2026.102873). Install `requirements-chip.txt` and run `python chip_clinic.py`; it fetches the source ZIP and Figure 5 image from PMC, verifies both SHA256 hashes, averages three technical replicates per patient, and prints aggregate patient-held-out classifications. The predeclared optimized vessel/tumoroid mean classifies **17/22** clinical responses, compared with **15/22** for the original-chip mean and **11/22** for an all-resistant rule. The optimized vessel-only channel classifies **21/22** versus **17/22** for original vessel, while optimized tumoroid classifies **19/22**. Vessel-only was selected after examining six readouts; it is an exploratory candidate for a separately registered patient cohort. The original authors built the chips, measured outcomes, and reported optimized **86.36%** same-cohort concordance. Our cutoff audit leaves each patient out of threshold selection; it is still retrospective and single-study. Their article files are CC BY-NC-ND 4.0. This MIT repository contains only our source code and aggregate conclusions, never the original image, workbook, or patient-level clinical table.

**Assay Discordance Contract** runs with `python assay_discordance.py` after installing `requirements-chip.txt`. On the Dai data it chooses among six readouts *inside* each outer patient's other 21 training patients, then fits the training-only threshold. It classifies **20/22**, with the optimized vessel channel selected in 21 folds and the optimized tumoroid channel in one. The procedure was designed after examining the six A9 results; the outer fold protects each individual prediction from direct selection on its own label, but does not make the overall algorithm an independent validation. On [Steinberg et al.'s CC BY 4.0 source workbook](https://doi.org/10.1038/s42003-023-05531-5), it pairs viability and area reduction for each patient and tested drug. Strictly opposite signs occur in **14/49** complete pairs. Area-only screening would miss **12/40** pairs with reduced viability. The article's caption reports n=48; the source workbook contains 49 complete paired cells. We report the workbook denominator and expose this difference. These rows have no unambiguous chip-perfusion flag or exact matching clinical-treatment endpoint, so the script does not report clinical accuracy for this source. The program downloads and checks both articles' source hashes at runtime, prints aggregate results, and keeps patient-level rows local unless `--out` is requested. No raw source workbook is redistributed.

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

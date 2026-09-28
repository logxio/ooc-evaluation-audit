---
title: "Decision Contract Map"
subtitle: "Cell review, drug-schedule stability, and patient-held-out chip response"
author: "Yan Su"
date: "28 September 2026"
lang: en-US
documentclass: article
fontsize: 12pt
geometry: margin=0.92in
linestretch: 1.25
colorlinks: true
linkcolor: black
urlcolor: blue
toc: false
numbersections: true
header-includes:
  - \setcounter{tocdepth}{1}
  - \usepackage{booktabs}
  - \usepackage{longtable}
  - \usepackage{array}
  - \usepackage{microtype}
  - \usepackage{fancyhdr}
  - \pagestyle{fancy}
  - \fancyhf{}
  - \fancyhead[L]{Decision Contract Map}
  - \fancyhead[R]{Yan Su}
  - \fancyfoot[C]{\thepage}
---

**Submission category: Tool & Platform**  
**Team: Yan Su (individual entrant)**

**Measured result:** Review Contract Map records eligible rows, a score-only sample-key order, later label-defined findings, and what the review budget misses. A fixed Velasco-trained model reached **0.9078 macro-F1** on **207,871 Bhaduri cells** and **0.9374** on **236,453 selected Uzquiano cells**. In a separately frozen complete-intake replay of **263,827 Uzquiano cells**, the margin queue reviewed 51,993 cells and exposed **17,046/34,656** retrospective findings, leaving **17,610**. This remains a same-atlas label comparison, not independently adjudicated biology or measured staff time.

**Physical chip results:** In the published Schuster et al. pancreatic tumor-organoid chip data, 8/48 temporal-versus-static drug-response contrasts reverse sign between 24 and 72 hours; a leave-one-patient-out forecast loses to carrying the 24-hour reading forward (MAE 0.4071 versus 0.1526). In separate Dai et al. colorectal patient-derived chip data, the prespecified mean of two optimized assay channels classifies 17/22 clinical responses in a patient-held-out threshold audit. An exploratory optimized vessel-only channel classifies 21/22; that channel was selected after examining six readouts. These are retrospective reanalyses of the authors' data, not new chips or clinical deployment.

**Decision boundary:** Bhaduri's unfiltered sample-key order did not establish stable enrichment under a fixed 20% cell budget. On the separately acquired Uzquiano publication, a predeclared selected-cohort replay exposed 2,989/7,282 HNOCA disagreements, and the complete-intake replay exposed 17,046/34,656 later findings at the same proportional budget. The publication was selected using HNOCA metadata and class labels, and those labels define the findings. Results across these intakes are not interchangeable; a matching metadata contract alone cannot certify review yield.

\newpage
\tableofcontents
\newpage

# Abstract

A Phenotype Transfer Map measures a cell-type model across acquisition sources, orders atlas-selected sample keys by model-score uncertainty for review, and separately audits errors where reference labels exist. We trained on 135,053 cells from Velasco et al. and evaluated once on all 207,871 selected cells from Bhaduri et al. in the public Human Neural Organoid Cell Atlas (HNOCA) [9-12]. The held-out-study macro-F1 was **0.907831**; a 2,000-draw bootstrap over 34 `bio_sample` keys gave a 95% interval of **0.842324-0.937195**. A source-trained nearest-centroid comparator scored 0.806783 on the same cells. The paired macro-F1 difference was +0.101048, with a sample-key interval of +0.070494 to +0.120536. Glioblast precision was only 0.679004: 1,353 cells of other classes were flagged as Glioblast. The usable action is to prioritize sample-level annotation review, not to treat predicted proportions as a new biological ground truth.

In a subsequent exploratory analysis, a queue based only on classifier decision-score margins ranked all 34 Bhaduri sample keys without using their HNOCA labels in the ranking calculation. Mean score uncertainty and observed key error rate had equal-key Spearman correlation **0.779068**, with a 2,000-draw key-resampling interval **0.554570-0.901040**. The eight most uncertain keys had **1.720951 times** the all-key mean error rate. After seeing this ratio, we kept those eight ranks fixed and shuffled the 34 observed group error rates 10,000 times; zero shuffles reached the observed ratio (one-sided plus-one **p=0.00009999**). HNOCA labels selected the three-class cohort before ranking, and the utility check reused the same Bhaduri source and labels; it has not been tested prospectively on a wholly unannotated batch.

A secondary annotation-source check matched Bhaduri's preserved original labels to these cells. On 175,160 unambiguous Neuron/Radial Glia cells, binary macro-F1 was 0.941193 (34-key interval 0.922403-0.956609), but the fixed nearest-centroid comparator scored 0.947220; the paired model-minus-comparator interval was -0.010067 to -0.002531. This result does not add model superiority. It shows that the preferred model changes when the annotation source and endpoint change, and it is not a new laboratory or independently blind label set.

The two experiments were collected in different laboratories, but HNOCA chose its 3,000-gene panel across studies and assigned harmonized labels. This is a **cross-acquisition-source test conditional on a shared panel and annotation**, not a blind independent-label validation, donor-level replication, drug-response measure, or clinical result. These are neural **organoids**, not perfused organ-on-chip cultures; the score does not validate cell typing in a chip. Source-internal random-cell and held-`bio_sample` validation scored 0.953046 and 0.955731 on different validation rows. Their differences from the cross-study score describe protocol changes and do not isolate the cause of a performance gap.

The same evaluation discipline is illustrated on 3,072 expert-labeled organ-on-chip brightfield images [1, 2]. The source ZIP has 57 of 57 date-like test prefixes also present in training. A frozen image model scored 0.799925 balanced accuracy on its 656-image source test and 0.657920 on a different 736-image prefix-held-out test. On the 151 shared images, the paired difference was +0.066088 with a 14-prefix interval of -0.042091 to +0.122483. That interval crosses zero; the prefixes are not verified physical chip IDs. These two cases show the same practical rule: publish source and group denominators, false alarms, comparable test rows, and uncertainty beside the headline score. The workflow uses public data and free CPU computation, without a paid API or proprietary model.

Two further physical-chip reanalyses test what a readout can support. In Schuster et al. 17, 8/48 patient-by-regimen-by-comparator-by-marker contrasts change temporal-versus-static sign between 24 and 72 hours, while a three-patient leave-one-out forecast fails against a persistence baseline. In Dai et al. 18, 22 patient-derived colorectal chip responses have paired clinical outcomes. A threshold learned on the other 21 patients classifies 17/22 with the prespecified average of two optimized readouts, versus 15/22 with the original-chip average. An optimized vessel-only channel reaches 21/22, versus 17/22 in the original vessel channel, but this channel was chosen after outcomes were inspected. Both sources are single-study retrospective analyses; neither supports clinical treatment advice.

**Keywords:** neural organoid; single-cell phenotype; cross-study validation; organ-on-chip; patient holdout; review audit; reproducibility.

# Review Contract Map: fixed-budget review evidence

## A decision record, not a new cell classifier

Each contract fixes four items before counting findings: eligible rows, the sample-key order computed only from model scores, the later reference-label endpoint, and a whole-key cell budget. The downstream action is to inspect the chosen keys and retain the explicit missed-finding count; a changed intake or endpoint requires a new test. The underlying classifier, nearest-centroid comparator, HNOCA panel, and harmonized labels are existing methods and data. The margin score `1/(1 + gap between the top two decision scores)` is an ordering signal, **not** a calibrated probability of error. `bio_sample` is an atlas key, not a proven physical organoid, donor, or chip.

Five Bhaduri contracts use the same 34 keys but change retained rows, the later endpoint, or the score order. Their first-eight equal-key error-rate ratios were 1.721 in the HNOCA-selected three-class cohort, 1.860 under retained original-author binary labels, 1.441 when carrying that selected queue into all rows, 0.819 after rescoring all rows, and 0.840 after a combined score. These are descriptive contrasts on reused data. Under a **floor(all eligible cells / 5)** cap, complete keys are accepted in order when they fit and oversized keys are skipped. On Bhaduri all-row rescoring, 44,543 of 223,453 cells were reviewed; 6,881 of 22,721 later findings were exposed and **15,840 missed**. A 10,000-order random whole-key reference reached at least 6,881 findings in 19.33% of orders. The selected-cohort result did **not** rescue complete intake on Bhaduri. The five-row map, per-key output, fixed-budget replay, and source summaries can be recomputed with `python review_contract_map.py` and `python fixed_budget.py`; see `review_reference/` in the public code repository.

## Frozen third-publication test and review queues

A metadata rule excluded Velasco and Bhaduri, required 10,000-250,000 HNOCA-selected NPC/Neuron/Glioblast rows, at least 100 cells in each class, at least five `bio_sample` keys, and no key overlap with Velasco. It selected the largest eligible publication before model fitting or inspection of candidate outcomes: **Uzquiano 2022**, with 236,453 selected cells and 47 keys. The unchanged Velasco model trained on 135,053 selected cells reached macro-F1 **0.937418** on this publication (2,000-draw whole-key interval **0.918595-0.952664**). Source-trained nearest centroid reached **0.815074**; the paired difference was **+0.122344** (47-key interval **+0.099082 to +0.147403**). This tests another acquisition publication under the same HNOCA 3,000-gene panel and harmonized labels, not independent biological truth.

The selected-cohort review replay used the same model and 20% whole-key budget, then inspected HNOCA disagreements only after computing the score-only order. Of 47,290 allowable cells, the margin order reviewed **47,228** across ten keys and exposed **2,989/7,282** disagreements; **4,293** remained. None of 10,000 seeded random whole-key orders reached 2,989 (plus-one estimate 0.00010); their 95% descriptive finding range was 784-2,153. A source-trained nearest-centroid distance order reviewed 47,048 cells and exposed 1,759. The margin queue found 1,230 more while reviewing 180 more cells. These counts are retrospective label disagreements, not expert-confirmed errors.

A separate, preregistered replay admitted **all 263,827 Uzquiano rows** without a three-class row filter. Its later finding endpoint was either an HNOCA label outside the three classes or a within-class prediction disagreement. There were 27,374 endpoint-outside cells and 7,282 within-class disagreements, hence **34,656** later findings. The 20% cap was 52,765 cells. The margin queue admitted seven full keys and reviewed **51,993** cells, exposing **17,046** findings (14,442 outside endpoint and 2,604 within class) while missing **17,610**. Ten thousand seeded random whole-key orders had a 95% total-finding range of 3,095-13,100; three reached at least 17,046 (0.03% high tail). The random outside-endpoint median was 4,464.5, versus 14,442 observed (0.10% high tail). The nearest-centroid distance order reviewed 51,954 cells and exposed 9,181 findings, 7,534 of them outside endpoint. Margin found **7,865** more items while reviewing **39** more cells.

The three full-intake pass conditions were set before that run: total-finding random high tail below 5%, more total findings than centroid distance, and more outside-endpoint findings than the random median. All three passed. This is a **retrospective complete-intake replay within one atlas**. HNOCA metadata and selected-class counts chose the publication, and HNOCA labels define the later finding endpoint; it is not a fresh independent source relative to the selected-cohort replay, expert adjudication, prospective deployment, or measured labor saving. Bhaduri's complete-intake failure remains a direct counterexample to carrying this order across intakes. A metadata gate (`review_contract_gate.py`) rejects changed publication, eligibility, score, group, label scheme, or endpoint before reuse; matching declared metadata is necessary but does not prove effective selection, and the current gate does not inspect actual row membership.

## Reproduction and disclosure

The [HNOCA v1 archive](https://zenodo.org/records/15004818) supplies the original 2,880,860,613-byte file and published MD5 `078675d6108e93cebc99676b6b0626aa`; the free-CPU runs verified both. The public repository includes `f32_third_source.py`, `f36_third_review.py`, `f38_full_intake.py`, the existing `organoid_phenotype.py`, and small JSON references in `review_reference/`. Each third-source script downloads and verifies the same HNOCA archive when no `--input` is supplied. To avoid three downloads, pass the same verified local H5AD to all runs. Run in order: `python f32_third_source.py --input hnoca_minimal_for_mapping.h5ad`, then `python f36_third_review.py --input hnoca_minimal_for_mapping.h5ad --f32-reference f32_third_source/third_source.json`, then `python f38_full_intake.py --input hnoca_minimal_for_mapping.h5ad --f32-reference f32_third_source/third_source.json`. The later scripts assert the frozen publication selection, training row identity, and 47 selected-key confusion matrices against the first output. Their outputs contain the complete per-key scores, choices, random reference, found and missed counts. Our source code is MIT licensed; the derived summary JSON retains attribution to HNOCA under its CC BY 4.0 data record, and the original data remain at that source. No paid service, proprietary model or special hardware is needed; our completed runs used free Kaggle CPU. Each full-source run exceeds the five-minute local development budget and belongs on a remote free CPU.

The additional real organ-on-chip image case remains a separate task: on 38 post hoc chosen images from one date-like prefix, the source-folder and prefix-held-out image models falsely flagged 3 versus 9 of 13 expert-good images and missed 4 versus 0 of 25 expert-bad images. This selected example illustrates both review costs; it does not validate the organoid cell queue, identify a physical chip, or establish a population effect.

# Research problem and intended use

## Two decisions at the bench

A neural-organoid team may want to check NPC, Neuron, and Glioblast cell-type calls across studies. Within an atlas-selected cohort, a model trained on another study can rank sample keys for annotation review, but a high aggregate score can conceal rare-class false positives or a few dominant samples. The evaluation must therefore show each class's errors, the full source split, and uncertainty over sample keys. We do not use model output to replace marker-gene review or the study's original annotation process; a wholly unannotated batch needs a separate end-to-end test.

An organ-on-chip imaging team may train a classifier to send low-quality brightfield images for manual review. Before using that model, the team needs to know whether held-out images truly come from acquisition contexts absent from training. It also needs the number of good cultures that would be incorrectly flagged. A single balanced-accuracy value hides both questions.

The Phenotype Transfer Map answers the organoid decision with three explicitly different measurements: source-held-out macro-F1 and sample-key interval, model-score review order within the atlas-selected three-class cohort, and a retrospective known-label error audit. A single aggregate test score does not show that Glioblast precision is 0.679004 or that the highest-scored review keys have 1.721 times the equal-key mean error rate. The map is exploratory evidence for review order, not proof of benefit on wholly unannotated future batches.

The nearest existing work is the source [HNOCA atlas and its tools](https://www.nature.com/articles/s41586-024-08172-8) [9]: its [AtlasMapper](https://devsystemslab.github.io/HNOCA-tools/api/mapping/AtlasMapper/) already maps query cells, transfers labels, and computes presence scores with a grouping option. Khatri and Bonn previously studied calibrated uncertainty for single-cell label transfer [15]. This report does not claim a new label-transfer algorithm, atlas, or generic uncertainty estimator; our margin score is not calibrated as an error probability. Its contribution is a reproducible **decision record** on one whole-study holdout: the fixed predictor's group-resampled transfer result, score-prioritized review lift, and known-label false positives are tied to the same 34 sample keys. Whether that record improves review decisions on an independently labeled, wholly new cohort remains untested.

A separate organ-on-chip image audit answers the imaging decision. Its inputs are one record per image from each evaluation: a stable image ID, a group identifier, the reference good/bad label, the split assignment, and a test prediction. The group might be a physical chip, an experiment, an imaging session, or a weaker proxy. The scientist must identify which it is from the source data. The tool computes what the records support and labels the comparison's evidence level. It does not infer a physical chip ID from a filename.

Our worked example uses the public image-quality dataset. In it, the first six digits of each image ID resemble a date. We use that prefix to ask whether the source folder split reuses acquisition context across training and test. The prefix is not a verified chip identifier. Accordingly, the user-facing report says "acquisition-context overlap," not "chip leakage."

## Why this is an AI-for-life-science problem

The useful unit of generalization depends on how the life-science data were collected. Many cells from the same biological sample are not independent laboratories; many images from the same imaging context are not independent future acquisitions. The organoid case has independently collected expression experiments but a shared atlas panel and annotation. The image case has expert quality labels and real brightfield images but no verified physical chip IDs. Reporting those distinctions helps a researcher decide what to check next. Neither dataset supplies toxicity outcomes, neural connectivity labels, or drug-response ground truth; none is claimed here.

The prior classification study using this same source data reports a single image-level split and identifies stability across splits as future work [3]. Our contribution is a different question: expose grouping assumptions, test-set composition, and same-image prediction changes using a reusable record contract. We neither reproduce its InceptionV3 model nor claim superiority over it.

# Data, provenance, and permission

## Source material

The [HNOCA v1 archive](https://zenodo.org/records/15004818) [9, 10] supplies `hnoca_minimal_for_mapping.h5ad`, a 2,880,860,613-byte file whose published MD5 is `078675d6108e93cebc99676b6b0626aa`. A clean free Kaggle CPU run downloaded the entire file and recomputed that MD5. It contains a 1,770,578-by-3,000 sparse count-like expression matrix, harmonized `annot_level_1` labels, publication names, and `bio_sample` keys. We select Velasco 2019 [11] as development and Bhaduri 2020 [12] as a whole-study test. The selected three classes contain 135,053 and 207,871 cells respectively. Their 21 and 34 complete `bio_sample` keys do not overlap. Some composite Bhaduri keys contain the text “Velasco, 2019”; source assignment uses the separate `publication` field, never a name parsed from the key. These keys are not established physical organoid or donor identities. HNOCA's global highly variable gene choice and harmonized annotation used information from the studies represented in the atlas, including the held-out acquisition source. We do not use its cross-study scPoli model weights or embedding.

For a separate annotation-source sensitivity test, the [official HNOCA cleaned archive](https://zenodo.org/records/14161275) holds the same Bhaduri cells and preserves `cell_type_original`; Zenodo lists this 18,740,061,388-byte archive as CC BY 4.0 with published MD5 `409a14a9772e6488c90cda7900b474ef`. We did **not** download or independently hash the whole cleaned archive: HTTP Range requests retrieved only needed metadata. All 223,453 Bhaduri HNOCA row keys were unique and identical in order between the cleaned and 3,000-gene archives (ordered SHA-256 `77a0ff74a31468084253534e0244d3368b706e0bcb3514d067f821f74d5986ee`). [HNOCA's curation code](https://github.com/theislab/neural_organoid_atlas/blob/2d4d16c7cfd0c900d64f5a3f56496d2e2c25c5f8/Fig1_HNOCA_establishment/01_curate_atlas.ipynb) preserved original observation fields; the [Bhaduri sfaira loader](https://github.com/theislab/sfaira/blob/55bcbbf2588a08e4a98b1e65324119407ec6e75c/sfaira/data/dataloaders/loaders/d10_1038_s41586_020_1962_0/homosapiens_x_2020_10x3v2_bhaduri_001.py) constructs `celltype` from the original paper's supplementary `Type` and `Subtype` columns. These are a second annotation source for the **same** Bhaduri acquisition, not a fresh laboratory or independently blind gold standard.

The [Organ-on-a-Chip Image Dataset](https://zenodo.org/records/10203721) [1] contains 3,072 PNG images, a spreadsheet of experimental metadata and expert image-quality labels, and original train/validation/test folders. The accompanying data descriptor explains image capture, cultures, and expert labeling [2]. The original table's quality code is 1 for good and 2 for bad, as checked against the source ZIP folders. We map good to 0 and bad to 1 in the audit records. Six cell types occur in the table. No patient-level or private clinical data are used.

The spreadsheet is 119,712 bytes and is checked by SHA-256 before parsing. The image ZIP is 6,710,767,405 bytes; its downloaded content matched the Zenodo MD5 `8f7e058996203d48eb03b2d86c0a2e4d`. Extracted image IDs are checked one-to-one against the 3,072 table rows. The source split is read from the ZIP64 central directory via range requests, then every mapped ID, folder label, and cell type is reconciled to the spreadsheet. The source directory mapping has 2,130 training, 286 validation, and 656 test images. The code stores raw images and derived feature records locally; the public code repository does not redistribute them.

## License boundary

HNOCA's minimal and cleaned archives have separate official Zenodo CC BY 4.0 records [9, 16]. The organ-on-chip image Zenodo record lists CC BY 4.0 for its files [1], while the associated descriptor refers to the image dataset as CC-BY-SA without a version [2]. We report both image statements. Neither raw dataset nor derived per-cell or per-image records are included in our code repository. Users obtain data from the attributed source. Our own code is MIT licensed. NumPy and SciPy use BSD-3-Clause, Pillow describes its license as MIT-CMU, scikit-learn and h5py use BSD-3-Clause, and Requests uses Apache-2.0 [4-8, 13, 14]. The source of each external component is listed in the references.

## Evaluation groups

For the alternative holdout, define `prefix = image_id[:6]`. To make the split reproducible without choosing groups based on their labels, compute `SHA256("26" + prefix)` as an integer, then take the remainder modulo 100. Buckets 0-19 are test, 20-29 validation, and 30-99 training. This yields 38/6/15 prefixes and 2,084/252/736 images respectively. The grouped test has 376 good and 360 bad images. The original source test has 365 good and 291 bad. All 57 date-like prefixes in the source test also occur in its training data; none of the 15 grouped-test prefixes occurs in the grouped training data.

These group counts refer to filename prefixes. They are evidence of overlap in that observed identifier. They do not count independently known physical chips, and they cannot establish whether different prefixes belong to the same chip.

# Audit design

## Record contract and validation

The reusable audit takes two JSONL files. Each line has `id`, `group`, `label`, `split`, and `prediction`; an optional `subgroup` can carry a cell type. Labels are 0 for good and 1 for bad. Predictions are 0 or 1 on test images and null on training and validation images. Each evaluation must contain one record per ID. The program rejects duplicate IDs, missing groups, invalid labels or splits, predictions on non-test rows, and conflicting labels or groups for a shared ID. It does not invent a class score when only one class is present.

For each evaluation, it counts images by split and label, computes the test confusion matrix, balanced accuracy, recalls, and good-image false-positive rate, then counts test groups also seen in training. It intersects the two test sets by exact image ID and recomputes the same measures on the shared images. A four-cell transition table records whether both models were right, only the first was right, only the second was right, or both were wrong.

Balanced accuracy is the arithmetic mean of good and bad recall. With confusion matrix rows as true good/bad and columns as predicted good/bad, write the cells as `[[GG, GB], [BG, BB]]`. Then good recall is `GG/(GG+GB)`, bad recall is `BB/(BG+BB)`, and the good-image false-positive rate is `GB/(GG+GB)`. A missing class makes balanced accuracy undefined rather than zero.

## Paired uncertainty calculation

On the shared test images, we resample observed prefix groups with replacement, using the **same chosen groups** for both models. Each replicate recomputes balanced accuracy on each model's predictions and stores the source-minus-grouped difference. We take the 2.5th and 97.5th percentiles of 2,000 valid replicates with seed 26. There are 14 prefixes in the shared set. This is an approximate descriptive interval for this dataset and this observed grouping, not a confidence guarantee across physical chips or new laboratories.

## Evidence categories

The HTML and JSON distinguish three claims. Group overlap is directly observable for the supplied group IDs. The full-test score difference compares different images and is descriptive. The shared-test comparison holds test image IDs fixed, but the two fitted models still use different training rows and different validation rows and thresholds. It therefore narrows one source of confounding without isolating the cause of the difference. All conclusions remain specific to one dataset.

# Cross-study neural-organoid phenotype audit

## Frozen question and sample accounting

Before model fitting, we fixed NPC, Neuron, and Glioblast as the primary classes. A four-class plan was stopped before training because the held-out Bhaduri Astrocyte label had 1,312 cells in only six `bio_sample` keys, with at least 100 cells in only four keys. **This choice inspected target-study label counts before training, so the endpoint definition was not blind to the target study.** The three-class training set contains 22,587 NPC, 94,395 Neuron, and 18,071 Glioblast cells from Velasco (135,053 cells, 21 keys). The whole Bhaduri test contains 110,067 NPC, 94,733 Neuron, and 3,071 Glioblast cells (207,871 cells, 34 keys). NPC and Neuron occur in all 34 test keys; Glioblast occurs in 20, with at least 100 cells in eight. Astrocyte remains descriptive and is not silently included in the reported three-class score.

We fixed the main decision before the full run: a whole-study test macro-F1 above 0.45, and a paired `bio_sample` bootstrap interval for the main-minus-best-prespecified-comparator difference entirely above zero, would justify presenting the model as a review aid. This does not set a biological deployment threshold. The preregistered point prediction for whole-study macro-F1 was 0.55-0.83; the observed 0.907831 exceeded that range. The source-internal random and grouped validation predictions were also lower than the observed scores; none was rewritten to fit the result.

## Count transform, model, and comparison

We extract the same 3,000 HNOCA genes for selected cells. For each cell, we divide its panel counts by that cell's panel total, multiply by 10,000, then apply `log1p` to nonzero values. This fixed operation does not fit on the test rows, although the **choice of the panel itself was made by HNOCA across studies**. We fit `SGDClassifier` with log loss, L2 penalty, `alpha=1e-4`, 30 maximum iterations, tolerance `1e-3`, balanced class weights, averaged coefficients, one fitting thread, and seed 26. No Bhaduri labels enter the transform definition, weight fitting, threshold selection, or hyperparameter choice. The full model is trained on all Velasco cells and evaluated once on all selected Bhaduri cells.

As source-internal diagnostics, we fit the same specification separately after a seed-26 stratified 20% cell holdout and a seed-26 `bio_sample` holdout of about 20% of keys. The random split trains on 108,042 cells and validates on 27,011; all 21 source keys appear on both sides. The grouped split trains on 96,022 cells in 16 keys and validates on 39,031 cells in five other keys. Because groups have unequal sizes, 20% of keys does not mean 20% of cells. These are **three separately fitted models and three different test rows**. The score gaps are descriptive; they are not a causal leakage estimate.

We fixed two inexpensive external comparators: predict the most common Velasco class for every Bhaduri cell, and assign each transformed Bhaduri cell to the highest-cosine-similarity Velasco class centroid. The centroids use only Velasco rows. We report the larger comparator macro-F1, but this choice uses external test scores and its paired interval is conditional on that selection. No comparator was added or retuned after seeing Bhaduri outcomes.

For uncertainty, we compute a 3-by-3 confusion matrix for each of the 34 Bhaduri `bio_sample` keys. In each of 2,000 seed-26 draws, we sample 34 keys with replacement and sum their entire matrices, recompute three-class macro-F1, and take the 2.5th and 97.5th percentiles. The same sampled keys are used for the main model and selected comparator, so their difference is paired at the sample-key level. All 2,000 draws retained all three true classes. This interval expresses variation over observed keys under this resampling scheme, not over independently established donors or physical organoids.

## Measured external result and failure cases

| Evaluation | Test cells / keys | Macro-F1 | Interpretation |
|:--|--:|--:|:--|
| Velasco random cell holdout | 27,011 / 21 overlapping | 0.953046 | Source-internal diagnostic |
| Velasco held `bio_sample` keys | 39,031 / 5 disjoint | 0.955731 | Source-internal diagnostic |
| Bhaduri whole-study test | 207,871 / 34 | **0.907831** | Cross-acquisition-source test with a shared atlas panel and labels |
| Velasco majority class on Bhaduri | 207,871 / 34 | 0.208706 | Fixed comparator |
| Velasco nearest centroid on Bhaduri | 207,871 / 34 | **0.806783** | Best of the two prespecified comparators |

The Bhaduri macro-F1 95% sample-key interval is **0.842324-0.937195**. The main model exceeds the nearest-centroid comparator by **+0.101048** on exactly the same cells, with a paired sample-key interval of **+0.070494 to +0.120536**. Both prespecified screens passed. The grouped source validation score exceeds the whole-study score by 0.047900, while random source validation is 0.002685 *lower* than grouped validation. Thus this dataset does not show a monotone random-split inflation story. Different test compositions, training sets, and shared atlas preprocessing prevent attributing any one gap to sample overlap.

| True class / predicted class | NPC | Neuron | Glioblast |
|:--|--:|--:|--:|
| NPC (110,067) | 106,403 | 2,370 | 1,294 |
| Neuron (94,733) | 3,207 | 91,467 | 59 |
| Glioblast (3,071) | 159 | 50 | 2,862 |

NPC, Neuron, and Glioblast F1 scores are 0.968022, 0.969855, and 0.785616. Here **Glioblast is HNOCA's neural progenitor cell-type label**, not a glioblastoma diagnosis. Glioblast recall is 0.931944, but precision is **0.679004**: 209 true Glioblast cells are missed, while **1,353** NPC/Neuron cells are incorrectly flagged. Of 4,215 predicted Glioblast cells, about 32.1% are false positives. One Bhaduri key with 3,030 selected cells has eight consensus-labeled Glioblast cells but 96 model calls. A researcher can place that sample ahead of lower-disagreement samples for marker-gene and annotation review. The prediction alone cannot establish that those 88 extra calls are truly of the annotated cell type. No test key was removed after inspection, and the output retains every key's denominators and matrix.

## Score-only ordering within an atlas-selected cohort

The error audit above uses known HNOCA labels; it cannot rank an unannotated future sample by its observed mistakes. Before analyzing the saved decision scores, we registered a separate ranking: for each cell, take the highest minus second-highest of the three `SGDClassifier.decision_function` values, transform that nonnegative margin to `1/(1+margin)`, then average these values within each `bio_sample` key. The rank uses model scores and keys only. The transform is monotone and is **not** a calibrated probability of being wrong.

For a retrospective check, we compare that ranking with each key's observed error fraction against HNOCA labels. We give the 34 keys equal weight, compute Spearman rank correlation, and resample keys with replacement for 2,000 seed-26 draws to form a percentile interval. Before reading this result, our working prediction was correlation 0.2-0.6, with a continuation gate of correlation at least 0.35, interval lower bound above zero, and the top eight uncertainty keys having at least 1.3 times the all-key mean error rate. The observed correlation was **0.779068**, interval **0.554570-0.901040**; the top-eight ratio was **1.720951**. All three exploratory gates passed. The prediction interval itself was exceeded, and it was not rewritten after observation.

After observing the top-eight ratio, we separately registered a conditional rate-shuffle check before running it. We hold the score-based top-eight selection fixed and randomly permute the **34 observed group error rates** with seed 26 for 10,000 draws; each draw compares the top-eight equal-key mean rate against the same all-key equal-weight denominator. Zero shuffles reached the observed 1.720951 ratio, giving a one-sided, plus-one Monte Carlo p of **1/10,001 = 0.00009999**. This checks association against random reassignment of these observed rates to these ranks. Because we chose the queue and inspected its ratio first, the p-value is post hoc and does not correct for that choice, group-size differences, shared atlas labels, or future cohorts.

This check reused the already analyzed Bhaduri source. The cells entering its three-class cohort were selected by their HNOCA labels; only the subsequent score-based ordering is label-free. Its interval describes variation over those 34 keys under the stated resampling method; it is not an external confirmation that the queue will work for a wholly unannotated new laboratory, organoid, or label convention. We chose and inspected this one simple score-derived queue after seeing the classifier's main external result, so its apparent utility should be treated as exploratory. The 3,030-cell example above ranks sixth by its **known-label false-positive count** but 27th by the **score-only uncertainty rank**. The two lists answer different questions and are displayed separately; neither ranking should silently stand in for the other.

## Original-author annotation sensitivity: comparator reversal

After the harmonized-label analysis, we preregistered a secondary two-class endpoint using the Bhaduri paper's preserved original `Type` and `Subtype` labels. Within the already HNOCA-selected three-class test cohort, original labels beginning `Excitatory Neuron` or `Inhibitory Neuron` are Neuron; those beginning `Radial Glia` are the other class. Labels containing `Low quality`/`Low-Quality`, or belonging to Mixed, Unknown, Astrocyte, Endothelial, or another class, are excluded. This retains **175,160 of 207,871 cells** across all **34** Bhaduri `bio_sample` keys: **79,356 Neuron** and **95,804 Radial Glia**. We collapse the fixed model's Neuron prediction to positive and NPC/Glioblast to negative. No original-author label enters feature selection, training, classifier tuning, or the cohort selection; HNOCA's labels still selected that cohort.

On this distinct endpoint, the fixed model reached binary macro-F1 **0.941193**, with a seed-26, 2,000-draw whole-key bootstrap interval **0.922403–0.956609**. The prespecified source-trained nearest-centroid comparator reached **0.947220** on the same retained cells; the paired model-minus-centroid difference was **−0.006027** with interval **−0.010067 to −0.002531**. The Velasco source-majority comparator scored **0.311792**. Thus the model's 0.941 score cannot be offered as another superiority result: **the nearest-centroid ordering reverses** when the annotation source and class endpoint change. The model confusion matrix, with original-author Radial Glia/Neuron rows and predicted non-neuron/Neuron columns, is `[[89823,5981],[4247,75109]]`; nearest centroid is `[[91041,4763],[4404,74952]]`. `author_label_sensitivity.json` preserves all 34 paired group matrices, exclusions, interval inputs, and archive provenance.

This is a joint label-convention and two-class-endpoint sensitivity check on the same Bhaduri acquisition, not a second acquisition-source test, fully unselected batch, or independently blind label set. It does not isolate whether the author-label convention, the class collapse, or their interaction causes the comparator reversal. HNOCA curation may have inspected the original-study annotations. The continuation gate for a new model-advantage result required a positive paired interval against nearest centroid; it did not pass. We retain the reversal because a single harmonized-label macro-F1 would otherwise hide that model choice depends on the evaluation endpoint.

The three full Velasco fits emitted scikit-learn's maximum-iteration `ConvergenceWarning`; we did not raise the iteration limit after viewing the test. Numerical stability under longer or alternative optimization remains to be measured. The model's linear decision values are not calibrated probabilities. HNOCA's unified annotation, cross-study gene selection, and the low number of keys with large Glioblast counts are material limits even though the prespecified score screen passed. Bhaduri's original-study labels are now matched to these cells, but they are from the **same acquisition** and were available to the atlas curation process; they are not an independently blind reference. This result supports **annotation review prioritization under the HNOCA label convention**, not clinical classification, drug toxicity, neural function, or an unbiased estimate of biological composition.

# Image features and frozen model protocol

## Low-cost image representation

Each source PNG is converted to grayscale and bilinearly resized to 128 by 96 pixels. The 29-dimensional feature vector contains five intensity percentiles, mean, standard deviation, Laplacian variance, mean horizontal and vertical absolute differences, a thresholded edge fraction, eight normalized histogram bins, four quadrant means, four quadrant standard deviations, and variation of row and column means. Every feature is finite-checked. This representation was selected as a low-cost baseline, not as a claim of state-of-the-art morphology recognition. Source images are only read to compute these local features; the report itself audits evaluation records.

## F1: initial baselines

F1 fits a deterministic L2-regularized logistic classifier on the grouped split. Metadata-only features are cell type, seeding density, time after seeding, day, and flow rate. Missing-value medians and scaling are estimated on training rows only. The image-only model uses the 29 grayscale features; training-only scaling and fitting are followed by a validation-only threshold chosen to maximize balanced accuracy, with fixed tie rules. The constant-good baseline is included to expose the 0.5 balanced-accuracy floor. F1's image test score was observed before we selected the F2 model, so later reuse of this test is adaptive.

## F2: one prespecified nonlinear comparison

After F1, we registered one random-forest comparison using the same 29 features and grouped split: 300 trees, `min_samples_leaf=8`, `max_features=sqrt`, `class_weight=balanced_subsample`, seed 26, and the remaining scikit-learn defaults. No new features are added. The threshold is selected using validation probabilities only. Candidate thresholds include distinct probabilities, adjacent midpoints, and 0, 0.5, and 1. The first selection tier requires bad recall at least 0.60 and good recall at least 0.55; within an eligible tier, maximize balanced accuracy, break ties by distance to 0.5, then by higher threshold. The grouped validation set selected 0.314465497255814 in the Linux reference; the earlier macOS run selected 0.31713680975737424.

The continuation gate, written before fitting F2, required test balanced accuracy at least 0.65, bad recall at least 0.60, **and** good-image false-positive rate at most 0.45. F2 passed the first two conditions and missed the third. We stopped optimizing automatic image rejection on this repeatedly viewed test.

## F3 and F4: split comparison without model search

F3 uses the same feature vector, forest configuration, and threshold rule, now with the original ZIP's train/validation/test folders. Its validation threshold is 0.503368900036556 in the Linux reference; the earlier macOS run selected 0.4984234764442013. F4 refits both frozen configurations and scores them on the intersection of their test image IDs. F4 changes no feature, model parameter, or threshold rule. The source and grouped full-test results were already seen when F4 was chosen; F4 is a diagnostic paired comparison, not a fresh blinded validation. A second dataset would be required to test transport beyond this source.

# Measured results

## F1 and F2 on prefix-group holdout

| Evaluation | Test good/bad | Balanced accuracy | Bad recall | Good images flagged bad |
|:--|--:|--:|--:|--:|
| Always good | 376/360 | 0.500000 | 0.000000 | 0/376 |
| Metadata logistic | 376/360 | 0.523345 | 0.472222 | 160/376 |
| F1 image logistic | 376/360 | 0.608836 | 0.802778 | 220/376 |
| F2 image forest | 376/360 | 0.657920 | 0.797222 | 181/376 |

Confusion matrices (true good/bad rows, predicted good/bad columns) are: always good `[[376,0],[360,0]]`; metadata `[[216,160],[190,170]]`; F1 image `[[156,220],[71,289]]`; and Linux F2 forest `[[195,181],[73,287]]`. The F2 validation set has 179 good and 73 bad images, matrix `[[99,80],[19,54]]`, and balanced accuracy 0.646399.

F1 improves balanced accuracy by 0.085491 over metadata, but falsely flags 58.51% of good test images. Linux F2 lowers that count to 181 and improves balanced accuracy by 0.049084, while its good-image false-positive rate remains 181/376 = 0.481383. This exceeds the prespecified 0.45 ceiling, so the automatic quality-gate direction was stopped. A 2,000-resample bootstrap over its 15 test prefixes gives an approximate balanced-accuracy interval of 0.575-0.730; these prefixes are not verified chips. F2 reused a test already viewed for F1 and cannot be called a fresh blind evaluation.

## Full tests under different splits

| Evaluation | Test good/bad | Balanced accuracy | Good recall | Bad recall | Good-image false positives |
|:--|--:|--:|--:|--:|--:|
| F3, source folders | 365/291 | 0.799925 | 0.843836 | 0.756014 | 57/365 |
| F2, prefix groups | 376/360 | 0.657920 | 0.518617 | 0.797222 | 181/376 |

The Linux source matrix is `[[308,57],[71,220]]`; the grouped matrix is `[[195,181],[73,287]]`. Source validation has 163 good and 123 bad images, matrix `[[135,28],[32,91]]`, and balanced accuracy 0.784029. A 2,000-resample bootstrap over source test prefixes gives an approximate balanced-accuracy interval of 0.744-0.848.

The source-folder test has 57/57 date-like prefixes also present in source training. The grouped test has 0/15 prefixes in grouped training. The Linux full-test balanced-accuracy gap is 0.142005. However, the tests differ in composition: 505 source-test images are absent from grouped test, and 585 grouped-test images are absent from source test. The two training sets, validation sets, and selected thresholds also differ. The gap is an audit signal, not a causal estimate of the cost of overlap.

## Same 151 images under both models

The test intersection has 68 good and 83 bad images from 14 date-like prefixes. It is smaller than either full test. The table below reuses those exact IDs on both sides.

| Model | Balanced accuracy | Good recall | Bad recall | Good-image false positives |
|:--|--:|--:|--:|--:|
| F3 source-split model | 0.756467 | 0.838235 | 0.674699 | 11/68 |
| F2 grouped-split model | 0.690379 | 0.573529 | 0.807229 | 29/68 |

The source model's shared-image matrix is `[[57,11],[27,56]]`; the grouped model's is `[[39,29],[16,67]]`. The paired balanced-accuracy difference is +0.066088. Both models are correct on 92 images; only the source model is correct on 21; only the grouped model is correct on 14; both are wrong on 24. A paired 14-prefix bootstrap gives an approximate 95% difference interval of -0.042091 to +0.122483 (2,000/2,000 valid draws). The prespecified strong-evidence gate required a difference of at least 0.08 and an interval lower bound above zero; neither condition passed. The interval does not establish a general direction of evaluation bias.

Holding test images fixed removes test-composition differences. It does not equalize the rows used to train the forests or the rows used to choose their thresholds. It also cannot turn a date-like prefix into a physical chip ID. The result is not evidence that the same chip was used for training and test.

## Cell-type boundaries

The grouped F2 full test includes A549 (151 good/81 bad), CACO (27/55), HPMEC (187/152), HSAEC (11/24), HUVEC (0/39), and NHBE (0/9). With no good images in the last two cell types, their good recall and balanced accuracy are undefined. The generated JSON retains each cell type's denominator and confusion matrix; no single cell-type result is promoted as a separate discovery.

# Physical-chip decision contracts

## Schedule Decision Horizon: later signs in a three-patient chip study

Schuster et al. 17 developed the programmable microfluidic pancreatic tumor-organoid platform, ran temporal and static drug schedules, and published Figure 5a-b source data. We add a retrospective readout contract. A contract unit is one patient, one of four combination therapies, one of two static comparators (4-hour or 72-hour exposure), and one marker (caspase 3/7 apoptosis or propidium-iodide death). Each arm's two to four technical replicate traces is normalized as `signal(t)/signal(0)-1`; normalized replicates are averaged before temporal delivery is compared with the corresponding static schedule. This yields **48 contrasts from three patients**, not 48 independent patients.

The temporal-minus-static effect changes sign between 24 and 72 hours in **8/48** contrasts: 7/24 death-marker contrasts and 1/24 apoptosis contrasts. A retrospective terminal-stability horizon, defined as the first four-hour sampled time after which every remaining contrast sign matches the 72-hour sign, occurs after 24 hours in **13/48**. A 24-hour difference between the two markers captures only four of eight matched pairs with a later reversal. The horizon uses the completed future trace and is not a prospective alert. One nearly zero contrast moves from +0.005 to -0.037, so a sign flip alone does not imply a large biological effect.

A frozen leave-one-patient-out trajectory template fits the other two patients' same-schedule traces at 0-24 hours and predicts the held-out patient's 72-hour temporal-minus-static effect. It obtains MAE **0.407105**, compared with **0.152629** for carrying the 24-hour effect forward and **0.267345** for 16-24-hour linear extrapolation. It loses to persistence in each held-out patient and predicts the final sign in **27/48** contrasts. Of five preregistered gates (48 complete pairs, at least ten flips, at least 20% error reduction, improvement in every patient, and at least 75% sign accuracy), only completeness passed. This negative forecast is part of the result. A scientist may inspect the full trace and both markers before interpreting an early schedule difference; these data cannot justify stopping a run or choosing a patient's treatment at 24 hours.

`schedule_horizon.py` verifies the original XLSX against a pinned SHA256 and writes the 48-row CSV and JSON in `review_reference/`. The original article and source workbook remain at the publisher; its article is CC BY 4.0. The script runs on CPU with `requirements-schedule.txt`. The authors' platform, schedules, and original endpoint comparison are prior work; the sampled sign-horizon ledger and failed holdout forecast are our reanalysis. Independent chip-lab or clinical validation is absent.

## Clinical Holdout Contract: 22 paired patient responses

Dai et al. 18 published patient-derived vascularized colorectal tumoroid chips exposed to FOLFOX plus bevacizumab. In the article's Figure 5 source workbook, sheet 5n contains vessel response and sheet 5o tumoroid response. Each sheet gives three original-chip and three optimized-chip measurements for each of **22 patient IDs**. Figure 5P's third colored row records clinical response: 11 sensitive (RECIST CR or PR) and 11 resistant (SD or PD). Its first two rows contain chip calls and are not clinical truth. We link the two source files by the same patient ordering and verify both SHA256 values before extraction. Because individual outcomes are only published in the figure, their transcription is a reproducibility limit.

The contract unit is a patient, chip condition, assay channel, other-patient-trained cutoff, and held-out clinical label. Three technical replicates are averaged per patient and channel. Lower relative vessel density or tumoroid size predicts sensitivity. Before effect calculation, we fixed the primary score as the simple mean of the two optimized channel means. For each patient, all adjacent midpoints among the other 21 patient scores compete on training balanced accuracy (the Youden index); the smallest threshold wins ties. We then classify the omitted patient once. The original-chip mean, each individual channel in both conditions, and an all-resistant fixed rule are comparators. Class recall, balanced accuracy, accuracy, and ranking AUROC are calculated on the 22 held-out calls or raw scores as appropriate; AUROC does not use the held-out thresholds.

| Patient-held-out readout | Correct /22 | Balanced accuracy | Sensitive recall | Resistant recall | AUROC |
|:--|--:|--:|--:|--:|--:|
| Optimized two-channel mean, prespecified | 17 | 0.772727 | 9/11 | 8/11 | 0.917355 |
| Original two-channel mean | 15 | 0.681818 | 9/11 | 6/11 | 0.776860 |
| Optimized vessel, exploratory | 21 | 0.954545 | 11/11 | 10/11 | 0.966942 |
| Original vessel | 17 | 0.772727 | 10/11 | 7/11 | 0.801653 |
| Optimized tumoroid | 19 | 0.863636 | 10/11 | 9/11 | 0.834711 |
| Original tumoroid | 17 | 0.772727 | 10/11 | 7/11 | 0.735537 |
| Fixed all-resistant | 11 | 0.500000 | 0/11 | 11/11 | 0.500000 |

The optimized vessel channel corrects four of the original vessel channel's errors and adds none; both miss resistant patient P36. Combining optimized vessel and tumoroid readouts by an unweighted mean loses four correct classifications relative to vessel alone, despite its high AUROC. **This is a channel-selection warning, not a validated 95% clinical predictor.** The vessel-only channel was chosen after inspecting six readouts in the same 22 patients. The source cohort, treatment, and assay were already published; our threshold audit remains single-lab and retrospective. The original authors' optimized 86.36% and original 72.73% accuracy used same-cohort selected cutoffs and their own rule, so they are context rather than independent holdout comparators. The authors' sensitivity treats resistance as positive; this table instead names each clinical class explicitly. No confidence claim of superiority, future-patient treatment decision, or cross-lab generalization follows from 22 patients.

`chip_clinic.py` downloads the original source ZIP and figure from the article's PMC mirror, verifies their SHA256 values, reads the two sheets and clinical color row, and prints aggregate metrics on CPU using `requirements-chip.txt`. It can write a patient-level audit JSON locally when `--out` is supplied. The article files are CC BY-NC-ND 4.0 and are linked, never copied into this repository. The MIT license covers our audit code only. An independently registered cohort should fix the vessel channel, threshold procedure, treatment, and clinical endpoint before data collection.

# Software artifact and real workflow

The offline workflow makes group identity and error denominators explicit in two biological settings. Its image-audit core reads two JSONL record sets, validates them, and writes `audit.html` and `audit.json`. The HTML summarizes overlap, test denominators and errors, the shared-image comparison, and interpretation limits. The JSON stores input records, counts, metadata, and input file hashes. The organoid route produces a whole-study three-class score, per-class and per-`bio_sample` matrices, comparator scores, and sample-key intervals from the HNOCA original. Both routes use local or free CPU computation and do not call a model API or upload research data to a service.

For the image case, the `ooc` command rebuilds test predictions from locally extracted image features and fixed model specifications. Before export, it checks fresh F2 and F3 results against the refitted models and checks F4's shared-image counts, confusion matrices, transitions, paired difference, and interval. On a prepared real feature cache, Linux ARM64 reproduced the independent Kaggle Linux x86-64 deterministic F2-F4 fields and exported the report with `status: verified`. This checks the image-reporting path; it is not a second biological dataset or a new external validation result.

A researcher with their own per-image predictions can bypass the example adapter. They supply source and grouped JSONL records, with group IDs that reflect their actual experimental provenance. The generic report then exposes group overlap and both test compositions. If the test sets have no shared IDs, it cannot compute a same-image contrast. If a test has only one class, balanced accuracy is undefined. These are intentional boundaries of the evidence.

The organoid route is `python organoid_phenotype.py` on a free Kaggle Linux CPU with Internet enabled. The dependency versions are pinned in `requirements-organoid.txt`; the command downloads and checks the 2,880,860,613-byte HNOCA v1 file against MD5 `078675d6108e93cebc99676b6b0626aa`, extracts selected sparse rows, fits the fixed Velasco model, and writes `organoid_audit/audit.html`, `audit.json`, and `groups.csv`. The first whole-study run completed with script exit 0 in 669.356 seconds, with 2,554,363,904 bytes peak resident memory. An independent local verifier read all 207,871 scored cell records and recomputed the 34 group matrices, external macro-F1, and 2,000-draw primary interval. A second **clean run of the final public entry point**, from the original file on Kaggle Linux x86-64 with Python 3.12.13 and four free CPU cores, completed with script exit **0** in **675.147 seconds** and peak resident memory **2,561,519,616 bytes**. It exactly reproduced the first run's 207,871-cell and 34-key denominators, full confusion matrix, macro-F1 `0.9078308669478505`, interval `[0.8423242754145907, 0.9371954104623934]`, and paired difference interval `[0.07049358560024495, 0.12053559237535703]`. Ninety-three compared floating fields had maximum observed difference **0**; exact integer and key equality was required and `1e-12` was the preregistered absolute tolerance for floats. The output HTML is rendered from the JSON written by that same run. The source file is removed after extraction; no raw atlas, per-cell predictions, or fitted weights are published with this repository.

The optional `python organoid_phenotype.py --author-label-sensitivity` runs the same model and adds a byte-range read of the separate cleaned archive's original-author annotations. It validates the complete Bhaduri row-key digest before scoring the prespecified Neuron/Radial Glia endpoint, then writes `organoid_audit/author_label_sensitivity.json` and the same values into `audit.json` and HTML. The JSON holds each key's paired 2-by-2 confusion matrices, exclusions, labels, and 2,000-draw group interval. The clean archive's **published** MD5 is documented, but the byte-range run does not claim to recompute the hash of all 18.74 GB.

The [competition-linked public Kaggle notebook](https://www.kaggle.com/code/loxigicck/neural-organoid-phenotype-audit-across-labs) separately ran that exact source hash `72752afaf60ee7922f77b6937bd7095846353d3ff9fcb0471f04a3f57ea538a9` from the original HNOCA file. Its job reached `COMPLETE` with script exit 0 in **2,641.932 seconds** and **2,554,421,248 bytes** peak resident memory; its `original_verified` stage alone took **2,593.253 seconds** to fetch and hash the source. The downloaded notebook output had all 34 CSV rows and exactly matched the first run's method, group matrices, external macro-F1, and bootstrap interval under an independent output comparison. The notebook is listed on this competition's public Code page.

The image source-to-report route is `python run_full_audit.py`. It downloads and verifies both original Zenodo files, extracts the 3,072 image feature vectors, computes F1-F4, and writes the offline HTML, JSON, and `run_evidence.json`. On a local machine its default four-minute budget allows the same command to resume the ZIP download and feature extraction. A clean Kaggle Linux CPU run used `--time-budget 0` to complete the route in one invocation, produced the report, matched the Linux reference, and exited 0. The corresponding macOS run uses the same feature SHA-256 but different forest trees; its report marks the platform difference and the command exits 3.

# Reliability, limitations, and application value

## What is directly observed

The HNOCA source file's full MD5 and size, 342,924 selected cells, 21/34 distinct source/test `bio_sample` keys, per-cell predictions, class matrices, source-internal and external scores, and 34-key bootstrap outputs are recorded. The Velasco and Bhaduri experiments were collected by separate research teams [11, 12]. The external metric is above the prespecified screen and its difference from the prespecified comparator has a positive paired interval. The rare Glioblast false-positive count remains visible beside the high macro-F1.

The source folder assignments, the labels, the date-like image prefixes, and the predictions are inspectable. For those supplied identifiers, 57 of 57 source-test prefix groups also occur in source training. The different full-test scores and their denominators are observable, as are the same-image predictions on the 151-image intersection. We supply counts rather than only a single summary score so a researcher can see false alarms on good cultures.

## What is not identified

HNOCA's cross-study panel selection and harmonized labels limit independence: an acquisition-source holdout is not a fully external annotation gold standard. Its `bio_sample` values do not prove physical organoid or donor identities. The grouped interval resamples 34 keys, and the rare Glioblast class has at least 100 cells in only eight keys. No prospective deployment or independently blinded annotation test is reported.

A filename prefix is not independently validated as a physical chip, biological replicate, or day of acquisition. Even if the apparent date meaning were exact, images from different dates could share a chip, and images from the same date could come from different chips. The dataset does not resolve that ambiguity. The same-image result cannot isolate group overlap from a change of training data or threshold. The paired interval uses only 14 observed prefixes and crosses zero. No second non-pathogen organ-on-chip *image-quality* dataset with verified per-sample groups and labels has yet produced an effect estimate. Repeated attention to this source test during F1-F4 also limits how much the later numeric comparisons can be treated as confirmatory.

The quality labels assess brightfield image suitability. They do not quantify cell viability, therapeutic effect, toxicity, or clinical outcome. In particular, our false-positive counts are flags on expert-labeled good images, not measured damage to cultures. Any production triage workflow would require prospective testing, a definition of the actual acquisition unit, and user-selected costs for missed bad images versus good images sent to review.

## Intended application

For neural-organoid single-cell work, the score-based queue can prioritize keys **within the already atlas-selected three-class cohort** without using those keys' outcome labels in its ordering. When HNOCA consensus labels are available, a separate error audit puts samples with unusually high predicted-versus-consensus Glioblast proportions into an annotation review queue. The per-key tables identify where marker genes or original cell annotations deserve inspection. A wholly unannotated new batch has not passed this end-to-end test; neither queue is automated release of an unbiased composition estimate.

For organ-on-chip brightfield work, the image audit can serve as an evaluation checklist with executable calculations. When a team has real chip IDs, it can use them as group fields and inspect whether its test chips were truly absent from training. When it has only acquisition sessions or batches, the result must carry that weaker name. The same code can also compare two test protocols on their shared images, so apparent improvements on different test sets are not casually treated as paired effects. This remains useful even when an image model does not clear a deployment gate.

# Reproducibility and dependency disclosure

## Hardware and software

The image audit runs on CPU with Python 3.12. `requirements.txt` pins NumPy 2.5.3, Pillow 12.3.0, SciPy 1.18.1, and scikit-learn 1.9.1. The initial organoid result used free Kaggle CPU with Python 3.12.13, NumPy 2.0.2, SciPy 1.16.3, scikit-learn 1.6.1, and h5py 3.16.0; its public dependency set and clean-run check are reported with the published organoid entry point. Both cases use no paid service, proprietary model, non-public data, or GPU. The source image ZIP is 6.71 GB and the HNOCA archive is 2.88 GB, so source transfer dominates a clean run. Raw source data, generated features, scored cells, and fitted weights remain local or in temporary Kaggle job outputs; they are not redistributed in this repository. Runtime measurements are specific to their stated environments.

## HNOCA original-file run and output checks

The initial free Kaggle CPU job fetched all 2,880,860,613 bytes from Zenodo, recomputed MD5 `078675d6108e93cebc99676b6b0626aa`, and extracted a 342,924-by-3,000 sparse matrix with 57,695,927 nonzero entries. Its 669.356-second script runtime included 608.708 seconds for download and hash verification; peak resident memory was 2,554,363,904 bytes on four CPU cores. The job reached `COMPLETE` and the script reported exit 0. The result JSON recorded the three-class full-test matrix and every Bhaduri sample key. Its SHA-256 was `67cbaec484e7fc4dded61b3b82b8d317faab80c34c4f5949a51b8ce92291099f` and the compressed 207,871-row prediction file's SHA-256 was `37bd891dea647dbcdc77b428643ce8cdeebebe82c908c0db9eb560a81eff64af`. A separate verifier read that file and reconstructed the full and per-key confusion matrices, macro-F1 0.9078308669, and 95% sample-key interval 0.8423242754-0.9371954105 in 2,000 effective draws. The comparator predictions and paired interval come from the same full job; the separate verifier did not independently refit or reconstruct the nearest-centroid predictions. We keep that limit explicit.

## Linux reference and independent clean run

An earlier clean Kaggle Linux x86-64 CPU run started without a prepared cache, verified the 6,710,767,405-byte ZIP against source MD5 `8f7e058996203d48eb03b2d86c0a2e4d`, verified the datasheet SHA-256, and extracted features for all 3,072 image IDs. Its feature-cache SHA-256 was `65bb227546f96b7f4643ccf5f98caf50ca38b90c23cce221367dae7d5c6e5902`. That run exited 3 because the reference still contained earlier macOS measurements. Its actual Linux F2-F4 output is now the frozen Linux reference; the macOS record remains separately identified in the same file.

A second Kaggle run used the public one-command code and a new, empty `/kaggle/temp/ooc_audit_cache`. It downloaded the original files again, verified the same source and feature hashes, recomputed F1-F4, and produced `audit.html`, `audit.json`, and `run_evidence.json` with `status: verified`. The private verification job completed with exit 0 on four free Linux x86-64 CPU cores, with GPU disabled and internet access for Zenodo. The audit command took 601.00 seconds and recorded 218.98 MiB peak resident memory. The two report SHA-256 digests are recorded in `run_evidence.json` and match the downloaded artifacts. Its source test had 57/57 date-like prefixes also in training, and the shared test had 151 images, 68 good and 83 bad, from 14 prefixes.

| Measure | Clean Linux reference | Original macOS measurement |
| --- | ---: | ---: |
| Grouped F2 test balanced accuracy | 0.657920 | 0.657801 |
| Grouped F2 good images falsely flagged | 181/376 | 179/376 |
| Source F3 test balanced accuracy | 0.799925 | 0.797882 |
| Source F3 good images falsely flagged | 57/365 | 61/365 |
| Same-151-image paired balanced-accuracy difference | +0.066088 | +0.070783 |
| Paired 14-prefix bootstrap 95% interval | -0.042091 to +0.122483 | -0.031747 to +0.127527 |

We located the first measured divergence before validation and threshold selection. On the same ordered feature and label arrays, with identical seeds and one fitting thread, the first forest tree is identical across macOS Python 3.12 and Linux x86-64/ARM64 Python 3.12. In a 300-tree grouped fit, tree 3 first differs at node index 96: macOS selects feature 7 at threshold 0.0150570632, while Linux selects feature 9 at 0.0283526825. A 64-row probe first differs in tree 16. Linux x86-64 and ARM64 agree on every probed tree, validation probability, and threshold. The precise lower-level cause of the tree split is not established; the identical source and feature hashes rule out a different image cache as its cause.

The Linux ARM64 check reproduced 820 deterministic reference leaf fields, including 207 floating-point fields, with maximum observed difference zero. The frozen comparison allows only `1e-12` absolute numeric difference and requires exact counts, labels, split summaries, thresholds' nonnumeric selection fields, and confusion matrices. The feature SHA-256 must match exactly; source ZIP MD5 and datasheet SHA-256 are verified before evaluation. This tolerance is far below the measured cross-platform score and threshold differences. On macOS, the report explicitly marks matching features with platform-dependent forest scores and exits 3. A changed source or feature file likewise cannot receive `verified` status.

The grouped false-positive rate exceeds the prespecified 45% ceiling on both systems. The descriptive full-test gap exceeds the audit-direction screen of 0.10 on both systems. The paired difference is below the 0.08 stronger-evidence screen and its interval crosses zero on both systems. We do not overwrite the earlier measurements or infer a general physical-chip leakage effect from either run.

## Reproduction sequence

From the public repository root, create a Python 3.12 virtual environment, install `requirements.txt`, and run `python run_full_audit.py`. The default local time budget pauses with a resumable instruction; repeat the same command until it completes. On a remote CPU without a short process limit, use `python run_full_audit.py --time-budget 0`. The script performs the spreadsheet and ZIP checks, feature extraction, F1-F4 calculations, Linux-reference comparison, and report export. The source mapper reads ZIP64 metadata, reconciles 3,072 IDs and source-folder labels to the spreadsheet, and writes the mapping locally. F4 refits both models and checks the stored F2/F3 results before the offline report is written. The JSON records input SHA-256 hashes and per-image predictions. No private database, model file, paid API, or GPU is needed.

A separate generic route accepts two user-provided record files:

```text
python audit_report.py records \
  --source-records SOURCE.jsonl \
  --grouped-records GROUPED.jsonl \
  --output OUTPUT_DIR
```

Each JSONL record must use a stable `id`, a provenance-backed `group`, `label` 0 or 1, `split` train/val/test, and a `prediction` on test only. The record contract lets another team run the audit without adopting our image features or random forest. Their group labels, reference labels, and predictions remain their responsibility.

# Prior work, originality, and responsible disclosure

The HNOCA atlas, its 3,000-gene panel, harmonized labels, and the original Velasco and Bhaduri experiments predate this competition [9-12]. We did not create those cells or annotations and do not present their label convention as an independent gold standard. The image dataset, expert quality labels, and a same-data classification study also predate this work [1-3]. Our competition work is the fixed cross-study cell-type model and sample-level evaluation, plus the organ-on-chip image split and shared-image audit, offline report routes, and reproducibility checks. All reported numeric results are derived from publicly obtainable inputs by the described scripts. No result or demo is simulated.

The source package's split was accepted as an object of study, not as an independent ground truth about physical chips. A finding of 57/57 prefix overlap is not a finding of chip-level data leakage. The full-test accuracy difference does not compare identical samples. The paired difference and its crossing-zero interval do not warrant a claim that source splits are systematically optimistic. We make these distinctions because the competition asks for verifiable results and because an evaluation tool loses value if its own headline overstates the evidence.

There is one individual entrant, Yan Su. Python, NumPy, SciPy, scikit-learn, h5py, Requests, and Pillow provide the runtime; no foundation model or paid inference API is part of the quantitative result. AI coding assistance may be used to write and review code and prose, but reported numbers come from real runs and are checked against scored records. Research data remain attributed to their sources and are not redistributed in this repository. The code is released under MIT.

# References

1. Movčana et al. [Organ-on-a-Chip (OOC) Image Dataset](https://zenodo.org/records/10203721). Zenodo (2023), DOI: [10.5281/zenodo.10203721](https://doi.org/10.5281/zenodo.10203721). Source record, downloadable data, and record-level license metadata.
2. Movčana et al. [Organ-On-A-Chip (OOC) Image Dataset for Machine Learning and Tissue Model Evaluation](https://www.mdpi.com/2306-5729/9/2/28). *Data* 9(2), 28 (2024), DOI: [10.3390/data9020028](https://doi.org/10.3390/data9020028). Experimental context and expert image-quality labels.
3. George and Kenry. [Supervised-Learning-Driven Interrogation of Organ-on-a-Chip Quality from Microscopy Images](https://pmc.ncbi.nlm.nih.gov/articles/PMC12745998/). *Chemical & Biomedical Engineering* 2(12), 739-745 (2025), DOI: [10.1021/cbe.5c00087](https://doi.org/10.1021/cbe.5c00087). Its image-level split and stated need for further stability assessment motivate the distinct audit question here.
4. [NumPy license](https://numpy.org/doc/stable/license). Official NumPy documentation.
5. [Pillow license](https://pillow.readthedocs.io/en/stable/about.html#license). Official Pillow documentation.
6. [scikit-learn 1.9.1 release](https://pypi.org/project/scikit-learn/1.9.1/). Official PyPI distribution and license metadata.
7. [CC BY 4.0 legal code](https://creativecommons.org/licenses/by/4.0/) and [CC BY-SA 4.0 legal code](https://creativecommons.org/licenses/by-sa/4.0/). Creative Commons.
8. [SciPy license](https://projects.scipy.org/scipylib/license.html). Official SciPy project license.
9. [HNOCA v1 archive](https://zenodo.org/records/15004818). Zenodo (2025), DOI: [10.5281/zenodo.15004818](https://doi.org/10.5281/zenodo.15004818). Original file, MD5, and CC BY 4.0 archive metadata.
10. He et al. [An integrated transcriptomic cell atlas of human neural organoids](https://www.nature.com/articles/s41586-024-08172-8). *Nature* 635, 690-698 (2024), DOI: [10.1038/s41586-024-08172-8](https://doi.org/10.1038/s41586-024-08172-8). Cross-study gene selection and harmonized annotation methods.
11. Velasco et al. [Individual brain organoids reproducibly form cell diversity of the human cerebral cortex](https://www.nature.com/articles/s41586-019-1289-x). *Nature* (2019), DOI: [10.1038/s41586-019-1289-x](https://doi.org/10.1038/s41586-019-1289-x). Development-study provenance.
12. Bhaduri et al. [Cell stress in cortical organoids impairs molecular subtype specification](https://www.nature.com/articles/s41586-020-1962-0). *Nature* (2020), DOI: [10.1038/s41586-020-1962-0](https://doi.org/10.1038/s41586-020-1962-0). Held-out acquisition-study provenance.
13. [h5py license](https://github.com/h5py/h5py/blob/master/licenses/license.txt). Official project repository.
14. [Requests license](https://github.com/psf/requests/blob/main/LICENSE). Official project repository.
15. Khatri and Bonn. [Uncertainty Estimation for Single-cell Label Transfer](https://proceedings.mlr.press/v179/khatri22a.html). *Proceedings of Machine Learning Research* 179, 109-128 (2022). Prior work on calibrated uncertainty for transferred single-cell labels.
16. [HNOCA cleaned archive](https://zenodo.org/records/14161275). Zenodo (2024), DOI: [10.5281/zenodo.14161275](https://doi.org/10.5281/zenodo.14161275). Preserved original annotation fields, published MD5 and CC BY 4.0 metadata.
17. Schuster et al. [Automated microfluidic platform for dynamic and combinatorial drug screening of tumor organoids](https://doi.org/10.1038/s41467-020-19058-4). *Nature Communications* (2020). Original Figure 5a-b Source Data and CC BY 4.0 article.
18. Dai et al. [Self-assembly of tumor-related vascularized colorectal tumoroid-on-a-chip for precision medicine drug testing](https://doi.org/10.1016/j.xcrm.2026.102873). *Cell Reports Medicine* (2026). Figure 5 Source Data and Figure 5P, article CC BY-NC-ND 4.0.

# Appendix A: denominators and decision gates

| Version | Test unit / denominator | Primary observation | Decision |
|:--|:--|:--|:--|
| F1 | 15 held-out date-like prefixes, 736 images | Image BA 0.608836; 220/376 good images flagged bad | One prespecified nonlinear comparison allowed |
| F2 | Same grouped test, 736 images | Linux forest BA 0.657920; 181/376 good images flagged bad | Automatic quality gate stopped because 48.14% > 45% |
| F3 | Original folder test, 57 overlapping prefixes, 656 images | Linux forest BA 0.799925; nonpaired gap +0.142005 | Audit direction explored; paired check required |
| F4 | Exact common test IDs, 151 images, 14 prefixes | Linux paired gap +0.066088; interval crosses zero | Strong-evidence gate failed; report as diagnostic |
| F7 | Real indexed images | Offline HTML and JSON with per-image records | One-command report entrance accepted |

The F3 candidate screen required source-test balanced accuracy at least 0.75 and full-test gap at least 0.10, both of which were observed on macOS and Linux. That screen only justified the F4 diagnostic, not a leakage claim. The F4 strong-evidence screen required a paired gap at least 0.08 and an approximate interval lower bound above zero; neither was observed on either platform. These thresholds were used as research decisions, not post hoc significance tests.

# Appendix B: numeric audit checks

The following equalities can be checked against the generated Linux JSON and code:

- F2 grouped full test: 195 + 181 = 376 expert-good images; 73 + 287 = 360 expert-bad images. Balanced accuracy is `(195/376 + 287/360)/2 = 0.6579196217`.
- F3 source full test: 308 + 57 = 365 expert-good images; 71 + 220 = 291 expert-bad images. Balanced accuracy is `(308/365 + 220/291)/2 = 0.7999246811`.
- Shared test: 68 expert-good plus 83 expert-bad images equals 151 IDs. The F3 matrix is `[[57,11],[27,56]]`; the F2 matrix is `[[39,29],[16,67]]`.
- Shared-image F3 balanced accuracy is `(57/68 + 56/83)/2 = 0.7564670446`; F2 is `(39/68 + 67/83)/2 = 0.6903791637`; their difference is 0.0660878809.
- Correctness transitions sum to the common denominator: 92 both correct + 21 source-only correct + 14 grouped-only correct + 24 both wrong = 151.
- Test-composition accounting: 656 source test - 151 common = 505 source-only; 736 grouped test - 151 common = 585 grouped-only.

The audit program computes these numbers from records. The appendix shows how to check them by hand; it is not a separate source of values. Full precision, source hashes, and per-image assignments are held in the generated local `audit.json`. The HTML rounds for reading, and the JSON preserves the computed values.

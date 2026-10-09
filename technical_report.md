---
title: "More screening decisions from fewer measurements"
date: "10 October 2026"
lang: en-US
documentclass: article
papersize: letter
fontsize: 11pt
geometry: margin=0.88in
linestretch: 1.15
mainfont: "Times New Roman"
sansfont: "Helvetica"
monofont: "Menlo"
CJKmainfont: "Songti SC"
colorlinks: true
linkcolor: black
urlcolor: blue
toc: false
numbersections: false
header-includes:
  - \usepackage{float}
  - \usepackage{caption}
  - \captionsetup{labelformat=empty}
  - \usepackage{booktabs}
  - \usepackage{longtable}
  - \usepackage{microtype}
  - \usepackage{fancyhdr}
  - \pagestyle{fancy}
  - \fancyhf{}
  - \fancyhead[L]{Sparse concentration-response screening}
  - \fancyfoot[C]{\thepage}
---

**Team: Three-Pointer**

**Yan Su (苏颜)**, Team leader, Kaggle `yansuu`  
**Ziyang Liu (刘子扬)**, Team member, Kaggle `ZY.Liu777`

**Category: Tool & Platform**

[Public code](https://github.com/logxio/ooc-evaluation-audit) · [Interactive workbench](https://logxio.github.io/ooc-evaluation-audit/workbench/)

# Abstract

AnchorBoost decides, from three measured concentrations, whether to report a compound's activity call, add one concentration of its own choosing, or complete the series. Replaying 965 three-concentration designs from the EPA rat-neuronal network-formation screen, with training, calibration and test chemical identities kept apart, it reports 925 calls with 69 wrong from 12,119 exposure wells. A measured-only rule under the same drug-level calibration reports 818 with 75 wrong from 13,503 wells: AnchorBoost gives 107 more reports [81, 134] and uses 10.2% fewer wells [7.7%, 12.8%], 56.8% fewer than completing every series. At equal cost the advantage holds: within the 12,031 wells of three-point AnchorBoost, the best measured-only threshold makes 110 wrong reports against 84. The predictor learns from every sparse design inside archived complete curves, reconstructs unmeasured responses with 13.7% lower error than interpolation, and its disagreement with simpler forecasters chooses the next concentration. On the same folds and the same metric, AnchorBoost leading a residual stack wins 97 of 98 comparisons with published predictor configurations at one to four measured concentrations, ties one and loses none; at three concentrations it beats all 32, from TabPFN and LimiX-2 to neural processes and the EPA's GenRA. The gains carry to plates and culture dates absent from training. In a perfused liver-chip test whose 46 held-out responses a separate custodian released only after predictions were fixed, calibrated envelopes held back all twelve calls, seven of which a zero-width rule would have made wrongly, and a sequential replay settled every curve with 25 of the 46 measurements and no early error. A public command runs the same three actions on a laboratory's own plate table and locks its forecasts before the remaining wells are read; on held-out compounds from the EPA human neural-cell screen, 92.0% of 2,520 hidden wells fell inside its 90% intervals and its next steps used 35.6% fewer wells than running every series.


# 1. More calls, fewer wrong reports, fewer wells

AnchorBoost turns three measured concentrations into one of three actions: report the predicted full-series activity call, add one concentration where its forecasters disagree, or complete the series. One calibrated margin governs both decision points, holding the expected drug-level wrong-report loss at or below 10% whichever concentration is added. On the EPA screen this decision chain reports more designs than the conventional measured-only rule, with fewer wrong reports and fewer wells (Table 1). On forecasting error alone, AnchorBoost leading a residual stack beats all 32 published predictor configurations we could run at three measured concentrations, from TabPFN and LimiX-2 to neural processes and the EPA's GenRA. Across one to four concentrations it wins 97 of 98 comparisons and loses none; the one tie is LimiX-2 at two concentrations, whose weights are licensed for noncommercial use only (Section 2.4).

**Table 1. Activity calls and exposure wells in the four primary test folds.** 188 identity groups and 965 three-concentration designs, with training, calibration and test identities kept apart. Every rule uses the same drug-level calibration and reports directly the designs whose measured concentrations already reach the activity threshold. Wells count exposed wells, including completion of unresolved series.

| Rule | Reports / 965 | Wrong reports | Exposure wells |
|:--|--:|--:|--:|
| AnchorBoost: report, add one concentration, or complete | **925** | **69** | 12,119 |
| AnchorBoost: report or complete | 914 | 84 | **12,031** |
| Measured points only: report or complete | 818 | 75 | 13,503 |
| Complete every series | Reference | Reference | 28,080 |

Against the measured-only rule, the chain gives **107 more reports [81, 134] with 6 fewer wrong ones**, uses **10.2% fewer wells [7.7%, 12.8%]** with a wrong-report-loss difference of −0.7 points [−2.5, 1.0]; against complete measurement it uses 56.8% fewer wells. The comparison also holds at equal cost: within the 12,031 wells of three-point AnchorBoost, the best measured-only threshold makes 110 wrong reports against 84 (Section 4.4).

The distinctive choice is to train on the measurement situations a researcher may encounter. Three concentrations spanning an activity transition carry different information from three below it. Complete training curves supply examples of both. A gradient-boosted model learns how to correct log-concentration interpolation across these contexts, sharing information between chemicals and assay outputs.

The primary evidence comes from a static rat-neuronal microelectrode-array (MEA) assay [32,33]. We evaluate reconstruction against every published predictor we could run, selection of a fourth concentration, three-point reporting and the closed loop in separate experiments, then test the chain on plates and culture dates absent from training, on other neuronal assays and on perfused liver-chip data with withheld responses. Section 6 gives the command that runs the same three actions on a laboratory's own plate table. Figure 1 follows a sparse design from recorded wells to a reconstructed curve, then places reporting alongside its exposure-well cost.


![Figure 1. From sparse measurements to a reporting decision. Panels a–d and the upper part of e follow Trimethyltin hydroxide, design 1 at DIV 12, in the historical MEA replay. Gray cells in b indicate features without recorded measurements at that concentration. Held-out means provide the measured reference; bars in c are nominal 90% well-response prediction intervals from historical calibration. The lower part of e shows three-point AnchorBoost reporting in the four primary test folds (Table 6): 914/965 reported designs and 12,031/28,080 exposure wells. One dot represents approximately 100 wells. Costs include observed replicates, the initial wells and completion of the remaining series for each alternative starting design.](figures/F1-workflow.png){#fig-workflow width=100%}


# 2. Learning from sparse concentration designs

## 2.1. Prediction gains reach most held-out chemicals

Forecast-based activity calls depend on responses at concentrations that remain unmeasured. We test their reconstruction against interpolation, chemical analogs, Hill curves and the published conditional neural process (CNP), using the same three-concentration designs for 194 held-out chemicals. Absolute error is averaged over day-feature outputs and designs within each chemical, then equally across chemicals. Appendix A specifies the frozen protocol and source data, and Section 2.4 extends the comparison to every published predictor we could run.

**Table 2. Static three-concentration reconstruction on the original 194-chemical benchmark.** Differences are AnchorBoost minus the listed comparator; 95% confidence intervals (CIs) use paired chemical bootstraps. Lower error is better. The CNP row uses the original published run.

| Predictor | Mean absolute error, normalized response units | Paired difference, 95% CI |
|:--|--:|:--|
| AnchorBoost | **1.1606** | Reference |
| Published CNP | 1.1940 | −0.0333 [−0.0703, −0.0004] |
| Log-concentration interpolation | 1.345 | −0.185 [−0.217, −0.154] |
| Analog chemicals | 1.349 | −0.189 [−0.216, −0.162] |
| Per-output Hill curve | 1.457 | −0.296 [−0.329, −0.264] |

AnchorBoost lowers interpolation error by **13.7%**, improving every primary fold and 88.7% of chemicals. With two measured concentrations, its error is close to interpolation's four-concentration error, evaluated on each method's remaining forecast targets: paired difference −0.001 [−0.043, 0.043] (Table A1).

The CNP comparison is closer. Removing phenobarbital, whose parent identity crosses an original training/test boundary through its sodium form, leaves 193 chemicals and an AnchorBoost–CNP difference of **−0.029874 [−0.065825, 0.002217]**. The interval spans zero (Figure 2c), and resampling whole identity groups gives the same reading, a tie at −0.030 [−0.065, +0.003] (Table 4). The AnchorBoost stack beats the CNP at every concentration budget, by −0.074 [−0.102, −0.048] at three concentrations (Section 2.4). Against interpolation, Figure 2a–b resolves the average gain into individual chemicals, while Figure A1 shows one high-variation response from chemicals with the largest, median and smallest gains.

## 2.2. Design coverage contributes at a fixed training budget

Enumerating more concentration designs also creates more training rows. To isolate the value of coverage, full enumeration and repeated use of the five published contexts receive the same scalar training-row count, features and 600 boosting iterations (Figure 2e). Coverage lowers MAE from **1.183515 to 1.160612**, a **1.94%** reduction, with paired difference −0.022903 [−0.035089, −0.012074]. It improves 134 of 194 chemicals and all four folds.

The separate design-count series in Figure 2f shows how prediction changes when coverage and training-row count grow together. The controlled comparison therefore attributes part of the gain to the variety of measurement situations seen during training. Information from analogous training chemicals supplies another gain; residual rather than direct-response prediction has an interval spanning zero. Appendix A records these ablations and the identity sensitivity.

## 2.3. Prediction gains extend to acute and human-neural screens

The same training recipe can be tested with different neuronal readouts. The acute assay measures mature rat cortical networks after about one hour of exposure; the human assay measures neural progenitor and neuronal responses through nine imaging and plate-reader endpoints [34,35]. We retain the model configuration and fit weights within each screen.

**Table 3. Three-concentration forecasting in additional screens.** These are within-screen chemical holdouts with an unchanged modeling recipe. The first two rows use all eligible source labels. The neural comparisons use identity-aware subsets. MAE uses each screen's vehicle-normalized response scale; bootstrap units follow the labels or identities listed.

| Comparison | Chemical units | AnchorBoost MAE | Comparator MAE | AnchorBoost − comparator, 95% CI |
|:--|--:|--:|--:|:--|
| Acute rat MEA vs interpolation | 384 labels | 1.554 | 1.814 | −0.260 [−0.281, −0.238] |
| Human neural cells vs interpolation | 71 labels | 1.693 | 1.965 | −0.272 [−0.352, −0.195] |
| Acute rat MEA vs CNP | 383 identities | 1.554265 | 1.570140 | −0.015875 [−0.030804, −0.001256] |
| Human neural cells vs CNP | 69 identities | 1.694976 | 1.744422 | −0.049446 [−0.113124, 0.013459] |

Reconstruction error falls by 14.3% and 13.9% relative to interpolation, so learning across designs carries to both readouts. AnchorBoost is also lower than the retrained CNP on both screens, by 0.016 and 0.049; the wider 97.5% intervals of Appendix A.2 include zero for both. Appendix A describes preprocessing and cross-screen identity overlap.

![Figure 2. Prediction errors and design coverage in static forecasting. Panel a compares errors for each chemical. Panel b plots each chemical's five-design mean AnchorBoost minus interpolation MAE by test fold; short horizontal lines mark fold means, and counts above show chemicals with lower AnchorBoost error. Panel c gives paired AnchorBoost–CNP differences on each screen's normalized scale and chemical win/loss proportions; the thin whisker for the acute screen is its 97.5% interval. Panel d resolves normalized-response MAE by day and feature. Panel e shows paired differences and chemical win/loss proportions with scalar training rows and 600 boosting iterations fixed. Panel f lets coverage and training-row count grow together. Each glyph row is one three-concentration design, with filled cells marking measured concentrations; 5, 10 and 20 are random schematic examples, while All contains all C(7,3)=35 designs for seven concentrations. CNP denotes conditional neural process. Reporting results appear separately in Figures 5 and 6.](figures/F2-evidence.png){#fig-evidence width=100%}

## 2.4. Every published predictor, same folds, same metric

**Across 98 paired comparisons with published predictor configurations at one to four measured concentrations, AnchorBoost leading a residual stack wins 97, ties one and loses none; at three concentrations it beats all 32** (Table 4 and Figure 3). The field runs from tabular foundation models (TabPFN-2, TabPFN-3.5, TabICLv2, LimiX-2) and neural processes (CNP, TNP, TE-TNP, FlowNP) through dose-response models (LPM, DR-PFN, Hill empirical Bayes, Gaussian processes) and molecular models (KANO, MotiL, ARCANet and the EPA's GenRA) to matrix and tensor completion, neighbor methods and interpolation. The one tie is LimiX-2 with AnchorBoost features and CheMeleon at two concentrations, whose weights are licensed for noncommercial use only. AnchorBoost alone, the public model, wins 26 of the 32 at three concentrations and ties six; the CPU single model wins 27 and ties five, and loses none of the 98. Every comparison uses the same four test folds, concentration designs and normalized-response MAE, matching each method to the same available chemicals; a win means the paired 95% interval lies wholly below zero. The counts are configurations, including adaptations and several variants of one published family, rather than 32 independent publications.

The stack keeps AnchorBoost's features and its residual learning. At one and two measured concentrations, TabPFN-2 reading AnchorBoost's features and a 20-seed LPM supply a weighted forecast; at three and four, AnchorBoost's gradient boosting learns the correction on top of that forecast. Each outer fold chooses the member weights and the correction by inner cross-validation on its own training chemicals, so no scored chemical selects its own model, and every member is licensed for commercial use. AnchorBoost alone is the frozen public model behind every reporting and well-saving result of Sections 4–6. The CPU single model uses a distilled AnchorBoost at k=1–2 and the five-bag boosting model at k=3–4, both on CPU. The stack and the CPU model are forecasting results, so their lower errors are the next input to the same calibrated reporting rule. The research committee adds noncommercial LimiX-2 weights; Table 4 lists it with our rows, outside the opponent counts, and the released scoreboard (`results/final/baselines/scoreboard.csv`) holds four further ensemble ablations of the stack.

**Table 4. Every published predictor configuration on the same folds and metric.** MAE at three measured concentrations, in normalized response units; lower is better. Stack, CPU and Alone are the three AnchorBoost references of Section 2.4 and Figure 3. Each reference column gives the paired outcome at k=1, 2, 3 and 4 measured concentrations (W win, = tie, L loss, — not run), then the k=3 difference, reference minus row, with its paired 95% interval; negative favors the reference. Our four rows lead and the 32 opponent configurations follow in order of k=3 MAE. AB abbreviates AnchorBoost; the first column gives each family and a linked source.

| Predictor; family, source | k=3 MAE | Stack − row | CPU − row | Alone − row |
|:--|--:|--:|--:|--:|
| **AnchorBoost stack**; Ensemble, [this work](https://github.com/logxio/ooc-evaluation-audit) | 1.1170 | — | L L L L · +0.0370 [+0.0235, +0.0502] | L L L L · +0.0436 [+0.0211, +0.0670] |
| AnchorBoost CPU single model; Boosting, [this work](https://github.com/logxio/ooc-evaluation-audit) | 1.1540 | W W W W · −0.0370 [−0.0502, −0.0235] | — | L L = = · +0.0066 [−0.0112, +0.0249] |
| AnchorBoost alone, public model; Boosting, [this work](https://github.com/logxio/ooc-evaluation-audit) | 1.1606 | W W W W · −0.0436 [−0.0670, −0.0211] | W W = = · −0.0066 [−0.0249, +0.0112] | — |
| Research committee; Noncommercial, [this work](https://github.com/logxio/ooc-evaluation-audit) | 1.1168 | L L = = · +0.0002 [−0.0086, +0.0093] | L L L L · +0.0372 [+0.0192, +0.0527] | L L L L · +0.0439 [+0.0191, +0.0681] |
| LimiX-2 + AB + CheMeleon; Tabular foundation, [2026](https://arxiv.org/abs/2609.17488) | 1.1424 | W = W W · −0.0255 [−0.0411, −0.0101] | = = = = · +0.0115 [−0.0090, +0.0310] | L L = = · +0.0182 [−0.0045, +0.0404] |
| KANO embedding + AB; Molecular + boosting, [2023](https://www.nature.com/articles/s42256-023-00654-0) | 1.1515 | W W W W · −0.0345 [−0.0534, −0.0151] | W W = = · +0.0025 [−0.0131, +0.0189] | L = = = · +0.0091 [−0.0039, +0.0229] |
| MotiL embedding + AB; Molecular + boosting, [2025](https://www.nature.com/articles/s41467-025-66685-w) | 1.1564 | W W W W · −0.0394 [−0.0638, −0.0168] | W W = = · −0.0024 [−0.0215, +0.0152] | L = = = · +0.0042 [−0.0036, +0.0118] |
| TabPFN-3.5 + AB + CheMeleon; Tabular foundation, [2026](https://arxiv.org/abs/2609.17895) | 1.1569 | W W W W · −0.0399 [−0.0559, −0.0251] | W = = = · −0.0029 [−0.0201, +0.0136] | L L = = · +0.0037 [−0.0162, +0.0247] |
| LPM, 20 seeds; Latent phenotype, [2025](https://doi.org/10.1038/s43588-025-00870-1) | 1.1759 | W W W W · −0.0589 [−0.0775, −0.0411] | W W = = · −0.0219 [−0.0481, +0.0022] | = = = = · −0.0152 [−0.0469, +0.0154] |
| DR-PFN, fine-tuned; Synthetic prior, [LC-PFN 2023](https://github.com/automl/lcpfn) | 1.1795 | — — W — · −0.0626 [−0.0861, −0.0405] | — — W — · −0.0256 [−0.0478, −0.0046] | — — W — · −0.0189 [−0.0366, −0.0028] |
| TabPFN-3.5 + AB features; Tabular foundation, [2026](https://arxiv.org/abs/2609.17895) | 1.1824 | W W W W · −0.0654 [−0.0859, −0.0456] | W W W = · −0.0285 [−0.0489, −0.0083] | W = W = · −0.0218 [−0.0393, −0.0052] |
| TabPFN-2 + AB features; Tabular foundation, [2025](https://doi.org/10.1038/s41586-024-08328-6) | 1.1825 | W W W W · −0.0656 [−0.0858, −0.0463] | W W W = · −0.0286 [−0.0466, −0.0103] | = = W = · −0.0219 [−0.0330, −0.0110] |
| TabICLv2; Tabular foundation, [2026](https://arxiv.org/abs/2602.11139) | 1.1893 | W W W W · −0.0723 [−0.0911, −0.0538] | W W W W · −0.0353 [−0.0538, −0.0173] | = W W W · −0.0287 [−0.0435, −0.0138] |
| CNP, released checkpoints†; Neural process, [2018](https://proceedings.mlr.press/v80/garnelo18a.html) | 1.1920 | W W W W · −0.0739 [−0.1019, −0.0484] | W W W W · −0.0373 [−0.0702, −0.0078] | = = = W · −0.0299 [−0.0653, +0.0028] |
| TNP; Neural process, [2022](https://github.com/tung-nd/TNP-pytorch) | 1.2013 | — — W — · −0.0843 [−0.1097, −0.0608] | — — W — · −0.0473 [−0.0752, −0.0216] | — — W — · −0.0407 [−0.0713, −0.0139] |
| LPM, three seeds; Latent phenotype, [2025](https://doi.org/10.1038/s43588-025-00870-1) | 1.2083 | W W W W · −0.0913 [−0.1124, −0.0717] | W W W W · −0.0543 [−0.0832, −0.0276] | = W W W · −0.0477 [−0.0814, −0.0165] |
| FlowNP, three seeds; Neural process, [2025](https://arxiv.org/abs/2512.23853) | 1.2098 | — — W — · −0.0928 [−0.1188, −0.0680] | — — W — · −0.0558 [−0.0870, −0.0280] | — — W — · −0.0492 [−0.0823, −0.0212] |
| DR-PFN, synthetic prior; Synthetic prior, [LC-PFN 2023](https://github.com/automl/lcpfn) | 1.2307 | — — W — · −0.1137 [−0.1428, −0.0856] | — — W — · −0.0767 [−0.1045, −0.0503] | — — W — · −0.0701 [−0.0950, −0.0447] |
| TE-TNP; Neural process, [2024](https://github.com/cambridge-mlg/tnp) | 1.2624 | — — W — · −0.1454 [−0.1689, −0.1228] | — — W — · −0.1085 [−0.1340, −0.0844] | — — W — · −0.1018 [−0.1256, −0.0781] |
| Empirical GP; Gaussian process, [2026](https://arxiv.org/abs/2602.12082) | 1.2814 | W W W W · −0.1645 [−0.1938, −0.1367] | W W W W · −0.1275 [−0.1578, −0.1005] | W W W W · −0.1208 [−0.1510, −0.0958] |
| KANO, structure + k points; Molecular, [2023](https://www.nature.com/articles/s42256-023-00654-0) | 1.3208 | W W W W · −0.2038 [−0.2391, −0.1693] | W W W W · −0.1668 [−0.1994, −0.1364] | W W W W · −0.1602 [−0.1903, −0.1305] |
| Gaussian process†; Curve fitting, [our code](https://github.com/logxio/ooc-evaluation-audit) | 1.3224 | — — W — · −0.2043 [−0.2419, −0.1677] | — — W — · −0.1677 [−0.2056, −0.1316] | — — W — · −0.1603 [−0.1952, −0.1264] |
| Log-linear interpolation; Interpolation, [our code](https://github.com/logxio/ooc-evaluation-audit) | 1.3453 | W W W W · −0.2283 [−0.2676, −0.1900] | W W W W · −0.1913 [−0.2263, −0.1574] | W W W W · −0.1847 [−0.2153, −0.1545] |
| TabImpute; Matrix completion, [2025](https://arxiv.org/abs/2510.02625) | 1.3454 | — — W — · −0.2284 [−0.2828, −0.1793] | — — W — · −0.1914 [−0.2478, −0.1424] | — — W — · −0.1847 [−0.2422, −0.1349] |
| MotiL, structure + k points; Molecular, [2025](https://www.nature.com/articles/s41467-025-66685-w) | 1.3465 | W W W W · −0.2295 [−0.2692, −0.1906] | W W W W · −0.1925 [−0.2288, −0.1584] | W W W W · −0.1859 [−0.2186, −0.1538] |
| Analog nearest neighbors; Neighbors, [our code](https://github.com/logxio/ooc-evaluation-audit) | 1.3491 | W W W W · −0.2321 [−0.2613, −0.2042] | W W W W · −0.1951 [−0.2234, −0.1676] | W W W W · −0.1885 [−0.2171, −0.1601] |
| Hill empirical Bayes†; Curve fitting, [our code](https://github.com/logxio/ooc-evaluation-audit) | 1.3603 | — — W — · −0.2422 [−0.2760, −0.2112] | — — W — · −0.2056 [−0.2426, −0.1722] | — — W — · −0.1982 [−0.2329, −0.1666] |
| SNN; Neighbors, [2026](https://arxiv.org/abs/2609.13586) | 1.3625 | W W W W · −0.2455 [−0.2786, −0.2135] | W W W W · −0.2085 [−0.2422, −0.1773] | W W W W · −0.2019 [−0.2370, −0.1690] |
| N², DRNN; Neighbors, [2025](https://arxiv.org/abs/2506.04166) | 1.3867 | W W W W · −0.2698 [−0.2981, −0.2421] | W W W W · −0.2328 [−0.2617, −0.2056] | W W W W · −0.2261 [−0.2567, −0.1965] |
| N², AutoNN; Neighbors, [2025](https://arxiv.org/abs/2506.04166) | 1.3922 | W W W W · −0.2753 [−0.3049, −0.2470] | W W W W · −0.2383 [−0.2696, −0.2096] | W W W W · −0.2316 [−0.2659, −0.1993] |
| SoftImpute; Matrix completion, [2010](https://www.jmlr.org/papers/v11/mazumder10a.html) | 1.4620 | W W W W · −0.3450 [−0.3978, −0.2990] | W W W W · −0.3080 [−0.3647, −0.2619] | W W W W · −0.3014 [−0.3585, −0.2532] |
| CP tensor; Tensor completion, [2025](https://arxiv.org/abs/2507.03024) | 1.5463 | W W W W · −0.4293 [−0.4749, −0.3882] | W W W W · −0.3923 [−0.4397, −0.3503] | W W W W · −0.3857 [−0.4341, −0.3410] |
| ARCANet, structure only; Molecular, [2024](https://github.com/alonsocampana/ARCANet) | 1.6286 | — — W — · −0.5116 [−0.5925, −0.4379] | — — W — · −0.4746 [−0.5569, −0.3993] | — — W — · −0.4680 [−0.5564, −0.3873] |
| GenRA, structure only; Molecular, [2019](https://doi.org/10.1016/j.yrtph.2019.104480) | 1.6484 | — — W — · −0.5314 [−0.6197, −0.4575] | — — W — · −0.4945 [−0.5868, −0.4195] | — — W — · −0.4878 [−0.5831, −0.4095] |
| KANO, structure only; Molecular, [2023](https://www.nature.com/articles/s42256-023-00654-0) | 1.7046 | W W W W · −0.5876 [−0.6729, −0.5083] | W W W W · −0.5506 [−0.6373, −0.4719] | W W W W · −0.5440 [−0.6352, −0.4614] |
| MotiL, structure only; Molecular, [2025](https://www.nature.com/articles/s41467-025-66685-w) | 1.8201 | W W W W · −0.7031 [−0.7754, −0.6306] | W W W W · −0.6661 [−0.7407, −0.5928] | W W W W · −0.6595 [−0.7360, −0.5844] |
| CNP, retrained; Neural process, [2018](https://proceedings.mlr.press/v80/garnelo18a.html) | 1.2363 | Separate scale | Separate scale | Separate scale |

The standard cohort contains 194 chemical labels in 189 parent-identity groups. Rows marked † use the common 193-chemical, 188-group subset, so each paired difference uses its own matched reference mean. Intervals resample whole identity groups and compute chemical-weighted means: 4,000 paired bootstrap resamples, seed 0, or 10,000 for TNP, TE-TNP, ARCANet and GenRA to retain the original replicate count. Intervals are unadjusted for multiple comparisons. Saved results cover 22 configurations at k=1, 2 and 4 and all 32 at k=3; ten methods were run at k=3 only. For k=1 through 4, the stack's win/tie/loss totals are **22/0/0, 21/1/0, 32/0/0 and 22/0/0**; the CPU single model's are **21/1/0, 20/2/0, 27/5/0 and 15/7/0**; and AnchorBoost alone's are **13/5/4, 14/6/2, 26/6/0 and 15/7/0**.

The inventory separates original methods from the evaluated implementations. DR-PFN adapts LC-PFN to concentration-response data; KANO and MotiL each have structure-only, structure-plus-measurement and AnchorBoost-feature variants. The ARCANet and GenRA rows cover the full 194-chemical cohort using the saved fallback predictions for unusable structures. The retrained CNP, last in Table 4, was normalized on a training-only response scale; its MAE is listed for completeness and enters no difference or count. Appendix A.3 reports predictors whose pretraining saw activity labels for these chemicals, and Appendix F lists source, code and weight terms.

![Figure 3. Every published predictor on the same folds and the same scale. Panel a gives three-concentration (k = 3) MAE in normalized response units for 32 comparator configurations, grouped by family and ordered by error within each family; the AnchorBoost stack (1.1170, solid line), the CPU single model (1.1540) and AnchorBoost alone (1.1606) sit on top, the latter two as pale dashed lines. "+ AB features" means the model reads AnchorBoost's 22 features; "+ CheMeleon" adds a structure embedding pretrained on computed descriptors. Panel b reads each row against each reference at k = 1, 2, 3 and 4 measured concentrations, stack first: a circle is a win for the reference (the paired 95% interval of reference minus row MAE lies wholly below zero), a square a tie and a triangle a loss. Self-comparisons are blank, each pair of references appears once, in the column of the stronger model, and dashes mark the ten methods run at k = 3 only. The stack wins 97 of its 98 comparator cells and ties LimiX-2 + AB + CheMeleon at k = 2. The benchmark covers 194 chemicals in 189 identity groups from test folds 1–4; rows marked n=193 use the common 193-chemical subset. Table 4 gives every interval and the separately scaled retrained CNP; Appendix A.3 reports the five Monroe configurations, whose pretraining corpus carries bioassay labels for 181 of the 194 test chemicals.](figures/FZ-baselines.png){#fig-baselines width=100%}

# 3. Choosing a fourth concentration from the observed response

The forecasting tests keep the measured concentrations fixed. An adaptive screen can also use the observed response to choose where to measure next. After three concentrations, disagreement among AnchorBoost, interpolation and a training-chemical analog supplies that choice. We compare this policy with uniform random selection, maximin spacing in log concentration and the highest unobserved dose. Each policy adds one concentration.

**Table 5. MAE after one additional concentration, 193 common chemicals and 965 designs.** Columns use the same chosen concentrations across predictors. Random is the exact expectation over the candidate set. Highest-dose selection was added after the original results as a geometric control. MAE uses NFA normalized response units and the original three-point design's unmeasured target set, with zero error at the newly observed concentration.

| Predictor | Random | Maximin | Highest unmeasured dose | Disagreement |
|:--|--:|--:|--:|--:|
| Interpolation | 0.957636 | 0.904011 | 0.936894 | 0.858613 |
| AnchorBoost, broad coverage | 0.841156 | 0.817798 | 0.807778 | **0.765536** |
| AnchorBoost, five designs | 0.844788 | 0.821015 | 0.809539 | 0.770248 |
| CNP | 0.863891 | 0.837427 | 0.818474 | 0.776620 |

Highest-dose selection supplies a strong comparison that can be chosen without the observed responses. For broad-coverage AnchorBoost, disagreement lowers error by **0.042242 [0.024617, 0.061329]**, or **5.2%**, beyond highest-dose selection. The policies coincide in 630 of 965 designs. The mean benefit persists when the highest concentration was already measured, supporting a contribution beyond high-dose geometry.

Across chemical-average errors, disagreement wins 76 times, highest-dose selection wins 61, and 56 tie; the two-sided sign test gives **p=0.231537**. The positive mean-effect interval reflects improvement size as well as win frequency. The gain comes both from measuring an informative point and from improving the forecasts that remain (Figure 4). Appendix B gives the decomposition, matched training budgets and concentration-specific well costs. Section 4.3 places the same choice inside the reporting decision, beside the variance rules of Gaussian-process and Hill-curve models.

![Figure 4. Choosing one additional concentration. Panel a shows a rule-selected example (Loperamide, fold 1, design 2): disagreement picks the interior concentration where the three forecasts differ most. Panel b gives MAE after acquisition across 193 chemicals and 965 designs, scored as in Table 5. Panel c shows chemical-average highest-dose minus disagreement error; positive values favor disagreement. Panel d counts designs in which rules choose the same concentration; disagreement and highest dose coincide in 630 of 965. Panel e places each choice relative to the three measured concentrations; Random is the exact expectation. Highest-dose selection is a post hoc geometric control.](figures/F3-acquisition.png){#fig-acquisition width=100%}

# 4. Forecast-based decisions settle more calls with fewer wells

## 4.1. From a reconstructed curve to an activity call

The acquisition test spends one additional concentration on reconstruction; the decision tests ask which designs can yield a call. An activity call is binary against the complete-series assay reference: a design is active when its largest absolute DIV-averaged response across concentrations and features reaches three on the normalized scale. Every rule first reports, as active, any design whose measured concentrations already reach that threshold, since its complete-series reference is then active by construction. For the remaining designs the rule accepts the predicted full-series call when its rank confidence margin exceeds a calibrated value, and otherwise completes the series.

Training, calibration and test identities remain separate, including grouped parent forms. Each plate is centered on its own vehicle controls and the response scale is estimated from training plates alone (scale B); scale A, which estimates the scale from all vehicle controls, is reported beside it. Drug-level conformal risk control (CRC) targets 10% expected marginal wrong-report loss under exchangeability [30]: each drug's loss averages wrong reports over its alternative starting designs. Appendix B.2 gives the splits, scales and finite-sample correction.

## 4.2. Three-point reporting and exposure-well cost

The four primary folds contain **188 identity groups, 193 substance labels and 965 designs**, five alternative starting designs per substance.

**Table 6. Three-point report-or-complete results.** Every rule uses the same drug-level calibration and reports directly the designs whose measured concentrations reach the activity threshold. Costs count the observed concentration-specific replicates, including completion of unresolved series; vehicle controls, assay failures and overhead are outside the count. Completing every series costs 28,080 wells across these alternative designs.

| Rule | Reports / 965 | Wrong reports | Completed series | Exposure wells |
|:--|--:|--:|--:|--:|
| AnchorBoost | **914** | 84 | **51** | **12,031** |
| Measured points only | 818 | 75 | 147 | 13,503 |
| Interpolation | 816 | 74 | 149 | 13,539 |
| Observed activity only | 583 | 0 | 382 | 17,653 |

AnchorBoost reports 96 more designs than the calibrated measured-only rule. At equal identity-group weighting the reporting-rate gain is **9.88 percentage points [6.79, 13.28]**, with a wrong-report-loss difference of +0.90 points [−1.07, 2.87]. Better classification comes before selection: reporting every design would give AnchorBoost 3.17 points lower error [−5.28, −1.06]. Its 102 additional reports include 26 wrong ones, offset by 13 fewer wrong reports among the 812 designs both rules report and by 4 among the measured-only rule's 6 sole reports (Figure 5).

Those reports cut exposure wells from 13,503 to 12,031: **10.90% fewer [7.67%, 14.23%]** than the measured-only rule and 57.15% fewer than complete measurement. On scale A the same comparison gives 925 reports against 822 and an 11.84% saving [8.40%, 15.36%]. Observed drug-average wrong-report loss is 8.78% [6.49%, 11.22%] against the 10% target, reaching 12.61% in one fold. The calibration targets expected marginal loss; error among reported calls and a bound for each future batch are distinct quantities.

The reporting analysis was revised twice after its first results had been seen. The response scale moved to own-plate centering with training-plate scale parameters, and every three-point rule then received the direct report of measured activity. The first version gave 946 against 806 reports with 15.24% fewer wells, and scale B without direct reports gave 884 against 690 with 19.33%; both favored AnchorBoost more. This report takes the current version as its main result, and Table B1 sets the versions side by side. The final demonstration video uses the current reporting and closed-loop results; its workbench segment retains the separately labeled historical 970-design replay.

The gain concentrates where a screen rations concentrations. AnchorBoost's reporting-rate gain is 6.65 points [3.50, 10.15] in the 406 designs whose start already includes the chemical's highest concentration and 13.70 points [9.35, 18.50] in the other 559. For the 169 test chemicals measured at exactly seven concentrations, we calibrated each of the 35 possible starts separately and selected one per fold on training and calibration identities alone. The selected start held the highest concentration in all four folds, and with it AnchorBoost, the measured-only rule and interpolation each report all 169 chemicals, with 8, 8 and 7 wrong reports. Across the 35 starts the gain is zero when the start reaches the top concentration (15 starts), 1.87 points [0.09, 3.92] one step below it (10) and 12.56 points [8.94, 16.20] two or more steps below (10). The calibration that sets the margin therefore also names the start to use, and prediction pays most for the compounds whose top concentration a screen has not run.

![Figure 5. Three-point reporting actions and exposure-well costs in the four primary test folds. Panel a orders the 965 designs by fold, full-series call and wrong-report count. Panel b crosses reported calls with the full-series reference; 65 of AnchorBoost's 84 wrong reports and all 75 of the measured-only rule's report an active reference as inactive. Panel c traces action transitions from the measured-only rule (743 correct reports, 75 wrong reports, 147 completed series) to AnchorBoost (830, 84, 51). Panel d counts exposure wells including observed replicates and series completion. Panel e gives identity-group-weighted paired differences with 95% intervals from 4,000 identity-group bootstrap resamples, holding fitted decisions fixed. Every rule reports directly the designs whose measured concentrations reach the activity threshold. These retrospective intervals describe between-drug variation conditional on the fitted rules. CRC denotes conformal risk control.](figures/F4-reporting.png){#fig-reporting width=100%}

## 4.3. One calibrated margin for reporting, adding a concentration or completing the series

Reporting and acquisition then run as one decision chain under a single exposure-well account. Each of the 965 designs is reported from its three concentrations or continues; a continuing design receives one further concentration, chosen by forecaster disagreement, and is then reported or completed. Both stages use the same margin, calibrated on calibration identities so that expected drug-level wrong-report loss stays at or below 10% whichever candidate concentration is added (Appendix B.2). The predictors are the frozen reporting models; none is refitted.

The chain reports 872 designs from three concentrations and 53 more after the fourth, and sends 40 to the complete series: **925 reports with 69 wrong from 12,119 exposure wells**, 56.8% fewer wells than complete measurement. Against the calibrated measured-only rule it gives 107 more reports [81, 134] and uses 10.2% fewer wells [7.7%, 12.8%], with a wrong-report-loss difference of −0.7 points [−2.5, 1.0]. Against three-point AnchorBoost it makes 15 fewer wrong reports [7, 24] for 88 more wells [−186, 395], lowering wrong-report loss from 8.78% to 7.18% (−1.60 points [−2.55, −0.74]). The fourth concentration corrected 33 calls and reversed three; all three then proceeded to the complete series, and the 53 reports it added were all correct.

**Table 7. Fourth-concentration rules inside the closed loop.** All rows share the 872 three-concentration reports, the calibrated margin and the well account; they differ only in the 93 designs that continue. Random is the exact expectation over candidate concentrations. Hill-var is the predictive variance of a Hill curve with an empirical-Bayes population prior; GP-IVR and GP-var are integrated variance reduction and posterior variance of a Gaussian process on log concentration. GP-var is a descriptive row computed from the same saved choices.

| Fourth-concentration rule | Reports / 965 | Wrong reports | Exposure wells |
|:--|--:|--:|--:|
| Disagreement among forecasters | 925 | 69 | 12,119 |
| Highest unmeasured dose | 928 | 70 | 12,083 |
| Maximin spacing | 911 | 71 | 12,253 |
| Uniform random | 906.65 | 71.5 | 12,334.8 |
| Hill-var | 917 | 71 | 12,190 |
| GP-IVR | 913 | 72 | 12,204 |
| GP-var | 912 | 69 | 12,244 |

An activity call defined by the largest response in the series is settled mostly at high concentrations, which disagreement and highest-dose selection both reach: the two differ by −3 reports [−9, 2], −1 wrong report [−3, 0] and 36 wells [−36, 114]. Disagreement arrives there without a rule that sends it. In the acquisition experiment of Section 3, 46.6% of its choices extrapolate above the measured range, 36.5% interpolate and 16.9% extrapolate below, against 57.9%, 40.1% and 2.0% for highest-dose selection, and it keeps the 5.2% reconstruction advantage of Table 5.

The classical variance rules add fewer reports for more wells. Against disagreement, reports differ by −8 [−18, 2] for Hill-var, −12 [−27, 1] for GP-IVR and −13 [−24, −3] for GP-var, and wells by 71 [−39, 179], 85 [−43, 227] and 125 [26, 234]. The fourth-concentration reports of Hill-var and GP-IVR include 2 and 3 wrong ones; those of GP-var and disagreement include none.

![Figure 6. Reporting, adding one concentration or completing the series under one exposure-well account. Panel a follows the 965 three-concentration designs: 872 are reported at once and 93 receive one further concentration chosen by forecaster disagreement; 53 of these are then reported and 40 proceed to the complete series, giving 925 reports, 69 wrong reports and 12,119 exposure wells against 28,080 for complete measurement. Panel b divides exposure wells into initial, added and completion wells for four fourth-concentration rules of Table 7 and the two three-point rules of Table 6, with their reports, wrong reports and error among reported designs. Panel c gives identity-group paired differences between the disagreement loop and each three-point rule; bars are 95% percentile intervals from 4,000 identity-group bootstrap resamples, conditional on fitted pipelines. Panel d plots wrong-report loss against exposure wells along the common-margin sweep; markers show each rule's calibrated working point and the closed loop, and the horizontal line marks the 10% target. The vertical comparison uses the loop's budget of 12,119 wells; Section 4.4 separately compares rules at the three-point budget of 12,031 wells.](figures/FX-loop.png){#fig-loop width=100%}

## 4.4. Fewer wrong reports at equal wells, fewer wells at equal error

Two rules compare cleanly only at equal cost or equal error, so we swept the reporting threshold of each three-point rule across every score boundary, 1,294 thresholds in all (Figure 6d). Within AnchorBoost's calibrated budget of 12,031 wells, the best measured-only threshold makes **110 wrong reports against 84**, a wrong-report loss higher by 2.66 points [0.85, 4.65]. At a loss ceiling of 8%, AnchorBoost needs 8.9% fewer wells [2.6%, 13.6%] when one margin applies across folds and 7.9% fewer [1.4%, 12.6%] when each fold's calibrated margin shifts by a common offset.

The closed loop reaches its 7.18% loss with **11.1% fewer wells [7.7%, 17.6%]** than the measured-only frontier requires under the calibrated-offset sweep. Against AnchorBoost's own three-point frontier at equal wells, its loss is lower by 1.06 points [0.11, 3.14] and 1.60 points [0.53, 2.61] under the two sweeps. For this activity call the fourth concentration buys accuracy that a stricter three-point margin does not.

## 4.5. Plates and culture dates absent from training

Chemical identity is one boundary between an archive and a new experiment; plates and culture dates are another. We partitioned the 237 identity groups into connected components that share no plate and no date, seven in all with the largest holding 177 groups, and drew training, calibration and test roles from different components. See Figure B1 for the held-out-component, chronological and forecast-degradation results.

In the four folds whose models train on 189–193 identity groups and are tested on plates and dates absent from training and calibration (50 groups, 255 designs), AnchorBoost reconstructs responses with **10.4% lower error than interpolation [6.4%, 13.8%]**, against 10.7% when only identities are separated. It reports 195 designs against 178 for the measured-only rule, with 22 against 24 wrong reports, on **6.6% fewer wells [1.9%, 11.7%]**. In a replay ordered by plating date, with every training, calibration and scale-estimation plate preceding the test block, AnchorBoost saves 8.94% of wells in the 2017 block [3.08%, 15.57%] and 5.57% in 2016 [−0.16%, 11.51%].

A fifth fold inverts the archive: 28 identity groups from the small components train, and the 138 primary groups of the largest component are tested. With that little training the learned correction sits 10.6% above interpolation [4.2%, 18.6%], and the reporting rule inherits it. On scale B it gives 667 reports against 571 on 14.3% fewer wells [10.4%, 18.3%] with wrong-report loss 4.64 points above the measured-only rule [1.59, 7.68]; on scale A it gives 483 against 551 on 12.7% more wells [6.9%, 19.7%] with loss matched (0.14 points [−2.32, 2.61]). The pipeline reads which regime it is in before a test well is spent: AnchorBoost's calibrated margin sits 0.12 below the measured-only rule's where the correction wins and 0.06 above it where interpolation does, so the calibration margins flag the change in predictor performance before test responses are read.

The margin also responds when forecasts degrade. With noise of growing scale added to the frozen forecasts and only the margin recalibrated, three-point exposure wells climb from 42.85% of the complete series to 62.87%, the point at which only designs already measured active are reported. The median wrong-report loss over seeds stays at or below 9.20% at every noise level, and error among reported designs peaks at 10.25%. As the predictor weakens, the rule buys measurements.

# 5. Calibrated envelopes hold back the liver-chip calls that would be wrong

A perfused liver-chip dataset tests the method on a second organ model, under a stricter rule and with responses withheld. A separate data custodian digitized the published 72-hour albumin and viability means of Bircsak et al. [37] for 21 drugs. Six drugs train the predictor, nine calibrate it and six are tested, with both endpoints of a drug kept together. The rule must resolve a reduction below half the lowest-concentration response through calibrated 90% response envelopes. Predictions, envelopes, actions and next concentrations were fixed before the custodian released the 46 withheld test responses.

Every withheld response fell inside its envelope, across all twelve drug–endpoint curves. The envelopes were wide, with mean widths of 174.81 percentage points for viability and 2,847.03 ng/mL for albumin, and each method requested a further measurement for all twelve curves. At three concentrations that was the right action: with zero-width envelopes the same frozen predictions would have reported all twelve curves as showing no reduction, and **seven of those calls would have been wrong**. The rule held back all seven (Figure 7).

Every frozen request asked for the highest unmeasured concentration. After release, the response there lay at or below the threshold in all seven curves that truly crossed it, so one further measurement settled each of them; the other five were measured to completion. Replayed to a decision for every curve, the frozen rule used **25 of the 46 withheld measurements** (61 of 82 concentration responses in all), with seven early calls and no early error. Choosing the next concentration at random would have taken 31.3 measurements in expectation, and starting from the lowest unmeasured concentration 41.

More calibration drugs would not have brought those calls earlier. Cross-fitting all 21 drugs and deriving the conformal quantile for calibration sets of 5 to 200 drugs keeps the median number of resolvable three-concentration calls at 0 of 12 at every size, at 90% and at 80% nominal coverage. Earlier calls require tighter response envelopes. More replicate chips per concentration provide a prospective way to test whether measurement variability can be reduced enough to resolve them.

The Ewart and Yuan perfused liver-chip tables hold six and five drugs [31,36]. Training-only selection among thirteen candidates, interpolation included, decides how much model such a cohort supports. Across 27 held-out drug-endpoint folds from eleven drugs, selection lowers Yuan LDH error by 6.74% and ALT error by 1.81% relative to the original model, and interpolation keeps the lowest mean error on both Yuan endpoints. Keeping interpolation among the candidates is what lets a six-drug cohort return it (Appendix C.4, Tables C2 and C3).

![Figure 7. Forecasts, requested measurements and errors in the liver-chip tests. Panel a shows six drugs and two endpoints, giving twelve Bircsak curves normalized to their own lowest-concentration response. The research response-reduction threshold is half that response (50%). Bold-outlined filled points are the three inputs; at hidden points, the outer ring is the training-selected prediction and the inner core the revealed published mean. A triangle marks the frozen next-concentration request. Point colors saturate at 0–100%; the right column retains the numerical scale for the requested-point prediction, revealed mean and 90% envelope. Diamonds above circles show forecasts and revealed means, respectively; their vertical offset separates the marks while preserving response values. After prediction freeze, the requested published means lie at or below threshold in 7 of 12 curves. Actions remain measure-next, with 0 of 12 reports. This retrospective test uses digitized 72 h means and custodian-separated prediction freeze; the envelopes concern these means and use the stored drug-level calibration. Appendix C.4 gives the source and calibration details. Panel b shows Ketoconazole viability in original % live iHep units against concentration in µM; its threshold, 44.886364, is half the lowest-concentration response. Panel c compares the five leave-one-drug-out endpoints in Table C2 and the two Bircsak endpoints in Table C3. Each ratio divides drug-equally-weighted MAE in the endpoint's original units by interpolation MAE; below 1 means lower error. Training-selected circles and original leaf-50 triangles occupy separate rows within each endpoint. Bars count drugs with lower, equal or higher training-selected error than interpolation. Row denominators are 6, 6, 6, 5, 4, 6 and 6 drugs. Drugs recur within studies, and endpoints retain separate comparisons.](figures/F5-liverchip.png){#fig-liverchip width=100%}

# 6. Running the method on a laboratory's own plates

## 6.1. Three concentrations in, forecasts and next steps out

`three_point.py` in the [public repository](https://github.com/logxio/ooc-evaluation-audit) takes a laboratory's plate table and returns the three actions of Section 4. The table has one row per well and endpoint, with the columns `compound, concentration, unit, endpoint, value, plate, date`; vehicle wells have concentration 0, and the completed compounds of the same endpoint in the file train the model. Each unfinished compound comes back with a forecast and a 90% interval at every concentration still to run and one next step: report the active or inactive call, add one named concentration, or complete the series.

```sh
python -m pip install -r requirements.txt
python three_point.py my_plates.csv
python three_point.py my_finished_plates.csv --reconcile three_point_my_plates
```

The command writes `forecast.csv`, a one-page `summary.md` and `lock.json`, which records the SHA-256 of the input, forecast, models, protocol and code with the UTC time. The lock fixes the forecast before the remaining plates are read; `--reconcile` then checks it against the finished series, concentration by concentration. Viability, albumin, MEA and imaging readouts from chips, organoids or well plates use the same table.

We ran this sequence on the US EPA human neural-cell screen of Harrill et al. [35], using its completed compounds to train and calibrate the model while keeping the unfinished test compounds apart. The locked forecasts precede the release of their remaining responses. Forecasts for 107 unfinished series, covering 15 compounds and 9 endpoints, came back in about a minute on a laptop CPU. Revealed after the lock, **2,318 of 2,520 hidden wells (92.0%) fell inside the 90% intervals**. The command called 53 series before they were finished, 2 of them wrong against the full-series call, and its next steps used 2,244 of 3,483 exposed wells, **35.6% fewer** than running every series to the end. The locked [summary](https://github.com/logxio/ooc-evaluation-audit/blob/main/three_point_example/forecast/summary.md) and its [check against the finished series](https://github.com/logxio/ooc-evaluation-audit/blob/main/three_point_example/forecast/reconcile.md) are in the repository, and `python three_point.py --example epa_dnt` writes the screen in this format. A table of completed series is replayed instead: across neurite length and viability in that screen, 545 three-concentration designs give 172 early calls with 16 wrong, where the same calibrated rule reading the measured concentrations alone makes 228 calls with 39 wrong ([replay](https://github.com/logxio/ooc-evaluation-audit/blob/main/three_point_example/replay/summary.md)).

## 6.2. Inspecting responses and exporting actions in the workbench

In the [Chip Forecast workbench](https://logxio.github.io/ooc-evaluation-audit/workbench/), **Chemicals** displays measured wells, reconstructed responses and empirical intervals alongside plate positions and comparator errors. Select a chemical and a three-concentration design, inspect where its forecast interpolates or extrapolates, and use **Download actions** to export the decision. **Your data** accepts a planned concentration layout and displays its saved held-out replay.

Figure 8 connects three curves to their actions. Trimethyltin hydroxide's predicted high-dose decline supports a correct active call. Terbufos's forecast also reaches activity, while its small rank margin sends the design to series completion. For Diazoxon, the predicted high-dose decline contrasts with a positive held-out mean. The response curve in c shows the discrepancy, and its labeled position in the historical decision plane in d places the wrong active report among all 970 replay designs.


![Figure 8. Curves and actions in the historical 970-design replay. Panels a–c display one DIV 12 feature with nominal 90% well-response prediction intervals and the saved action for each example. Panel d plots stored forecast activity score against rank margin. Score is the maximum absolute DIV-mean response across features and concentrations, combining measured inputs with forecast completion. Across all 970 designs from 194 chemicals, 826 reports agree with the full-series call, 79 reports disagree, and 65 designs request series completion. Labels a–c mark the three examples; the adjacent stacked counts use margin bins of width 0.04. The measured-reference cutoff is 3. Fitted forecast-call cutoffs are 2.9836 in fold 1 and 2.9994 in folds 2–4; their chemical-weighted mean, 2.9954, is drawn as one vertical line. Reporting requires margin strictly above 0.03 in folds 1–3 (horizontal line) and above 0 in fold 4. These saved historical actions are distinct from the 965-design analyses in Figures 5 and 6. COMPLETE SERIES adds the remaining measurements. Trimethyltin hydroxide uses design 5 here and design 1 in Figure 1.](figures/F6-cases.png){#fig-cases width=100%}


The **Patients** view makes measured organoid responses and published clinical outcomes inspectable in the same way. Open the rectal cohort and select **Reveal outcomes** to compare the calls with their reference, then **Download actions** to export the patient list (Figure 9). Compatible patient tables can be pasted and processed in the browser, with measurements kept on the local machine.

On the fixed 43-patient rectal test split, the measured combined-regimen signal yields 43 reports with one wrong call, versus 27 reports with four wrong calls for the earlier agreement rule. The fixed combined-signal cutoff gives the same result as calibration, locating the gain in the measured assay. Appendix C presents the regimen-matched comparison, its failed equal-risk target against the strongest single component, and the action-level costs.

![Figure 9. Inspecting the published rectal-cancer cohort after revealing outcomes. Both axes show day-24/day-0 organoid size ratios on log scales. Teal filled/open markers denote sensitive/resistant calls; red marks the single wrong call among 43 patients. Download actions exports the patient call list. The header's 56.6% saving refers to the historical chemical-screen replay.](workbench/shots/reveal.png){width=100%}

# 7. Discussion

Completed concentration-response curves contain training examples for every sparse design a laboratory could run. Learning across those designs makes an archive useful beyond the concentrations chosen in any one experiment: on the same folds and metric, AnchorBoost leading a residual stack beats all 32 published predictor configurations we could run at three concentrations and loses none of 98 comparisons at one to four. One calibrated margin turns AnchorBoost's forecasts into three actions, each with a price in wells and a bound on wrong reports. On the EPA screen the chain reports more designs than the measured-only rule with fewer wrong reports and fewer wells; at equal wells it makes fewer wrong reports; and its advantage carries to plates and culture dates absent from training. In the liver-chip test the same logic held back every call that would have been wrong and sent the next measurement to the concentration that decided it.

The next experiment is prospective. Three initial concentrations go onto the chips; `three_point.py` locks its forecasts and actions before the remaining wells are read; unresolved compounds receive the concentration on which the forecasters disagree; and the lock is reconciled when each series finishes. A matched fixed-budget comparison across independent culture batches then counts completed chemical assessments, wrong reports and the full laboratory cost. The stack's lower forecasting error is the next input to the same calibrated rule. Every saving here replays archived plates, and the well counts cover exposure wells; the prospective run adds the wet-laboratory record of vehicle controls, repeats, failed assays and staff time. Our aim is to make response-guided measurement a routine part of organ-chip screening, so that the same culture budget reaches more compounds and more biological contexts.


# Appendix A. Forecasting methods and sensitivity analyses

![Figure A1. Locating response examples within the distribution of gains over interpolation. The upper strip ranks all 194 chemicals by AnchorBoost minus interpolation MAE over all recorded outputs and five designs; examples a–c occupy ranks 1, 98 and 194, with rank 98 representing the middle of this even-sized set. Each curve retains the DIV 12 feature with the greatest measured concentration variation, the chemical's first published three-point design and its own fold model. Open circles reveal held-out measured means against the predictions. Panel d shows per-output absolute-error differences (AnchorBoost minus interpolation), averaged first over hidden target concentrations and then over five designs, for 17 features across DIV 5, 7, 9 and 12. Negative values favor AnchorBoost; gray cells lack a recorded target. Panel e compares AnchorBoost, interpolation and CNP MAE over all recorded outputs and five designs, extending beyond the single feature and design in a–c. The largest loss is retained alongside the largest gain and middle-ranked example.](figures/A1-examples.png){width=100%}

## A.1. Model specification and frozen development protocol

The public EPA network-formation benchmark contains 243 chemicals and 6,902 exposed wells, with 17 features on days in vitro (DIV) 5, 7, 9 and 12 [32,33]. A nominal seven-concentration series in triplicate uses 21 exposure wells and follows firing, bursting and synchrony over twelve days. We use the NeuroChip Twin v2 packaging, five chemical folds and five seeded context designs per chemical and concentration count. The primary static comparison uses three measured concentrations and the 194 chemicals in folds 1–4; fold 0 supplied method development. The target is the mean response at an unmeasured concentration. Absolute errors are averaged over available day-feature entries and designs within a chemical, then equally across chemicals.

The published CNP comparator uses an interpolation-informed decoder, local dose attention and a three-seed ensemble. Our implementation reproduces its published interpolation errors within 0.0001 for every chemical at one to four measured concentrations. Features and hyperparameters were frozen publicly before evaluation of folds 1–4.

For a training chemical with L concentrations, AnchorBoost enumerates the possible three-concentration contexts. It interpolates in log concentration with flat continuation outside the measured range, then learns the residual at each remaining concentration.

The static model is scikit-learn's `HistGradientBoostingRegressor` with absolute-error loss, 600 iterations, learning rate 0.05, at most 127 leaves, minimum leaf size 50 and early stopping disabled. The target is the concentration-mean response minus log-concentration interpolation. Features comprise that interpolation, measured response levels and slopes, gaps and extrapolation distances, query position, measured activity summaries, Hill and analog deviations, and output day/feature identity. The analog pool contains the ten nearest training chemicals and excludes each chemical from its own training examples. Missing responses retain their masks.

At three measured concentrations, full scalar enumeration produces approximately 2.6 million training rows per fold. Eleven configurations were tried on development fold 0; `chip_forecast_protocol.json` retains each entry and the selected fold-0 error of 1.061. Public commit `2b4c20e` froze the protocol before primary scoring. Amendment `0cff5d2` fixed the single-concentration slope case; feature arrays for 1,080 designs at two to four concentrations remained identical. The static protocol's bootstrap uses 4,000 chemical resamples, seed 0; the released strong-baseline package uses 10,000 and supplies the more precise CNP intervals in Table 2.

**Table A1. Mean absolute reconstruction error by measured-concentration budget, in NFA normalized response units.** All rows use the original 194 chemical labels; the remaining unmeasured concentrations define each row's forecast targets.

| Measured concentrations | AnchorBoost | Interpolation | Published CNP |
|:--|--:|--:|--:|
| 1 | 1.393 | 1.893 | 1.421 |
| 2 | 1.252 | 1.549 | 1.283 |
| 3 | 1.161 | 1.345 | 1.194 |
| 4 | 1.112 | 1.254 | 1.143 |

Fold 1–4 three-point MAEs are 1.221/1.150/1.110/1.162 for AnchorBoost, 1.219/1.200/1.146/1.212 for CNP and 1.378/1.321/1.327/1.356 for interpolation. Among 63 reference-positive chemicals, AnchorBoost/CNP/interpolation errors are 1.293/1.345/1.496; among 15 negatives they are 0.936/1.029/1.008; among 116 without a reference label, 1.118/1.133/1.307. Reference toxicant labels stratify this analysis; the forecast target remains the measured response.

The largest AnchorBoost–CNP gains occur for colchicine (−2.23), valinomycin (−0.95) and cadmium chloride (−0.89); losses include sodium valproate (+1.06), chlorpromazine (+0.37) and spiroxamine (+0.32). Per-chemical errors are saved in `chip_forecast_result.csv`. The original five-design ablation used fewer scalar rows than enumeration; the row-matched result in the main text supplies the controlled coverage comparison. Removal of the interpolation anchor or Hill deviation gave differences of +0.009 [−0.007, 0.034] and +0.004 [−0.001, 0.010], respectively.

The matched-budget coverage comparison retains its improvement after removing phenobarbital: −0.023175 [−0.035216, −0.012254] across 193 chemicals. A complementary series gives MAE 1.176, 1.174, 1.166 and 1.161 for five, ten, twenty and all available designs, with row counts increasing alongside coverage. Removing the analog feature raises error by 0.019 [0.011, 0.029]. Residual prediction minus direct-response prediction gives −0.008573 [−0.033706, 0.006656].

## A.2. Response intervals and cross-screen preprocessing

The historical workbench bands use a quantile booster trained on absolute well errors: quantile 0.9, 300 iterations, 31 leaves. Inputs include measured concentration distances, replicate spread, response level and activity. Cross-fitting width models and calibration across the other folds yields empirical coverage **0.900 [0.895, 0.905]** over **964,187 well-by-day-by-feature entries**, with mean half-width 3.74. These entries are repeated outputs from the held-out chemicals. A fixed per-output quantile gives coverage 0.896 and half-width 4.19; the width ratio is 0.892 [0.873, 0.911]. CNP reports coverage 0.899 and half-width 3.71 using a different nonconformity construction, including full-series cytotoxicity strata.

This historical cross-conformal experiment and the new nested evaluation have separate preprocessing and calibration paths. The nested bands use training-inner residuals and are descriptive. The reporting rule operates on an activity-score rank margin rather than either interval's width.

Acute and human-screen preprocessing centers on plate vehicle wells, scales readouts by robust vehicle standard deviations and clips to ±10. The human source excludes rejected wells and keys one ambiguous plate by position and sample. Its five chemical-fold sizes are 12/17/14/13/15. The external neural comparisons use the released CNP code, original configuration and three seeds on the same contexts. They merge the acute source's 384 labels into 383 identities and use 69 identity-clean human chemicals. Their wider 97.5% intervals are [−0.032964, 0.000778] and [−0.122864, 0.022714]. Cross-screen identity overlap remains part of the evidence record.

A separately released screen-out neural experiment trains on the other screens. On one held-out fold of each rat MEA screen, it improves over interpolation by 4.5% and 7.2%; within-screen AnchorBoost remains ahead by 0.095 and 0.115. Its public CPU notebook aggregates frozen predictions: 326 drug-endpoint results and 26 main-table rows match exactly. The package separates this statistical reproduction from the original neural training.

## A.3. Predictors pretrained on bioassay labels for the test compounds

Monroe-based predictors have prior supervised bioactivity information about most chemicals in this benchmark. We therefore report their results separately from the main comparison. The [Monroe encoder](https://github.com/blazejba/monroe) was pretrained jointly on computed quantum-chemical properties and supervised binary outcomes in [PCBA](https://zenodo.org/records/8024997). Matching the released corpus to the 243 benchmark compounds finds 229 with PCBA labels, including 181 of the 194 primary test chemicals. Across the full benchmark, 220 compounds have Tox21 labels and 215 have acetylcholinesterase-inhibition labels, with 47 positive compounds. The corresponding acetylcholinesterase counts in the 194-chemical test cohort are 169 and 40. These are prior activity answers for the same compounds at related biological targets; the corpus audit found zero MEA, network-formation or ToxCast/invitrodb assays. The overlap concerns related bioactivity supervision rather than the exact response endpoint forecast here.

The structure-only comparison uses [CheMeleon](https://github.com/JacksonBurns/chemeleon), whose pretraining targets are 1,613 computed molecular descriptors. Its released corpus contains structures for 210 of the 243 compounds, including 164 of the 194 primary test chemicals, with no experimental activity labels in its pretraining objective. Replacing Monroe with CheMeleon in the otherwise matched TabPFN-3.5 configuration gives the CheMeleon row of Tables 4 and A2. KANO and MotiL use the same 250,000-molecule ZINC15 pretraining corpus; the structure audit found zero matches among the benchmark compounds. Seven benchmark entries have no verifiable single molecular structure and remain unverified in structure-based matching.

The audit compares the connectivity block of InChIKey for the complete structure and its parent form, checks individual corpus fragments and uses PubChem identifiers where available. Element and connectivity checks preserve active metal-containing compounds when removing fragments would change their identity. The retained overlap counts describe compounds with confirmed corpus matches; unverified compounds are recorded separately.

**Table A2. Structure-only versus related-bioactivity pretraining.** The first row uses the structure-only CheMeleon encoder; all remaining rows use Monroe. MAEs are listed for k=1, 2, 3 and 4. Reference columns follow Table 4: outcome at k=1–4 (W win, = tie, L loss, — not run), then the k=3 difference, reference minus row, with its paired identity-group 95% interval. The last row was normalized on a training-only scale and has no paired comparison on the standard scale.

| Predictor | MAE at k=1, 2; 3, 4 | Stack − row | CPU − row | Alone − row |
|:--|--:|--:|--:|--:|
| TabPFN-3.5 + AB + CheMeleon | 1.3472, 1.2244; 1.1569, 1.1029 | W W W W · −0.0399 [−0.0559, −0.0251] | W = = = · −0.0029 [−0.0201, +0.0136] | L L = = · +0.0037 [−0.0162, +0.0247] |
| TabPFN-3.5 + AB + Monroe | 1.3268, 1.2118; 1.1474, 1.1003 | W = W W · −0.0305 [−0.0476, −0.0132] | = = = = · +0.0065 [−0.0123, +0.0251] | L L = = · +0.0132 [−0.0104, +0.0380] |
| LimiX-2 + AB + Monroe | —, —; 1.1306, — | — — = — · −0.0136 [−0.0312, +0.0055] | — — L — · +0.0234 [+0.0004, +0.0465] | — — L — · +0.0301 [+0.0028, +0.0567] |
| AnchorBoost + Monroe | 1.3512, 1.2448; 1.1648, 1.1228 | W W W W · −0.0478 [−0.0661, −0.0290] | = W = = · −0.0108 [−0.0257, +0.0040] | L = = = · −0.0042 [−0.0204, +0.0133] |
| AnchorBoost-v2 DWS + Monroe | 1.3555, 1.2361; 1.1513, 1.1148 | W W W W · −0.0343 [−0.0490, −0.0184] | W = = = · +0.0027 [−0.0101, +0.0151] | L = = = · +0.0093 [−0.0111, +0.0313] |
| AnchorBoost-v2 + Monroe | —, —; 1.2032, — | Separate scale | Separate scale | Separate scale |

Encoders that saw bioactivity labels for these chemicals still fall behind the stack at three concentrations: it beats TabPFN-3.5 with Monroe (−0.0305 [−0.0476, −0.0132]), AnchorBoost with Monroe and AnchorBoost-v2 DWS with Monroe, and ties LimiX-2 with Monroe (−0.0136 [−0.0312, +0.0055]). With the structure-only CheMeleon encoder in place of Monroe, TabPFN-3.5 reaches MAE 1.1569 against 1.1474; the stack beats it by −0.0399 [−0.0559, −0.0251], and the CPU single model and AnchorBoost alone tie it.


# Appendix B. Next-concentration selection and reporting calibration

## B.1. Acquisition policies, scoring and exposure-well costs

The full four-fold acquisition experiment includes 194 chemical labels and 970 initial designs. The common comparison in Table 5 removes phenobarbital to match the historical CNP identity sensitivity. Both AnchorBoost arms are trained jointly for three- and four-point contexts, with equal scalar rows, features and 600 iterations; CNP uses its original three-seed checkpoints. Each context in the broad design pool has training rows. Predictions are recomputed from the enlarged context after acquisition, with zero gradient updates.

The highest-dose control was specified after the original three-policy results. For broad-coverage AnchorBoost, highest-dose acquisition improves on random by 0.033379 [0.012006, 0.054253]. Its paired intervals use 10,000 chemical bootstrap samples, seed 0, conditional on fitted models. Among common designs with the highest concentration already measured, the highest-minus-disagreement effect is +0.038502 [0.019546, 0.059033]; among those with it initially absent, +0.048033 [0.025690, 0.073603]. The strata contain 181 chemicals/406 designs and 190 chemicals/559 designs, with 178 chemicals present in both. Each stratum averages designs within a chemical before averaging chemicals.

The mean error difference decomposes into the selected point's measurement contribution, **0.029504 [0.015705, 0.044897]**, and reconditioning at the remaining targets, **0.012738 [0.005575, 0.021083]**. This is an arithmetic decomposition of saved predictions. On the 193-chemical common cohort, the coverage-by-acquisition difference-in-differences against random is −0.001080 [−0.006528, 0.003633]. Under identical disagreement-selected doses, broad AnchorBoost minus CNP is −0.011084 [−0.027840, 0.004367].

Disagreement is the across-predictor standard deviation, averaged over available day–feature outputs at each candidate concentration; the policy selects its maximum. Maximin instead maximizes the distance to the nearest measured log concentration.

Each policy spends one extra concentration per design, and replicate counts vary by concentration. On the complete 194-label ledger, 2,910 initially measured concentrations become 3,880. Final exposure-well totals are 15,077 for highest, 15,129 for disagreement, 15,083 for maximin and an expected 15,186.478175 for random. The policy comparison matches concentration count, with these separate well costs. The local 49-chemical pilot is retained in its own directory; Table 5 uses the complete four-fold Kaggle outputs.

## B.2. Identity splits, response scales and drug-level calibration

**Identity splits.** The full reporting population contains 237 conservative identity groups from 243 substance labels and 1,215 designs. DTXSID/SPID mappings and parent grouping join phenobarbital forms, tributyltin forms, manganese salts, allethrin/stereoisomer and DDT/isomer. These are conservative partition groups; pharmacological equality is a separate question. A group takes its lowest original fold, moving four substance assignments, and all sources of a group remain in the same role. In each outer fit, two of the remaining folds train and two calibrate, giving 97–98 training, 91–95 calibration and 45–49 test groups. The four primary folds (188 groups, 193 labels, 965 designs) carry every reporting result of Section 4; the historical development fold supplied method development.

**Response scales.** Scale B serves every reporting analysis. Each plate is centered on its own vehicle controls, and an asinh scale and a robust standard deviation for each recording day are estimated from the vehicle controls of training plates alone, with test-plate controls used only to center their own plate. Scale parameters are fixed from training plates. Scale A keeps the own-plate centers and estimates the scale parameters from all 4,112 deduplicated vehicle-control well records. The complete-series activity reference is computed in the same scale: a design is active when its largest absolute DIV-mean response over all concentrations and features is 3 or more.

**Scores, cutoffs and direct reports.** Within each outer fold, the transformation, the predictor, its analog library and all rules see training identities only. An activity score is the largest absolute predicted or measured DIV-mean response across concentrations and features. Two inner folds within the training identities provide out-of-fold scores; the cutoff for the active call maximizes drug-weighted balanced accuracy, and the confidence of a call is the absolute difference between the weighted empirical rank of its score and that of the cutoff. Before the margin applies, every rule reports as active a design whose three measured concentrations already reach the activity threshold; these direct reports enter calibration with zero loss. Calibration then selects only the reporting margin. Test predictions and actions are saved and hashed before the remaining responses are scored. Checks on the completed pipeline perturbed hidden response values and masks and found a maximum prediction change of zero.

**Calibration.** For drug g and design d, let the predicted and full-series activity calls be $\widehat{a}_{gd}$ and $a_{gd}$, and the rank confidence margin be $m_{gd}$. The calibration loss averages wrong reports across the drug's $D_g$ alternative designs:

$$
L_g(\lambda)=\frac{1}{D_g}\sum_{d=1}^{D_g}
\mathbf{1}\{m_{gd}>\lambda\}\,\mathbf{1}\{\widehat{a}_{gd}\ne a_{gd}\}.
$$

The selected margin is the smallest fixed-grid value satisfying

$$
\frac{\sum_{g=1}^{n_{\mathrm{cal}}}L_g(\lambda)+1}
{n_{\mathrm{cal}}+1}\leq 0.10.
$$

Each drug contributes one bounded loss, regardless of its number of substance labels or designs. With independent training and exchangeable calibration/future drugs, conformal risk control concerns expected marginal drug loss [30]. The margin grid is −1, 0, 0.01, …, 1, with strict acceptance `margin > lambda`; a margin of −1 reports every design. Margins and corrected losses are compared in exact rational arithmetic. An empty feasible set sends every design to complete measurement; fewer than nine calibration drugs cannot satisfy the 10% correction even with zero empirical loss. Three-point AnchorBoost selects margins 0.04, 0.03 and 0.08 in folds 1–3 and reports every design in fold 4.

**Closed loop.** For a calibration design, let $e_3$ and $m_3$ be the error indicator and confidence of its three-point call, and $e_{4c}$ and $m_{4c}$ those of its four-point call after adding candidate concentration $c$. The envelope loss

$$
U_d(\lambda)=\max\Bigl\{e_3\,\mathbf{1}\{m_3>\lambda\},\ \max_c\, e_{4c}\,\mathbf{1}\{m_{4c}>\lambda\}\Bigr\},
$$

averaged within identity group, bounds the wrong-report loss of any policy that reports at three points or after any single added concentration, so one margin controls both stages for every fourth-concentration rule. The margin is the smallest grid value satisfying the same corrected inequality at 0.10; the selected margins are 0.08, 0.07, 0.09 and 0.04 in the four folds. Four-point predictions recondition the frozen three-point model on the expanded context. A design reported at three points is charged its three measured concentrations; a continuing design is charged the wells of its fourth concentration and, if completed, the remaining wells of the series. Each choice is written to disk before the selected response is read. The Gaussian-process and Hill empirical-Bayes models are fitted per output on each outer fold's training identities and only choose the fourth concentration; reporting stays with the AnchorBoost margin.

**Costs and intervals.** The exposure-well cost is the sum of the measured wells for reported designs and the full series for completed designs. The full-series label is a measured in-vitro reference, so its self-comparison has zero error by construction. The observed-activity rule also has zero error: a maximum-response threshold crossed at a measured concentration is necessarily crossed in that concentration's full series. Intervals are paired 95% percentile intervals from 4,000 identity-group resamples with seed 0, conditional on fitted models, selected margins and saved choices. Counts and well totals are resampled as totals over the sampled groups, and rates and losses as identity-group means.

**Sweeps, starts and degraded forecasts.** The sweeps of Section 4.4 scan the test set at fixed models, cutoffs and confidence mappings. The common-margin path applies one margin to all folds; the calibrated-offset path shifts each fold's calibrated margin by a common offset and passes through the calibrated working point. Matched comparisons re-optimize within every bootstrap resample: at a loss ceiling each rule takes the threshold with the fewest wells whose resampled loss stays within the ceiling, and at a well budget the threshold with the lowest loss whose resampled cost stays within the budget. The starting-design analysis of Section 4.2 reuses each outer fold's frozen transformation, predictor, cutoff and rank mapping; each start, method and fold receives its own margin from the seven-concentration calibration identities. The degradation analysis of Section 4.5 adds standard normal noise, scaled by a multiple of each output's residual standard deviation, to the frozen forecasts of calibration and test chemicals alike, for seven scales from 0 to 8 with five seeds each, and recalibrates only the margin.

**Plates and culture dates.** Two identity groups are linked when any of their records share a plate or a culture date. The 237 groups form seven connected components of 177, 16, 12, 11, 9, 6 and 6 groups. Four folds train on the largest component with small ones (189–193 groups) and test on other small components; one trains on 28 groups from small components, calibrates on 32 and tests on the largest. Scoring is restricted to the primary population, so the four large-archive folds score 50 groups and 255 designs and the small-archive fold 138 groups and 710 designs. The plating-date replay dates each identity group by its first plating. At an origin date, the archive holds the groups whose plates all precede the origin, and the test block holds the groups first plated in the following calendar year; models, cutoffs, rank references and margins are fitted at every origin with the reporting procedure.

![Figure B1. Reporting on plates and culture dates absent from training and under degraded forecasts. Panel a compares four large-archive held-out-component folds, covering 50 identities and 255 designs; intervals describe exposure-well saving versus measured-only and MAE reduction versus interpolation. Panel b replays screening chronologically by plating date, with 90 identities and 460 designs in 2016 and 67 identities and 340 designs in 2017. Error bars are paired identity-group 95% bootstrap intervals. Panel c adds noise to frozen calibration and test forecasts and recalibrates the reporting margin across 965 designs from 188 identities. Points are medians over five noise seeds; shaded bands are median bootstrap 95% bounds. Noise is scaled by each output's training residual standard deviation.](figures/FY-shift.png){#fig-shift width=100%}

**Analysis versions.** The reporting analysis was revised twice after its first results had been seen. The first version refitted the response transformation inside every outer fold. Scale B replaced it so that one scale, centered on each plate's own controls, serves every reporting analysis, including plates absent from training. Inspection of the scale-B decisions then showed that the calibrated measured-only rule sent 128 designs whose measured concentrations were already active to full measurement, so every three-point rule received the direct report, specified in a protocol amendment frozen before any reading with it was computed. Both earlier versions favored AnchorBoost more (Table B1).

**Table B1. Reporting results across analysis versions and response scales.** 188 identity groups and 965 designs in the four primary folds. The rule columns give reports / wrong reports / exposure wells; differences are AnchorBoost minus the calibrated measured-only rule. All rows use the same 4,000 identity-group resamples. Relative to the first version, the main-text analysis lowers AnchorBoost's reporting-rate advantage by 4.68 points [0.48, 8.94] and its well saving by 4.34 points [0.72, 8.18]. The final demonstration video uses the current reporting results and labels its historical workbench segment separately.

| Analysis version | AnchorBoost | Measured points only | Reporting-rate difference, points | Wells saved, % |
|:--|--:|--:|--:|--:|
| Scale B with direct reports (main text) | 914 / 84 / 12,031 | 818 / 75 / 13,503 | 9.88 [6.79, 13.28] | 10.90 [7.67, 14.23] |
| Scale A with direct reports | 925 / 83 / 11,851 | 822 / 78 / 13,443 | 10.57 [7.30, 14.06] | 11.84 [8.40, 15.36] |
| Scale B without direct reports | 884 / 84 / 12,414 | 690 / 75 / 15,389 | 20.25 [15.97, 24.63] | 19.33 [15.59, 23.05] |
| First version: fold-specific transformation, no direct reports | 946 / 77 / 11,588 | 806 / 75 / 13,671 | 14.56 [11.06, 18.23] | 15.24 [11.89, 18.45] |

## B.3. Historical 970-design reporting results

**Table B2. The earlier public decision replay, kept as a separate experiment.** These are the values behind the current public workbench and `ledger/` outputs.

| Historical rule | Reports / 970 | Wrong / all | Wrong / reports | Exposure-well equivalents |
|:--|--:|--:|--:|--:|
| AnchorBoost | 905 (93.30%) | 79/970 (8.14%) | 79/905 (8.73%) | 12,240 |
| Measured points only | 711 (73.30%) | 79/970 (8.14%) | 79/711 (11.11%) | 15,373 |
| Complete series | Reference | Reference | Reference | 28,185 |

The historical saving is **56.6%** relative to complete measurement and **20.4% [16.5%, 24.0%]** relative to measured-only fallback. Initial measurements account for 11,395 wells and fallback adds 845. A uniform seven-concentration, triplicate model gives 53.3% instead; concentration counts and observed replicate allocation explain the difference. A separately outcome-selected 5% operating point reports 74.4% versus 56.4% of designs. That operating point is a retrospective sensitivity.

The earlier forecaster and calibration roles overlapped, calibration counted design rows, and preprocessing used global controls. The nested refit separates all three. Identity grouping and normalization also change, so the numerical difference between 56.6% and the 57.15% of Section 4.2 combines several changes. The original static 194-label benchmark, the 193-chemical CNP/acquisition sensitivity and the nested 188-group analysis answer different questions. Even where both newer analyses contain 965 designs, their grouping, fits and response scales remain distinct.

Figure 8 illustrates three saved actions. Trimethyltin hydroxide, design 5, reports activity correctly after nine exposure wells. Terbufos, design 4, has rank margin 0.0286 below the historical 0.03 threshold and requests all 21 wells. Diazoxon, design 3, reports activity despite an inactive measured reference, driven by its predicted high-dose response.

A still earlier fixed low/middle/high design on an 81/81/81 split reports all 81 test chemicals with six errors (7.41%, exact interval 2.77%–15.43%). At the observed 10% budget it leaves zero reporting headroom. It is retained as a ceiling case for that particular fixed design and endpoint.

# Appendix C. Patient and organ-chip validation

## C.1. Organoid response and patient-action comparisons

The patient workflows use source-specific endpoints and treatment maps. Their output is a research follow-up action. Clinical treatment effects and outcomes of actual retests remain outside these replays.

For the 43-patient rectal workbench example, the data split is 42 training, 42 calibration and 43 test patients. The primary regimen-matched subset contains 36 test patients receiving radiation, capecitabine and irinotecan; the assay uses 5-FU as capecitabine's proxy. The measured combination reports 36 with one wrong call, versus 20 with three wrong for the older agreement rule. The coverage difference is +44.44 points [27.78, 61.11]. The remaining seven test patients lack clinical irinotecan and belong to the all-patient sensitivity.

Training selects irradiation as the strongest single component. Under the same calibration it reports 12 of the matched 36, with six errors, exceeding the registered 10% overall-error target at 16.67%. The primary equal-risk comparison therefore fails. At full coverage, the combination makes one error versus twelve for that component, a 30.56-point reduction [13.89, 47.22], paired exact p=0.00342. Adding the separately defined seven-patient pancreatic mean-rank comparison gives a descriptive 43-patient, source-stratified reduction of thirteen errors; its different endpoints and comparators remain separate from calibration.

The all-patient action comparison converts sixteen retests to correct reports and corrects four earlier errors, while adding one new error and leaving twenty-two calls unchanged. At retest cost 0.25 relative to a wrong call, batch loss falls from eight to one. That seven-unit gross reduction supports a break-even additional assay cost of **7/43 = 0.16279 wrong-call equivalents per patient**. At an added assay cost of 0.20, batch loss instead rises by 1.6 units. Actual monetary and staff-time costs require measured inputs.

**Table C1. Frozen-prediction organoid replays.** Counts are source-specific; the rectal analyses and Figure 9 reuse the published cohort. A freeze before opening individual outcome values is a computational sequence on published studies.

| Source and primary endpoint | Evaluation units | Correct / reported | Outcome access and comparator |
|:--|:--|:--|:--|
| Biliary, disease course [25] | 10 patients, amended labels | 6 / 7 | Registered-word subset: 3 / 4 in 7 patients |
| Gastric, disease course [24] | 12 patients, amended labels | 4 / 9 | Registered-word subset: 4 / 6 in 8; weak single-drug signals |
| Rectal, TRG 0–1 or clinical complete response (cCR) [28] | 85 patients | 43 / 50 | Patients 1–42 were exposed before freeze and are separate |
| Liver metastasis, disease control [29] | 23 patients | 14 / 15 | Primary-tumour-only sensitivity: 12 / 18 |
| Tan, composite benefit [38] | 22 treatments in 18 patients | 10 / 13 | Better single readout: 17/22 correct; combination: 16/22 |
| Tiriac, PFS ≥6 months [39] | 7 patients | 4 / 4 | Frozen mean rank: 7/7 correct; anchor: 5/7 |
| Wang lung, CR/PR [40] | 12 test patients | 3 / 4 | Equally calibrated fixed cutoff gives identical actions |
| Cartry, PR/SD [41] | 5 metastatic patients | 4 / 5 | Always benefit also gives 4/5; exact-drug subset 2/3 |

The first gastric/biliary freeze omitted the outcome words “metastasis” and “death”; both the original and amended analyses are retained. One biliary identifier was reconciled through matching assay values. For rectal and liver-metastasis data, the agreement formula and tolerance were frozen first, while its numeric inputs were the single-readout accuracies observed after opening outcomes. The resulting 0.863 and 0.928 values differ from released accuracy by 0.003 and 0.005; these are checks of a frozen formula. A correlation correction worsened later prediction. The combined rectal assay itself classifies 78/86, outperforming the two-component agreement approach.

Tan's first-treatment-per-patient sensitivity has 11 reports with eight correct among eighteen patients. An outcome-informed strict regimen subset has five reports with four correct among eight patients. The original map substitutes a two-drug pair for three FOLFOXIRI treatments and ignores added antibodies. At retest cost 0.25, the primary agreement rule loses to the better single readout (0.239 versus 0.227 per treatment); its break-even cost is 2/9.

Tiriac's reference distributions use fifty nonclinical patients, excluding clinical patients and sibling organoids. Layout was seen before outcome values. All drug subsets were frozen; plotted PFS times retain reading intervals. The pilot predicts 70.83% released accuracy and the primary test gives 100% on four releases; zero errors on the seven-patient full-coverage mean-rank rule still has a 34.82% single-rule upper 95% error bound. Wang assigns 12/12/12 patients to training/calibration/test before staged label opening. Its forecast of 91.67% released accuracy becomes 75%; both calibrated rules report four with one error, hence 8.33% overall and 25% conditional error.

Cartry freezes five metastatic patients before reading individual outcomes, routing six adjuvant patients to linkage review. The rule uses the source's largest component score strictly above 1.9. Aggregate paper results were already known and the analyst controlled concealment. Primary accuracy is 80% [37.55%, 96.38%]; the paired test against always no benefit gives p=0.25. CGR0010 is the wrong no-benefit call. The three exact-drug patients give 2/3, while always benefit gives 3/3. These sources are reported separately from the previously analyzed rectal signal comparison.

## C.2. Agreement rules and calibration in small cohorts

For two binary readouts with independent correctness probabilities p1 and p2, accuracy among agreements is `p1*p2 / (p1*p2 + (1-p1)*(1-p2))`. It exceeds the better readout's accuracy when the weaker readout exceeds chance. Shared errors change that forecast. For a fixed agreement gate with r disagreements, let d1 and d2 count the disagreements where each readout is wrong. Its break-even retest prices are d1/r and d2/r and sum to one. This is an error-plus-perfect-retest cost identity, with reject-option and dependence precedents [26,27].

A corrected patient CRC implementation learns cutoffs, reference distributions and the margin family outside calibration. At 10%, the primary rectal/liver-metastasis/Tan splits report 27/43, 0/9 and 0/6, with four, zero and zero wrong calls. Larger-calibration sensitivities retain realized risk failures: rectal has four errors in 26 test patients, and Tan has one in five at 10%/15% and two in five at 20%. Exact-binomial conditional calibration returns all-retest for all nine source-by-level settings. A single fixed rule needs at least 29 error-free accepted calibration patients to certify 10% at 95% confidence; the three-source confidence allocation needs 39.

A pooled rank-logistic candidate reports 21/43 with seven wrong, versus 14/43 with six wrong for an equally calibrated single readout. Both exceed the intended observed budget. The combined-regimen signal in Section 6.2 provides the useful alternative, and its fixed-threshold equality identifies where that benefit comes from. Yao's eighty-patient supplement overlaps the already used rectal cohort and contributes zero confirmed independent patients.

## C.3. Physical-chip endpoints and experimental timing

On Dai's 22 vascularized colorectal tumoroid-chip patients [18], the frozen two-channel mean gets 17/22 correct, a nested channel selector 20/22, and a post hoc best vessel channel 21/22. Agreement reports twenty with nineteen correct. The method was developed after inspecting this cohort. In independent osteosarcoma organoids [23], post-treatment agreement reports eleven of thirteen with ten correct; pre-treatment agreement reports six of seventeen with three correct. The latter is a substantive failure when component readouts are near chance.

Steinberg's paired spheroid area and viability measurements [19] have opposite signs in 14/49 patient-drug pairs, and area misses 12/40 viability decreases. The workbook contains 49 pairs where the caption says 48. Patient-derived spheroid measurement provenance and regimen matching limit the chip/clinical interpretation. Hu's lung microwell study [20] has ten author-defined clinically comparable lines among twenty-one tested; two of the ten rely on a comparison involving prior treatment. The remaining eleven lack an eligible paired outcome or treatment match.

Ewart's two-donor safety replay uses uncorrected margins of safety with threshold 50 [31]. On eighteen shared drugs, the donor union flags twelve of fifteen hepatotoxic drugs and clears all three safe drugs. All three donor disagreements are known toxicants; levofloxacin, stavudine and tacrine are shared misses. Agreement reports fifteen with twelve correct. Donor 2's visible per-drug table contains ten true positives while the source summary reports nine. The protein-binding-corrected thresholds of 375/2250 belong to different inputs.

Schuster's three-patient microfluidic study [17] has 8/48 schedule contrasts reverse direction between 24 and 72 hours and 13/48 stabilize after 24 hours. A held-patient temporal forecast has MAE 0.407105 versus 0.152629 for persistence, losing for all three patients. In Petreus [21], the chip's preferred schedule is confirmed against both alternatives at mouse day 35; earlier comparisons remain unresolved. That result rests on twenty of forty-five nominal animals and reverses under the recorded missing-value sensitivity. In Zhai [22], the frozen confirmation rule first succeeds at administration three in the source's Figure 3d and two in its Figure 4c, with full-cohort concordances up to 0.980. Final administrations lose attrition robustness. These are cell-line mouse arms defined by the source, with no supplied individual chip-to-mouse reading key.

## C.4. Liver-chip model capacity, the Bircsak withheld-response test and its sequential replay

**Capacity selection in small cohorts.** The Ewart and Yuan perfused liver-chip datasets provide far fewer independent drugs than the neuronal screens [31,36]. Under the frozen neuronal recipe, the three Ewart paired intervals against interpolation span zero, while both Yuan comparisons favor interpolation. In the Yuan fits, 12 or 16 scalar training targets per outer fold meet a minimum leaf size of 50, producing 600 single-leaf trees and a constant residual correction. Training-only selection among thirteen candidates addresses that capacity mismatch: interpolation, and four minimum-leaf rules crossed with residual multipliers 0.25, 0.5 and 1. Leave-one-drug-out validation within the outer training set selects the lowest mean drug MAE, with ties toward interpolation and then the smaller multiplier, and the selection is saved before outer prediction. Across 27 held-out drug-endpoint folds, it improves Yuan LDH error by 6.74% and ALT by 1.81% relative to the original model.

**Table C2. Perfused liver-chip MAE across eleven source drugs and five endpoints.** Model selection uses only the outer training drugs. Rows reuse drugs within each study. Endpoint units are given in the row labels; each row is its own comparison.

| Endpoint | Drugs | Training-selected | Original model | Interpolation |
|:--|--:|--:|--:|--:|
| Ewart albumin, percentage points of control | 6 | 26.306426 | 24.795981 | 24.072177 |
| Ewart ALT, ng/day/10⁶ hepatocytes | 6 | 1.481815 | 1.463519 | 1.491908 |
| Ewart morphology, score units | 6 | 0.361720 | 0.364336 | 0.386805 |
| Yuan LDH, percentage points of control | 5 | 8.502316 | 9.116800 | 8.376799 |
| Yuan ALT, author-reported relative secretion units | 4 | 0.030831 | 0.031399 | 0.029318 |

Interpolation leads both Yuan endpoints in Table C2, and all five selected-versus-interpolation Holm-adjusted p-values equal 1. Adjusting capacity recovers part of the lost accuracy, and keeping interpolation among the candidates lets a small cohort return it.

**Bircsak partition and freeze.** The separate Bircsak study [37] uses digitized published means from twenty-one drugs: six training, nine calibration and six test drugs, with both endpoints of each drug together. Predictions were frozen on 5 October at 01:19 JST, references were released at 01:33, and scoring completed at 01:35. Reconciliation verifies all 138 predictions and 36 action records, with the original fitted models and frozen predictions unchanged.

**Table C3. Bircsak withheld-response test, endpoint errors.** The same six test drugs contribute both endpoints. MAE averages hidden queries within each curve, then weights drugs equally. Endpoint units remain separate.

| Endpoint | Training-selected | Original leaf-50 | Interpolation |
|:--|--:|--:|--:|
| Viability, percentage points | 19.104155 | **17.372178** | 20.716898 |
| Albumin, ng/mL | **280.097154** | 322.109616 | **280.097154** |

Selection chooses pure interpolation for albumin and a 0.25-scaled residual correction for viability; the latter lowers mean error by 7.785% relative to interpolation, improving five drugs and worsening one, while the original leaf-50 model retains the lowest mean viability error. The selected/interpolation envelope covers 46/46 hidden queries, compared with 44/46 for the original model. Mean widths are 174.81 percentage points for viability and 2,847.03 ng/mL for albumin. Calibration uses nine drugs' maximum standardized residuals across endpoints and queries. At the nominal 90% level, the conformal order statistic is the largest of those nine residuals. All viability-query upper limits exceed 100%; the frozen envelopes retain their original range.

**Decision rule.** The research threshold is half the lowest-concentration response of a curve. A measured value or a predicted upper bound at or below the threshold supports reporting a reduction; all measured values and all predicted lower bounds above it support reporting no reduction; otherwise another measurement is requested. Every curve also records its next concentration before the reference is released: unmeasured concentrations whose interval contains the threshold are preferred, then the largest log-distance from measured concentrations, with ties toward the higher concentration. All methods request a further measurement for all twelve curves, so conditional error among reports has a zero denominator. A zero-width counterfactual applies the same rule to the frozen three-point predictions with the quantile set to zero: it reports all twelve curves as showing no reduction, and seven of those calls are wrong against the released series.

**Sequential replay.** The first request for each curve was frozen before the reference was released. Everything after the first reveal (reconditioning of the frozen predictors on four or more points, later requests and stopping) is a post-release replay under a protocol frozen before the replay was run. The threshold stays at half the response at the initial lowest concentration, the calibration quantile is the original nine-drug value, and no model is refitted. At each step a curve is called reduced if any measured value or any remaining upper bound is at or below the threshold, called not reduced if all measured values and all remaining lower bounds are above it, and otherwise measured again until the grid is exhausted. Costs count one unit per endpoint-specific concentration response: 12 curves, 36 initial and 46 withheld values. With model, quantile, threshold, starting context and stopping rule held fixed, the frozen action rule uses 25 of the 46 withheld values, uniform random choice 31.3 as an exact expectation over all stopped paths, and lowest-unmeasured-concentration-first 41. Each of the seven early calls followed an observed response at or below the threshold. The original 90% calibration was for three-point contexts; the replay reuses its quantile at later steps as a fixed rule.

**Calibration size.** Each of the 21 drugs was predicted by models fitted to the other 20, with the thirteen-candidate selection repeated inside every fit, giving 21 drug-level scores. For a calibration set of $n$ drugs and nominal coverage $1-\alpha$, the conformal quantile is the $\lceil (n+1)(1-\alpha)\rceil$-th smallest of $n$ scores. We computed the exact distribution of this order statistic under sampling $n$ scores with replacement from the 21, for $n$ from 5 to 200 and coverage 90% and 80%. The median number of resolvable three-concentration calls stays at 0 of 12 at every size. Values of $n$ above 21 resample the same 21 drugs and serve as a planning curve.

**Source.** The data custodian saw the full test curves while digitizing and checking the figures before the protocol freeze and performed no model fitting. Prediction used the partitioned package and the three-point test contexts. This is a custodian-separated, frozen-protocol test on published aggregate responses. Exact author-supplied response values, donor/batch keys and physical-chip replicate identities are unavailable, and digitization uncertainty remains additional to the calibrated prediction envelope.

# Appendix D. Code, data and reproduction

## D.1. Public reproduction commands

The [MIT repository](https://github.com/logxio/ooc-evaluation-audit) contains the public forecasting, workbench, patient and benchmark code. The workbench also runs offline by opening `workbench/index.html` after downloading the repository. Environment requirements and source hashes accompany each entry. Forecasting and numerical replay use free CPU. For a new assay, the Python forecaster takes a measured-response table mapped to its input schema, with preprocessing and calibration fitted to that assay.

From the repository root, the existing public entries are:

```sh
python chip_forecast.py --check
python chip_forecast.py
python benchmarks/strong_baseline/reproduce.py --out strong-baseline-recomputed.json
python chip_forecast_designcurve.py
python chip_forecast_intervals.py
python chip_forecast_decision.py --analyze
python chip_forecast_acute.py --merge
python chip_forecast_dnt.py --merge
python chip_forecast_actions.py
python ledger/run.py
python patient_workbench.py
python patient_action_delta.py
python clinical_external.py score
```

`python three_point.py --example epa_dnt` writes the EPA human neural-cell screen in the plate-table format of Section 6.1, and `three_point_example/` holds its locked forecast, the check against the finished series and the replay. `--check` verifies the published baseline match. Saved fold files in `chip_forecast_runs/` support summary reconstruction. The [strong-baseline package](https://github.com/logxio/ooc-evaluation-audit/tree/main/benchmarks/strong_baseline) includes matched-ablation outputs, identity-aware neural comparisons and separate full-training instructions. The [screen-out CPU notebook source](https://github.com/logxio/ooc-evaluation-audit/blob/main/benchmarks/screen_out_neural/kaggle/cpu_reproduction.ipynb) reproduces statistics from frozen predictions. The [Ewart package](https://github.com/logxio/ooc-evaluation-audit/tree/main/benchmarks/ooc) supplies a source-verified concentration-response reproduction through `sh benchmarks/ooc/reproduce.sh`.

Patient entries include `chip_release.py`, `blind2_predict.py`, `blind2_score.py`, `blind3_score.py`, `tiriac_reproduce.py`, `lung_reproduce.py` and `liver_chip_release.py`. `python horizon_attrition.py` reproduces the schedule/attrition analyses from publisher originals. Source files with restricted redistribution terms are downloaded at runtime.

## D.2. First-version reporting, acquisition and capacity artifacts

Release [v1.0.0](https://github.com/logxio/ooc-evaluation-audit/releases/tag/v1.0.0) of the public repository contains the code and saved outputs of the first-version reporting analysis (last row of Table B1), the acquisition/geometry experiments and the capacity experiments.

| Experiment | Public code | Saved files in `results/` |
|:--|:--|:--|
| Drug-disjoint report-or-measure, first version | `paper_nested_decision.py` | `nested/`: protocol, splits, identities, summary, `drug_decisions.csv`, `design_decisions.csv`; per fold: fitted model, rules, calibration, freezes, test decisions |
| Verification and point export | `paper_nested_decision_check.py`, `paper_nested_decision_export.py` | `nested/verification.json`; the export writes `point_predictions.csv.gz` (358,360 rows) |
| Fourth-concentration acquisition | `paper_acquisition.py`, `paper_acquisition_verify.py` | `acquisition/`: protocol, summary, verification; per fold: choices and design results |
| Highest-dose control | `paper_acquisition_geometry.py` | `acquisition/geometry_control/`: analysis specification and four-fold results, contrasts, budgets and selection overlap |
| Capacity selection and Bircsak replay | `paper_capacity.py`, `paper_capacity_independent.py`, `paper_capacity_verify.py`, `paper_capacity_score_audit.py` | `capacity/`: protocols, selections and predictions before scoring; `bircsak_run_v1/` prediction manifest and scores; `bircsak_packet/` |

The commands below fit no model. They recompute Table 5, Tables C2 and C3, the first-version row of Table B1 and the nested point export from these files and check the recorded SHA-256 hashes. After `pip install -r requirements-d2.txt` and `python chip_forecast.py --check` (Appendix D.1), which downloads the pinned NeuroChip Twin bundle, run from the repository root:

```sh
python paper_nested_decision.py summarize --out results/nested
python paper_nested_decision_check.py --out results/nested
python paper_nested_decision_export.py --out results/nested
python paper_acquisition.py summarize --out results/acquisition \
  --data .cache/neurochip_twin/nfa_tasks.npz \
  --identities benchmarks/screen_out_neural/identities.json
python paper_acquisition_verify.py --out results/acquisition \
  --data .cache/neurochip_twin/nfa_tasks.npz \
  --historical benchmarks/strong_baseline/nfa
python paper_acquisition_geometry.py --source results/acquisition \
  --out results/acquisition/geometry_control/full_four_fold \
  --folds 1 2 3 4 \
  --spec results/acquisition/geometry_control/analysis_spec.json
python paper_capacity_verify.py --out results/capacity \
  --inputs results/capacity/inputs
python paper_capacity_score_audit.py --run results/capacity/bircsak_run_v1 \
  --packet results/capacity/bircsak_packet
```

`summarize` rebuilds the first-version reporting results and their paired drug effects. The check, which downloads the pinned EPA source file on first use, re-verifies drug-disjoint splits, the five fitted models, freeze hashes, calibration arithmetic and hidden-response invariance. The export writes 358,360 point rows. The acquisition commands reproduce Table 5, its paired contrasts and the exposure-well budgets; the capacity commands reproduce Tables C2 and C3. In our runs each command finished within 10 seconds and 0.5 GB of memory, including a run from a clean copy of the release that downloaded the EPA source file.

Nine published files are redacted copies. Eight result files recorded absolute local paths; each path is replaced by `<local-input>/` and its file name. The Bircsak runner renames one session environment variable. `results/REDACTIONS.json` lists each file's frozen and published SHA-256, the changed lines and the replacement rule. The verification code accepts a listed file only when its hash equals the published value and then uses the frozen hash, so the pretest, prediction and manifest records keep their original links. The frozen SHA-256 of the nested protocol is:

```text
d15f70d8ba11f111516a13a087d3970ea270bb2e9711547db8aaf6b6f71ff20d
```

The public nested code compares release margins in exact rational arithmetic and reads frozen inputs from repository copies. `exact_rule_receipt.json` re-judges the saved calibration and test decisions in exact arithmetic and finds all 42 fold–method calibrations and release sets unchanged. `paper_nested_decision_amendments.json` maps the frozen code hash to the public one.

## D.3. Final-analysis reproduction package

`results/final/` holds the protocols, saved decisions and summaries of the current analyses: three-point reporting on scales B and A, the closed loop with every fourth-concentration rule, the risk–cost sweeps, the plate-and-date folds with the plating-date replay, the degraded-forecast and starting-design analyses, the Bircsak sequential replay with its calibration-size curve, and the analysis versions of Table B1. `results/final/numbers.json` lists each number of Sections 4 and 5 with its source file, field and the command that recomputes it. The commands fit no model.

Install the small numerical environment with `python -m pip install -r requirements-final.txt`, then run the following commands from the repository root. The reference environment is Python 3.13.14 with NumPy 2.5.3. The recorded clean-snapshot check completed all eleven commands; the longest took 5.66 seconds and the largest peak memory use was 211.7 MB (`results/final/verification.json`).

```sh
# Table 6 and Figure 5: three-point reports, errors, wells and intervals
python paper_final_reporting.py summarize
# Tables 1 and 7, Figure 6: closed-loop actions and paired differences
python paper_final_loop.py summarize
# Section 4.4: equal-well and equal-loss comparisons
python paper_final_frontier.py summarize
# Section 4.5: unseen plates, dates and chronological replay
python paper_final_heldout.py summarize --numbers
# Section 4.5: degraded forecasts and recalibrated margins
python paper_final_stress.py summarize --numbers
# Section 4.2: starting concentrations and the 35-start comparison
python paper_final_starts.py summarize --numbers
# Section 5 and Appendix C.4: withheld responses and sequential replay
python paper_final_bircsak.py summarize
# Table B1: reporting-analysis versions
python paper_final_versions.py summarize
# Saved three-concentration comparator results
python paper_final_opponents.py summarize
# Agreement with the EPA expert reference labels
python paper_final_labels.py summarize
# Verify input hashes and every indexed value and interval
python paper_final_verify.py verify
```

The index contains 9,168 entries across ten analysis groups, including 3,423 confidence intervals. The verification command checks each entry against its source field. The paired resampling conditions on the saved fits and decisions. The plate/date, start and stress commands retain their recorded statistical scope alongside the summaries.

The additional command `python paper_final_baselines.py` reconstructs Tables 4 and A2 from the released per-chemical errors and component metadata. It writes the full-precision MAEs, paired intervals and all four win/tie/loss tallies to `results/final/baselines/scoreboard.json` and `scoreboard.csv`. An isolated run took 0.54 seconds and 101 MB peak memory; both outputs were byte-identical to the released files.

**AnchorBoost stack.** The [stack package](https://github.com/logxio/ooc-evaluation-audit/tree/main/benchmarks/stack) recomputes the Section 2.4 stack from its saved member predictions and retrains it from public data and public weights. With NumPy installed, run from the repository root:

```sh
# Table 4 stack at k=1-4 from the saved member predictions
python benchmarks/stack/reproduce.py
# Retrain one outer fold and concentration budget
python benchmarks/stack/train.py --fold 1 --k 3 --device cuda
```

The first command reads the per-point TabPFN-2, LPM (20 seeds at k=1–2, 10 at k=3–4) and residual-correction predictions for test folds 1–4 together with `selection.json`, runs on CPU and fits no model. It recomputes the 194-chemical MAEs at k=1–4, 1.299769, 1.193188, 1.116981 and 1.073939, and compares every chemical with `results/final/baselines/anchorboost_team_k*.csv`; the largest difference is 1.33 × 10^−15^. Recorded runs took 0.20–0.75 seconds and 89–101 MB peak memory, and the four member archives total 19.3 MB. `selection.json` records each outer fold's member weights and correction, chosen by inner cross-validation on that fold's training chemicals as in Section 2.4.

The second command, after installing `benchmarks/stack/requirements-training.txt`, downloads the 44.4 MB Prior Labs `tabpfn-v2-regressor.ckpt`, verifies its SHA-256, trains the TabPFN-2 and ten-seed LPM members with their inner out-of-fold predictions and fits the selected five-bag residual correction. Task data, task definitions and CheMeleon features ship with the package, and the run needs no account, paid service or special hardware. A recorded run with `--workers 4` on four RTX 4090 GPUs completed fold 1 at k=3 in 14 minutes 16 seconds and scored 1.1414 MAE on its 49 chemicals, within 0.02603 of the frozen value for every chemical. `--device cpu` runs the same stages, with a planning estimate of 100–300 hours per complete fold and 16 GB of memory. LPM retraining varies at the level of individual points even at fixed versions, instance and seed, so the published values come from the frozen-member recomputation, and the training command rebuilds the full chain from public data and public weights. Member terms are TabPFN-2 code Apache-2.0 with Prior Labs License 1.1 weights (commercial use with attribution), LPM Apache-2.0, CheMeleon MIT and AnchorBoost MIT (Table F2).

## D.4. Compute requirements and recorded executions

The original forecasting fits took 222–235 seconds per fold on free Kaggle CPU. The completed public forecast notebook v4 ran the one-to-four-concentration entry in 46 minutes; 855 numeric result fields and 3,888 CSV rows matched the registered run. The physical-chip/patient notebook v14 completed seventy cells on free CPU, and the separate external clinical replay completed seven cells.

The first-version nested evaluation fitted all fifteen inner/outer models. Fold 0 ran locally and folds 1–4 used Kaggle CPU jobs. Verification records five completed outer folds and matching source/model hashes. Local fitting peaked at 781,484,032 bytes and 216.99 seconds; recorded remote fits peaked at 647,757,824 bytes and 62.44–125.18 seconds. The AnchorBoost stack recomputes on CPU in 0.20–0.75 seconds with 89–101 MB peak memory, and its fold-1, k=3 retraining took 14 minutes 16 seconds on four RTX 4090 GPUs with 1.99 GB peak RAM per member-training process and 7.74 GB peak GPU allocation.

Tree refits vary across platforms. Recomputing two primary forecasting folds on macOS changes fold MAEs by at most 0.004 while preserving the interpolation advantage; the AnchorBoost–CNP comparison's upper interval endpoint moves slightly above zero. Image-release counts are 71/7 reports/errors on macOS versus 66/7 on Linux; the probability comparators are 54/10 versus 52/9. Both image primary comparisons fail. Patient actions and the corrected Liver-Chip counts reproduce unchanged.

# Appendix E. Cell annotation, image quality and paper extraction

## E.1. Neural-organoid annotation and review priorities

The HNOCA module fits a linear classifier to 135,053 Velasco cells and evaluates 207,871 Bhaduri cells in 34 sample keys [9–12]. Library-size normalization over the fixed 3,000-gene panel and `log1p` precede an SGD logistic classifier: L2, alpha 0.0001, 30 iterations, balanced class weights and seed 26. Whole-key resampling yields macro-F1 **0.907831 [0.842324, 0.937195]**, versus **0.806783** for source-trained nearest centroid, a paired +0.101048 [0.070494, 0.120536]. The panel and harmonized labels were constructed across studies, and sample keys represent atlas metadata rather than verified independent donors.

Glioblast, an atlas progenitor label, has recall 0.931944 but precision 0.679004: 1,353 other cells receive that label and 209 true Glioblast cells are missed. A score-only sample ordering correlates with observed harmonized-label error (Spearman 0.779068); its selected top-eight ratio is 1.720951, with an explicitly post hoc permutation check. On an original-author, two-class endpoint retaining 175,160 cells, the comparator reverses: model macro-F1 0.941193 versus centroid 0.947220, difference −0.006027 [−0.010067, −0.002531]. The fits emit maximum-iteration warnings; longer optimization was left untested after outcome inspection.

A frozen third-publication test on 236,453 Uzquiano cells gives 0.937418 [0.918595, 0.952664] versus centroid 0.815074, paired +0.122344 [0.099082, 0.147403]. Under a 20% whole-key cell budget, its complete 263,827-row intake exposes 17,046 of 34,656 later label disagreements while reviewing 51,993 cells; 17,610 remain. By contrast, Bhaduri full-intake rescoring exposes 6,881 of 22,721 while reviewing 44,543 cells, leaving 15,840; random whole-key orders reach its finding count in 19.33% of runs. The queue's successful third-source result and failed Bhaduri transfer both remain. These endpoints are atlas disagreements, with expert-confirmed correction and staff time awaiting separate measurement.

Reproduction entries are `organoid_phenotype.py`, `review_contract_map.py`, `fixed_budget.py`, `f32_third_source.py`, `f36_third_review.py` and `f38_full_intake.py`. They use the HNOCA archive and retained source-specific outputs.

## E.2. Image-quality prediction across acquisition groups

The image module uses 3,072 expert-labeled organ-chip images [1–3], twenty-nine image features and date-like filename prefixes as acquisition proxies. On the 736-image grouped test, the Linux random forest has balanced accuracy 0.657920 and flags 181/376 good images, exceeding the prespecified 45% ceiling. On the different 656-image source-folder test, accuracy is 0.799925 and 57/365 good images are flagged. Every one of the 57 source-test prefixes also appears in source training; the grouped test holds out fifteen prefixes.

On the exact 151 shared test images, the source and grouped models score 0.756467 and 0.690379. Their paired difference is +0.066088 [−0.042091, 0.122483], below the stronger-evidence criterion. Prefix overlap, differing training data and a crossing-zero paired interval support a diagnostic audit of acquisition context. Physical-chip identity and a causal estimate of split optimism require stronger grouping information.

A separate group-calibrated error score reports 71 images with seven errors, compared with 54 with ten errors for grouped probability calibration. The image-weighted coverage difference is +4.64 points [−4.18, 10.39]; equal-group coverage is 15.87% versus 17.98%. Removing group calibration reports 200 with forty-four errors, exceeding the intended budget. The main gain criterion fails. A selected 38-image example illustrates false flags and missed bad images but supplies no independent population validation.

`run_full_audit.py` reconstructs the image audit from the source archive; `audit_report.py records` accepts user-supplied source/grouped prediction files. A clean Linux run verified the 6,710,767,405-byte archive, extracted every feature, and wrote `audit.html`, `audit.json` and `run_evidence.json` with `status: verified`. The 151-image matrices are `[[57,11],[27,56]]` and `[[39,29],[16,67]]`; these expose the different false-positive and false-negative costs directly.

## E.3. Reproducing patient-level evidence from publications

The optional [paper-extraction module](https://github.com/logxio/ooc-evaluation-audit/tree/main/contract_agent) ties a published headline to its patient records, assay cutoffs and outcome cells. A tool-using commercial-model experiment reconstructs 19 of 26 frozen external headlines after record-level checking: seventeen of twenty-three clinical-response papers and two of three toxicity papers. All four no-headline controls are correctly declined. Three additional judged passes fail the record audit; four chains reach the token cap. The eight development papers are reported separately.

The live external run used the commercial provider configuration recorded in the public module, at medium reasoning effort, with up to 24 model calls, 64 tool calls and 1,000,000 cumulative tokens per paper. It cost approximately CNY34.1 at recorded list prices, with interrupted first requests adding an estimated CNY1.0. The public module records the provider, model identifier and settings as experimental provenance. Fresh extraction requires a configured provider or the documented local route. The tested free local 0.6-billion-parameter GGUF route, served through llama.cpp, scored 0/100 on its separate extraction benchmark; its outcome does not reproduce the commercial agent's accuracy.

The effective free reproduction is `python -m contract_agent.replay_agent`: it executes the saved contracts and source references offline, using the Python standard library. This replays the reported computation; it leaves fresh model generation as a distinct experiment. The repository retains provider settings, cached outputs, source licenses, model-weight attribution and the documented local setup. Quantitative forecasting and the workbench operate independently of this optional agent.

# Appendix F. Source terms and competition contributions

The pre-existing EPA measurements, NeuroChip Twin code and evaluation protocol, clinical studies, HNOCA atlas and image dataset retain their original attribution. The competition contribution is the sparse-design learner, controlled comparisons, acquisition and reporting experiments, study-specific follow-up analyses, workbench and executable reproduction routes. AI assistance supported programming and prose. Completed biological experiments and clinical cohorts belong to their original investigators.

Yan Su is responsible for methods, code, computational experiments and the report. Ziyang Liu is responsible for biological review, participant recruitment for trial use and presentation collaboration.

The present research stage comprises retrospective assay analyses, published-cohort replays and one independent participant session. In that self-serve, screen-recorded session, a participant with no laboratory experience and no prior use of the tool worked through the frozen tasks without assistance. Measured from task release to the first correct export, the workbench action lists matched the sealed answers for 3 of 3 chemicals in 23 seconds and 6 of 6 patients in 57 seconds. Having no screening rule of their own, the participant made no call on the matched current-method tasks, so the session has no comparator; the risk-comprehension answers scored 0 of 3. The participant's package omitted the workbench version lock, so the session used the live build `5ea7998` instead of the locked `eaeb887`; both exports still matched the sealed answers. Prospective wet-laboratory validation, measured staff-time savings and real laboratory well-use savings remain to be established.

**Table F1. Data and external artifacts.** Code licenses and source-data terms are recorded separately.

| Source | Terms and handling |
|:--|:--|
| EPA network formation, acute MEA, human DNT [32–35] | Public EPA measurements. Original protocols label them US Government/public-domain work; a separate dataset-specific license was not captured. Pinned source records and this qualification accompany the derived arrays. |
| NeuroChip Twin v2 code and comparator [33] | MIT, Francisco Angulo de Lafuente; pinned upstream license accompanies the released comparator subset. |
| Ewart liver-chip source [31] | CC BY 4.0; the attributed benchmark includes the workbooks and extracted numerical observations. |
| Yuan immune-liver source [36] | CC BY-NC-ND 4.0; publisher figures and readings remain at the source; released outputs are calculated summaries. |
| Bircsak source [37] | Publisher article and figures retain their source terms; working evaluation uses digitized published means. Public redistribution permission for those digitized readings remains unresolved. |
| HNOCA minimal/cleaned archives [9,16] | CC BY 4.0, separate archive records; raw archives are acquired from the source. |
| Organ-chip images [1,2] | Zenodo record: CC BY 4.0; descriptor: CC-BY-SA, version unspecified. Both statements are retained; images are downloaded from source. |
| Dai, Tan, Wang clinical supplements [18,38,40] | CC BY-NC-ND 4.0; source files are fetched at runtime. |
| Schuster, Steinberg, Hu, Petreus, Zhai [17,19–22] | CC BY 4.0; attributed source workbooks support the respective analyses. |
| Osteosarcoma, gastric, biliary, rectal, liver metastasis [23–25,28,29] | CC BY 4.0; source-specific extraction and outcome mappings are retained. |
| Tiriac AACR Figshare tables; Cartry supplement [39,41] | CC BY 4.0; source checksums and curated mappings accompany replays. |

The NFA prepared-bundle license identifies the code distribution; underlying EPA documents retain their own terms. The detailed [source inventory](https://github.com/logxio/ooc-evaluation-audit/blob/main/benchmarks/screen_out_neural/SOURCES.md) makes that distinction explicit. HNOCA's cleaned archive was accessed for the required metadata by byte-range reads; only the minimal archive was downloaded and hashed in full. Source MD5s and byte counts accompany the reproduction outputs.

Our code is MIT licensed. NumPy, SciPy, scikit-learn, pandas and h5py use BSD-3-Clause; PyTorch uses its BSD-style license; Pillow uses MIT-CMU; Requests uses Apache-2.0; openpyxl and rdata use MIT [4–8,13,14]. Package versions are pinned by the experiment-specific requirements; PyTorch and pandas support the neural benchmarks, while rdata and openpyxl read the original assay files. The package distributions carry their upstream license notices. The optional paper agent documents its commercial APIs, Apache-2.0 local-model alternative and MIT llama.cpp runtime separately. Learned forecasting weights are produced by the documented fits; commercial language-model access supplies no hidden dependency for those predictions.


**Table F2. Model and implementation licenses.** Terms are taken from the component-level source records in `results/final/baselines/methods.json`, checked on 9 October 2026. The model name links to the source; the weight entry links to the recorded license evidence. “Yes” records permission under the stated terms, including any attribution requirements. “Unresolved” records an absent code-license statement. Pretraining overlap and commercial permission are separate properties.

| Model / source | Code license | Weight license or origin | Commercial use |
|:--|:--|:--|:--|
| [AnchorBoost and own classical implementations](https://github.com/logxio/ooc-evaluation-audit) | MIT | [Self-trained / not applicable](https://github.com/logxio/ooc-evaluation-audit/blob/main/LICENSE) | Yes |
| [TabPFN-2](https://github.com/PriorLabs/TabPFN) | Apache-2.0 | [Prior Labs License 1.1 (attribution)](https://huggingface.co/Prior-Labs/TabPFN-v2-reg/blob/main/LICENSE.txt) | Yes |
| [TabPFN-3.5](https://github.com/PriorLabs/TabPFN) | Apache-2.0 | [TABPFN-3.5 Non-Commercial License v1.0](https://huggingface.co/Prior-Labs/tabpfn_3_5/blob/main/LICENSE) | No |
| [TabICLv2](https://github.com/soda-inria/tabicl) | BSD-3-Clause | [BSD-3-Clause](https://huggingface.co/jingang/TabICL/raw/main/README.md) | Yes |
| [SoftImpute implementation](https://github.com/logxio/ooc-evaluation-audit) | MIT (own NumPy implementation) | [Not applicable](https://github.com/logxio/ooc-evaluation-audit/blob/main/LICENSE) | Yes |
| [CP tensor implementation](https://github.com/logxio/ooc-evaluation-audit) | MIT (own NumPy implementation) | [Not applicable](https://github.com/logxio/ooc-evaluation-audit/blob/main/LICENSE) | Yes |
| [CNP / NeuroChip Twin](https://github.com/Agnuxo1/neurochip-twin) | MIT | [MIT (repository checkpoint) / self-trained](https://github.com/Agnuxo1/neurochip-twin) | Yes |
| [CheMeleon](https://github.com/JacksonBurns/chemeleon) | MIT | [MIT](https://zenodo.org/api/records/15460715) | Yes |
| [LimiX-2](https://github.com/limix-ldm-ai/LimiX) | Stable AI Technology License v1.0 | [StableAI LimiX Non-Commercial License v1.0](https://huggingface.co/stable-ai/LimiX-2) | No |
| [TNP](https://github.com/tung-nd/TNP-pytorch) | MIT | [Self-trained](https://github.com/tung-nd/TNP-pytorch) | Yes |
| [TE-TNP implementation](https://github.com/cambridge-mlg/tnp) | MIT (own implementation; reference framework MIT) | [Self-trained](https://github.com/cambridge-mlg/tnp) | Yes |
| [FlowNP](https://github.com/danrsm/flowNP) | Unresolved (author repository has no license) | [Self-trained](https://github.com/danrsm/flowNP) | Unresolved |
| [Empirical GP implementation](https://github.com/logxio/ooc-evaluation-audit) | MIT (own NumPy implementation) | [Not applicable](https://github.com/logxio/ooc-evaluation-audit/blob/main/LICENSE) | Yes |
| [LPM / perturblib](https://github.com/perturblib/perturblib) | Apache-2.0 | [Self-trained](https://github.com/perturblib/perturblib) | Yes |
| [SNN](https://github.com/deshen24/syntheticNN) | Unresolved (reference repository has no license) | [Not applicable](https://github.com/deshen24/syntheticNN) | Unresolved |
| [N²](https://github.com/aashish-khub/NearestNeighbors) | MIT | [Not applicable](https://github.com/aashish-khub/NearestNeighbors) | Yes |
| [ARCANet](https://github.com/alonsocampana/ARCANet) | MIT | [Self-trained](https://github.com/alonsocampana/ARCANet) | Yes |
| [GenRA](https://github.com/USEPA/genra-py) | MIT | [Not applicable](https://github.com/USEPA/genra-py) | Yes |
| [LC-PFN / DR-PFN](https://github.com/automl/lcpfn) | MIT | [Self-trained](https://github.com/automl/lcpfn) | Yes |
| [TabImpute](https://github.com/jacobf18/tabular) | Unresolved (no repository or package license statement) | [Apache-2.0](https://huggingface.co/Tabimpute/TabImpute/raw/main/README.md) | Unresolved |
| [KANO](https://github.com/HICAI-ZJU/KANO) | MIT | [MIT (repository checkpoint)](https://github.com/HICAI-ZJU/KANO) | Yes |
| [MotiL](https://github.com/Young0222/MotiL) | MIT | [MIT (repository checkpoint)](https://github.com/Young0222/MotiL) | Yes |
| [Monroe](https://github.com/blazejba/monroe) | MIT | [MIT (repository encoder checkpoint)](https://github.com/blazejba/monroe) | Yes |

The CPU single model and the AnchorBoost stack use only components with commercial permission in this inventory. TabPFN-3.5 and LimiX-2 weights are noncommercial; FlowNP, SNN and TabImpute retain unresolved code-license entries. Their saved errors support the scientific comparison, and the comparison package distributes chemical-level errors and source metadata rather than their pretrained weights.


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
19. Steinberg et al. [A fully 3D-printed versatile tumor-on-a-chip allows multi-drug screening and correlation with clinical outcomes for personalized medicine](https://doi.org/10.1038/s42003-023-05531-5). *Communications Biology* (2023). Figure 5 Supplementary Data 1; article CC BY 4.0.
20. Hu et al. [Lung cancer organoids analyzed on microwell arrays predict drug responses of patients within a week](https://doi.org/10.1038/s41467-021-22676-1). *Nature Communications* (2021). Supplementary Data 2 and Source Data; article CC BY 4.0.
21. Petreus et al. [Tumour-on-chip microfluidic platform for assessment of drug pharmacokinetics and treatment response](https://doi.org/10.1038/s42003-021-02526-y). *Communications Biology* 4, 1001 (2021). Supplementary Data 1 figure source tables; article CC BY 4.0.
22. Zhai et al. [Drug screening on digital microfluidics for cancer precision medicine](https://doi.org/10.1038/s41467-024-48616-3). *Nature Communications* 15, 4363 (2024). Source Data figures 3d and 4c; article CC BY 4.0.
23. [Personalized prediction of chemotherapy efficacy in osteosarcoma through patient-derived organoids: correlation with survival and tumor proliferation potential](https://doi.org/10.1186/s13046-025-03541-1). *Journal of Experimental & Clinical Cancer Research* 45, 16 (2025). Tables 2-4; article CC BY 4.0.
24. [Personalized drug screening using patient-derived organoid and its clinical relevance in gastric cancer](https://doi.org/10.1016/j.xcrm.2024.101627). *Cell Reports Medicine* (2024). Tables S3 and S4; article CC BY 4.0.
25. [Personalized drug screening in patient-derived organoids of biliary tract cancer and its clinical application](https://doi.org/10.1016/j.xcrm.2023.101277). *Cell Reports Medicine* (2023). Tables S1, S3 and S4; article CC BY 4.0.
26. Chow. [On optimum recognition error and reject tradeoff](https://doi.org/10.1109/TIT.1970.1054406). *IEEE Transactions on Information Theory* 16(1), 41-46 (1970). Optimal reject rule under a reject cost.
27. Vacek. [The effect of conditional dependence on the evaluation of diagnostic tests](https://doi.org/10.2307/2530967). *Biometrics* 41(4), 959-968 (1985). Bias from assuming two tests err independently.
28. Xu et al. [Comprehensive dissection of rectal cancer organoids in responses to chemoradiation](https://doi.org/10.1016/j.xcrm.2025.102397). *Cell Reports Medicine* 6(10), 102397 (2025). Supplementary Tables 1 and 2; article CC BY 4.0.
29. Mo et al. [Patient-derived organoids from colorectal cancer with paired liver metastasis reveal tumor heterogeneity and predict response to chemotherapy](https://doi.org/10.1002/advs.202204097). *Advanced Science* 9(31), e2204097 (2022). Tables S6 and S7; article CC BY 4.0.
30. Angelopoulos, Bates, Fisch, Lei and Schuster. [Conformal risk control](https://arxiv.org/abs/2208.02814). *International Conference on Learning Representations* (2024). Finite-sample control of an expected loss on exchangeable data.
31. Ewart et al. [Performance assessment and economic analysis of a human Liver-Chip for predictive toxicology](https://doi.org/10.1038/s43856-022-00209-1). *Communications Medicine* 2, 154 (2022). Tables 1, 4 and 5 for the uncorrected-MOS replay; Table 6 is a separate protein-binding-corrected analysis, from the open-access XML; article CC BY 4.0.
32. Shafer et al. [Evaluation of chemical effects on network formation in cortical neurons grown on microelectrode arrays](https://doi.org/10.1093/toxsci/kfz052). *Toxicological Sciences* 169(2), 436-455 (2019). Assay design and features.
33. US EPA. [CompTox DNT NFA refinement repository](https://github.com/USEPA/CompTox-DNT-NFA-Refinement), commit `01adf3e`, network-formation data packaged at DIV 5/7/9/12 in the [NeuroChip Twin v2 repository](https://github.com/Agnuxo1/neurochip-twin/tree/f9848800dfab66a8bc005e6b3087153eeaabe9ac) (code MIT; EPA data US Government work), whose published per-chemical results supply the original neural comparator.
34. Kosnik et al. US EPA acute microelectrode-array screen, EPA ScienceHub (2020). [Dataset DOI 10.23719/1504294](https://doi.org/10.23719/1504294).
35. Harrill et al. Developmental-neurotoxicity battery in neural progenitors and neurons. *Toxicology and Applied Pharmacology* 354, 24–39 (2018). [EPA dataset DOI 10.23719/1407642](https://doi.org/10.23719/1407642).
36. Yuan et al. Targeted cellular depletion in an immune-liver-on-a-chip platform elucidates cell-type-specific heterogeneity in drug-induced hepatotoxicity. *Communications Biology* 8, 1560 (2025). [DOI 10.1038/s42003-025-08928-6](https://doi.org/10.1038/s42003-025-08928-6).
37. Bircsak et al. A 3D microfluidic liver model for high throughput compound toxicity screening in the OrganoPlate®. *Toxicology* 450, 152667 (2021). [DOI 10.1016/j.tox.2020.152667](https://doi.org/10.1016/j.tox.2020.152667).
38. Tan et al. Patient-derived colorectal organoids and the FORECAST-1 study. *Cell Reports Medicine* (2023). [DOI 10.1016/j.xcrm.2023.101335](https://doi.org/10.1016/j.xcrm.2023.101335).
39. Tiriac et al. Pancreatic cancer organoid pharmacotyping and clinical outcomes. *Cancer Discovery* (2018). [DOI 10.1158/2159-8290.CD-18-0349](https://doi.org/10.1158/2159-8290.CD-18-0349). AACR Figshare supplementary drug-response tables and PFS figure.
40. Wang et al. Lung-cancer organoid drug responses and longitudinal clinical records. *Cell Reports Medicine* (2023). [DOI 10.1016/j.xcrm.2022.100911](https://doi.org/10.1016/j.xcrm.2022.100911). Table S6.
41. Cartry et al. Colorectal-cancer organoid drug response and clinical benefit. *Journal of Experimental & Clinical Cancer Research* (2023). [DOI 10.1186/s13046-023-02853-4](https://doi.org/10.1186/s13046-023-02853-4). Supplementary Table 3.

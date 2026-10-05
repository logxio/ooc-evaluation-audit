---
title: "More screening decisions from fewer measurements"
date: "5 October 2026"
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

AnchorBoost reports 946 activity calls from 965 three-concentration designs, compared with 806 for a calibrated measured-only rule, with 15.24% fewer exposure-well equivalents. The retrospective evaluation uses the EPA rat-neuronal network-formation assay, with disjoint training, calibration and test drugs; wrong reports number 77 and 75, respectively. The predictor learns across sparse concentration designs to correct interpolation at unmeasured responses. In a separate static comparison, reconstruction error falls by 13.7% relative to interpolation. Matched-budget training isolates a gain from design coverage, and a one-step acquisition experiment finds that model disagreement selects a more informative fourth concentration than random, maximin or a post hoc highest-dose control. Comparisons across neuronal screens and small perfused liver-chip datasets establish the assays in which learned prediction or interpolation performs better. A browser workbench connects saved responses and forecasts to downloadable report-or-measure actions. Together, these capabilities support an adaptive screening strategy that directs further measurement toward unresolved responses.


# 1. More reports from the wells already measured

AnchorBoost turns a three-concentration response into a predicted full-series activity call and a decision to report or complete the remaining measurements. In the EPA screen, more accurate calls allow more designs to stop at their initial measurements. The gain is a larger completed screen for a given exposure-well budget.

The distinctive choice is to train on the measurement situations a researcher may encounter. Three concentrations spanning an activity transition carry different information from three below it. Complete training curves supply examples of both. A gradient-boosted model learns how to correct log-concentration interpolation across these contexts, sharing information between chemicals and assay outputs.

The primary evidence comes from a static rat-neuronal microelectrode-array (MEA) assay [32,33]. We evaluate reconstruction, selection of a fourth concentration and reporting in separate experiments, then test the prediction recipe on other neuronal assays and perfused liver-chip data. Figure 1 follows a sparse design from recorded wells to a reconstructed curve, then places reporting alongside its exposure-well cost.


![Figure 1. From sparse measurements to a reporting decision. Panels a–d and the upper part of e follow Trimethyltin hydroxide, design 1 at DIV 12, in the historical MEA replay. Gray cells in b indicate features without recorded measurements at that concentration. Held-out means provide the measured reference; bars in c are nominal 90% well-response prediction intervals from historical calibration. The lower part of e shows the separate nested test folds 1–4: 946/965 reported designs and 11,588/28,080 exposure-well equivalents. One dot represents approximately 100 wells. Costs include observed replicates, the initial wells and completion of the remaining series for each alternative starting design.](figures/F1-workflow.png){#fig-workflow width=100%}


# 2. Learning from sparse concentration designs

## 2.1. Prediction gains reach most held-out chemicals

Forecast-based activity calls depend on responses at concentrations that remain unmeasured. We test their reconstruction against interpolation, chemical analogs, Hill curves and the published conditional neural process (CNP), using the same three-concentration designs for 194 held-out chemicals. Absolute error is averaged over day-feature outputs and designs within each chemical, then equally across chemicals. Appendix A specifies the frozen protocol and source data.

**Table 1. Static three-concentration reconstruction on the original 194-chemical benchmark.** Differences are AnchorBoost minus the listed comparator; 95% confidence intervals (CIs) use paired chemical bootstraps. Lower error is better. The CNP row uses the original published run.

| Predictor | Mean absolute error, normalized response units | Paired difference, 95% CI |
|:--|--:|:--|
| AnchorBoost | **1.1606** | Reference |
| Published CNP | 1.1940 | −0.0333 [−0.0703, −0.0004] |
| Log-concentration interpolation | 1.345 | −0.185 [−0.217, −0.154] |
| Analog chemicals | 1.349 | −0.189 [−0.216, −0.162] |
| Per-output Hill curve | 1.457 | −0.296 [−0.329, −0.264] |

AnchorBoost lowers interpolation error by **13.7%**, improving every primary fold and 88.7% of chemicals. With two measured concentrations, its error is close to interpolation's four-concentration error, evaluated on each method's remaining forecast targets: paired difference −0.001 [−0.043, 0.043] (Table A1).

The CNP comparison is closer. Removing phenobarbital, whose parent identity crosses an original training/test boundary through its sodium form, leaves 193 chemicals and an AnchorBoost–CNP difference of **−0.029874 [−0.065825, 0.002217]**. The interval spans zero (Figure 2c). Against interpolation, Figure 2a–b resolves the average gain into individual chemicals, while Figure A1 shows one high-variation response from chemicals with the largest, median and smallest gains.

## 2.2. Design coverage contributes at a fixed training budget

Enumerating more concentration designs also creates more training rows. To isolate the value of coverage, full enumeration and repeated use of the five published contexts receive the same scalar training-row count, features and 600 boosting iterations (Figure 2e). Coverage lowers MAE from **1.183515 to 1.160612**, a **1.94%** reduction, with paired difference −0.022903 [−0.035089, −0.012074]. It improves 134 of 194 chemicals and all four folds.

The separate design-count series in Figure 2f shows how prediction changes when coverage and training-row count grow together. The controlled comparison therefore attributes part of the gain to the variety of measurement situations seen during training. Information from analogous training chemicals supplies another gain; residual rather than direct-response prediction has an interval spanning zero. Appendix A records these ablations and the identity sensitivity.

## 2.3. Prediction gains extend to acute and human-neural screens

The same training recipe can be tested with different neuronal readouts. The acute assay measures mature rat cortical networks after about one hour of exposure; the human assay measures neural progenitor and neuronal responses through nine imaging and plate-reader endpoints [34,35]. We retain the model configuration and fit weights within each screen.

**Table 2. Three-concentration forecasting in additional screens.** These are within-screen chemical holdouts with an unchanged modeling recipe. The first two rows use all eligible source labels. The neural comparisons use identity-aware subsets. MAE uses each screen's vehicle-normalized response scale; bootstrap units follow the labels or identities listed.

| Comparison | Chemical units | AnchorBoost MAE | Comparator MAE | AnchorBoost − comparator, 95% CI |
|:--|--:|--:|--:|:--|
| Acute rat MEA vs interpolation | 384 labels | 1.554 | 1.814 | −0.260 [−0.281, −0.238] |
| Human neural cells vs interpolation | 71 labels | 1.693 | 1.965 | −0.272 [−0.352, −0.195] |
| Acute rat MEA vs CNP | 383 identities | 1.554265 | 1.570140 | −0.015875 [−0.030804, −0.001256] |
| Human neural cells vs CNP | 69 identities | 1.694976 | 1.744422 | −0.049446 [−0.113124, 0.013459] |

Reconstruction error falls by 14.3% and 13.9% relative to interpolation. Differences from the retrained CNP are smaller, and both wider 97.5% intervals include zero. The recurring advantage over interpolation supports learning across designs for these readouts, while the smaller differences from CNP leave their relative performance less settled. Appendix A describes preprocessing and cross-screen identity overlap.

![Figure 2. Prediction errors and design coverage in static forecasting. Panel a compares errors for each chemical. Panel b plots each chemical's five-design mean AnchorBoost minus interpolation MAE by test fold; short horizontal lines mark fold means, and counts above show chemicals with lower AnchorBoost error. Panel c gives paired AnchorBoost–CNP differences on each screen's normalized scale and chemical win/loss proportions; the thin whisker for the acute screen is its 97.5% interval. Panel d resolves normalized-response MAE by day and feature. Panel e shows paired differences and chemical win/loss proportions with scalar training rows and 600 boosting iterations fixed. Panel f lets coverage and training-row count grow together. Each glyph row is one three-concentration design, with filled cells marking measured concentrations; 5, 10 and 20 are random schematic examples, while All contains all C(7,3)=35 designs for seven concentrations. CNP denotes conditional neural process. Nested reporting results appear separately in Figure 4.](figures/F2-evidence.png){#fig-evidence width=100%}

# 3. Choosing a fourth concentration from the observed response

The forecasting tests keep the measured concentrations fixed. An adaptive screen can also use the observed response to choose where to measure next. After three concentrations, disagreement among AnchorBoost, interpolation and a training-chemical analog supplies that choice. We compare this policy with uniform random selection, maximin spacing in log concentration and the highest unobserved dose. Each policy adds one concentration.

**Table 3. MAE after one additional concentration, 193 common chemicals and 965 designs.** Columns use the same chosen concentrations across predictors. Random is the exact expectation over the candidate set. Highest-dose selection was added after the original results as a geometric control. MAE uses NFA normalized response units and the original three-point design's unmeasured target set, with zero error at the newly observed concentration.

| Predictor | Random | Maximin | Highest unmeasured dose | Disagreement |
|:--|--:|--:|--:|--:|
| Interpolation | 0.957636 | 0.904011 | 0.936894 | 0.858613 |
| AnchorBoost, broad coverage | 0.841156 | 0.817798 | 0.807778 | **0.765536** |
| AnchorBoost, five designs | 0.844788 | 0.821015 | 0.809539 | 0.770248 |
| CNP | 0.863891 | 0.837427 | 0.818474 | 0.776620 |

Highest-dose selection supplies a strong comparison that can be chosen without the observed responses. For broad-coverage AnchorBoost, disagreement lowers error by **0.042242 [0.024617, 0.061329]**, or **5.2%**, beyond highest-dose selection. The policies coincide in 630 of 965 designs. The mean benefit persists when the highest concentration was already measured, supporting a contribution beyond high-dose geometry.

Across chemical-average errors, disagreement wins 76 times, highest-dose selection wins 61, and 56 tie; the two-sided sign test gives **p=0.231537**. The positive mean-effect interval reflects improvement size as well as win frequency. The gain comes both from measuring an informative point and from improving the forecasts that remain (Figure 3). Appendix B gives the decomposition, matched training budgets and concentration-specific well costs.

![Figure 3. Choosing one additional concentration. Panel a shows a rule-selected example (Loperamide, fold 1, design 2): disagreement picks the interior concentration where the three forecasts differ most. Panel b gives MAE after acquisition across 193 chemicals and 965 designs, scored as in Table 3. Panel c shows chemical-average highest-dose minus disagreement error; positive values favor disagreement. Panel d counts designs in which rules choose the same concentration; disagreement and highest dose coincide in 630 of 965. Panel e places each choice relative to the three measured concentrations; Random is the exact expectation. Highest-dose selection is a post hoc geometric control.](figures/F3-acquisition.png){#fig-acquisition width=100%}

# 4. Forecast-based reporting resolves more calls with fewer wells

## 4.1. From a reconstructed curve to an activity call

The acquisition test spends one additional concentration; the reporting test asks which designs can yield a call from the initial three. The rule accepts the predicted full-series call when its calibrated confidence margin is sufficient and otherwise completes the remaining measurements. Activity is defined by a largest absolute DIV-averaged response of at least three across concentrations and features in the training-derived normalized scale.

Training, calibration and test drugs remain separate, including grouped parent forms. Drug-level conformal risk control (CRC) targets 10% expected marginal wrong-report loss under exchangeability [30]: each drug's loss averages wrong reports over its alternative starting designs. Appendix B.2 gives the five outer fits, independent calibration and finite-sample correction.

## 4.2. Reporting and exposure-well cost

The primary folds 1–4 contain **188 drug groups, 193 substance labels and 965 designs**, representing five alternative starting designs per substance. Historical development fold 0 is reported in Appendix B.


**Table 4. Primary report-or-measure results.** Costs count the observed concentration-specific replicates, including completion of unresolved series; controls, assay failures and overhead are outside the count. The complete-series reference costs 28,080 wells across these alternative designs. Percentages in this table weight designs; paired effects in the following paragraph weight drugs equally.

| Rule | Reports / 965 | Wrong / all designs | Wrong / reports | Exposure-well equivalents |
|:--|--:|--:|--:|--:|
| AnchorBoost + drug CRC | **946 (98.03%)** | 77 (7.98%) | 77/946 (8.14%) | **11,588** |
| Interpolation + drug CRC | 789 (81.76%) | 76 (7.88%) | 76/789 (9.63%) | 13,923 |
| Three measured points + drug CRC | 806 (83.52%) | 75 (7.77%) | 75/806 (9.31%) | 13,671 |
| Report observed activity; otherwise complete | 626 (64.87%) | 0 (0%) | 0/626 (0%) | 17,017 |

The reporting gain in Table 4 is supported by better underlying calls. Before selective reporting, forecast-based calls make 88 errors across the 965 designs, compared with 131 for the measured-only rule. At equal drug weighting, the resulting reporting-rate gain is **14.56 percentage points [11.05, 18.39]**, with a wrong-report-loss difference of **+0.11 points [−1.81, 2.02]**. The forced-full-report drug-average error difference is −4.45 points [−6.76, −2.29]. Figure 4 places the reporting increase beside its wrong-report loss and paired uncertainty.

Completing fewer unresolved series saves **2,083 exposure-well equivalents, or 15.24%**, relative to the calibrated measured-only rule. The saving against complete measurement is **16,492 of 28,080 wells, or 58.73%**.

Observed drug-average wrong-report loss is **8.09% [5.85%, 10.64%]**; primary fold 3 reaches 10.22%. The evaluation shares 107–125 technical plate/date combinations across training and test and lacks donor and culture-batch keys, leaving exchangeability as an assumption. These are retrospective estimates conditional on the fitted rules: the bootstrap captures between-drug variation and leaves refitting uncertainty unmeasured. Conditional error among reported calls and a bound for each future batch are distinct from the expected marginal target.





![Figure 4. Reporting actions and exposure-well costs in nested test folds 1–4. Panel a orders the 965 designs by fold, full-series call and wrong-report count. Panel b crosses released calls with the full-series reference: AnchorBoost reports 64 active references as inactive and 13 inactive references as active; the measured-only rule reports 75 active references as inactive and zero in the reverse direction. The archived encoding is active=0, inactive=1. Panel c traces action transitions from measured-only to AnchorBoost; d counts exposure-well equivalents including observed replicates and series completion. Panel e gives drug-weighted paired differences with 95% bootstrap intervals, holding fitted decisions fixed and resampling drug groups. These retrospective intervals describe between-drug variation conditional on the fitted rules. CRC denotes conformal risk control.](figures/F4-reporting.png){#fig-reporting width=100%}

# 5. Interpolation remains competitive in small liver-chip datasets

Moving to the Ewart and Yuan perfused liver-chip datasets changes a critical condition: far fewer independent drugs are available for training [31,36]. Under the frozen neuronal recipe, the three Ewart paired intervals against interpolation span zero, while both Yuan comparisons favor interpolation. In the Yuan fits, 12 or 16 scalar training targets per outer fold meet a minimum leaf size of 50, producing 600 single-leaf trees and a constant residual correction.

Training-only selection among thirteen candidates, including interpolation and smaller or adaptive leaves, tests that capacity mismatch. Across 27 held-out drug-endpoint folds, it improves Yuan LDH error by 6.74% and ALT by 1.81% relative to the original model.

**Table 5. Perfused liver-chip MAE across eleven source drugs and five endpoints.** Model selection uses only the outer training drugs. Rows reuse drugs within each study. Endpoint units are given in the row labels; each row is its own comparison.

| Endpoint | Drugs | Training-selected | Original model | Interpolation |
|:--|--:|--:|--:|--:|
| Ewart albumin, percentage points of control | 6 | 26.306426 | 24.795981 | 24.072177 |
| Ewart ALT, ng/day/10⁶ hepatocytes | 6 | 1.481815 | 1.463519 | 1.491908 |
| Ewart morphology, score units | 6 | 0.361720 | 0.364336 | 0.386805 |
| Yuan LDH, percentage points of control | 5 | 8.502316 | 9.116800 | 8.376799 |
| Yuan ALT, author-reported relative secretion units | 4 | 0.030831 | 0.031399 | 0.029318 |

Interpolation still leads both Yuan endpoints in Table 5, and all five selected-versus-interpolation Holm-adjusted p-values equal 1. Adjusting capacity recovers part of the lost accuracy; interpolation remains a practical choice for these small training sets.

A separate Bircsak replay [37] tests these predictor choices on six drugs using digitized published viability and albumin means. The selected viability correction improves on interpolation in five drugs and worsens in one; the original leaf-50 model retains the lowest mean error. Albumin selection returns interpolation (Table 6).

**Table 6. Bircsak external replay.** The same six test drugs contribute both endpoints. MAE averages hidden queries within each curve, then weights drugs equally. Endpoint units remain separate.

| Endpoint | Training-selected | Original leaf-50 | Interpolation |
|:--|--:|--:|--:|
| Viability, percentage points | 19.104155 | **17.372178** | 20.716898 |
| Albumin, ng/mL | **280.097154** | 322.109616 | **280.097154** |

Each method reports **0 of 12 drug–endpoint curves**. The selected and interpolation envelopes cover all twelve curves, but their width keeps the action at further measurement despite the prediction gains (Figure 5). Appendix C.4 gives the frozen prediction sequence, envelope widths and limits of the digitized source.

![Figure 5. Forecasts, requested measurements and errors in the liver-chip replays. Panel a shows six drugs and two endpoints, giving twelve Bircsak curves normalized to their own lowest-concentration response. The research response-reduction threshold is half that response (50%). Bold-outlined filled points are the three inputs; at hidden points, the outer ring is the training-selected prediction and the inner core the revealed published mean. A triangle marks the frozen next-concentration request. Point colors saturate at 0–100%; the right column retains the numerical scale for the requested-point prediction, revealed mean and 90% envelope. Diamonds above circles show forecasts and revealed means, respectively; their vertical offset separates the marks while preserving response values. After prediction freeze, the requested published means lie at or below threshold in 7 of 12 curves. Actions remain measure-next, with 0 of 12 reports. This retrospective replay uses digitized 72 h means and custodian-separated prediction freeze; the envelopes concern these means and use the stored drug-level calibration. Appendix C.4 gives the source and calibration limits. Panel b shows Ketoconazole viability in original % live iHep units against concentration in µM; its threshold, 44.886364, is half the lowest-concentration response. Panel c compares the five leave-one-drug-out endpoints in Table 5 and two Bircsak external-replay endpoints in Table 6. Each ratio divides drug-equally-weighted MAE in the endpoint's original units by interpolation MAE; below 1 means lower error. Training-selected circles and original leaf-50 triangles occupy separate rows within each endpoint. Bars count drugs with lower, equal or higher training-selected error than interpolation. Row denominators are 6, 6, 6, 5, 4, 6 and 6 drugs. Drugs recur within studies, and endpoints retain separate comparisons.](figures/F5-liverchip.png){#fig-liverchip width=100%}

# 6. Inspecting responses and exporting screening actions

In the [Chip Forecast workbench](https://logxio.github.io/ooc-evaluation-audit/workbench/), **Chemicals** displays measured wells, reconstructed responses and empirical intervals alongside plate positions and comparator errors. Select a chemical and a three-concentration design, inspect where its forecast interpolates or extrapolates, and use **Download actions** to export the decision. **Your data** accepts a planned concentration layout and displays its saved held-out replay.

Figure 6 connects three curves to their actions. Trimethyltin hydroxide's predicted high-dose decline supports a correct active call. Terbufos's forecast also reaches activity, while its small rank margin sends the design to series completion. For Diazoxon, the predicted high-dose decline contrasts with a positive held-out mean. The response curve in c shows the discrepancy, and its labeled position in the historical decision plane in d places the wrong active report among all 970 replay designs.


![Figure 6. Curves and actions in the historical 970-design replay. Panels a–c display one DIV 12 feature with nominal 90% well-response prediction intervals and the saved action for each example. Panel d plots stored forecast activity score against rank margin. Score is the maximum absolute DIV-mean response across features and concentrations, combining measured inputs with forecast completion. Across all 970 designs from 194 chemicals, 826 reports agree with the full-series call, 79 reports disagree, and 65 designs request series completion. Labels a–c mark the three examples; the adjacent stacked counts use margin bins of width 0.04. The measured-reference cutoff is 3. Fitted forecast-call cutoffs are 2.9836 in fold 1 and 2.9994 in folds 2–4; their chemical-weighted mean, 2.9954, is drawn as one vertical line. Reporting requires margin strictly above 0.03 in folds 1–3 (horizontal line) and above 0 in fold 4. These saved historical actions are distinct from the nested 965-design analysis in Figure 4. COMPLETE SERIES adds the remaining measurements. Trimethyltin hydroxide uses design 5 here and design 1 in Figure 1.](figures/F6-cases.png){#fig-cases width=100%}


The **Patients** view makes measured organoid responses and published clinical outcomes inspectable in the same way. Open the rectal cohort and select **Reveal outcomes** to compare the calls with their reference, then **Download actions** to export the patient list (Figure 7). Compatible patient tables can be pasted and processed in the browser, with measurements kept on the local machine.

On the fixed 43-patient rectal test split, the measured combined-regimen signal yields 43 reports with one wrong call, versus 27 reports with four wrong calls for the earlier agreement rule. The fixed combined-signal cutoff gives the same result as calibration, locating the gain in the measured assay. Appendix C presents the regimen-matched comparison, its failed equal-risk target against the strongest single component, and the action-level costs.

![Figure 7. Inspecting the published rectal-cancer cohort after revealing outcomes. Both axes show day-24/day-0 organoid size ratios on log scales. Teal filled/open markers denote sensitive/resistant calls; red marks the single wrong call among 43 patients. Download actions exports the patient call list. The header's 56.6% saving refers to the historical chemical-screen replay.](workbench/shots/reveal.png){width=100%}

# 7. Discussion

Completed concentration-response curves contain training examples for many possible sparse designs. Learning across those designs makes the recorded assay useful beyond the particular concentrations chosen in one experiment. The matched-budget result identifies a contribution from this coverage, while the acquisition result shows that the observed response can improve the choice of the next concentration. Reporting gives those predictive gains an experimental purpose: deciding which series to complete.

We envisage a prospective organ-chip screen in which three initial concentrations inform both the activity call and the next allocation of cultures. Predicted responses would be stored before additional measurements are made; unresolved chemicals would receive the concentrations expected to clarify their response. A matched fixed-budget comparison across independent experimental batches would measure the number of completed chemical assessments alongside errors and the full laboratory cost. The workbench already makes the measurements, forecasts and actions visible together, providing the interface through which researchers can inspect this sequence as it unfolds. Our aim is to make response-guided measurement a routine part of organ-chip screening, expanding the number of compounds studied within the same culture budget.


# Appendix A. Forecasting methods and sensitivity analyses

![Figure A1. Locating response examples within the distribution of gains over interpolation. The upper strip ranks all 194 chemicals by AnchorBoost minus interpolation MAE over all recorded outputs and five designs; examples a–c occupy ranks 1, 98 and 194, with rank 98 representing the middle of this even-sized set. Each curve retains the DIV 12 feature with the greatest measured concentration variation, the chemical's first published three-point design and its own fold model. Open circles reveal held-out measured means against the predictions. Panel d shows per-output absolute-error differences (AnchorBoost minus interpolation), averaged first over hidden target concentrations and then over five designs, for 17 features across DIV 5, 7, 9 and 12. Negative values favor AnchorBoost; gray cells lack a recorded target. Panel e compares AnchorBoost, interpolation and CNP MAE over all recorded outputs and five designs, extending beyond the single feature and design in a–c. The largest loss is retained alongside the largest gain and middle-ranked example.](figures/A1-examples.png){width=100%}

## A.1. Model specification and frozen development protocol

The public EPA network-formation benchmark contains 243 chemicals and 6,902 exposed wells, with 17 features on days in vitro (DIV) 5, 7, 9 and 12 [32,33]. A nominal seven-concentration series in triplicate uses 21 exposure wells and follows firing, bursting and synchrony over twelve days. We use the NeuroChip Twin v2 packaging, five chemical folds and five seeded context designs per chemical and concentration count. The primary static comparison uses three measured concentrations and the 194 chemicals in folds 1–4; fold 0 supplied method development. The target is the mean response at an unmeasured concentration. Absolute errors are averaged over available day-feature entries and designs within a chemical, then equally across chemicals.

The published CNP comparator uses an interpolation-informed decoder, local dose attention and a three-seed ensemble. Our implementation reproduces its published interpolation errors within 0.0001 for every chemical at one to four measured concentrations. Features and hyperparameters were frozen publicly before evaluation of folds 1–4.

For a training chemical with L concentrations, AnchorBoost enumerates the possible three-concentration contexts. It interpolates in log concentration with flat continuation outside the measured range, then learns the residual at each remaining concentration.

The static model is scikit-learn's `HistGradientBoostingRegressor` with absolute-error loss, 600 iterations, learning rate 0.05, at most 127 leaves, minimum leaf size 50 and early stopping disabled. The target is the concentration-mean response minus log-concentration interpolation. Features comprise that interpolation, measured response levels and slopes, gaps and extrapolation distances, query position, measured activity summaries, Hill and analog deviations, and output day/feature identity. The analog pool contains the ten nearest training chemicals and excludes each chemical from its own training examples. Missing responses retain their masks.

At three measured concentrations, full scalar enumeration produces approximately 2.6 million training rows per fold. Eleven configurations were tried on development fold 0; `chip_forecast_protocol.json` retains each entry and the selected fold-0 error of 1.061. Public commit `2b4c20e` froze the protocol before primary scoring. Amendment `0cff5d2` fixed the single-concentration slope case; feature arrays for 1,080 designs at two to four concentrations remained identical. The static protocol's bootstrap uses 4,000 chemical resamples, seed 0; the released strong-baseline package uses 10,000 and supplies the more precise CNP intervals in Table 1.

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

# Appendix B. Next-concentration selection and reporting calibration

## B.1. Acquisition policies, scoring and exposure-well costs

The full four-fold acquisition experiment includes 194 chemical labels and 970 initial designs. The common comparison in Table 3 removes phenobarbital to match the historical CNP identity sensitivity. Both AnchorBoost arms are trained jointly for three- and four-point contexts, with equal scalar rows, features and 600 iterations; CNP uses its original three-seed checkpoints. Each context in the broad design pool has training rows. Predictions are recomputed from the enlarged context after acquisition, with zero gradient updates.

The highest-dose control was specified after the original three-policy results. For broad-coverage AnchorBoost, highest-dose acquisition improves on random by 0.033379 [0.012006, 0.054253]. Its paired intervals use 10,000 chemical bootstrap samples, seed 0, conditional on fitted models. Among common designs with the highest concentration already measured, the highest-minus-disagreement effect is +0.038502 [0.019546, 0.059033]; among those with it initially absent, +0.048033 [0.025690, 0.073603]. The strata contain 181 chemicals/406 designs and 190 chemicals/559 designs, with 178 chemicals present in both. Each stratum averages designs within a chemical before averaging chemicals.

The mean error difference decomposes into the selected point's measurement contribution, **0.029504 [0.015705, 0.044897]**, and reconditioning at the remaining targets, **0.012738 [0.005575, 0.021083]**. This is an arithmetic decomposition of saved predictions. On the 193-chemical common cohort, the coverage-by-acquisition difference-in-differences against random is −0.001080 [−0.006528, 0.003633]. Under identical disagreement-selected doses, broad AnchorBoost minus CNP is −0.011084 [−0.027840, 0.004367].

Disagreement is the across-predictor standard deviation, averaged over available day–feature outputs at each candidate concentration; the policy selects its maximum. Maximin instead maximizes the distance to the nearest measured log concentration.

Each policy spends one extra concentration per design, and replicate counts vary by concentration. On the complete 194-label ledger, 2,910 initially measured concentrations become 3,880. Final exposure-well totals are 15,077 for highest, 15,129 for disagreement, 15,083 for maximin and an expected 15,186.478175 for random. The policy comparison matches concentration count, with these separate well costs. The local 49-chemical pilot is retained in its own directory; Table 3 uses the complete four-fold Kaggle outputs.

## B.2. Nested drug splits and calibration

The full nested population contains 237 conservative drug groups from 243 substances and 1,215 designs. DTXSID/SPID mappings and parent grouping join phenobarbital forms, tributyltin forms, manganese salts, allethrin/stereoisomer and DDT/isomer. These are conservative partition groups; pharmacological equality is a separate question. A group takes its lowest original fold, moving four substance assignments. All sources of a group remain in the same role.

In each outer fit, two of the remaining folds train and two calibrate. Within the training set, a frozen hash defines two inner folds. Vehicle controls associated with training-drug plate/date keys fit the transform; duplicate physical controls count once. Inner fits repeat this restriction. Unseen plate centers use the training median for that DIV. Training-inner predictions determine weighted cutoffs, empirical-rank references and descriptive residual bands. Each drug receives total weight one. Calibration and test then use the same final training fit, transform and rule family. Calibration chooses only the reporting margin. Test predictions and actions are saved before the remaining responses are scored.

For drug g and design d, let the predicted and full-series activity calls be $\widehat{a}_{gd}$ and $a_{gd}$, and the rank confidence margin be $m_{gd}$. The calibration loss averages wrong reports across the drug's $D_g$ alternative designs:

$$
L_g(\lambda)=\frac{1}{D_g}\sum_{d=1}^{D_g}
\mathbf{1}\{m_{gd}>\lambda\}\,\mathbf{1}\{\widehat{a}_{gd}\ne a_{gd}\}.
$$

The selected margin is the smallest fixed-grid value satisfying

$$
\frac{\sum_{g=1}^{n_{\mathrm{cal}}}L_g(\lambda)+1}
{n_{\mathrm{cal}}+1}\leq 0.10.
$$

Each drug contributes one bounded loss, regardless of its number of substance labels or designs. With independent training and exchangeable calibration/future drugs, conformal risk control concerns expected marginal drug loss [30].

The margin grid is −1, 0, 0.01, …, 1, with strict acceptance `margin > lambda`. The corrected calibration denominator counts drugs. An empty feasible set sends every design to complete measurement; fewer than nine calibration drugs cannot satisfy the 10% correction even with zero empirical loss. Arithmetic checks cover this branch, group-replication invariance and an exchangeable toy population. Completed-run verification confirms all five outer identity splits, all fifteen model fits, hidden-target value/mask invariance (maximum prediction change 0), and unchanged preprocessing after perturbing 48 held-out-only control rows.

**Table B1. Outer-fold reporting results.** Fold 0 is the historical development fold; main-text estimates pool folds 1–4. Reporting and wrong/all weight designs; mean drug loss weights drug groups equally. AB denotes AnchorBoost.

| Fold | Test drug groups | Designs | AB reporting | AB wrong/all designs | AB mean drug loss | Three-point reporting |
|:--|--:|--:|--:|--:|--:|--:|
| 0, development | 49 | 250 | 90.40% | 10.00% | 10.20% | 61.60% |
| 1 | 48 | 250 | 92.40% | 6.40% | 6.67% | 66.80% |
| 2 | 49 | 255 | 100.00% | 7.06% | 6.94% | 91.76% |
| 3 | 45 | 230 | 100.00% | 10.00% | 10.22% | 81.30% |
| 4 | 46 | 230 | 100.00% | 8.70% | 8.70% | 94.78% |

Calibration sizes are 91, 91, 91, 95 and 94 drugs. AnchorBoost selects margin 0.05 in folds 0/1 and −1 in folds 2/3/4; −1 reports every design. Corrected calibration losses are 8.91%, 9.35%, 9.78%, 9.17% and 8.63%. Each fold has a feasible margin.

The 4,000-resample drug bootstrap keeps fitted decisions fixed. Against interpolation, the reporting difference is +16.31 points [12.64, 20.16], the drug-loss difference +0.00 [−1.91, 2.02], and the forced-full-report error difference −4.56 [−6.81, −2.34]. The primary exposure-well cost is the sum of the measured wells for reported designs and the full series for fallback designs. The full-series label is a measured in-vitro reference, so its self-comparison has zero error by construction. The observed-activity rule also has zero error: a maximum-response threshold crossed at a measured concentration is necessarily crossed in that concentration's full series. Folds 2–4 select full reporting from calibration.

## B.3. Historical 970-design reporting results

**Table B2. The earlier public decision replay, kept as a separate experiment.** These are the values behind the current public workbench and `ledger/` outputs.

| Historical rule | Reports / 970 | Wrong / all | Wrong / reports | Exposure-well equivalents |
|:--|--:|--:|--:|--:|
| AnchorBoost | 905 (93.30%) | 79/970 (8.14%) | 79/905 (8.73%) | 12,240 |
| Measured points only | 711 (73.30%) | 79/970 (8.14%) | 79/711 (11.11%) | 15,373 |
| Complete series | Reference | Reference | Reference | 28,185 |

The historical saving is **56.6%** relative to complete measurement and **20.4% [16.5%, 24.0%]** relative to measured-only fallback. Initial measurements account for 11,395 wells and fallback adds 845. A uniform seven-concentration, triplicate model gives 53.3% instead; concentration counts and observed replicate allocation explain the difference. A separately outcome-selected 5% operating point reports 74.4% versus 56.4% of designs. That operating point is a retrospective sensitivity.

The earlier forecaster and calibration roles overlapped, calibration counted design rows, and preprocessing used global controls. The nested refit separates all three. Identity grouping and normalization also change, so the numerical difference between 56.6% and 58.73% combines several changes. The original static 194-label benchmark, the 193-chemical CNP/acquisition sensitivity and the nested 188-group analysis answer different questions. Even where both newer analyses contain 965 designs, their grouping, fits and response scales remain distinct.

Figure 6 illustrates three saved actions. Trimethyltin hydroxide, design 5, reports activity correctly after nine exposure wells. Terbufos, design 4, has rank margin 0.0286 below the historical 0.03 threshold and requests all 21 wells. Diazoxon, design 3, reports activity despite an inactive measured reference, driven by its predicted high-dose response.

A still earlier fixed low/middle/high design on an 81/81/81 split reports all 81 test chemicals with six errors (7.41%, exact interval 2.77%–15.43%). At the observed 10% budget it leaves zero reporting headroom. It is retained as a ceiling case for that particular fixed design and endpoint.

# Appendix C. Patient and organ-chip validation

## C.1. Organoid response and patient-action comparisons

The patient workflows use source-specific endpoints and treatment maps. Their output is a research follow-up action. Clinical treatment effects and outcomes of actual retests remain outside these replays.

For the 43-patient rectal workbench example, the data split is 42 training, 42 calibration and 43 test patients. The primary regimen-matched subset contains 36 test patients receiving radiation, capecitabine and irinotecan; the assay uses 5-FU as capecitabine's proxy. The measured combination reports 36 with one wrong call, versus 20 with three wrong for the older agreement rule. The coverage difference is +44.44 points [27.78, 61.11]. The remaining seven test patients lack clinical irinotecan and belong to the all-patient sensitivity.

Training selects irradiation as the strongest single component. Under the same calibration it reports 12 of the matched 36, with six errors, exceeding the registered 10% overall-error target at 16.67%. The primary equal-risk comparison therefore fails. At full coverage, the combination makes one error versus twelve for that component, a 30.56-point reduction [13.89, 47.22], paired exact p=0.00342. Adding the separately defined seven-patient pancreatic mean-rank comparison gives a descriptive 43-patient, source-stratified reduction of thirteen errors; its different endpoints and comparators remain separate from calibration.

The all-patient action comparison converts sixteen retests to correct reports and corrects four earlier errors, while adding one new error and leaving twenty-two calls unchanged. At retest cost 0.25 relative to a wrong call, batch loss falls from eight to one. That seven-unit gross reduction supports a break-even additional assay cost of **7/43 = 0.16279 wrong-call equivalents per patient**. At an added assay cost of 0.20, batch loss instead rises by 1.6 units. Actual monetary and staff-time costs require measured inputs.

**Table C1. Frozen-prediction organoid replays.** Counts are source-specific; the rectal analyses and Figure 7 reuse the published cohort. A freeze before opening individual outcome values is a computational sequence on published studies.

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

A pooled rank-logistic candidate reports 21/43 with seven wrong, versus 14/43 with six wrong for an equally calibrated single readout. Both exceed the intended observed budget. The combined-regimen signal in Section 6 provides the useful alternative, and its fixed-threshold equality identifies where that benefit comes from. Yao's eighty-patient supplement overlaps the already used rectal cohort and contributes zero confirmed independent patients.

## C.3. Physical-chip endpoints and experimental timing

On Dai's 22 vascularized colorectal tumoroid-chip patients [18], the frozen two-channel mean gets 17/22 correct, a nested channel selector 20/22, and a post hoc best vessel channel 21/22. Agreement reports twenty with nineteen correct. The method was developed after inspecting this cohort. In independent osteosarcoma organoids [23], post-treatment agreement reports eleven of thirteen with ten correct; pre-treatment agreement reports six of seventeen with three correct. The latter is a substantive failure when component readouts are near chance.

Steinberg's paired spheroid area and viability measurements [19] have opposite signs in 14/49 patient-drug pairs, and area misses 12/40 viability decreases. The workbook contains 49 pairs where the caption says 48. Patient-derived spheroid measurement provenance and regimen matching limit the chip/clinical interpretation. Hu's lung microwell study [20] has ten author-defined clinically comparable lines among twenty-one tested; two of the ten rely on a comparison involving prior treatment. The remaining eleven lack an eligible paired outcome or treatment match.

Ewart's two-donor safety replay uses uncorrected margins of safety with threshold 50 [31]. On eighteen shared drugs, the donor union flags twelve of fifteen hepatotoxic drugs and clears all three safe drugs. All three donor disagreements are known toxicants; levofloxacin, stavudine and tacrine are shared misses. Agreement reports fifteen with twelve correct. Donor 2's visible per-drug table contains ten true positives while the source summary reports nine. The protein-binding-corrected thresholds of 375/2250 belong to different inputs.

Schuster's three-patient microfluidic study [17] has 8/48 schedule contrasts reverse direction between 24 and 72 hours and 13/48 stabilize after 24 hours. A held-patient temporal forecast has MAE 0.407105 versus 0.152629 for persistence, losing for all three patients. In Petreus [21], the chip's preferred schedule is confirmed against both alternatives at mouse day 35; earlier comparisons remain unresolved. That result rests on twenty of forty-five nominal animals and reverses under the recorded missing-value sensitivity. In Zhai [22], the frozen confirmation rule first succeeds at administration three in the source's Figure 3d and two in its Figure 4c, with full-cohort concordances up to 0.980. Final administrations lose attrition robustness. These are cell-line mouse arms defined by the source, with no supplied individual chip-to-mouse reading key.

## C.4. Bircsak data partition, prediction freeze and scoring

The separate Bircsak study [37] uses digitized published means from twenty-one drugs: six training, nine calibration and six test drugs, with both endpoints of each drug together. Predictions were frozen on 5 October at 01:19 JST, references were released at 01:33, and scoring completed at 01:35. Reconciliation verifies all 138 predictions and 36 action records, with the original fitted models and frozen predictions unchanged.

Table 6 gives the endpoint errors. Selection chooses pure interpolation for albumin and a 0.25-scaled residual correction for viability; the latter lowers mean error by 7.785% relative to interpolation. The selected/interpolation envelope covers 46/46 hidden queries, compared with 44/46 for the original model. Mean widths are 174.81 percentage points for viability and 2,847.03 ng/mL for albumin. All methods request further measurement; conditional error among reports has a zero denominator. Calibration uses nine drugs' maximum standardized residuals across endpoints and queries. At the nominal 90% level, the conformal order statistic is the largest of those nine residuals. All viability-query upper limits exceed 100%; the frozen envelopes retain their original range.

The data custodian saw the full test curves while digitizing and checking the figures before the protocol freeze and performed no model fitting. Prediction used the partitioned package and the three-point test contexts. This is a custodian-separated, frozen-protocol replay of published aggregate responses. Exact author-supplied response values, donor/batch keys and physical-chip replicate identities are unavailable. Digitization uncertainty remains additional to the calibrated prediction envelope. All methods request the same highest registered next dose; the saved error at that point measures pre-measurement forecast error, while the benefit after measuring it remains a separate experiment.

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

`--check` verifies the published baseline match. Saved fold files in `chip_forecast_runs/` support summary reconstruction. The [strong-baseline package](https://github.com/logxio/ooc-evaluation-audit/tree/main/benchmarks/strong_baseline) includes matched-ablation outputs, identity-aware neural comparisons and separate full-training instructions. The [screen-out CPU notebook source](https://github.com/logxio/ooc-evaluation-audit/blob/main/benchmarks/screen_out_neural/kaggle/cpu_reproduction.ipynb) reproduces statistics from frozen predictions. The [Ewart package](https://github.com/logxio/ooc-evaluation-audit/tree/main/benchmarks/ooc) supplies a source-verified concentration-response reproduction through `sh benchmarks/ooc/reproduce.sh`.

Patient entries include `chip_release.py`, `blind2_predict.py`, `blind2_score.py`, `blind3_score.py`, `tiriac_reproduce.py`, `lung_reproduce.py` and `liver_chip_release.py`. `python horizon_attrition.py` reproduces the schedule/attrition analyses from publisher originals. Source files with restricted redistribution terms are downloaded at runtime.

## D.2. Nested, acquisition and capacity artifacts awaiting release

The nested reporting, acquisition/geometry and capacity experiments are complete locally and await a versioned public code-and-result archive. Their local entries and saved outputs are:

| Experiment | Local code entry | Recorded result files |
|:--|:--|:--|
| Drug-disjoint report-or-measure | `paper_nested_decision.py` | `results.md`, `summary.json`, `drug_decisions.csv`, `design_decisions.csv` |
| Data-flow and arithmetic verification | `paper_nested_decision_check.py` | `verification.json`, `data_flow.md` |
| Prediction export | `paper_nested_decision_export.py` | `point_predictions.csv.gz` |
| Full acquisition | `paper_acquisition.py` | `summary.json`, per-design and per-drug results, `completion.json` |
| Highest-dose control | `paper_acquisition_geometry.py` | `results.md`, `contrasts.csv`, `choices.jsonl` |
| Capacity selection / external replay | `paper_capacity.py`, `paper_capacity_independent.py` | selected fits, `scores.json`, `score_audit.json`, prediction freeze |

The nested output also contains `protocol.json`, `splits.json`, `identities.json`, per-fold `pretest_freeze.json` and `prediction_freeze.json`, and all fitted-stage artifacts. Its completed export contains 358,360 point rows. Protocol SHA-256:

```text
d15f70d8ba11f111516a13a087d3970ea270bb2e9711547db8aaf6b6f71ff20d
```

With that experiment directory supplied, the working-copy summary and verification commands are:

```sh
python paper_nested_decision.py summarize --out RESULTS_DIR
python paper_nested_decision_check.py --out RESULTS_DIR
python paper_nested_decision_export.py --out RESULTS_DIR
```

`RESULTS_DIR` denotes the saved experiment artifact directory. Acquisition geometry uses the complete four-fold prediction archive and its recorded `analysis_spec.json`; those inputs accompany the forthcoming experiment package. Bircsak includes the original prediction freeze and the reconciled post-reveal scores in Appendix C; `paper_capacity_score_audit.py` checks its curve and point-level results.

## D.3. Compute requirements and recorded executions

The original forecasting fits took 222–235 seconds per fold on free Kaggle CPU. The completed public forecast notebook v4 ran the one-to-four-concentration entry in 46 minutes; 855 numeric result fields and 3,888 CSV rows matched the registered run. The physical-chip/patient notebook v14 completed seventy cells on free CPU, and the separate external clinical replay completed seven cells.

The nested evaluation fitted all fifteen inner/outer models. Fold 0 ran locally and folds 1–4 used Kaggle CPU jobs. Verification records five completed outer folds and matching source/model hashes. Local fitting peaked at 781,484,032 bytes and 216.99 seconds; recorded remote fits peaked at 647,757,824 bytes and 62.44–125.18 seconds.

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

The live external run used Doubao-Seed-2.1-pro at medium reasoning effort, with up to 24 model calls, 64 tool calls and 1,000,000 cumulative tokens per paper. It cost approximately CNY34.1 at recorded list prices, with interrupted first requests adding an estimated CNY1.0. Provider models are commercial services. Their names and settings appear here as experimental provenance. Fresh extraction requires a configured provider or the documented local route. The tested free local Qwen3-0.6B GGUF route, served through llama.cpp, scored 0/100 on its separate extraction benchmark; its outcome does not reproduce the commercial agent's accuracy.

The effective free reproduction is `python -m contract_agent.replay_agent`: it executes the saved contracts and source references offline, using the Python standard library. This replays the reported computation; it leaves fresh model generation as a distinct experiment. The repository retains provider settings, cached outputs, source licenses, model-weight attribution and the documented local setup. Quantitative forecasting and the workbench operate independently of this optional agent.

# Appendix F. Source terms and competition contributions

The pre-existing EPA measurements, NeuroChip Twin code and evaluation protocol, clinical studies, HNOCA atlas and image dataset retain their original attribution. The competition contribution is the sparse-design learner, controlled comparisons, acquisition and reporting experiments, study-specific follow-up analyses, workbench and executable reproduction routes. AI assistance supported programming and prose. Completed biological experiments and clinical cohorts belong to their original investigators.

Yan Su is responsible for methods, code, computational experiments and the report. Ziyang Liu is responsible for biological review, participant recruitment for trial use and presentation collaboration.

The present research stage comprises retrospective assay analyses and published-cohort replays. Independent participant sessions completed: **0**. Prospective wet-laboratory validation, measured staff-time savings and real laboratory well-use savings remain to be established.

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

Our code is MIT licensed. NumPy, SciPy, scikit-learn, pandas and h5py use BSD-3-Clause; PyTorch uses its BSD-style license; Pillow uses MIT-CMU; Requests uses Apache-2.0; openpyxl and rdata use MIT [4–8,13,14]. Package versions are pinned by the experiment-specific requirements; PyTorch and pandas support the neural benchmarks, while rdata and openpyxl read the original assay files. The package distributions carry their upstream license notices. The optional paper agent documents its commercial APIs, Apache-2.0 Qwen3 local-model alternative and MIT llama.cpp runtime separately. Learned forecasting weights are produced by the documented fits; commercial language-model access supplies no hidden dependency for those predictions.


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

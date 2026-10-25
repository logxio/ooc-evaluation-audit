# Stratified Literature Survey and Paired Coding Agreement

The PubMed candidate frame contains 17,386 records from 2019 to 2026 across 85 sampling strata. The original stratified random sample comprises 400 papers. The released analysis contains 399 paired papers with Horvitz Thompson weights summing to 17,376. The sampling lock records the frame, sampling seed and within stratum selection algorithm.

Q and R contribute 6,905 and 5,239 evidence checks, respectively, for 12,144 checks of original quotations and image hashes. R includes 253 image hash checks. The released statistics describe evidence aligned paired coding. Each numerical field retains its observed status, and each available case estimate retains its own denominator.

## Twelve field agreement

Intervals use 10,000 paired paper bootstrap draws within the original sampling strata, seed 20261024. Interval variables use squared differences; nominal variables use inequality indicators. Point estimates range from 0.8054 to 1.0000. All 36 point estimates across the three reported analyses meet 0.80.

| Field | Comparable papers | Observed agreement | Alpha | 95% interval | Valid bootstrap draws | Normalized alpha | Projection alpha |
| --- | --- | --- | --- | --- | --- | --- | --- |
| physical_model | 195 | 86.67% | 0.8660 | [0.8208, 0.9081] | 10000 | 0.8660 | 0.8910 |
| claimed_n | 90 | 76.67% | 0.9866 | [0.2060, 0.9969] | 10000 | 0.9866 | 0.9866 |
| independent_human_donor_n | 38 | 78.95% | 0.9468 | [0.7770, 0.9951] | 10000 | 0.9468 | 0.9468 |
| technical_pseudoreplication_ratio | 14 | 42.86% | 0.8054 | [0.5614, 1.0000] | 9605 | 0.8054 | 0.8054 |
| raw_multidose_public_level | 41 | 95.12% | 0.8816 | [0.6802, 1.0000] | 10000 | 0.8816 | 0.8816 |
| clinical_attrition | 5 | 60.00% | 0.9954 | [0.9766, 1.0000] | 9310 | 0.9954 | 0.9954 |
| treatment_timing_match | 109 | 99.08% | 0.9202 | [0.6627, 1.0000] | 9997 | 0.9202 | 0.9202 |
| positive_doses_ge5 | 65 | 93.85% | 0.8636 | [0.7231, 0.9676] | 10000 | 0.8636 | 0.8636 |
| positive_doses_ge6 | 64 | 95.31% | 0.8673 | [0.7045, 1.0000] | 10000 | 0.8673 | 0.8673 |
| strict_clinical_eligible | 148 | 99.32% | 0.8542 | [0.0000, 1.0000] | 9867 | 0.8542 | 0.8542 |
| cutpoint_in_sample | 6 | 100.00% | 1.0000 | [1.0000, 1.0000] | 8612 | 1.0000 | 1.0000 |
| n_distinct_positive_doses | 86 | 90.70% | 0.8779 | [0.7123, 0.9777] | 10000 | 0.8779 | 0.8779 |

Normalization applies exact vocabulary aliases. The common dimension projection supplies a separate sensitivity analysis. The table retains the comparable paper count and interval for each field, including fields with five or six comparable papers.

## Weighted prevalence by coding channel

Each estimate divides the Horvitz Thompson numerator by the available case Horvitz Thompson denominator among papers eligible in that channel. Q and R retain their own eligibility decisions. The intervals use the same stratified paper bootstrap as the agreement analysis.

| Indicator | Q estimate | Q 95% interval | Q papers | R estimate | R 95% interval | R papers |
| --- | --- | --- | --- | --- | --- | --- |
| Human models | 88.91% | [84.28%, 93.28%] | 193 | 89.53% | [85.44%, 93.43%] | 217 |
| Direct patient material | 48.39% | [40.87%, 55.94%] | 193 | 52.06% | [45.19%, 58.91%] | 217 |
| Chip models | 14.94% | [10.07%, 19.84%] | 193 | 15.39% | [11.06%, 19.73%] | 217 |
| At most three independent human donors | 53.66% | [39.18%, 69.27%] | 44 | 65.36% | [57.26%, 73.42%] | 139 |
| Public raw multidose tables | 5.28% | [0.09%, 13.13%] | 44 | 15.10% | [10.26%, 20.12%] | 192 |
| Absent clinical outcome linkage | 94.84% | [90.30%, 98.82%] | 113 | 96.29% | [93.51%, 98.79%] | 217 |
| Strict clinical eligibility | 2.23% | [0.00%, 4.98%] | 154 | 2.13% | [0.51%, 4.32%] | 217 |

## Data and recalculation

[Paired observations and sampling weights](sample400_agreement_v2.json), [agreement formulas](agreement.py) and [sampling lock](sampling_lock.json) supply the released analysis. Paper aliases preserve all 399 Q and R observations and statuses for each field. The verifier recomputes 36 alpha estimates and their bootstrap intervals, all 28 channel specific Horvitz Thompson estimates and their intervals, and the distributed SHA256 digests.

```sh
python workbench/audits/survey400_s54/public_s58/verify_survey.py
```

# Shared design-conditioned neural transfer

This frozen four-screen experiment uses a 14,449-parameter set encoder with a
log-linear residual anchor. One set of weights in each fit serves all source
screens and endpoints, conditioned on observed design, dose and endpoint descriptors.
The two-epoch protocol and all 11 fitted models are included.

From the repository root, with NumPy installed, one offline command recomputes
every main-table error and paired confidence interval:

```sh
python benchmarks/screen_out_neural/aggregate.py
```

Install the small environment once with
`python -m pip install -r benchmarks/screen_out_neural/requirements-aggregate.txt`.
The command streams 271,766 target/prediction cells, calculates five-design MAEs,
and resamples paired chemical identities 4,000 times (seed 0). AnchorBoost and
published NP use frozen **per-chemical reference errors**. Frozen summaries serve
only as post-computation checks. All 326 drug-endpoint rows and 26 table rows
matched exactly: maximum numerical difference **0.0**. Outputs are
[`recomputed/main_table.csv`](recomputed/main_table.csv),
[`main_table.md`](recomputed/main_table.md), `drug_results.json`, `summary.json` and
[`resources.json`](recomputed/resources.json). CSV/JSON include both ordinary 95%
and six-comparison familywise intervals. `--probe` evaluates one complete chemical.

| Measured run | Time | Peak process RSS | GPU allocation / reservation |
|---|---:|---:|---:|
| Offline single-chemical probe | 0.103 s | 40.21 MB | CPU |
| Full offline aggregation | 0.900 s | 185.24 MB | CPU |
| Original 11 neural fits | 346.33 s in fit blocks | 2,492.19 MB maximum fit RSS | 33.97 / 50.33 MB |
| Original experiment, including evaluation and reference refit | 426.39 s (0.11844 h) | See fit peak above | One Tesla T4 used; two visible |

MB are decimal. Aggregation measurements use Python 3.13.14 / NumPy 2.5.3 on
macOS arm64, excluding interpreter startup. Original training used Python 3.13.15,
PyTorch 2.11.0+cu128 and NumPy 2.1.3. The original scikit-learn version was not
recorded; retraining on other environments may vary. Full retraining is separate:

```sh
python -m pip install -r benchmarks/screen_out_neural/requirements-train.txt
python benchmarks/screen_out_neural/run_experiment.py --probe --out training_probe
python benchmarks/screen_out_neural/run_experiment.py --device cuda --out trained
```

`--device cpu` supports CPU training. Full CPU training time is unmeasured. The
public training probe passed target-readout poisoning, set permutation invariance
and four-screen log-linear design parity. The original experiment consumed free
Kaggle compute; recorded paid cost and scale-up recommendation are both **$0**.

**Evaluation scope.** Screen-out excludes the whole target screen and all its
chemical identities from every source screen. Within-screen uses one shared
original fold-1 fit for NFA/acute/Harrill and six Ewart leave-one-drug-out fits.
Both regimes evaluate the same 49/79/17 chemicals and six Ewart drugs at three
endpoints. AnchorBoost and published NP are target-screen-trained references, with
stronger target-domain access than screen-out neural transfer. The published NP
comparison covers NFA only. `identities.json` and `splits.json` preserve alias and
split decisions; the Harrill reference excludes a cross-fold valproate alias.

Response-scale fitting uses training rows; observed-context amplitude uses only
the three measured concentrations. The inherited matrices retain the original
control transforms, pooled vehicle normalization and acute outlier filtering.
Isolation claims are conditional on these frozen matrices. Ewart MAEs remain
separate in each endpoint's author units. The model lost to AnchorBoost on NFA,
acute and Harrill screen-out tests; Ewart albumin improved by 3.5940 MAE units,
with a six-drug familywise interval crossing zero. All negative results are kept.

**Files and provenance.** [`summary.json`](summary.json) and
[`protocol.json`](protocol.json) preserve the frozen numerical results and
pre-fit predictions; `predictions.csv.gz`, `comparator_errors.csv`, `tasks.*`,
`models/` and `source/` provide evaluation and training inputs.
[`reproduce.ipynb`](reproduce.ipynb) runs the same offline command locally.
The original [Kaggle notebook, version 2](https://www.kaggle.com/code/loxigicck/shared-design-screen-transfer-s1-1004)
remains private; this package is self-contained. Code is MIT, including the
attributed NeuroChip Twin comparator; Ewart data are CC BY 4.0. EPA source access
and dataset-license qualifications are documented in [SOURCES.md](SOURCES.md).
`checksums.json` covers the packaged scientific inputs and code.

The public [CPU reproduction notebook](https://www.kaggle.com/code/loxigicck/screen-out-neural-cpu-reproduction) completed as version 1,
using Git commit `1fca4edbb7ba2e579e50401179f245a67b33966a` and a pinned manifest SHA-256.
Kaggle confirmed public visibility with GPU and TPU disabled. It downloaded and
verified 54 files (14,618,588 bytes) from GitHub,
including all prepared training inputs and 11 checkpoints, then ran aggregation.
The complete download-and-recompute sequence took **6.23 s**;
aggregation took **2.399 s**, with **171.15 MB** peak process RSS.
All 326 drug-endpoint results and 26 main-table rows matched the frozen experiment;
the maximum main-table difference was **0.0**. Recorded cost was **$0**.
The original private notebook above remains training provenance.

The [local notebook](kaggle/cpu_reproduction.ipynb),
[platform completion](kaggle/platform_completion.txt),
[reproduction receipt](kaggle/reproduction_receipt.json),
[published metadata](kaggle/published_metadata.json) and
[Kaggle table](kaggle/main_table.csv) preserve the actual public run.
`kaggle/prepare.py --commit COMMIT` prepares a notebook for another immutable
public commit. `checksums.json` records the current scientific and publication files;
the completed notebook retains the original source commit's manifest digest.

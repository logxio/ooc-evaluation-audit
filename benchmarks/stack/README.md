# AnchorBoost residual stack

This package reproduces the held-out MAE of the commercial AnchorBoost team on 194 chemicals, four concentration budgets, and five equally weighted designs per chemical. The frozen cells contain TabPFN-2 predictions, LPM predictions (20 seeds for k=1/2; 10 seeds for k=3/4), observed responses, and the selected residual GBM correction. Selection used inner folds of each outer training set; no reported chemical was used to select its own model or weights. The fold-0 T+L weights in `selection.json` describe a separate control.

From the repository root, with NumPy installed:

```bash
python benchmarks/stack/reproduce.py
```

This reads only `members_k*.npz`, `cohort.csv`, and `selection.json`, writes `benchmarks/stack/output/anchorboost_team_k*.csv`, and compares every chemical with `results/final/baselines/`. Measured on a Mac: 0.70 seconds, 89 MB peak RSS, CPU only. The four member archives total 19,339,338 bytes.

To regenerate one fold from public data and public model weights, install `benchmarks/stack/requirements-training.txt` and run:

```bash
python benchmarks/stack/train.py --fold 1 --k 3 --device cpu
```

For k=3 or 4, the command trains the TabPFN-2 teacher, 10 LPM seeds and their five inner out-of-fold teachers, then fits the selected five-bag residual GBM. For k=1 or 2, it trains the TabPFN-2 member and 20 outer LPM seeds. It downloads the 44.4 MB `tabpfn-v2-regressor.ckpt` from [Prior Labs](https://huggingface.co/Prior-Labs/TabPFN-v2-reg) and verifies SHA-256. The EPA NFA task data, task definitions, and CheMeleon features are included locally. No account, paid API, or special hardware is required. A free CUDA GPU shortens training; the unmeasured CPU planning estimate for one complete fold is 100–300 hours, and 16 GB RAM is recommended. One measured fold-1, k=3 run on four RTX 4090 GPUs took 14 minutes 16 seconds, with 1.99 GB peak RAM per teacher process and 7.74 GB peak GPU allocation. It wrote per-chemical results to `output/trained_f1_k3.csv`. Fresh training is stochastic: that run scored 1.141364 MAE and differed from the frozen reference by at most 0.02603 per chemical. Use the first command for exact published values; add `--strict-reference` to the training command to fail on any difference above 1e-9. Stages are separate processes and can reuse finished outputs.

TabPFN code is [Apache-2.0](https://github.com/PriorLabs/TabPFN); its v2 regression checkpoint uses [Prior Labs License 1.1](https://huggingface.co/Prior-Labs/TabPFN-v2-reg/blob/main/LICENSE.txt), which permits commercial use with attribution. The adapted LPM code is [Apache-2.0](training/vendor/lpm/LICENSE.txt), and its weights are trained by this command. CheMeleon features use MIT licensed weights. AnchorBoost code is MIT; EPA NFA measurements are public domain. The source and license inventory is also recorded in `results/final/baselines/methods.json`.

# Frozen chemical-paired comparison

From the repository root, install NumPy once with `python -m pip install -r benchmarks/strong_baseline/requirements.txt`, then recompute all three K-versus-C comparisons and the budget-matched ablation offline:

```sh
python benchmarks/strong_baseline/reproduce.py --out strong-baseline-recomputed.json
```

The command checks [SHA-256 hashes](SHA256SUMS.json), rebuilds external-screen errors from every saved prediction fold, verifies contexts, target means and masks against the included input matrices, and resamples independent chemical identities 10,000 times (seed 0). NFA uses the original published per-chemical score subset; its pointwise checkpoint replay is checked separately. The ablation recomputes chemical means from all five design errors in each of the eight fits and checks equal row/iteration budgets. Frozen results are comparisons for verification, not bootstrap inputs. [Summary JSON](summary.json) links numerically to the detailed results below.

| Comparison | Independent n | Mean difference | Paired 95% interval | Fold wins/losses/ties |
|---|---:|---:|---|---|
| NFA: K − published C | 194 | −0.033342 | [−0.070284, −0.000407] | 3/1/0 |
| Acute MEA: K − C | 383 | −0.015875 | [−0.030804, −0.001256] | 5/0/0 |
| Harrill human DNT: K − C | 69 | −0.049446 | [−0.113124, +0.013459] | 4/1/0 |
| NFA: full enumeration − five-design row-matched training | 194 | −0.022903 | [−0.035089, −0.012074] | 4/0/0 |

Protocols and results: [NFA](nfa/protocol.json), [external screens](external/protocol.json), [ablation](ablation/protocol.json), [same-runtime amendment](ablation/environment_amendment_002.json). Detailed [NFA](nfa/result.json), [acute](external/acute/result.json), [Harrill](external/harrill/result.json) and [ablation](ablation/result.json) JSONs retain all folds, exclusions, sensitivities and Methods/Results text. [Chip endpoint and risk statistics](chips/result.json) retain both preprocessing choices and all five endpoints.

NFA has 194 original test chemicals; a 193-identity sensitivity omits phenobarbital because its sodium form appears in training. C's published float32-input errors and replay with its public float16 bundle are separate columns (maximum per-chemical difference 0.000198948). Acute has 384 source IDs, including two same-fold IDs averaged into one identity. Harrill has 71 labels; its primary analysis excludes two valproate aliases in different folds, while all 71 label results remain available. Absent hN2 targets remain masked. The two external comparisons also report 97.5% intervals; both include zero. Three original Harrill reports failed to serialize empty-subgroup means after saving predictions; those failures and the reconstruction from unchanged arrays are recorded.

**Inputs and licenses.** [Sources and attribution](sources.json) provide pinned URLs and checksums. EPA data are US Government works; the NFA prepared bundle and the C model/evaluation code come from [NeuroChip Twin at f9848800](https://github.com/Agnuxo1/neurochip-twin/tree/f9848800dfab66a8bc005e6b3087153eeaabe9ac). Its MIT [notice](external/source/published_c/LICENSE) accompanies the 194-row, k=3 published C error subset. AnchorBoost source is unchanged from `dbddd7437b9f1643ef2872bd5de86de0779b209b`. Ewart source data use CC BY 4.0 in [the chip benchmark](../ooc/README.md). Yuan statistics here are calculated error summaries; publisher figures and source readings remain at the original DOI under CC BY-NC-ND 4.0. Code licensing does not replace dataset licensing.

**Measured resources.** The offline command took **1.277 s**, peak process RSS **66.26 MB**, with Python 3.13.14 / NumPy 2.5.3 on macOS arm64 (interpreter startup excluded). Its checksum/bootstrap probe used 52.99 MB. The original acute five-fold fits took 1,546.81 s in training blocks, peak RSS 2,175.73 MB; Harrill's two recorded fold reports total 474.88 s, peak 1,802.56 MB, with timing unavailable for the other three reports. All eight matched-ablation fits took 2,874.97 s including evaluation, peak 1,048.75 MB. [Runtime records](runtime.json) include environments and original Kaggle run URLs. Original training used free Kaggle CPU/T4; paid cost was $0. MB are decimal.

Full retraining is a separate, longer operation. Install [the recorded training dependencies](requirements-training.txt), then use the commands below; CPU is supported, and `--device cuda` selects a free GPU when available. Run both ablation arms in the same interpreter. Fresh arrays can be aggregated with `reproduce.py --acute-raw ... --harrill-raw ... --ablation-raw ...`; stochastic/runtime differences remain visible instead of overwriting frozen outputs.

```sh
python benchmarks/strong_baseline/train_external.py --base benchmarks/strong_baseline/external --screen acute --device cpu --probe --out training_probe
python benchmarks/strong_baseline/train_external.py --base benchmarks/strong_baseline/external --screen acute --device cpu --out trained/acute
python benchmarks/strong_baseline/train_external.py --base benchmarks/strong_baseline/external --screen harrill --device cpu --out trained/harrill
for fold in 1 2 3 4; do
  for arm in full five; do
    python benchmarks/strong_baseline/train_ablation.py --fold "$fold" --arm "$arm" --out trained/ablation
  done
done
```

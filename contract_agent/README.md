# Tool-using contract extraction

Give it a published organoid or organ-chip study and it rebuilds the paper's clinical headline from the paper's own tables and figures: which patients, which assay readout, which cutoff, which outcome. Then it recomputes the number, or says exactly which evidence is missing. On 26 external papers frozen before any model call, the unchanged agent reproduces **19/26** published headlines with every record confirmed by hand, and refuses all 4 papers that report no headline. Every number below replays offline from the saved contracts, with no network or model account:

```sh
python3 -m contract_agent.replay_agent
```

## Benchmark: can a model reproduce a clinical headline from the source data?

**Task.** For each paper the agent receives the published metric, value and denominator, the article and every supplementary table and figure. It must return an executable contract whose records bind each patient's assay prediction and clinical outcome to distinct source cells (or to figure cells transcribed by an independent reader or read from pixels), and whose computation reproduces the headline. Ten fields describe the contract (unit, platform, readout, direction, threshold rule and timing, patient mapping, regimen match, denominator, split).

**Data.** Eight papers with row-level data and a locatable headline: drug-induced liver injury on a perfused liver chip (sensitivity 13/15), lung-cancer organoids on a microwell chip (10/10), a colorectal vascularised tumour chip (19/22), rectal-cancer organoids under chemoradiation (45/48), colorectal liver-metastasis organoids (AUC 0.850), colorectal organoids in the FORECAST-1 cohort (24/29), pancreatic organoids (8/9) and lung-cancer organoids (45/54). Two further papers report no global clinical headline and must be refused.

**What current models reach.** Passes are re-checked by hand record by record against the source; that audited count is the score. Pass rates of different models or rounds are never subtracted or pooled.

| Run | Single extraction | + one feedback | Full tool loop, judged | Full tool loop, audited | Controls refused |
|---|---|---|---|---|---|
| Qwen3.8-max, thinking (round 1) | 0/8 | 1/8 | 5/8 (one stopped at call 10) | 3/8 | 2/2 |
| Qwen3.7-plus (round 1) | 0/8 | 0/8 | 1/8 | 1/8 | 2/2 |
| Doubao-Seed-2.1-pro, thinking (round 2) | 1/8 | 1/8 | 3/8 | 3/8 | 2/2 |
| Doubao-Seed-2.0-pro (round 2) | 0/8 | 0/8 | 1/8 | 1/8 | 2/2 |
| Doubao-Seed-2.1-pro, doubled step budget (round 3) | 1/8 | 1/8 | 4/8 | 3/8 | 2/2 |
| Doubao-Seed-2.0-pro, doubled step budget (round 3) | 0/8 | 0/8 | 2/8 | 2/8 | 2/2 |
| Doubao-Seed-2.1-pro + pixel grid reader (round 4) | 1/8 | 1/8 | 5/8 | **5/8** | 2/2 |

**External cohort (round 5): the same agent on papers it was never tuned on.** The eight papers above built the tools and the judge, so their pass rate is a development reading. For round 5 we searched Europe PMC and the PMC Open Access dataset outside those papers and screened 91 candidates. A paper is eligible when it states a headline in a supported metric (accuracy, sensitivity, specificity or AUC), gives per-unit rows in its article or supplements (figures may carry the labels), and a reference recomputation from those rows reproduces the published value within its printed rounding. 32 papers qualify; the first 26 in an order fixed before screening (an earlier candidate list, its spares, then two further searches) entered, with targets frozen in `experiment_v2.json` (`external`) before any model call, plus 4 papers without a global headline as controls. The agent, prompts, tools, judge and limits are those of round 4; only the workspace builder learned to read Word supplements and .webp figures.

| External cohort (Doubao-Seed-2.1-pro, round 5) | Papers | Single extraction | + one feedback | Full tool loop, judged | Full tool loop, audited |
|---|---|---|---|---|---|
| Clinical response: organoids, spheroids, tissue slices, ex vivo cultures, a microfluidic migration assay | 23 | | | 19/23 | **17/23** |
| Drug toxicity: liver microtissue, liver spheroids, a heart chip | 3 | | | 3/3 | **2/3** |
| All eligible | 26 | 2/26 | 4/26 | 22/26 | **19/26** |
| Controls without a headline, refused | 4 | 3/4 | 4/4 | 4/4 | 4/4 |

Development and external readings sit side by side and are never pooled. The audit compares every record of a judged pass with the private reference recomputation (score cell, outcome cell, threshold, denominator) and every figure-derived label with the rendered figure. Three judged passes fail it: two bind each unit's outcome to its own name or ID cell and put the outcome in a per-unit map, while the figure or table prints the class in group labels that no record cites; one reaches the published 87.5% sensitivity with a single assay parameter instead of the paper's combined index. Four chains stop at the 1,000,000-token cap on figure-only evidence: two dot plots never transcribed point by point, a 23-point scatter read within 0.01 per point but with three reader cells marked uncertain (AUC 0.879 against 0.88), and two responders who appear only as figure points in a 34-patient denominator. The run used 213 model calls and 65 reader calls, CNY 34.1 at list prices; 10 first requests stopped by a job restart add an estimated CNY 1.0. `agent_archive/audit.json` (round5) records every verdict.

Round 4 reruns the three figure papers with one added tool and keeps the other five papers' round-3 results. The strong agent now reproduces five of eight published headlines with every cited label confirmed by hand: liver metastasis (AUC 0.850), rectal cancer (45/48), FORECAST-1 (24/29), the vascularised tumour chip (19/22, at call 10) and the pancreatic organoids (8/9, at call 19). Qwen's lung microwell 10/10 remains the one further paper any model has passed. Where runs still stop: a 21-column heat map whose grid box the agent placed off-target three times before its token budget ran out (lung microwell, round 4); tables without an independent prediction (the 45/54 lung table publishes IC50, response and a consistency flag whose share is the headline); and values that must be derived (the liver-chip 13/15 uses protein-binding-corrected margins of safety that no table lists).

**Five ways a model passed the judge without reproducing anything, now rejected.** Each rule has a unit test and was applied to every saved contract in every round.

1. *Prediction and outcome read the same cell*: the prediction then equals the outcome.
2. *A published count stands in for patients*: 54 records built from the four cells of a 2x2 table.
3. *Figure labels recorded by the agent while it knows the target*: misreads that cancel to the published number (two round-1 passes). Round 2 removed the agent's ability to write figure values: `read_figure` sends the figure or a crop to the same model in a fresh conversation that never sees the task or the target (`reader_prompt.txt`). On Figure 4 of the FORECAST-1 paper both blind Doubao readers and the blind Qwen3.8-max reader match a manual reading on all 29 rows.
4. *A per-record mapping that hides a literal*: the same source label ("Progressive Disease") mapped to responder for three patients and non-responder for three others.
5. *A count from the text stands in for outcomes*: two patients' outcomes read off "5 were treated with at least one drug", one sentence about six patients.

**Colours are read from pixels.** The blind reader misread small grids in round 3: three red heat-map cells became "untested", and crops of one 22 x 4 grid named the same colours differently. Round 4 gives the agent `read_grid` (`grid_colors.py`): the agent names the figure, the grid box and its rows and columns; the tool samples each cell centre, names the colour, and returns `grid/<reading>/R<row>C<col>` references with the measured RGB and pixel position, plus an image marking every sample point so the agent can check the alignment. The agent can call it and map colour names to legend categories; it cannot change a label. On the heat map a snapped read agrees with the manual reading on all 273 cells; on the 22 x 4 grid it reads all 88 cells and gives 19/22 with exactly the three mismatches the figure marks. In round 4 the pancreatic chain read its nine outcomes as a one-column strip across the PFS bars (green or orange where a bar reaches the strip, white where it does not), and the 19/22 chain's reader labels match the pixel reading cell for cell. `agent_archive/audit.json` records each cited cell.

Usage at provider list prices: Qwen round 1 about CNY 27.2; Doubao round 2 about CNY 28.1, round 3 a further CNY 14.0 and round 4 CNY 6.9. Prefix-cache hits covered 69-79% of Qwen input tokens, 63-73% for Doubao-Seed-2.1-pro and 33-35% for Doubao-Seed-2.0-pro.

## Second experiment design

`experiment_v2.json` fixes eligibility, numeric targets, models and stopping rules. Ewart, Hu, Dai, rectal cancer, colorectal liver metastasis, Tan, Tiriac and Wang meet the row-level-data plus locatable-headline rule. Schuster and Steinberg are separate no-headline controls. Ewart's units are toxicity drugs. Tiriac's 8/9 target represents the authors' qualitative concordance statement.

Each model starts from the same deterministic paragraph retrieval, file inventory and table previews. The published metric, value and denominator are supplied as the verification query; field gold labels are withheld. The first checkpoint executes one returned program or contract, the second supplies numerical/execution feedback, and later calls expose eight tools: list files, search the article, preview tables, view a source image, read a figure through the independent reader, read a coloured grid through the pixel reader (round 4), run Python, and finish. Tool calls may run in parallel. A verified result carries forward to later checkpoints. These are nested compute-budget comparisons on ten previously studied development papers.

Each paper/model has at most 12 model calls, 32 tool calls and 1,000,000 cumulative tokens; rounds 3 and 4 double the first two (24, 64) and keep the token cap. Round 4 reruns hu, Dai, Tiriac and the two controls from the first call on the strong lane; two of those chains were stopped once mid-request by their dispatching session and resumed from their saved state, with the interrupted request kept beside its error file. The token cap was raised from 300,000 after the pilot, before any cohort result: one Max call already used 22,260 tokens, so 300,000 would end the 12-call design after about six calls. `experiment_v2.json` holds each model set (model, provider request fields such as the thinking switch, reasoning effort and output cap, price tiers, credential profile) and each round (model set, run folder, step limits). Doubao-Seed-2.1-pro runs at medium reasoning effort: the default effort used five times the thinking tokens on the same task and, under platform load, ran single steps past ten minutes. Each Python execution has a 20-second limit and a 1.5 GB sampled-RSS stop; each request has a 230-second (Qwen) or 900-second (Doubao) wall check. The live adapter runs on macOS, denies network and reads of other user files, and confines code writes to its execution directory. Service interruptions return exit 75; account errors keep the original provider error.

The source inventory contains 194 entries, 133 locally acquired files and 15 acquisition failures, all from Tiriac's old PMC aliases. Tiriac's workbook and supplementary PDF are available, including Figure S6 on PDF page 6; its million-row `Targeted` worksheet hits the two-million-cell parsing cap. PDF pages expose rows of words with x coordinates, and source images resolve alignment. Workbook previews preserve RGB/indexed/theme fills and tint.

## Live tool-agent entry

Use Python 3.13 on macOS for fresh tool execution. Install `contract_agent/requirements-agent.txt` into the interpreter environment used for the run. Download originals using the existing fetch entry, then prepare one workspace:

```sh
python3 -m contract_agent.fetch --out source_downloads
python3 -m contract_agent.workspace source_downloads/crlm agent_sources/crlm
```

With `CONTRACT_MODEL_KEY` already set, each command below performs **one bounded model step** and saves its state. Repeat the same command until it returns `done: true`.

```sh
python3 -m contract_agent.agent --root agent_runs --sources agent_sources --paper crlm --lane strong --base-url https://dashscope.aliyuncs.com/compatible-mode/v1 --model qwen3.8-max --thinking
python3 -m contract_agent.agent --root agent_runs --sources agent_sources --paper crlm --lane weak --base-url https://dashscope.aliyuncs.com/compatible-mode/v1 --model qwen3.7-plus
```

Raw requests, SSE streams, assembled replies, usage receipts, tool calls/results and checkpoints are cached for every step; `read_figure` calls are cached by request hash, so a repeated read returns the same transcription. The released archive keeps, for every chain, the checkpointed contracts and verdicts, usage receipts with request and stream SHA-256, assembled model replies and recorded figure labels. Tool traces are complete for the six CC BY sources; for the three CC BY-NC-ND sources and the text-mining-only source, tool outputs appear as SHA-256 and the replay index carries only the cited values, with article paragraphs used as field evidence replaced by their hash. The external cohort follows the same rule: complete traces for its 19 CC BY papers, hashes plus cited values for the 11 under NC, ND or text-mining terms; `agent_archive/provenance/` lists every screened paper's files, URLs and byte hashes.

Validation uses `python3 -m unittest contract_agent.test_engine contract_agent.test_agent` (25 passing checks). Openpyxl, xlrd and pdfplumber use MIT/BSD licenses; NumPy uses BSD-3-Clause; Pillow uses MIT-CMU; pypdfium2 has Apache-2.0/BSD-3-Clause terms and bundled PDFium third-party notices. Source licenses remain in the per-paper provenance.

## Earlier extraction pilot

This prototype extracts the analysis unit, assay, threshold chronology and clinical mapping from published organoid and organ-chip studies, then executes source-linked observations to check a published headline. Its current result is a **negative pilot**: one execution-feedback turn changes field accuracy from **83/100 to 80/100**, with **0/10 numerical passes in both conditions**. Later development iterations recover one paper's AUC, giving **1/10 numerical passes** and **0/10 contracts with every scored field plus the numerical check correct**.

Run from the repository root with Python 3.10 or later:

```sh
python3 -m contract_agent.replay
```

This command uses the standard library, verifies the archive hashes, reads cached model responses, executes their source references, and writes `contract_agent/results.json`. It needs no network, model account or GPU. The original model outputs are retained, including failed attempts; model outputs are never edited to improve the score.

| Condition | Core fields | Published headline reproduced |
|---|---:|---:|
| Qwen3.7-plus, single pass | 83/100 | 0/10 |
| Same response history, one execution-feedback turn | 80/100 | 0/10 |
| Latest adaptive development, up to three feedback turns | 80/100 | 1/10 |
| Local Qwen3-0.6B-Q8_0, compact retrieval, single pass | 0/100 | 0/10 |

The rescued case is colorectal liver metastasis: the agent initially pooled treatment cohorts, then selected the paper's 13 FOLFOX patients from Table S7 and recomputed AUC **0.850**, with eight SD/PR and five PD outcomes. The agent's `patient_regimen` unit still disagrees with the frozen `patient` label. This is one successful numerical check, not a fully verified semantic contract or evidence of general improvement.

The ten selected sources are Ewart, Hu, Schuster, Steinberg, Dai, the rectal validation study, the colorectal liver-metastasis study, Tan, Tiriac and Wang. `provenance.json` and each `data/<paper>/provenance.json` identify the paper, authors, source URLs, original-byte hashes and license. Seven have frozen numeric targets suitable for the implemented metrics; the primary denominator remains all ten. Schuster and Steinberg have clinical case descriptions without a global clinical accuracy/AUC headline; Tiriac's relevant comparison needs additional interpretation and plotted evidence.

This pilot establishes no field-wide prevalence, leave-one-out degradation or 10% patient-release result; the tool agent above is the route to a 30-paper expansion.

## What the experiment measures

Each of ten fields receives one point when its categorical value matches an accepted value in `gold.json`. Evidence-span fidelity, prose explanations, every patient identity and every regimen pairing are not part of this 100-point score. The gold was encoded by this implementation from existing audit notes and source passages, with some synonymous labels accepted; it has no independent double annotation. Ewart and Hu were pilots; the other eight field sets were frozen before their first calls. These are development sources, not an untouched validation set.

The executor accepts references to spreadsheet cells or PDF text lines, explicit string mappings, simple aggregation, thresholds and regular expressions. It calculates accuracy, sensitivity, specificity and rank AUC with ties. It rejects invented numeric literals as observations, invalid references, duplicate analysis IDs, inconsistent denominators and ambiguous censored values. It never executes model-generated Python. Execution feedback includes the frozen published numeric target and parser/denominator errors; field labels remain hidden.

The paired first-pass/one-feedback results are descriptive. Threshold-timing wording was clarified after the two pilots, and feedback handling was revised during development. The later successful rescue used revised feedback and additional attempts. It is not a prespecified controlled treatment effect. The complete requests record the prompts actually used, rather than silently substituting the current `prompt.txt`.

Matching a headline does not prove its interpretation. For example, Ewart's Table 4 contains uncorrected MOS values assessed at 50, whereas the 375 threshold and 87% headline use protein-binding-corrected MOS. Applying 375 to Table 4 can accidentally reproduce an aggregate. An explicit semantic exclusion records this issue separately from arithmetic.

The ingestion route extracts XML prose/table values, workbook values and PDF text lines. It omits figure pixels, workbook styling and geometric table structure. Selected supplements are listed in provenance; this is not a complete multimodal reading of every supplement. Figure-only truth labels and PDF column alignment are major current failure sources. Generic source binding also cannot establish that an assay-replicate column is a genuine clinical label, as illustrated by the failed Dai response.

## Free local extraction

Fresh extraction requires Python, `pdftotext` (Poppler), `xlrd==2.0.2` for the legacy workbook, and a `llama-server` build of [llama.cpp](https://github.com/ggml-org/llama.cpp) supporting Qwen3. Use the Apache-2.0 [official Qwen3-0.6B GGUF](https://huggingface.co/Qwen/Qwen3-0.6B-GGUF), file `Qwen3-0.6B-Q8_0.gguf`. The recorded configuration is a 16,384-token context, 128-token batch, 64-token microbatch, Q8 KV cache, thinking disabled and 2,048 maximum output tokens. The wrapper samples server RSS every 0.1 seconds, stops above 3.7 GB and terminates its server on exit.

```sh
python3 -m contract_agent.fetch --out local_sources
python3 -m contract_agent.compact local_sources local_compact
python3 -m contract_agent.free --model-path models/Qwen3-0.6B-Q8_0.gguf --sources local_compact --cache local_cache --results local_results --papers ewart hu
```

Run the remaining papers in two finite groups: `schuster steinberg dai rectal`, then `crlm tan tiriac wang`, using distinct result directories. Source downloads verify the original byte hashes and report changes explicitly. The paid route can use `contract_agent.run --live` with an OpenAI-compatible endpoint and `CONTRACT_MODEL_KEY` in the environment.

The local route scored **0/100**, an 83 percentage-point gap from the paid first pass. It emitted schema placeholders or structurally incorrect objects. It uses deterministic 24,000-character evidence retrieval while the paid route received larger source contexts; this is a comparison of complete routes, not an isolated model-size comparison. Cached replay is the working free reproduction route; the measured fresh local extraction route has inadequate accuracy.

The three measured local batches completed in 36.22, 86.47 and 105.15 seconds, with a maximum sampled RSS of 3,408,510,976 bytes (3.41 GB). All three servers exited. `benchmark.json` includes the model hash and runtime receipts. An earlier 32,768-context batch reached 4.64 GB; it was replaced by the smaller-context run and the memory-monitoring correction is recorded.

## Archive and licensing

Code follows the repository's MIT license. Third-party articles, data and model weights retain their own terms. XML and tables are normalized adaptations; the source license and attribution remain attached.

Full original request/response bytes and hashes are available for the six CC BY papers. Dai, Tan and Wang carry CC BY-NC-ND notices, while Tiriac's article file grants text-mining access rather than general redistribution. For those four, the public bundle contains responses, request hash manifests and selected numerical facts/source rows; full article prose and full requests remain in the research archive. Thus this release **does not satisfy full public raw-request redistribution for all ten papers**. Re-fetching the cited originals enables local study of the full inputs. Full semantic review of those four requires the originals.

The 27 successful paid calls used 4,427,232 input tokens and 112,260 output tokens. Received usage implies approximately CNY 14.01 at the [published Beijing Qwen3.7-plus rates](https://help.aliyun.com/zh/model-studio/qwen3-7-plus), including reported implicit-cache hits. One timed-out call has unknown usage; this estimate is not an invoice. Per-paper and per-turn usage are in `results.json` and cached receipts.

Validation:

```sh
python3 -m unittest contract_agent.test_engine
```

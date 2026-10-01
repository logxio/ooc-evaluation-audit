# Patient readouts to release or retest

Open `index.html`, load the public patient table, predict actions, reveal clinical outcomes, compare the fixed single-readout baseline, and download the report/retest list. All calculations run in the browser. Patient tables remain on the reader's computer.

The page is static and needs no package installation or backend. Serve this folder as `/workbench/` from the repository's GitHub Pages site. All assets use relative paths; there are no analytics, remote fonts, network requests for patient data, or runtime dependencies. The proposed Pages address is `https://logxio.github.io/ooc-evaluation-audit/workbench/`; publication is a separate repository action.

The default example is a retrospective 2025 rectal-organoid replay with a fixed patient split. Its measured combined-regimen single-readout comparator is stronger than the two separate assay channels. The page shows that result and the individual failures. “Report” describes a research reporting action under the selected rule. Assay scale, clinical endpoint and regimen mapping remain part of the study definition.

## Your own data

Paste a CSV or tab-separated table, or open/drop a CSV. Use `patient,readout1` and optional `readout2,baseline_readout,response`. Response is 1 for a clinical responder, 0 for a non-responder, or empty. Each row is one coded patient. The main chain applies the displayed frozen model to compatible assay measurements. Missing paired measurements go to retest. If `baseline_readout` is absent, the comparison uses the stored calibration-selected single channel and explicitly names it. A separate `patient,response` file can reveal all or some outcomes later; only labelled patients enter observed-risk denominators.

For a different assay, the retained `worksheet.html` fits leave-one-patient-out thresholds or exploratory cohort medians. `sample.html` and `audits/index.html` remain secondary analysis pages. The earlier timed-study files remain archived outside the entry page's navigation.

## Replace the result, keep the page

`result.json` is the result packet; `result.js` wraps the same object as `window.WORKBENCH_RESULT = ...;` for direct-file browsers. The page reads patient predictions from `cases`, then recomputes observed counts after reveal. The JavaScript contains no study-specific outcome totals.

The interface is `workbench.result.v1`:

- `version`, `study.{title,status,input_note,split}` identify the cohort and its interpretation.
- `rows` contains `{patient,readout1,readout2,baseline_readout,response}`; unused measurements and unknown responses are `null`.
- `cases`, in the same patient order, contains `{patient,calls:[0|1|null,0|1|null],margin,action,baseline_action}`. Actions are the strings `"0"`, `"1"`, or `"retest"`. `reason` is optional.
- `rule.{name,kind,description}` identifies the method. `kind:"two_readout_v2"` includes the existing CLI's `certificate` and enables local prediction for new compatible inputs. `kind:"precomputed"` displays any method's saved CLI predictions; new inputs for that method arrive as another result packet.
- `baseline.{kind,name,field,cutoff,selection,fallback_field,fallback_cutoff,fallback_name,fallback_selection}` describes a fixed single-readout comparator. Fallback is used only for local prediction when the comparator's measured field is missing.
- `cost.retest` is a nonnegative cost relative to one wrong release. `provenance` records core/source hashes; `expected` holds reference counts for verification.

For new results, keep those fields and replace the packet. The **Open updated result packet** control exercises that same interface locally. For a static release, wrap an updated JSON file with:

```sh
python -c 'import json,pathlib; p=pathlib.Path("workbench/result.json"); pathlib.Path("workbench/result.js").write_text("window.WORKBENCH_RESULT = "+json.dumps(json.loads(p.read_text()),allow_nan=False)+";\n")'
```

Rebuild this example from the repository's existing frozen outputs with:

```sh
python workbench/build_result.py
python workbench/verify.py --out workbench/verification
```

Verification calls `chip_release.py` before/after reveal, calls `matched_regimen.py` for the strong comparator, and compares patient calls, margins, aggregate risks/costs, changed inputs and exact-binomial sample calculations with the browser engine. It uses the repository's existing Python dependencies plus Node.js. A new method's author supplies its CLI prediction references in the same format and extends the adapter comparison for that method; the display does not require a method-specific rewrite.

Sample needs are planning minima for independent released validation patients, retaining all observed errors and assuming no further errors, with a one-sided 95% Clopper–Pearson upper bound. Relative loss counts wrong releases plus the chosen retest penalty. It measures a decision-cost assumption, not observed money or staff time.

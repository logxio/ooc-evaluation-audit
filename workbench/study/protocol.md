# Paired workflow study

Question: does the browser tool reduce the time needed to produce a correct patient-action worksheet compared with the researcher's usual manual workflow?

## Materials and assignment

Six tasks contain 36 distinct historical patients from the rectal-organoid publication (https://doi.org/10.1016/j.xcrm.2025.102397, CC BY 4.0). Measurements are organoid size ratios at day 24 / day 0 after irradiation and 5-FU. Outcomes are TRG 0/1 or cCR versus other responses, using the published treatment mapping already in the repository. `source_mapping.csv` maps task codes to the source's public patient codes. These are previously analysed public outcomes.

The fixed model was fitted on 42 patients and calibrated on 42 other patients. All task patients come from its separate 43-patient retrospective test split. T1/T2 each have two release-sensitive, two release-resistant and two retest actions with one wrong release. T3/T4 each have one sensitive, three resistant and two retests with one wrong release. T5/T6 each have one sensitive, two resistant and three retests with zero wrong releases. Task curation uses outcomes to match workload; these tasks establish workflow usability, not fresh clinical predictive performance.

Each participant performs three manual and three tool tasks, one of each within every matched pair. The two tasks in a pair contain different patients. `order.csv` uses a fixed random seed (20261002) for mode allocation and three rotated task orders, each paired with the opposite allocation. Across P01–P06, every task and every position is manual three times and tool three times. The first two codes form a counterbalanced block; allocate consecutive codes before seeing results. With three to five participants report the actual imbalance. Each person sees a patient only once in timed tasks.

## Facilitator procedure

1. Give the participant the one-page `guide.html`, `manual.html` and assigned code. Record consent through your institution's usual process outside this anonymous file. Keep contact details and scheduling outside the task records.
2. Use `examples/new_batch_input.csv` and its outcome CSV for untimed practice. These seven patients are separate from all six timed tasks. Provide both files directly or as part of the folder. Practise manual arithmetic and tool operation before measuring either condition.
3. Record the participant's usual workflow in the page. Allow the usual spreadsheet, paper or existing script in manual tasks; keep the automated recommendation button hidden for those tasks. Record any facilitator assistance externally by participant code and retain it alongside the export.
4. Start timing when the participant clicks Start task. The task ends after all actions and summary answers are submitted. Participants can pause explicitly. The exported record stores wall time, active time, pauses, tab-visibility events, every action change, result entry and locked final actions. Time spent in another window remains counted unless the participant explicitly pauses.
5. Receive the JSON file after six tasks. Preserve the original. Run `python3 analyze.py record1.json record2.json --out paired_results.json`. Partial exports stay labelled incomplete. The script keeps researcher, facilitator and agent self-test groups separate.

## Outcomes specified before participant data

Primary descriptive contrast: within each matched pair, manual active time minus tool active time; positive means the tool was faster. Report each person's mean and median over their three pairs, plus each individual pair. Also report wall time, action agreement with the frozen rule, arithmetic correctness, and task correctness (all actions correct and all four summary answers correct). Report time differences for all complete pairs and separately for pairs where both tasks were correct. Include every attempted task; incomplete or invalid records appear explicitly.

Clinical-error cost is `wrong releases + 0.25 * retests`, divided by all patients. This is a normalized decision proxy, not money saved. The two task forms have matched action and wrong-release counts under the frozen rule; other baseline outcomes can differ. The baseline that was strongest among four active rules on the calibration sample is readout 2 (11/42 errors). The comparison also includes retest-all. The lowest-cost baseline on the revealed task is an explicitly retrospective comparator, with ties accepted.

With a small convenience sample, report individual paired differences and descriptive summaries. These tasks support claims about the observed participants and workflow. General clinical benefit, population-wide time savings and prospective prediction performance require their own evidence.

## Export and privacy

No server, analytics, external fonts or runtime network requests are used. The interface records no name, email, IP address, browser fingerprint or local path. Task files contain coded public patients. Imported data must use coded identifiers and the same assay and units as the frozen model. Imported rows in events use row numbers rather than original IDs. The record stays in memory; export it before closing. Outcomes are hidden in the interface until lock, while source files remain inspectable; this is a workflow exercise, not secure outcome blinding.

## Reproducibility

`certificate.json` is the complete frozen CLI certificate. `answer_key.json` contains actions and metrics obtained by calling the existing Python `release_calibration.apply/measure`. `engine.js` is the browser inference adapter, tested against that core. `data.js` embeds examples so `index.html` works through `file://` and static hosting. Model and source digests are attached to every record. No Python installation is required for participants; the analysis script uses Python's standard library.

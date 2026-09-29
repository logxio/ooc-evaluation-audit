#!/usr/bin/env python3
"""Score the frozen blind predictions against the two articles' clinical-response tables.

`blind_predictions.json` was committed before these tables were opened. The clinical rows
below are transcribed from each article's Table S4. Outcome words come from the frozen
prediction file; one amendment, made after the tables were opened, is reported separately.
"""

import hashlib
import json
import re
from pathlib import Path

PREDICTIONS_SHA256 = 'bfb980002d8bdb16ab04ef736f044066f9f27a4b4be366d25d0279aeda4524ea'
COSTS = (0.10, 0.25, 0.50)
# Table S4 rows: patient key, regimen text, clinical-response text, author clinical class (biliary only).
GASTRIC = (
    ('G9T', 'Hyperthermic intraperitoneal chemotherapy (Oxaliplatin+5-FU) *3', 'No recurrence (49 months)', None),
    ('G32T', 'SOX (S-1+Oxaliplatin) *7', 'No recurrence (35 months)', None),
    ('G36T', 'FOLFOX (Oxaliplatin+5-FU) *7', 'No recurrence (34 months)', None),
    ('G39T', 'Hyperthermic intraperitoneal chemotherapy (Oxaliplatin+5-FU) *4', 'Death (RFS 10 months)', None),
    ('G41T', 'Capeox (Capecitabine +Oxaliplatin) *7', 'No recurrence (33 months)', None),
    ('G43T', 'SOX (S-1+Oxaliplatin) *4', 'No recurrence (33 months)', None),
    ('G59T', 'Capeox (Capecitabine + Oxaliplatin) *6', 'No recurrence (29 months)', None),
    ('G62T', 'SOX (S-1+Oxaliplatin) *5', 'No recurrence (29 months)', None),
    ('G20T', 'Capeox (Capecitabine + Oxaliplatin) *7', 'Omentum and lymphatic metastasis (PFS 11 months)', None),
    ('G30T', 'SOX (S-1+Oxaliplatin) *5', 'No recurrence (36 months)', None),
    ('G50T', 'SOX (S-1+Oxaliplatin) *7+PD-1', 'Death (PFS 25 months)', None),
    ('G56T', 'SOX (S-1+Oxaliplatin) *10', 'Peritoneal implantation metastasis (PFS 10 months)', None),
)
BILIARY = (
    ('ECC1T-P', 'FOLFORINOX (5FU+Oxaliplatin+Irinotecan) *12', 'No recurrence (20220405)', 'Sensitive'),
    ('ECC8T-P', 'AG (Gemcitabine+Paclitaxel) *6', 'Lymphatic metastasis (20211201)', 'Resistant'),
    ('ICC49T-P', 'GEMOX (Gemcitabine+Oxaliplatin) *2; GP (Gemcitabine+Cisplatin) *6; Capecitabine *4',
     'Lymphatic and lung metastasis (20220114)', 'Resistant'),
    ('ECC21T-P', 'Capecitabine *8', 'No recurrence (20230427)', 'Sensitive'),
    ('ICC65T-P', 'Capecitabine *8', 'No recurrence (20220915)', 'Sensitive'),
    ('ECC27T-P', 'GS (Gemcitabine+S-1) *6', 'No recurrence (20220914)', 'Sensitive'),
    ('ICC63T-P', 'Capecitabine *8', 'Recurrence and bone metastasis (20220118)', 'Resistant'),
    ('ECC17T-P', 'GP (Gemcitabine+Cisplatin) *6', 'Partial response (20211011)', 'Sensitive'),
    ('ICC50T-P', 'GP (Gemcitabine+Cisplatin) *4', 'Progressive disease, recurrence and liver metastasis (20211124)', 'Resistant'),
    ('ECC20T-P', 'GEMOX (Gemcitabine+Oxaliplatin) *8', 'Partial response (20220826)', 'Sensitive'),
    ('ICC71T-P', 'GP (Gemcitabine+Cisplatin) *6', 'Partial response (20220803)', 'Sensitive'),
    ('ICC69T-P', 'GP (Gemcitabine+Cisplatin) *6', 'Stable disease (20220804)', 'Sensitive'),
    ('ICC73T-P', 'GP (Gemcitabine+Cisplatin) *1; AG (Gemcitabine+Paclitaxel) *1', 'Death (20211201)', 'Resistant'),
)
AMENDMENT = {'non_responder': ('metastasis', 'death')}
# Table S4 names one patient ECC17T while Table S3 lists the same organoid as ICC-17T:
# both tables give it gemcitabine AUC 2.58% and cisplatin AUC 35.21%.
ALIASES = {'ECC17TP': 'ICC17TP'}


def norm(text):
    return re.sub(r'[^A-Z0-9]', '', text.upper())


def outcome(text, words):
    low = ' ' + re.sub(r'[^a-z0-9-]+', ' ', text.lower()) + ' '
    hits = [(len(w), cls) for cls, ws in words.items() for w in ws if f' {w} ' in low]
    return max(hits)[1] if hits else None


def regimen_pair(text, frozen):
    for token in re.findall(r'[A-Za-z][A-Za-z0-9]*', text):
        if token.upper() in frozen['regimen_pairs']:
            return tuple(frozen['regimen_pairs'][token.upper()])
    low = text.lower()
    present = {drug for drug, words in frozen['drug_words'].items() if any(w in low for w in words)}
    for pair in frozen['pair_priority']:
        a, b = pair.split('+')
        if a in present and b in present:
            return a, b
    return None


def score(rows, cohort, frozen, words, use_author_class=False):
    preds = frozen['cohorts'][cohort]['primary_median_split']
    keys = {norm(k): k for k in preds}
    table = []
    for key, regimen, clinical, author in rows:
        pair = regimen_pair(regimen, frozen)
        truth = outcome(author, words) if use_author_class and author else outcome(clinical, words)
        patient = keys.get(ALIASES.get(norm(key), norm(key)))
        if pair is None or truth is None or patient is None:
            table.append({'patient': key, 'evaluable': False, 'pair': pair, 'truth': truth})
            continue
        entry = preds[patient]
        p = entry['pairs']['+'.join(pair)]
        single = {d: 'responder' if entry['drug_sensitive'][d] else 'non_responder' for d in pair}
        table.append({'patient': key, 'evaluable': True, 'pair': '+'.join(pair), 'truth': truth,
                      'prediction': p['predicted'], 'single': single})
    ev = [r for r in table if r['evaluable']]
    n = len(ev)
    released = [r for r in ev if r['prediction'] != 'retest']
    errors = sum(r['prediction'] != r['truth'] for r in released)
    retests = n - len(released)
    drug_errors = {}
    for position in (0, 1):
        drug_errors[f'drug_{position+1}_errors'] = sum(
            list(r['single'].values())[position] != r['truth'] for r in ev)
    summary = {'evaluable': n, 'responders': sum(r['truth'] == 'responder' for r in ev),
               'released': len(released), 'released_correct': len(released) - errors, 'retests': retests,
               **{k: v for k, v in drug_errors.items()},
               'cost_per_patient': {str(c): round((errors + c * retests) / n, 6) for c in COSTS} if n else None,
               'single_drug_cost_per_patient': {k: round(v / n, 6) for k, v in drug_errors.items()} if n else None}
    return summary, table


def main():
    blob = Path('blind_predictions.json').read_bytes()
    actual = hashlib.sha256(blob).hexdigest()
    if actual != PREDICTIONS_SHA256:
        raise ValueError(f'blind_predictions.json changed: {actual}')
    frozen = json.loads(blob)
    registered = {k: tuple(v) for k, v in frozen['outcome_words']['disease_control_primary'].items()}
    amended = {k: registered[k] + AMENDMENT.get(k, ()) for k in registered}
    objective = {k: tuple(v) for k, v in frozen['outcome_words']['objective_response_secondary'].items()}
    result = {'schema': 'blind.consensus.score.v1', 'predictions_sha256': actual, 'analyses': {}}
    for label, words, author in (('registered_words', registered, False), ('amended_words', amended, False),
                                 ('objective_response', objective, False), ('biliary_author_class', registered, True)):
        block = {}
        for cohort, rows in (('gastric', GASTRIC), ('biliary', BILIARY)):
            if author and cohort == 'gastric':
                continue
            block[cohort] = score(rows, cohort, frozen, words, use_author_class=author)
        result['analyses'][label] = {c: s for c, (s, _) in block.items()}
        result['analyses'][label + '_rows'] = {c: t for c, (_, t) in block.items()}
    print(json.dumps({k: v for k, v in result['analyses'].items() if not k.endswith('_rows')}, indent=1))
    Path('blind_score.json').write_text(json.dumps(result, indent=1) + '\n')


if __name__ == '__main__':
    main()

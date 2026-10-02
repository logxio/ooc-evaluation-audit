"""Execute an extracted contract using source references, never generated code."""
import json
import math
import re

FIELDS = {
    'unit': ['patient', 'patient_regimen', 'organoid_line', 'drug', 'well', 'chip', 'patient_schedule', 'unknown'],
    'platform': ['organoid', 'perfused_chip', 'microwell', 'spheroid', 'mixed', 'unknown'],
    'readout': ['viability', 'ic50', 'auc', 'size_viability', 'vessel_size', 'apoptosis_death', 'toxicity_margin', 'other', 'unknown'],
    'direction': ['lower_sensitive', 'higher_sensitive', 'mixed', 'unknown'],
    'threshold_rule': ['roc_optimized', 'cohort_quantile', 'fixed_numeric', 'categorical', 'no_binary_rule', 'unknown'],
    'threshold_timing': ['outcome_optimized', 'independent_reference', 'explicitly_prespecified', 'not_reported', 'not_applicable'],
    'patient_mapping': ['individual_available', 'partial', 'absent', 'not_applicable'],
    'regimen_match': ['matched', 'partial', 'absent', 'not_applicable', 'not_reported'],
    'n_units': 'integer or null; denominator of the clinical/toxicity comparison, not all cultured samples',
    'split': ['same_cohort', 'independent_test', 'cross_validation', 'none', 'not_reported'],
}


def source_index(documents):
    out = {}
    for doc in documents:
        out.update(doc['cells'])
        for line in doc['narrative']:
            key, text = line.split(' ', 1)
            out[key] = text
    return out


def extract_value(spec, index):
    if isinstance(spec,dict) and 'calc' in spec:
        args=[extract_value(v,index) if isinstance(v,dict) else float(v) for v in spec.get('args',[])]
        if len(args)!=2:raise ValueError('Source calculation requires two arguments')
        operations={'add':lambda a,b:a+b,'subtract':lambda a,b:a-b,'multiply':lambda a,b:a*b,'divide':lambda a,b:a/b}
        if spec['calc'] not in operations:raise ValueError('Unsupported source calculation')
        if not any(isinstance(v,dict) for v in spec['args']):raise ValueError('Calculation requires a source reference')
        return operations[spec['calc']](*args)
    if not isinstance(spec, dict):
        raise ValueError(f'Observation must bind to source references, got literal {spec!r}')
    refs = spec.get('refs', [spec.get('ref')])
    if not refs or any(ref not in index for ref in refs):
        raise ValueError(f'Unknown source reference: {refs}')
    values = []
    for ref in refs:
        raw = str(index[ref]).strip()
        if 'regex' in spec:
            match = re.search(spec['regex'], raw)
            if not match:
                raise ValueError(f'Pattern {spec["regex"]!r} did not match {ref}: {raw!r}')
            raw = match.group(int(spec.get('group', 1)))
        if 'map' in spec:
            if raw not in spec['map']:
                raise ValueError(f'Unmapped value {raw!r} at {ref}')
            value = spec['map'][raw]
        else:
            raw = raw.replace(',', '').replace('−', '-')
            if raw.startswith(('>', '≥')):
                if spec.get('censor') != 'above_cutoff':
                    raise ValueError(f'Censored value at {ref} requires an explicit censor policy')
                value = float('inf')
            elif raw.startswith(('<', '≤')):
                if spec.get('censor') != 'below_cutoff':
                    raise ValueError(f'Censored value at {ref} requires an explicit censor policy')
                value = -float('inf')
            else:
                value = float(raw.rstrip('%'))
        values.append(float(value))
    aggregate = spec.get('aggregate', 'single')
    if aggregate == 'single':
        if len(values) != 1:
            raise ValueError('Multiple source values require an aggregation rule')
        value = values[0]
    elif aggregate == 'mean': value = sum(values) / len(values)
    elif aggregate == 'min': value = min(values)
    elif aggregate == 'max': value = max(values)
    else: raise ValueError(f'Unknown aggregate {aggregate}')
    if 'threshold' in spec:
        value = compare(value, spec['threshold'], spec.get('op', '<'))
    return value


def spec_refs(spec):
    if not isinstance(spec, dict): return set()
    if 'calc' in spec: return set().union(*(spec_refs(v) for v in spec.get('args', [])))
    return {ref for ref in spec.get('refs', [spec.get('ref')]) if ref}


def mapped_values(spec, index):
    if not isinstance(spec, dict) or 'calc' in spec or 'map' not in spec: return []
    pairs = []
    for ref in spec.get('refs', [spec.get('ref')]):
        if ref not in index: continue
        raw = str(index[ref]).strip()
        if 'regex' in spec:
            match = re.search(spec['regex'], raw)
            if not match: continue
            raw = match.group(int(spec.get('group', 1)))
        if raw in spec['map']: pairs.append((raw, spec['map'][raw]))
    return pairs


def compare(value, cutoff, op):
    operations = {'<': value < cutoff, '<=': value <= cutoff,
                  '>': value > cutoff, '>=': value >= cutoff, '==': value == cutoff}
    if op not in operations: raise ValueError(f'Unknown operator: {op}')
    return int(operations[op])


def evaluate(contract, index, target=None):
    errors = []
    fields = contract.get('fields', {})
    for key, choices in FIELDS.items():
        value = fields.get(key, {}).get('value')
        if key not in fields or (isinstance(choices, list) and value not in choices):
            errors.append(f'Invalid field {key}: {value!r}')
        evidence = fields.get(key, {}).get('evidence', [])
        for ref in evidence:
            if ref not in index: errors.append(f'{key}: missing evidence {ref}')
    headline = contract.get('headline', {})
    records = headline.get('records', [])
    rows = []
    ids = set()
    score_owner = {}
    truth_owner = {}
    meaning = {'score': {}, 'truth': {}}
    for record in records:
        try:
            key = str(record['id'])
            if key in ids: raise ValueError(f'Duplicate analysis unit {key}')
            ids.add(key)
            own = tuple(sorted(spec_refs(record['score'])))
            if own and own in score_owner:
                raise ValueError(f'Score of {key} reads exactly the same source cells as {score_owner[own]}; each analysis unit needs its own assay evidence, not a shared aggregate')
            score_owner.setdefault(own, key)
            told = tuple(sorted(spec_refs(record['truth'])))
            if told and not (isinstance(record['truth'], dict) and 'map' in record['truth']):
                # Only a categorical label (a group header) may be shared; a shared number is an aggregate.
                if told in truth_owner:
                    raise ValueError(f'Truth of {key} extracts a number from the same source cells as {truth_owner[told]}; a shared count is an aggregate, not each unit\'s outcome')
                truth_owner[told] = key
            shared = spec_refs(record['score']) & spec_refs(record['truth'])
            if shared:
                raise ValueError(f'Score and truth of {key} read the same source cell {sorted(shared)[0]}; the assay prediction and the clinical outcome need independent evidence')
            for role in ('score', 'truth'):
                # A source label means one thing for every unit; a per-record map would otherwise hide a literal.
                for raw, mapped in mapped_values(record[role], index):
                    seen = meaning[role].setdefault(raw, (mapped, key))
                    if seen[0] != mapped:
                        raise ValueError(f'{role} label {raw!r} maps to {mapped} for {key} but to {seen[0]} for {seen[1]}; a source label must mean the same for every unit')
            score = extract_value(record['score'], index)
            if not math.isfinite(score):
                # An interval cannot be replaced by a rank or by a binary call
                # when its finite endpoint straddles the decision threshold.
                spec=record['score']
                if headline.get('metric')=='auc' or spec.get('aggregate','single')!='single':
                    raise ValueError(f'Censored score for {key} requires an interval-aware metric')
                ref=spec.get('ref')
                raw=str(index.get(ref,'')).strip()
                if 'regex' in spec:
                    raw=re.search(spec['regex'],raw).group(int(spec.get('group',1)))
                match=re.fullmatch(r'([<>≤≥])\s*([0-9.eE+\-]+)',raw)
                threshold=headline.get('threshold')
                if not match or not isinstance(threshold,(int,float)):
                    raise ValueError(f'Unverifiable censor bound for {key}')
                bound=float(match.group(2));op=headline.get('op','<')
                if compare(bound,threshold,op)!=compare(score,threshold,op):
                    raise ValueError(f'Censor interval crosses the threshold for {key}')
            truth = extract_value(record['truth'], index)
            if truth not in (0, 1): raise ValueError(f'Nonbinary truth for {key}: {truth}')
            rows.append({'id': key, 'score': score, 'truth': int(truth)})
        except (ValueError, KeyError, TypeError, IndexError, re.error) as exc:
            errors.append(str(exc))
    value = None
    metric = headline.get('metric')
    if rows and not errors:
        if metric == 'auc':
            positives = [r['score'] for r in rows if r['truth'] == 1]
            negatives = [r['score'] for r in rows if r['truth'] == 0]
            if not positives or not negatives: errors.append('AUC requires both classes')
            else:
                direction = headline.get('score_direction', 'higher')
                sign = 1 if direction == 'higher' else -1
                value = sum((sign*a > sign*b) + .5*(a == b) for a in positives for b in negatives)/(len(positives)*len(negatives))
        elif metric in ('accuracy', 'sensitivity', 'specificity'):
            if headline.get('threshold') is None:
                errors.append('Binary metric requires a threshold')
            else:
                for row in rows:
                    row['prediction'] = compare(row['score'], headline['threshold'], headline.get('op', '<'))
                selected = rows if metric == 'accuracy' else [r for r in rows if r['truth'] == (metric == 'sensitivity')]
                if selected: value = sum(r['prediction'] == r['truth'] for r in selected)/len(selected)
                else: errors.append('Metric has an empty denominator')
        else: errors.append(f'Unsupported headline metric {metric!r}')
    if not records:
        errors.append('No source-bound observations: ' + str(headline.get('blocked_reason', 'not provided')))
    expected_n = fields.get('n_units', {}).get('value')
    if records and isinstance(expected_n, int) and len(records) != expected_n:
        errors.append(f'Contract denominator is {expected_n} but it supplies {len(records)} records')
    reported = headline.get('reported')
    if target:
        if metric != target['metric']: errors.append(f'Primary metric must be {target["metric"]}')
        if reported != target['reported']: errors.append('Extracted published value differs from frozen target')
        if len(rows) != target['n']: errors.append(f'Expected {target["n"]} analysis units, got {len(rows)}')
    tolerance = target['tolerance'] if target else headline.get('tolerance', .005)
    difference = value - reported if value is not None and isinstance(reported, (int, float)) else None
    matched = difference is not None and abs(difference) <= tolerance and not errors
    # JSON has no Infinity token. Preserve explicit censoring in exported rows.
    for row in rows:
        if not math.isfinite(row['score']):
            row['score'] = 'right_censored' if row['score'] > 0 else 'left_censored'
    return {'matched': matched, 'metric': metric, 'computed': value, 'reported': reported,
            'difference': difference, 'n': len(rows), 'errors': errors, 'rows': rows}


def parse_reply(text):
    text = text.strip()
    if text.startswith('```'):
        text = re.sub(r'^```(?:json)?\s*|\s*```$', '', text)
    def reject_constant(value):
        raise ValueError(f'Nonstandard JSON numeric constant: {value}')
    result = json.loads(text,parse_constant=reject_constant)
    if not isinstance(result, dict): raise ValueError('Contract must be a JSON object')
    return result

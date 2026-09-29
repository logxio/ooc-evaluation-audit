#!/usr/bin/env python3
"""Replay the two-readout release rule on an independent osteosarcoma organoid cohort.

The rule is imported unchanged from channel_consensus.py: release a call only when two
independent readouts agree, otherwise send the case to retest. Each readout uses the
binary call published by the original authors, so no threshold is fitted here.
"""

import argparse
import hashlib
import json
import urllib.request
from pathlib import Path

from channel_consensus import ABSTAIN_COSTS, release_counts


SOURCE_URL = 'https://jeccr.biomedcentral.com/counter/pdf/10.1186/s13046-025-03541-1.pdf'
SOURCE_SHA256 = 'cb8e77c2758231c6d28bd3e37e5abbde63f75139d2fbfba449df87170d905cd0'
# Transcribed from the article's Tables 2-4 (CC BY 4.0): sample, CIWS call (S/R),
# organoid formation potential of the same sample (OFP I/II/III), RECIST after NAT,
# and RECIST at 5 years (CR disease-free, PD relapse, NA not available).
POST_NAT = (
    ('OS-01-2', 'R', 'I', 'SD', 'PD'), ('OS-04', 'S', 'III', 'SD', 'CR'),
    ('OS-06', 'S', 'III', 'PD', 'PD'), ('OS-07-2', 'S', 'II', 'SD', 'CR'),
    ('OS-08-2', 'R', 'I', 'SD', 'PD'), ('OS-11', 'S', 'III', 'SD', 'CR'),
    ('OS-12-2', 'R', 'I', 'PD', 'PD'), ('OS-13-2', 'R', 'I', 'SD', 'PD'),
    ('OS-14', 'R', 'II', 'PD', 'PD'), ('OS-16-2', 'S', 'I', 'SD', 'PD'),
    ('OS-20-2', 'R', 'I', 'PD', 'PD'), ('OS-21-2', 'S', 'III', 'SD', 'CR'),
    ('OS-23', 'R', 'I', 'PD', 'PD'),
)
PRE_NAT = (
    ('OS-01-1', 'S', 'II', 'SD', 'PD'), ('OS-02', 'R', 'I', 'PD', 'NA'),
    ('OS-03', 'S', 'I', 'SD', 'CR'), ('OS-05', 'S', 'I', 'SD', 'PD'),
    ('OS-07-1', 'R', 'I', 'SD', 'CR'), ('OS-08-1', 'S', 'I', 'SD', 'PD'),
    ('OS-09', 'S', 'III', 'SD', 'PD'), ('OS-10', 'R', 'III', 'SD', 'CR'),
    ('OS-12-1', 'R', 'I', 'PD', 'PD'), ('OS-13-1', 'S', 'I', 'SD', 'PD'),
    ('OS-15', 'S', 'I', 'SD', 'CR'), ('OS-16-1', 'S', 'I', 'SD', 'PD'),
    ('OS-17', 'R', 'III', 'PD', 'PD'), ('OS-18', 'S', 'I', 'PD', 'PD'),
    ('OS-19', 'S', 'II', 'SD', 'CR'), ('OS-20-1', 'R', 'I', 'PD', 'PD'),
    ('OS-21-1', 'S', 'I', 'SD', 'CR'), ('OS-22', 'S', 'I', 'SD', 'CR'),
)


def check_transcription():
    """Reproduce counts printed in the article before using the transcribed rows."""
    pre_nat_agree = sum((c == 'S') == (n == 'SD') for _, c, _, n, _ in PRE_NAT)
    post_5y_agree = sum((c == 'S') == (y == 'CR') for _, c, _, _, y in POST_NAT)
    ofp = [o for _, _, o, _, _ in POST_NAT]
    assert pre_nat_agree == 15 and len(PRE_NAT) == 18, pre_nat_agree
    assert post_5y_agree == 11 and len(POST_NAT) == 13, post_5y_agree
    assert (ofp.count('I'), ofp.count('II'), ofp.count('III')) == (7, 2, 4), ofp
    return {'pre_nat_ciws_vs_recist_nat': '15/18', 'post_nat_ciws_vs_5y': '11/13',
            'post_nat_ofp_I_II_III': [7, 2, 4]}


def replay(rows):
    rows = [r for r in rows if r[4] != 'NA']
    truth = [1 if r[4] == 'CR' else 0 for r in rows]
    ciws = [1 if r[1] == 'S' else 0 for r in rows]
    ofp = [1 if r[2] in ('II', 'III') else 0 for r in rows]
    released, n_release, errors, abstain = release_counts(ciws, ofp, truth)
    single = {name: sum(a != b for a, b in zip(calls, truth))
              for name, calls in (('ciws', ciws), ('ofp', ofp))}
    n = len(truth)
    return {
        'samples': n, 'disease_free_at_5y': sum(truth),
        'released': n_release, 'released_correct': n_release - errors,
        'released_errors': errors, 'retested': abstain,
        'ciws_full_calls_correct': n - single['ciws'], 'ofp_full_calls_correct': n - single['ofp'],
        'cost_per_sample': {str(c): round((errors + c * abstain) / n, 6) for c in ABSTAIN_COSTS},
        'ciws_full_call_cost_per_sample': round(single['ciws'] / n, 6),
        'ofp_full_call_cost_per_sample': round(single['ofp'] / n, 6),
        'break_even_retest_cost_vs_ciws': round((single['ciws'] - errors) / abstain, 6) if abstain else None,
        'break_even_retest_cost_vs_ofp': round((single['ofp'] - errors) / abstain, 6) if abstain else None,
    }, [{'sample': r[0], 'released': flag, 'call': c, 'truth': t}
        for r, flag, c, t in zip(rows, released, ciws, truth)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-pdf', type=Path, help='Optional local copy of the article PDF')
    parser.add_argument('--out', type=Path, help='Optional per-sample JSON')
    args = parser.parse_args()
    if args.source_pdf:
        data = args.source_pdf.read_bytes()
    else:
        with urllib.request.urlopen(SOURCE_URL, timeout=90) as response:
            data = response.read()
    actual = hashlib.sha256(data).hexdigest()
    if actual != SOURCE_SHA256:
        raise ValueError(f'Source SHA256 mismatch: {actual}')
    post, post_rows = replay(POST_NAT)
    pre, pre_rows = replay(PRE_NAT)
    result = {
        'schema': 'consensus.external.replay.v1',
        'source_article': 'https://doi.org/10.1186/s13046-025-03541-1',
        'source_sha256': actual,
        'transcription_checks': check_transcription(),
        'rule': 'release only when the CIWS call and the OFP call agree (channel_consensus.release_counts)',
        'post_nat_primary': post,
        'pre_nat_secondary': pre,
        'limits': ['Organoids, not a perfused chip; a different cancer and laboratory from the colorectal chip cohort.',
                   'Both binary cut-offs were chosen by the original authors on this cohort; only the release step is ours.',
                   'The article tables were read before this replay was written, so it is not a blind prediction.',
                   'OFP measures organoid formation without drug; the authors link it to survival in post-NAT samples.'],
    }
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps({'post_nat': post_rows, 'pre_nat': pre_rows}, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()

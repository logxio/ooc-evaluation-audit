#!/usr/bin/env python3
"""Decide release or retest for your own two-readout chip or organoid data.

Give a CSV with one row per patient and two drug-response readouts (for example vessel and
tumoroid response, or the two drugs of a regimen). Lower values mean more sensitive unless
--higher-is-sensitive is set. With an outcome column, each readout's cutoff is learned
leave-one-patient-out; without one, each readout is split at its cohort median. A call is
released only when both readouts agree; otherwise the patient is sent to retest.

    python chip_release.py examples/biliary_gemcis_auc.csv --a gemcitabine_auc --b cisplatin_auc
"""

import argparse
import csv
import json
import statistics

from channel_consensus import release_counts
from chip_clinic import evaluate

POSITIVE = {'1', 'responder', 'sensitive', 'yes', 'cr', 'pr', 'sd', 'true'}
NEGATIVE = {'0', 'non_responder', 'non-responder', 'resistant', 'no', 'pd', 'false'}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('csv')
    parser.add_argument('--a', required=True, help='first readout column')
    parser.add_argument('--b', required=True, help='second readout column')
    parser.add_argument('--id', default=None, help='patient ID column (default: first column)')
    parser.add_argument('--outcome', default=None, help='optional responder/non-responder column')
    parser.add_argument('--higher-is-sensitive', action='store_true')
    parser.add_argument('--retest-cost', type=float, default=0.25, help='cost of a retest relative to a wrong call')
    parser.add_argument('--out', default=None, help='optional per-patient CSV')
    args = parser.parse_args()
    with open(args.csv, newline='') as handle:
        rows = [r for r in csv.DictReader(handle) if r[args.a].strip() and r[args.b].strip()]
    ident = args.id or list(rows[0])[0]
    sign = -1.0 if args.higher_is_sensitive else 1.0
    a = [sign * float(r[args.a]) for r in rows]
    b = [sign * float(r[args.b]) for r in rows]
    summary = {'patients': len(rows), 'readouts': [args.a, args.b], 'retest_cost': args.retest_cost}
    if args.outcome:
        labels = [r[args.outcome].strip().lower() for r in rows]
        unknown = sorted({x for x in labels if x not in POSITIVE | NEGATIVE})
        if unknown:
            raise SystemExit(f'unrecognised outcome values: {unknown}')
        truth = [int(x in POSITIVE) for x in labels]
        calls_a, calls_b = evaluate(truth, a)['predictions'], evaluate(truth, b)['predictions']
        released, n_release, errors, retests = release_counts(calls_a, calls_b, truth)
        single = {name: sum(c != t for c, t in zip(calls, truth)) for name, calls in ((args.a, calls_a), (args.b, calls_b))}
        n = len(truth)
        summary.update({'cutoffs': 'leave-one-patient-out', 'released': n_release,
                        'released_correct': n_release - errors, 'retests': retests,
                        'loss_per_patient': round((errors + args.retest_cost * retests) / n, 6),
                        'single_readout_loss_per_patient': {k: round(v / n, 6) for k, v in single.items()},
                        'break_even_retest_cost': {k: round((v - errors) / retests, 6) if retests else None
                                                   for k, v in single.items()}})
    else:
        ma, mb = statistics.median(a), statistics.median(b)
        calls_a, calls_b = [int(x <= ma) for x in a], [int(x <= mb) for x in b]
        released = [x == y for x, y in zip(calls_a, calls_b)]
        summary.update({'cutoffs': 'cohort median', 'released': sum(released), 'retests': len(rows) - sum(released)})
    actions = [{'patient': r[ident], 'call_' + args.a: 'sensitive' if x else 'resistant',
                'call_' + args.b: 'sensitive' if y else 'resistant',
                'action': ('release: ' + ('sensitive' if x else 'resistant')) if keep else 'retest'}
               for r, x, y, keep in zip(rows, calls_a, calls_b, released)]
    if args.out:
        with open(args.out, 'w', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(actions[0]))
            writer.writeheader()
            writer.writerows(actions)
    print(json.dumps({'summary': summary, 'first_patients': actions[:5]}, indent=2))


if __name__ == '__main__':
    main()

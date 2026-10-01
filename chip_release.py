#!/usr/bin/env python3
"""Decide release or retest for your own two-readout chip or organoid data.

Give a CSV with one row per patient and two drug-response readouts (for example vessel and
tumoroid response, or the two drugs of a regimen). Lower values mean more sensitive unless
--higher-is-sensitive is set. With an outcome column, each readout's cutoff is learned
leave-one-patient-out; without one, each readout is split at its cohort median. A call is
released only when both readouts agree; otherwise the patient is sent to retest.

With --train and --outcome, --certify ALPHA calibrates a release margin on a
separate labelled table. Training alone fixes the cutoffs, ECDFs and margin family.
The saved model and margin are applied unchanged to new patients. Under exchangeable
calibration/future patients, conformal risk control bounds expected wrong release
per patient overall; observed released-subset error is a separate quantity.

    python chip_release.py examples/biliary_gemcis_auc.csv --a gemcitabine_auc --b cisplatin_auc
    python chip_release.py calibration.csv --train training.csv --a r1 --b r2 --outcome response --certify 0.10 --save-certificate cert.json
    python chip_release.py new_patients.csv --a r1 --b r2 --certificate cert.json
"""

import argparse
import csv
import json
import math
import statistics

from channel_consensus import release_counts
from chip_clinic import evaluate, threshold
from release_calibration import fit, calibrate, apply, measure

POSITIVE = {'1', 'responder', 'sensitive', 'yes', 'cr', 'pr', 'sd', 'true'}
NEGATIVE = {'0', 'non_responder', 'non-responder', 'resistant', 'no', 'pd', 'false'}
def load_rows(path, args, with_outcome):
    with open(path, newline='') as handle:
        rows = [r for r in csv.DictReader(handle) if r[args.a].strip() and r[args.b].strip()]
    if not rows:
        raise ValueError('The CSV has no complete two-readout rows')
    ident = args.id or list(rows[0])[0]
    sign = -1.0 if args.higher_is_sensitive else 1.0
    result = []
    for r in rows:
        item = {'patient': r[ident], 'x': [sign * float(r[args.a]), sign * float(r[args.b])]}
        if with_outcome:
            label = r[args.outcome].strip().lower()
            if label not in POSITIVE | NEGATIVE:
                raise ValueError(f'unrecognised outcome value: {label}')
            item['y'] = int(label in POSITIVE)
        result.append(item)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('csv')
    parser.add_argument('--a', required=True, help='first readout column')
    parser.add_argument('--b', required=True, help='second readout column')
    parser.add_argument('--id', default=None, help='patient ID column (default: first column)')
    parser.add_argument('--outcome', default=None, help='optional responder/non-responder column')
    parser.add_argument('--higher-is-sensitive', action='store_true')
    parser.add_argument('--retest-cost', type=float, default=0.25, help='cost of a retest relative to a wrong call')
    parser.add_argument('--certify', type=float, default=None, metavar='ALPHA',
                        help='with --train and --outcome: calibrate expected overall wrong-release risk')
    parser.add_argument('--train', help='separate labelled training CSV; fixes cutoffs and reference distributions')
    parser.add_argument('--save-certificate', default=None, help='with --certify: write cutoffs and margin to this JSON')
    parser.add_argument('--certificate', default=None, help='apply a saved certificate to patients without outcomes')
    parser.add_argument('--out', default=None, help='optional per-patient CSV')
    args = parser.parse_args()
    data = load_rows(args.csv, args, bool(args.outcome))
    a, b = ([r['x'][j] for r in data] for j in (0, 1))
    summary = {'patients': len(data), 'readouts': [args.a, args.b], 'retest_cost': args.retest_cost}
    if args.certify is not None and (not args.outcome or not args.train):
        raise SystemExit('--certify requires --outcome and a separate labelled --train CSV')
    if args.certify is not None and args.certificate:
        raise SystemExit('Choose calibration or applying a saved certificate')
    if args.certificate:
        with open(args.certificate) as handle:
            cert = json.load(handle)
        if cert.get('schema') != 'release.certificate.v2':
            raise SystemExit('Recalibrate this legacy certificate with a separate --train CSV')
        if cert['readouts'] != [args.a, args.b] or cert['higher_is_sensitive'] != args.higher_is_sensitive:
            raise SystemExit('certificate was calibrated on other readout columns or direction')
        cases = apply(cert, data)
        calls_a, calls_b = ([c['calls'][j] for c in cases] for j in (0, 1))
        released = [c['released'] for c in cases]
        seen = set(cert['model']['training_ids']) | set(cert['calibration_ids'])
        summary.update({'cutoffs': 'frozen training model', 'certificate_alpha': cert['alpha'],
                        'model_sha256': cert['model']['model_sha256'], 'guarantee': cert['guarantee'],
                        'patients_seen_in_training_or_calibration': sum(r['patient'] in seen for r in data),
                        'released': sum(released), 'retests': len(data) - sum(released)})
        if args.outcome:
            summary['observed'] = {k: v for k, v in measure(cert, data, args.retest_cost).items() if k != 'rows'}
    elif args.certify is not None:
        training = load_rows(args.train, args, True)
        cert = calibrate(fit(training), data, args.certify)
        cert.update({'readouts': [args.a, args.b], 'higher_is_sensitive': args.higher_is_sensitive})
        cases = apply(cert, data)
        calls_a, calls_b = ([c['calls'][j] for c in cases] for j in (0, 1))
        released = [c['released'] for c in cases]
        summary.update({'cutoffs': 'frozen training model', 'model_sha256': cert['model']['model_sha256'],
                        'released': sum(released), 'retests': len(data) - sum(released),
                        'certificate': {k: v for k, v in cert.items() if k not in ('model', 'calibration_ids')}})
        if args.save_certificate:
            with open(args.save_certificate, 'w') as handle:
                json.dump(cert, handle, indent=2, allow_nan=False)
    elif args.outcome:
        truth = [r['y'] for r in data]
        ev_a, ev_b = evaluate(truth, a), evaluate(truth, b)
        calls_a, calls_b = ev_a['predictions'], ev_b['predictions']
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
        summary.update({'cutoffs': 'cohort median', 'released': sum(released), 'retests': len(data) - sum(released)})
    actions = [{'patient': r['patient'], 'call_' + args.a: 'sensitive' if x else 'resistant',
                'call_' + args.b: 'sensitive' if y else 'resistant',
                'action': ('release: ' + ('sensitive' if x else 'resistant')) if keep else 'retest'}
               for r, x, y, keep in zip(data, calls_a, calls_b, released)]
    if args.out:
        with open(args.out, 'w', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(actions[0]))
            writer.writeheader()
            writer.writerows(actions)
    print(json.dumps({'summary': summary, 'first_patients': actions[:5]}, indent=2))


if __name__ == '__main__':
    main()

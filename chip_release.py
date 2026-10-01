#!/usr/bin/env python3
"""Decide release or retest for your own two-readout chip or organoid data.

Give a CSV with one row per patient and two drug-response readouts (for example vessel and
tumoroid response, or the two drugs of a regimen). Lower values mean more sensitive unless
--higher-is-sensitive is set. With an outcome column, each readout's cutoff is learned
leave-one-patient-out; without one, each readout is split at its cohort median. A call is
released only when both readouts agree; otherwise the patient is sent to retest.

With an outcome column, --certify ALPHA empirically calibrates a release margin.
The present data reuse and the change from leave-one-out to full-pilot cutoffs leave
a formal conformal guarantee unestablished. --save-certificate keeps the cutoffs
and margin; --certificate applies them to new patients without outcomes.

    python chip_release.py examples/biliary_gemcis_auc.csv --a gemcitabine_auc --b cisplatin_auc
    python chip_release.py pilot.csv --a r1 --b r2 --outcome response --certify 0.10 --save-certificate cert.json
    python chip_release.py new_patients.csv --a r1 --b r2 --certificate cert.json
"""

import argparse
import csv
import json
import math
import statistics

from channel_consensus import release_counts
from chip_clinic import evaluate, threshold
from release_certificate import calibrate, ecdf, patient

POSITIVE = {'1', 'responder', 'sensitive', 'yes', 'cr', 'pr', 'sd', 'true'}
NEGATIVE = {'0', 'non_responder', 'non-responder', 'resistant', 'no', 'pd', 'false'}
CALIBRATION_SCOPE = ('Empirical calibration only: leave-one-out calls calibrate the margin, '
                     'but deployment uses full-pilot cutoffs; data-dependent margins and '
                     'cutoffs have no established conformal guarantee in this implementation.')


def margins(a, b, cut_a, cut_b, ref_a, ref_b):
    fa, fb = ecdf(ref_a), ecdf(ref_b)
    return [min(abs(fa(x) - fa(c)), abs(fb(y) - fb(d))) for x, y, c, d in zip(a, b, cut_a, cut_b)]


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
                        help='with --outcome: empirical wrong-release calibration at nominal ALPHA')
    parser.add_argument('--save-certificate', default=None, help='with --certify: write cutoffs and margin to this JSON')
    parser.add_argument('--certificate', default=None, help='apply a saved certificate to patients without outcomes')
    parser.add_argument('--out', default=None, help='optional per-patient CSV')
    args = parser.parse_args()
    with open(args.csv, newline='') as handle:
        rows = [r for r in csv.DictReader(handle) if r[args.a].strip() and r[args.b].strip()]
    ident = args.id or list(rows[0])[0]
    sign = -1.0 if args.higher_is_sensitive else 1.0
    a = [sign * float(r[args.a]) for r in rows]
    b = [sign * float(r[args.b]) for r in rows]
    summary = {'patients': len(rows), 'readouts': [args.a, args.b], 'retest_cost': args.retest_cost}
    if args.certify is not None and not args.outcome:
        raise SystemExit('--certify needs --outcome: a certificate is calibrated on patients with known outcomes')
    if args.outcome:
        labels = [r[args.outcome].strip().lower() for r in rows]
        unknown = sorted({x for x in labels if x not in POSITIVE | NEGATIVE})
        if unknown:
            raise SystemExit(f'unrecognised outcome values: {unknown}')
        truth = [int(x in POSITIVE) for x in labels]
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
        if args.certify is not None:
            gaps = margins(a, b, ev_a['training_cutoffs'], ev_b['training_cutoffs'], a, b)
            cases = [patient(x, y, t, m) for x, y, t, m in zip(calls_a, calls_b, truth, gaps)]
            lam = calibrate(cases, args.certify)
            released = [c['margin'] > lam for c in cases]
            wrong = sum(c['margin'] > lam and c['wrong'] for c in cases)
            summary['certificate'] = {
                'alpha': args.certify, 'margin': None if math.isinf(lam) else round(lam, 6),
                'releases_every_agreed_call': lam < 0, 'releases_none': math.isinf(lam),
                'released': sum(released), 'released_wrong': wrong, 'retests': n - sum(released),
                'pilot_bound': round((wrong + 1) / (n + 1), 6),
                'guarantee_status': 'unestablished', 'guarantee': CALIBRATION_SCOPE,
                'smallest_alpha_this_pilot_can_certify': round(1 / (n + 1), 6)}
            if args.save_certificate:
                with open(args.save_certificate, 'w') as handle:
                    json.dump({'readouts': [args.a, args.b], 'higher_is_sensitive': args.higher_is_sensitive,
                               'cutoffs': [threshold(a, truth), threshold(b, truth)], 'reference': [sorted(a), sorted(b)],
                               'margin': None if math.isinf(lam) else lam, 'alpha': args.certify,
                               'pilot_patients': n, 'pilot_released_wrong': wrong,
                               'guarantee_status': 'unestablished', 'calibration_scope': CALIBRATION_SCOPE}, handle, indent=2)
    elif args.certificate:
        with open(args.certificate) as handle:
            cert = json.load(handle)
        if cert['readouts'] != [args.a, args.b] or cert['higher_is_sensitive'] != args.higher_is_sensitive:
            raise SystemExit('certificate was calibrated on other readout columns or direction')
        cut_a, cut_b = cert['cutoffs']
        calls_a, calls_b = [int(x <= cut_a) for x in a], [int(y <= cut_b) for y in b]
        lam = math.inf if cert['margin'] is None else cert['margin']
        gaps = margins(a, b, [cut_a] * len(a), [cut_b] * len(b), *cert['reference'])
        released = [x == y and m > lam for x, y, m in zip(calls_a, calls_b, gaps)]
        summary.update({'cutoffs': 'from certificate', 'certificate_alpha': cert['alpha'],
                        'guarantee_status': 'unestablished', 'calibration_scope': CALIBRATION_SCOPE,
                        'released': sum(released), 'retests': len(rows) - sum(released)})
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

"""Integrity properties of the additional training-only signal experiments."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matched_regimen as single
from pooled_signal import fit_pooled, score, certify


class SignalFreezeTests(unittest.TestCase):
    def setUp(self):
        self.train = {'a': [{'patient': f'a{i}', 'x': [i, i * .8], 'y': int(i < 4)} for i in range(8)],
                      'b': [{'patient': f'b{i}', 'x': [i * 3., i], 'y': int(i < 3)} for i in range(7)]}

    def test_pooled_predictions_ignore_outcomes_and_batch_composition(self):
        model = fit_pooled(self.train)
        rows = [{'patient': 'new1', 'x': [1., 2.]}, {'patient': 'new2', 'x': [6., 4.]}]
        expected = score(model, 'a', rows)
        labelled = [dict(r, y=1) for r in rows]
        self.assertEqual(score(model, 'a', labelled), expected)
        self.assertEqual(score(model, 'a', rows[:1]), expected[:1])
        changed = copy.deepcopy(model)
        changed['coefficients'][0] += .01
        with self.assertRaisesRegex(ValueError, 'hash'):
            score(changed, 'a', rows)

    def test_calibration_rejects_changed_training_labels(self):
        model = fit_pooled(self.train)
        changed = copy.deepcopy(self.train['a'])
        changed[0]['y'] = 1 - changed[0]['y']
        calibration = [{'patient': 'cal1', 'x': [1., 2.], 'y': 1}]
        with self.assertRaisesRegex(ValueError, 'Training data differ'):
            certify(model, 'a', changed, calibration)

    def test_matched_regimen_has_one_fixed_readout_and_small_sample_fallback(self):
        training = [{'patient': f't{i}', 'x': float(i), 'y': int(i < 4)} for i in range(8)]
        calibration = [{'patient': f'c{i}', 'x': float(i), 'y': int(i < 4)} for i in range(8)]
        model = single.fit(training)
        before = copy.deepcopy(model)
        certificate = single.calibrate(model, training, calibration)
        self.assertEqual(model, before)
        self.assertFalse(certificate['conditional_certified'])
        self.assertEqual(certificate['overall_margin'], 1.)
        self.assertEqual(single.predict(model, [{'patient': 'new', 'x': 2., 'y': 0}]),
                         single.predict(model, [{'patient': 'new', 'x': 2., 'y': 1}]))


if __name__ == '__main__':
    unittest.main()

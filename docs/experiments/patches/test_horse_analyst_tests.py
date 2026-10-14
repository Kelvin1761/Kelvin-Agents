"""Leakage and denominator invariants for the research harness."""
import importlib.util
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    'horse_analyst_tests', Path(__file__).with_name('horse_analyst_tests.py'))
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


def run(day, distance=1200, position=2):
    return dict(date=day, dist=distance, p800=position, starters=10)


class EvidenceInvariants(unittest.TestCase):
    def test_future_and_current_events_cannot_change_prior_features(self):
        prior = [run('2026-06-01'), run('2026-08-01'), run('2026-08-12')]
        baseline = MOD.inputs(prior, '2026-08-20', career=3)
        candidate = MOD.inputs(prior + [run('2026-08-20', 9000, 10),
                                       run('2026-09-01', 9000, 10)],
                               '2026-08-20', career=3, same_day_or_future=True)
        self.assertEqual(baseline, candidate)
        self.assertEqual(baseline['negative_metres'], -2400)

    def test_career_metadata_cannot_certify_a_missing_window_boundary(self):
        prior = [run('2026-08-01'), run('2026-08-12')]
        baseline = MOD.inputs(prior, '2026-08-20', career=2)
        candidate = MOD.inputs(prior + [run('2026-09-01')], '2026-08-20',
                               career=2, same_day_or_future=True)
        self.assertEqual(baseline, candidate)
        self.assertNotIn('negative_metres', baseline)

    def test_trial_is_not_a_formal_workload_event(self):
        line = ('Deagon R1 2026-08-01 1050m cond:Soft 4th@800m starters:8 '
                'finish:2/8 RaceClass:[MDN-TRL Barrier Trial] WinningTime:1:00.000')
        self.assertEqual(MOD.history.parse_runs(line), [])

    def test_missing_values_are_neutral_in_a_race(self):
        self.assertEqual(MOD.zs([None, 1., 3.])[0], 0.)
        self.assertEqual(MOD.zs([None, 1., 1.]), [0., 0., 0.])

    def test_invalid_checkpoint_does_not_become_a_pace_feature(self):
        self.assertIsNone(MOD.f800(dict(p800=11, starters=10)))
        self.assertIsNone(MOD.f800(dict(p800=0, starters=10)))
        self.assertIsNone(MOD.f800(dict(p800=1, starters=1)))


if __name__ == '__main__':
    unittest.main()

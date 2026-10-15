"""Frozen-source regression: empty jockey must not consume a later form run."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT/'.agents/skills/au_racing'))
from claw_sportsbet_form import RE_RUN, parse_race  # noqa: E402


TRIAL = ('Colac ( ) 10/02/2026 Race 1 1000m Jump Out Barrier Trial '
         'Finished 2/5 (of 0), Jockey , Weight kg '
         '1st Pure Rain ( n/a) Winning Time 1:01.330 ')
FORMAL = ('Geelong ( Good ) 09/08/2024 Race 4 2400m MDN '
          'Finished 6/7 5.30L $675 (of $27,000), Jockey Jamie Mott, Barrier 2, '
          'Weight 59.5kg 11.00 1st Romans Luck (L Currie 59.5kg) Winning Time 2:31.820 ')


class SportsbetRunBoundaryTests(unittest.TestCase):
    def test_empty_jockey_retains_both_runs_and_own_metadata(self):
        runs = parse_race(TRIAL+FORMAL)['runs']
        self.assertEqual(len(runs), 2)
        self.assertEqual(runs[0]['jockey'], '')
        self.assertEqual(runs[0]['winning_time'], '1:01.330')
        self.assertTrue(runs[0]['is_trial'])
        self.assertEqual(runs[1]['jockey'], 'Jamie Mott')
        self.assertEqual(runs[1]['pos'], '6')
        self.assertEqual(runs[1]['winning_time'], '2:31.820')
        self.assertFalse(runs[1]['is_trial'])

    def test_every_match_contains_exactly_one_finished_anchor(self):
        matches = list(RE_RUN.finditer(TRIAL+FORMAL))
        self.assertEqual(len(matches), 2)
        self.assertTrue(all(m[0].count('Finished ') == 1 for m in matches))

    def test_missing_jockey_label_never_borrows_next_run(self):
        broken = TRIAL.replace('Jockey , ', '')
        runs = parse_race(broken+FORMAL)['runs']
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]['pos'], '6')

    def test_missing_weight_never_borrows_next_run(self):
        broken = TRIAL.replace(', Weight kg', '')
        runs = parse_race(broken+FORMAL)['runs']
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]['jockey'], 'Jamie Mott')

    def test_absent_trial_clock_is_not_filled_from_formal_run(self):
        no_clock = TRIAL.replace('Winning Time 1:01.330', '')
        runs = parse_race(no_clock+FORMAL)['runs']
        self.assertIsNone(runs[0]['winning_time'])
        self.assertEqual(runs[1]['winning_time'], '2:31.820')


if __name__ == '__main__':
    unittest.main()

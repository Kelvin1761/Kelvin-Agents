import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from au_sportsbet_time_inventory import audit, consistency, identity, prior_runs


def run(day='14/10/2026', **fields):
    return {'header': {'track': 'Gold Coast', 'date': day, 'race': '2', 'dist': '1200'},
            'winning_time': '1:10.00', 'l600': '34.00', 'margin': '2.5',
            'pos': '3', 'field': '10', **fields}


class SportsbetInventoryContracts(unittest.TestCase):
    def test_cutoff_and_trial_are_strict(self):
        rr = [run(), run('15/10/2026'), run('16/10/2026'), run(is_trial=True)]
        self.assertEqual(len(prior_runs(rr, '2026-10-15')), 1)
        bad = run('31/02/2026')
        self.assertIsNone(identity(bad))

    def test_same_winning_time_does_not_merge_distinct_races(self):
        a, b = identity(run()), identity(run('13/10/2026'))
        obs = [(a, 'A', run()), (a, 'B', run()),
               (b, 'C', run(l600='33.00')), (b, 'D', run(l600='33.00'))]
        result = consistency(obs, 'l600')
        self.assertEqual(result['comparable_historical_races'], 2)
        self.assertEqual(result['conflicting_races'], 0)

    def test_conflicting_duplicate_is_not_last_write_wins(self):
        key = identity(run())
        obs = [(key, 'A', run()), (key, 'A', run(winning_time='1:10.09')), (key, 'B', run())]
        result = consistency(obs, 'winning_time')
        self.assertEqual(result['conflicting_races'], 1)
        self.assertEqual(len(result['conflicts'][0]['by_runner']['A']), 2)

    def test_no_surface_folding(self):
        turf = run()
        poly = run()
        poly['header'] = dict(poly['header'], track='Gold Coast Poly')
        self.assertNotEqual(identity(turf), identity(poly))

    def test_empty_corpus_is_not_evidence_of_zero_coverage(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, 'no usable'):
                audit({}, Path(folder), {'2026-10-15'})

    def test_latest_missing_clock_does_not_backfill_older_clock(self):
        with tempfile.TemporaryDirectory() as folder:
            cache = Path(folder)
            url = 'https://www.sportsbetform.com.au/1/2/'
            (cache/(hashlib.sha1(url.encode()).hexdigest()+'.html')).write_text('Frozen source')
            blocks = [{'name': 'A', 'runs': [run(winning_time=None), run('01/10/2026')]}]
            with patch('au_sportsbet_time_inventory.parse_runner_blocks', return_value=blocks):
                result = audit({'meeting': {'date': '2026-10-15', 'meetingId': '1', 'races': ['2']}},
                               cache, {'2026-10-15'})
            self.assertEqual(result['latest_formal_presence']['winning_time'], 0)
            self.assertEqual(result['prior_formal_occurrence_presence']['winning_time'], 1)


if __name__ == '__main__':
    unittest.main()

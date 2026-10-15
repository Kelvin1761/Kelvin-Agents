"""Chronology, missing-last-run and next-start learning invariants."""
from copy import deepcopy
from datetime import date, timedelta
import unittest

import numpy as np

from au_next_start_speed_20261015 import fit_logistic, profile_lookup, runner_profile, train


class NextStartTests(unittest.TestCase):
    def test_missing_latest_does_not_select_older_measured_race(self):
        old = ('test', '2026-08-01', 1, 1200)
        last = ('test', '2026-08-04', 2, 1200)
        lookup = {(old, 'horse'): {'profile': [1]*6, 'going': 'good'}}
        raw, rel, audit = runner_profile([last, old], 'horse', '2026-08-05', 1200, 'good', lookup)
        self.assertIsNone(raw)
        self.assertEqual(rel, 0)
        self.assertEqual(audit['status'], 'latest_run_uncovered')
        self.assertEqual(audit['previous_date'], '2026-08-04')

    def test_target_and_future_runs_cannot_replace_previous(self):
        old = ('test', '2026-08-01', 1, 1200)
        lookup = {(old, 'horse'): {'profile': [1]*6, 'going': 'good'}}
        a = runner_profile([old], 'horse', '2026-08-05', 1200, 'good', lookup)
        b = runner_profile([('test', '2026-08-05', 1, 1200), ('test', '2099-01-01', 1, 1200), old],
                           'horse', '2026-08-05', 1200, 'good', lookup)
        self.assertEqual(a, b)

    def test_ambiguous_previous_date_is_not_arbitrarily_selected(self):
        keys = [('a', '2026-08-01', 1, 1200), ('b', '2026-08-01', 1, 1200)]
        raw, rel, audit = runner_profile(keys, 'horse', '2026-08-05', 1200, 'good', {})
        self.assertIsNone(raw)
        self.assertEqual(audit['status'], 'ambiguous_previous_day')

    def test_recent_same_trip_reliability_is_bounded(self):
        key = ('test', '2026-08-04', 1, 1200)
        lookup = {(key, 'horse'): {'profile': [1]*6, 'going': 'good'}}
        _, rel, audit = runner_profile([key], 'horse', '2026-08-05', 1200, 'good', lookup)
        self.assertTrue(0 < rel < .25)
        self.assertEqual(audit['gap_days'], 1)

    def test_logistic_direction(self):
        beta, meta = fit_logistic(np.ones((100, 1)), np.zeros(100))
        self.assertGreater(beta[0], 0)
        self.assertTrue(meta['converged'])

    def test_offset_reduces_already_explained_signal(self):
        x = np.ones((100, 1))
        neutral, _ = fit_logistic(x, np.zeros(100))
        residual, _ = fit_logistic(x, np.full(100, 5.))
        self.assertTrue(0 < residual[0] < neutral[0])

    def test_zero_features_produce_zero_correction(self):
        beta, _ = fit_logistic(np.zeros((100, 6)), np.ones(100))
        np.testing.assert_array_equal(beta, np.zeros(6))

    def test_insufficient_pairs_neutral(self):
        beta, meta = fit_logistic(np.ones((19, 6)), np.zeros(19))
        np.testing.assert_array_equal(beta, np.zeros(6))
        self.assertEqual(meta['fallback'], 'insufficient_pairs')

    def test_appending_future_labels_does_not_change_fit(self):
        races = []
        for day in range(5, 11):
            rows = []
            for pos in (1, 2, 4, 5):
                rows.append({'pos': pos, 'deployed': 60., 'next_x': [1 if pos <= 3 else -1]*6,
                    'next_profile_audit': {'status': 'observed', 'previous_date': '2026-08-01'}})
            races.append({'date': f'2026-08-{day:02}', 'rows': rows})
        a, ma = train(races, '2026-08-11', 6, True)
        future = deepcopy(races[-1])
        future['date'] = '2026-08-11'
        for row in future['rows']:
            row['next_x'] = [999]*6
            row['pos'] = 99
        b, mb = train(races+[future], '2026-08-11', 6, True)
        np.testing.assert_array_equal(a, b)
        self.assertEqual(ma, mb)

    @staticmethod
    def events():
        events = []
        for i in range(101):
            day = (date(2025, 1, 1)+timedelta(days=i)).isoformat()
            events.append({'date': day, 'track': 'test', 'distance': 1200,
                'key': ('test', day, 1, 1200), 'going': 'good', 'rating': '4',
                'class': 'CL3', 'rail': '2', 'total': 71., 'early': 25.,
                'rows': [{'horse': str(j), 'time': 70.+j, 'early': 24.+j, 'distance': 1200}
                         for j in range(3)]})
        return events

    def test_future_source_events_do_not_change_past_features(self):
        events = self.events()
        a, n = profile_lookup(events, '2026-08-05')
        future = deepcopy(events[-1])
        future['date'] = '2099-01-01'
        future['early'] = -999
        future['total'] = 0
        b, nn = profile_lookup(events+[future], '2026-08-05')
        self.assertEqual(n, nn)
        self.assertEqual(a, b)

    def test_result_and_price_do_not_change_features(self):
        events = self.events()
        a, _ = profile_lookup(events, '2026-08-05')
        for event in events:
            for row in event['rows']:
                row['actual_pos'] = 999
                row['sp'] = .01
        b, _ = profile_lookup(events, '2026-08-05')
        self.assertEqual(a, b)


if __name__ == '__main__':
    unittest.main()

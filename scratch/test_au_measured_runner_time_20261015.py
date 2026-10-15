"""Source semantics and temporal isolation for measured-time research."""
import unittest

from au_measured_runner_time_20261015 import parse_csv, features, seconds


class MeasuredRunnerTimeTests(unittest.TestCase):
    def test_legacy_minute_format(self):
        self.assertEqual(seconds('0:14.20'), 14.2)
        self.assertEqual(seconds('00:00:14.20'), 14.2)

    def test_sums_own_splits_and_ignores_header_time(self):
        header = 'Date,RaceNumber,8/10/2026 12:00:00 AM;2026-10-08 Ipswich QLD - Professional;Race;00:01:42.825;IPSW_800m_TRACK\n'
        # 5 is saddlecloth number, NOT finishing rank.
        row = '08/10/2026,1,Swanfels;5;200;17;00:00:13.00;400;18;00:00:11.00;600;18;00:00:11.00;800;18;00:00:11.00\n'
        rows, _ = parse_csv(header+row, 'official')
        self.assertEqual(rows[0]['time'], 46)
        self.assertEqual(rows[0]['tab'], 5)
        self.assertNotIn('source_rank', rows[0])

    def test_untracked_and_incomplete_rows_are_missing(self):
        header = 'Date,RaceNumber,date;2026-10-08 Ipswich QLD - Professional;Race;00:00:46.00;IPSW_800m_TRACK\n'
        rows, counts = parse_csv(header+'08/10/2026,1,X;1;200;0;00:00:00.000;800;18;00:00:45.0', 'official')
        self.assertEqual(rows, [])
        self.assertEqual(counts['invalid_or_untracked'], 1)

    def test_template_distance_is_not_actual_distance(self):
        header = 'Date,RaceNumber,date;2026-10-02 Rockhampton QLD - Professional;Race;00:01:01.00;ROCK_1100m_TRACK\n'
        payload = ';'.join(f'{p};18;00:00:{s}' for p, s in
                           [(50, '04.67'), (250, '11.34'), (450, '11.20'),
                            (650, '11.20'), (850, '11.20'), (1050, '11.20')])
        rows, counts = parse_csv(header+'02/10/2026,1,Wasabi Barbie;5;'+payload, 'official')
        self.assertEqual(rows[0]['distance'], 1050)
        self.assertEqual(counts['template_distance_mismatch'], 1)

    def test_excludes_target_future_and_missing_margin(self):
        runs = [{'track': 'ipswich', 'date': date, 'race': 1, 'distance': 1000,
                 'margin': margin, 'condition': 'good'} for date, margin in
                [('2026-09-01', 2), ('2026-09-02', 2), ('2026-09-03', None),
                 ('2026-10-01', 2), ('2026-10-02', 2)]]
        keyed = {(r['track'], r['date'], 1, 1000): 60 for r in runs}
        output = features(runs, '2026-10-01', ({('ipswich', 1000): 60}, {}, 10), keyed, keyed)
        self.assertIsNone(output['measured'])  # only TWO eligible historical runs

    def test_no_winner_or_estimate_substituted_for_missing_measurement(self):
        runs = [{'track': 'ipswich', 'date': f'2026-09-0{i}', 'race': 1,
                 'distance': 1000, 'margin': 3, 'condition': 'good'} for i in range(1,4)]
        winners = {(r['track'], r['date'], 1, 1000): 60 for r in runs}
        output = features(runs, '2026-10-01', ({('ipswich', 1000): 60}, {}, 10), {}, winners)
        self.assertTrue(all(value is None for value in output.values()))


if __name__ == '__main__':
    unittest.main()

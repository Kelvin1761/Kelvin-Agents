"""Regression for single tenth-place Facts versus compact Last 10 strings."""
import sys
from pathlib import Path
import unittest

ROOT = next(p for p in Path(__file__).resolve().parents if (p / 'AGENTS.md').is_file())
sys.path.insert(0, str(ROOT / '.agents/skills/au_racing/au_wong_choi_auto/scripts'))
from au_racing_engine.engine_core import RacingEngine
from au_racing_engine.scoring import CONSISTENCY_MICRO_WEIGHTS, parse_recent_finishes


class RecentFormFormatTests(unittest.TestCase):
    def test_decoded_double_digit_positions_remain_single_runs(self):
        for n in (10, 11, 12, 13, 20, 21, 24):
            self.assertEqual(parse_recent_finishes(str(n), source_format='positions'), [n])

    def test_explicit_compact_form_preserves_every_run(self):
        self.assertEqual(parse_recent_finishes('10', source_format='compact'), [1, 10])
        self.assertEqual(parse_recent_finishes('2134', source_format='compact'), [2, 1, 3, 4])
        self.assertEqual(parse_recent_finishes('0x13', source_format='compact'), [10, 1, 3])

    def test_legacy_compact_and_separated_inputs_still_work(self):
        self.assertEqual(parse_recent_finishes('2134'), [2, 1, 3, 4])
        self.assertEqual(parse_recent_finishes('10-5-3', source_format='positions'), [10, 5, 3])
        self.assertEqual(parse_recent_finishes('8-9-7-6'), [8, 9, 7, 6])

    def test_invalid_decoded_positions_cannot_create_a_win(self):
        for value in ('2134', 'N/A', '10x', '-1', '99', '10 (-3L)'):
            self.assertIsNone(parse_recent_finishes(value, source_format='positions'))
        with self.assertRaises(ValueError):
            parse_recent_finishes('10', source_format='guess')

    def engine(self, raw, *, marker=None, facts=''):
        data = {'recent_form': raw, 'career_record_line': '1:0-0-0'}
        if marker:
            data['recent_form_format'] = marker
        horse = {'horse_name': 'Platinum Card Regression', 'career_race_starts': 1,
                 'career_tag': 'EARLY_CAREER', '_data': data}
        return RacingEngine(horse, {}, facts_section=facts)

    def test_format_marker_prevents_phantom_podium_bonus(self):
        engine = self.engine('10', marker='positions')
        value, _, _ = engine._consistency_score()
        self.assertAlmostEqual(value, CONSISTENCY_MICRO_WEIGHTS['base'] + CONSISTENCY_MICRO_WEIGHTS['recent_poor_pen'])
        self.assertFalse(any(a['factor'] == '近績前三獎勵' for a in engine.consistency_detail['adjustments']))

    def test_archived_facts_without_marker_are_detected(self):
        engine = self.engine('10', facts='- 近績序列解讀: `10` (最新→最舊)')
        value, _, _ = engine._consistency_score()
        self.assertAlmostEqual(value, CONSISTENCY_MICRO_WEIGHTS['base'] + CONSISTENCY_MICRO_WEIGHTS['recent_poor_pen'])

    def test_different_facts_value_does_not_override_legacy_input(self):
        engine = self.engine('2134', facts='- 近績序列解讀: `10`')
        value, _, _ = engine._consistency_score()
        self.assertAlmostEqual(value, CONSISTENCY_MICRO_WEIGHTS['base'] + 3 * CONSISTENCY_MICRO_WEIGHTS['recent_place_bonus'])


if __name__ == '__main__':
    unittest.main()

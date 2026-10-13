"""Source integrity: non-standard formal starts and trial PF must not vanish/mix."""
from pathlib import Path
import sys
import tempfile
import unittest
ROOT = next(p for p in Path(__file__).resolve().parents if (p / 'AGENTS.md').exists())
sys.path[:0] = [str(ROOT / '.agents/scripts'), str(ROOT / '.agents/skills/au_racing'),
               str(ROOT / '.agents/skills/au_racing/au_wong_choi_auto/scripts')]
from claw_sportsbet_form import parse_race, run_line
from inject_fact_anchors import parse_formguide_for_horse
from au_racing_engine.engine_core import (_parse_formguide_pf_metrics,
    _parse_formguide_entries, _performance_quality_digest, refresh_pf_own_l600)
RAW = ("First Start Inverell ( Heavy ) 22/11/2025 Race 2 1050m MDN "
       "Finished -3/7 0.00L $1,425 (of $16,000), Jockey Ben Looker, "
       "Barrier 7, Weight 58.0kg 7.50 In running 800m 7th, 400m 5th "
       "1st Kool Bruce (S Lisnyy 57.0kg) Winning Time 1:02.400 "
       "2nd Version (G Geran 57.0kg) 0.39L 3rd Acira (L Small 56.0kg) 2.35L")
class HistoryIntegrityTest(unittest.TestCase):
    def source(self):
        runs = parse_race(RAW)['runs']
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]['pos'], '-3')
        return run_line(runs[0])
    def test_negative_result_preserved_without_fabricated_placing_margin(self):
        line, _ = self.source()
        self.assertTrue(line.startswith('Inverell R2 2025-11-22'))
        self.assertIn('ResultStatus:NON_STANDARD SourceFinish:[-3/7]', line)
        self.assertNotIn(' finish:', line)
        self.assertNotIn('margin:', line)
        self.assertNotIn('PF[', line)
    def test_formal_start_survives_facts_and_blocks_last10_result_fallback(self):
        line, opponents = self.source()
        # Deliberately put the horse into a podium result: status is authoritative.
        text = '[2] Platinum Card (3)\n' + line + '\n3-Platinum Card (58kg)'
        entries = parse_formguide_for_horse(text, 2, 'Platinum Card', [10], as_of='2026-10-12')
        self.assertEqual(len(entries), 1)
        self.assertFalse(entries[0]['is_trial'])
        self.assertIsNone(entries[0]['finish_pos'])
        self.assertIsNone(entries[0]['margin'])
        self.assertEqual(entries[0]['pos_source'], 'non_standard_result')
    def test_non_standard_result_excluded_from_quality_and_speed(self):
        line, _ = self.source()
        text = '[2] Platinum Card (3)\n' + line + ' PF[L600 Delta: -8.0]\n3-Platinum Card (58kg)'
        entries = _parse_formguide_entries(text, 'Platinum Card')
        self.assertIsNone(entries[0]['finish_pos'])
        self.assertIsNone(entries[0]['margin'])
        self.assertEqual(_performance_quality_digest(entries * 2, meeting_date='2026-10-12'), {})
        self.assertEqual(self.pf(text)['2']['pf_runs'], [])
    def pf(self, text):
        return _parse_formguide_pf_metrics(Path('2026-10-12 Test/Race 4 Facts.md'), formguide_text=text)
    def test_trial_forms_are_explicitly_distinguished_from_formal_speed(self):
        for header in ['Tamworth **(TRIAL)** R1', 'Tamworth R1', 'Tamworth Barrier Trial R1']:
            text = '[2] Platinum Card (3)\n' + header + ' 2025-11-04 1000m cond:Good $0 PF[L600 Delta: -8.0]'
            self.assertEqual(self.pf(text)['2']['pf_aggregates']['trial_run_count'], 1)
            self.assertEqual(self.pf(text)['2']['pf_aggregates']['formal_run_count'], 0)
    def test_mixed_history_retains_only_pre_race_pf_with_kind(self):
        text = ('[2] Platinum Card (3)\n'
            'Tamworth **(TRIAL)** R1 2025-11-04 1000m cond:Good $0 PF[L600 Delta: -8.0]\n'
            'Inverell R2 2025-11-22 1050m cond:Heavy $16000 margin:1.45L PF[Source: sportsbet_race_context L600 Delta: 0.2]\n'
            'Tamworth R4 2026-10-12 1000m cond:Soft $27000 PF[L600 Delta: -9.0]')
        pf = self.pf(text)['2']
        self.assertEqual(pf['pf_aggregates']['pf_run_count'], 2)
        self.assertEqual(pf['pf_aggregates']['formal_run_count'], 1)
        self.assertEqual(pf['pf_aggregates']['trial_run_count'], 1)
        self.assertEqual(pf['pf_runs'][1]['run_date'], '2025-11-22')
    def test_cached_trial_own_delta_is_refreshed_with_source_and_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            facts = Path(td) / 'Race 4 Facts.md'; facts.write_text('')
            facts.with_name('Race 4 Formguide.md').write_text('[2] Platinum Card (3)\nTamworth **(TRIAL)** R1 2025-11-04 1000m cond:Good $0 PF[L600 Delta: 0.18]')
            logic = {'horses': {'2': {'_data': {'pf_metrics': {'pf_aggregates': {'own_l600_delta_avg': .714}}}}}}
            self.assertEqual(refresh_pf_own_l600(logic, facts), 1)
            self.assertEqual(logic['horses']['2']['_data']['pf_metrics']['pf_aggregates']['trial_run_count'], 1)
            self.assertEqual(refresh_pf_own_l600(logic, facts), 0)
    def test_missing_formguide_preserves_cached_payload(self):
        logic = {'horses': {'2': {'_data': {'pf_metrics': {'pf_aggregates': {'own_l600_delta_avg': .714}}}}}}
        self.assertEqual(refresh_pf_own_l600(logic, Path('/nonexistent/Race 4 Facts.md')), 0)
        self.assertEqual(logic['horses']['2']['_data']['pf_metrics']['pf_aggregates']['own_l600_delta_avg'], .714)
    def test_non_standard_only_history_is_not_a_tenth_place_penalty(self):
        from au_racing_engine.engine_core import RacingEngine
        from au_racing_engine.scoring import CONSISTENCY_MICRO_WEIGHTS
        e = RacingEngine({'horse_name': 'Status Runner', 'career_race_starts': 1,
                          '_data': {'recent_form': '10', 'recent_form_format': 'positions'}}, {})
        e._official_entries = lambda: [{'result_status': 'NON_STANDARD'}]
        value, _, _ = e._consistency_score()
        self.assertEqual(value, CONSISTENCY_MICRO_WEIGHTS['base'])
        self.assertEqual(e.consistency_detail['recent_result_status'], 'non_standard_only')
    def test_report_exposes_single_old_trial_source(self):
        from au_racing_engine.renderer import _pace_perf_detail_lines
        lines = _pace_perf_detail_lines({'pace_perf_detail': {'pace': {
            'state': 'ok', 'z': -1.2, 'final': 84.1, 'runs': 1,
            'trial_runs': 1, 'formal_runs': 0, 'run_dates': ['2025-11-04']}}}, 'pace_figure_score')
        text = ' '.join(lines)
        self.assertIn('1 課試閘、0 場正式賽', text)
        self.assertIn('2025-11-04', text)
        self.assertIn('唔等於穩定速度', text)
    def test_trial_still_has_trial_result_and_opponents(self):
        raw = RAW.replace('First Start Inverell', 'Tamworth').replace('MDN ', 'OPEN-BT Barrier Trial ').replace('-3/7', '3/7').replace('$16,000', '0')
        run = parse_race(raw)['runs'][0]
        line, opponents = run_line(run)
        self.assertIn('**(TRIAL)**', line)
        self.assertIn('finish:3/7', line)
        self.assertTrue(opponents)
        self.assertNotIn('PF[', line)
if __name__ == '__main__': unittest.main()

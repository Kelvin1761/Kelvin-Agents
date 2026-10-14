"""Tests for research scorer boundaries, PIT and baseline equivalence."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import au_stability_redesign as design


def run(quality, distance=1000, going='Good', day='2026-08-01'):
    return {'quality': quality, 'distance': distance, 'going': going, 'date': day}


class StabilityDesignTests(unittest.TestCase):
    def test_identical_context_keeps_original_raw_average(self):
        raw, _ = design.contextual_quality([run(2), run(-2)], 1000, 'Soft 5', '2026-08-05')
        self.assertEqual(raw, round((2 - 0.8 * 2) / 1.8, 6))

    def test_matching_distance_changes_relative_evidence_not_blanket_penalty(self):
        raw, info = design.contextual_quality([run(2), run(-2, 2000)], 1000, 'Good', '2026-08-05')
        self.assertEqual(raw, round((2 - 0.8 * 0.25 * 2) / (1 + 0.8 * 0.25), 6))
        self.assertLess(info['weighted_compatibility'], 1)
        self.assertGreater(info['effective_n'], 1)

    def test_surface_mismatch_reweights_both_good_and_poor_evidence(self):
        positive, _ = design.contextual_quality([run(2), run(-2, going='Synthetic')], 1000, 'Good', '2026-08-05')
        negative, _ = design.contextual_quality([run(-2), run(2, going='Synthetic')], 1000, 'Good', '2026-08-05')
        self.assertAlmostEqual(positive, -negative)

    def test_unknown_context_keeps_old_weights(self):
        raw, _ = design.contextual_quality([run(2, 0, ''), run(-2, 0, '')], 1000, 'Good', '2026-08-05')
        self.assertEqual(raw, round((2 - 0.8 * 2) / 1.8, 6))

    def test_target_and_future_runs_fail_closed(self):
        for day in ('2026-08-05', '2026-08-06', ''):
            with self.assertRaises(ValueError):
                design.contextual_quality([run(2, day=day), run(-2)], 1000, 'Good', '2026-08-05')

    def test_fallback_intercept_excludes_debut_and_complete_evidence(self):
        self.assertEqual(design.fallback_quality(52.4, 'consistency_fallback', 0), 52.4)
        self.assertEqual(design.fallback_quality(80, 'class_adjusted_margin_field_relative', 10), 80)
        self.assertAlmostEqual(design.fallback_quality(61.9, 'consistency_fallback', 1), 57.3)

    def test_baseline_mix_is_identical_to_live_composition(self):
        row = {'features': {'form_score': 90, 'performance_quality_score': 35}, 'overlay': 2}
        self.assertAlmostEqual(design.scorer()(row), design.scorer(form_share=0.6)(row))

    def test_extreme_mix_preserves_outer_coefficient_and_overlay(self):
        row = {'features': {'form_score': 100, 'performance_quality_score': 20}, 'overlay': 2}
        self.assertAlmostEqual(design.scorer(form_share=1)(row), 62 + 40 * design.MATRIX_WEIGHTS['stability'])
        self.assertAlmostEqual(design.scorer(form_share=0)(row), 62 - 40 * design.MATRIX_WEIGHTS['stability'])

    def test_unmatched_runner_still_contributes_to_field_scale(self):
        def row(number, pos, raw):
            return {'n': number, 'pos': pos, 'features': {'performance_quality_score': 60},
                    'pq_source': 'class_adjusted_margin_field_relative', 'career_starts': 4,
                    'pq_field_raw': raw, 'contextual_raw': raw}
        race = {'full_rows': [row(1, 1, 1), row(2, 2, 2), row(3, None, 3)]}
        changed = design.candidate_race(race)
        self.assertEqual(len(changed['rows']), 2)
        self.assertLess(changed['rows'][0]['candidate_features']['B']['performance_quality_score'], 60)
        self.assertEqual(changed['rows'][1]['candidate_features']['B']['performance_quality_score'], 60)

    def test_evidence_route_uses_source_and_actual_form_rows(self):
        empty_form = {'form_detail': {'rows': []}, 'pq_source': 'class_adjusted_margin_field_relative'}
        fallback = {'form_detail': {'rows': [{'place': 10}]}, 'pq_source': 'consistency_fallback'}
        unknown = {'form_detail': {'rows': []}, 'pq_source': 'consistency_fallback'}
        self.assertEqual(design.evidence_share(empty_form, 'D1'), 0)
        self.assertEqual(design.evidence_share(empty_form, 'D2'), .6)
        self.assertEqual(design.evidence_share(fallback, 'D2'), 1)
        self.assertEqual(design.evidence_share(fallback, 'D1'), .6)
        self.assertEqual(design.evidence_share(unknown, 'D12'), .6)
        with self.assertRaises(ValueError):
            design.evidence_share(unknown, 'guess')


if __name__ == '__main__':
    unittest.main()

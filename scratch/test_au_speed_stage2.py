"""Meaningful chronology, immutable-profile and baseline reproduction checks."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest

from au_distance_par_20261015 import ExactStandard, SegmentStandard
from au_neutral_speed_20261015 import DIMS, MATRIX_WEIGHTS
from au_racing_engine.scoring import FEATURE_KEYS
from au_speed_forward_shadow import digest, fingerprint, shadow, validate_config


class StageTwoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.now = datetime(2026, 10, 15, 8, 0, tzinfo=timezone.utc)
        self.config = {'schema': 'au-speed-forward-v1', 'research_only': True,
            'frozen_at': (self.now-timedelta(minutes=2)).isoformat(),
            'valid_from': '2026-10-16', 'train_through': '2026-10-08',
            'baseline_weights': dict(MATRIX_WEIGHTS), 'engine_sha256': fingerprint(),
            'weights': {**{k: v*.9 for k, v in MATRIX_WEIGHTS.items()},
                        'A': sum(MATRIX_WEIGHTS.values())*.1},
            'speed_scale': 10, 'baseline_speed_gain': 1.5}
        self.config['config_sha256'] = digest(self.config)
        events = [{'date': '2026-10-14', 'key': ['test', '2026-10-14', 1, 1200], 'rows': []}]
        source_hash = digest(events)
        captured = self.now-timedelta(minutes=3)
        self.bundle = Path(self.tmp.name)/'bundle.json'
        self.bundle.write_text(json.dumps({'model_version': 'AU_CONTEXT_TOTAL_V1',
            'captured_at': captured.isoformat(), 'events': events, 'events_sha256': source_hash,
            'valid_from': '2026-10-16'}))
        audit = {'status': 'ready', 'model_version': 'AU_CONTEXT_TOTAL_V1',
            'target_date': '2026-10-16', 'captured_at': captured.isoformat(),
            'prediction_at': (self.now-timedelta(minutes=1)).isoformat(), 'source_hash': source_hash}
        self.logic = {'race_analysis': {'race_number': 1, 'full_time_speed': audit,
             'meeting_intelligence': {'date': '2026-10-16', 'venue': 'Synthetic fixture'}}, 'horses': {}}
        for n, contribution in enumerate((1.5, -1.5, 0., 0.), 1):
            detail = {'model_version': 'AU_CONTEXT_TOTAL_V1', 'status': 'observed',
                      'source_hash': source_hash, 'contribution': contribution}
            self.logic['horses'][str(n)] = {'horse_name': f'Fixture {n}', 'python_auto': {
                'feature_scores': dict.fromkeys(FEATURE_KEYS, 60.), 'wet_form_feature': 0.,
                'proven_class_feature': 0., 'ability_score': 60+contribution,
                'full_time_speed_feature': contribution, 'full_time_speed_detail': detail}}

    def tearDown(self):
        self.tmp.cleanup()

    def capture(self, logic=None, config=None, now=None):
        return shadow(logic or self.logic, config or self.config, self.bundle, now or self.now)

    def test_pure_speed_with_every_other_score_neutral(self):
        out = self.capture()
        first = out['horses'][0]
        self.assertEqual(first['baseline'], 61.5)
        self.assertEqual(first['candidate'], round(60+10*self.config['weights']['A'], 4))
        self.assertEqual(out['candidate_order'], [1, 3, 4, 2])

    def test_results_and_market_are_not_scoring_inputs(self):
        changed = deepcopy(self.logic)
        for horse in changed['horses'].values():
            horse['actual_pos'] = 999
            horse['sp'] = .01
        a, b = self.capture(), self.capture(changed)
        self.assertEqual(a['horses'], b['horses'])
        self.assertNotEqual(a['input_sha256'], b['input_sha256'])

    def test_manifest_tampering_rejected(self):
        config = deepcopy(self.config)
        config['weights']['A'] += .1
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            validate_config(config)

    def test_earlier_prediction_than_freeze_rejected(self):
        self.logic['race_analysis']['full_time_speed']['prediction_at'] = (self.now-timedelta(days=1)).isoformat()
        with self.assertRaisesRegex(ValueError, 'chronology'):
            self.capture()

    def test_after_race_day_capture_rejected(self):
        with self.assertRaisesRegex(ValueError, 'new pre-race'):
            self.capture(now=self.now+timedelta(days=2))

    def test_same_day_without_jump_time_rejected(self):
        with self.assertRaisesRegex(ValueError, 'same-day jump time'):
            self.capture(now=self.now+timedelta(days=1))

    def test_baseline_drift_rejected(self):
        self.logic['horses']['1']['python_auto']['ability_score'] += .1
        with self.assertRaisesRegex(ValueError, 'cannot be reproduced'):
            self.capture()

    def test_missing_evidence_cannot_be_nonzero(self):
        self.logic['horses']['1']['python_auto']['full_time_speed_detail']['status'] = 'no_matched_formal_runs'
        with self.assertRaisesRegex(ValueError, 'missing evidence'):
            self.capture()

    def test_same_day_source_rejected(self):
        bundle = json.loads(self.bundle.read_text())
        bundle['events'][0]['date'] = '2026-10-16'
        bundle['events_sha256'] = digest(bundle['events'])
        self.bundle.write_text(json.dumps(bundle))
        self.logic['race_analysis']['full_time_speed']['source_hash'] = bundle['events_sha256']
        with self.assertRaisesRegex(ValueError, 'same/future-day'):
            self.capture()

    def test_exact_standard_only_changes_distance_key(self):
        a = {'track': 'test', 'distance': 1400, 'going': 'good', 'rating': '4', 'class': 'CL3', 'rail': '2'}
        b = {**a, 'distance': 1500}
        self.assertEqual(SegmentStandard.category(a, 'track_band'), SegmentStandard.category(b, 'track_band'))
        self.assertNotEqual(ExactStandard.category(a, 'track_band'), ExactStandard.category(b, 'track_band'))
        for key in ('track', 'going', 'track_going', 'rating', 'track_rail', 'class'):
            self.assertEqual(ExactStandard.category(a, key), SegmentStandard.category(a, key))


if __name__ == '__main__':
    unittest.main()

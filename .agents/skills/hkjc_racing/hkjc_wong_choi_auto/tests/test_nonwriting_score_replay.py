"""Real production scoring parity; synthetic inputs are not PIT acceptance."""
from __future__ import annotations

from copy import deepcopy
from contextlib import ExitStack
import hashlib
import json
from unittest.mock import patch

import pytest

from test_auto_outputs import _logic, auto_orchestrator as auto


def fixture(tmp_path):
    path = tmp_path / 'Race_1_Logic.json'
    logic = _logic()
    for number in range(3, 9):
        horse = deepcopy(logic['horses']['1'])
        horse['horse_name'] = f'合成測試{number}'
        horse['barrier'] = str(number)
        horse['_data']['raw_l400'] = str(23.0 + number / 10)
        horse['last_6_finishes'] = f'{number}-4-3-2-5-6'
        logic['horses'][str(number)] = horse
    path.write_text(json.dumps(logic, ensure_ascii=False), encoding='utf-8')
    return path, logic


def model_fingerprint(value):
    keys = ('ability_score_raw', 'ability_score', 'official_ranking_score', 'grade',
            'matrix_scores', 'feature_scores', 'overlays')
    payload = {n: {key: h['python_auto'].get(key) for key in keys}
               for n, h in value['horses'].items()}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False).encode()).hexdigest()


def test_complete_scoring_api_preserves_inputs_and_production_result(tmp_path):
    path, logic = fixture(tmp_path)
    runner = auto.HKJCAutoOrchestrator(path)
    original = path.read_bytes()
    assert hashlib.sha256(json.dumps(logic, ensure_ascii=False).encode()).hexdigest() == \
        'b1155cc5488ce404a3a17c2d0b02ee757b9d0c33682dd918f7a18b53c8a43e3b'
    with patch.object(auto, '_get_profile_scraper', return_value=None):
        before = {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}
        result = runner.score_logic_data(path, logic)
        assert {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()} == before
        assert path.read_bytes() == original
        assert logic == json.loads(original)
        assert result is not logic
        expected = runner.score_race(path)
    assert result == expected
    # Captured from unmodified production2c50 before applying this extraction.
    assert model_fingerprint(result) == 'ec4b732a725e0f83dd8c617f723d3c18fc3d1df30264056e97cc24ed32f64a63'
    events = [json.loads(line) for line in runner.log_path.read_text().splitlines()]
    assert [e['horse_number'] for e in events if e['event_type'] == 'horse_scored'] == list(logic['horses'])


def test_output_writer_uses_the_complete_shared_scoring_entry(tmp_path):
    path, logic = fixture(tmp_path)
    runner = auto.HKJCAutoOrchestrator(path)
    with patch.object(runner, 'score_logic_data', return_value=None) as score:
        with patch.object(auto, 'prepare_race_outputs') as prepare:
            assert runner.score_race(path) is None
            score.assert_called_once()
            assert score.call_args.args == (path, logic)
            assert score.call_args.kwargs['event_sink'] == runner._emit_event
            prepare.assert_not_called()


def test_invalid_logic_does_not_publish_outputs_or_events(tmp_path):
    path, logic = fixture(tmp_path)
    runner = auto.HKJCAutoOrchestrator(path)
    with patch.object(auto, '_get_profile_scraper', return_value=None), \
            patch.object(auto, 'validate_logic_data', return_value=['fixture invalid']):
        assert runner.score_logic_data(path, logic) is None
    assert {p.name for p in tmp_path.iterdir()} == {path.name}


def test_scoring_error_does_not_write_partial_outputs(tmp_path):
    path, logic = fixture(tmp_path)
    runner = auto.HKJCAutoOrchestrator(path)
    before = path.read_bytes()
    with patch.object(auto, '_get_profile_scraper', return_value=None), \
            patch.object(auto.RacingEngine, 'analyze_horse', side_effect=RuntimeError('fixture')):
        with pytest.raises(RuntimeError, match='fixture'):
            runner.score_logic_data(path, logic)
    assert path.read_bytes() == before
    assert {p.name for p in tmp_path.iterdir()} == {path.name}


def test_shared_entry_keeps_all_field_adjustments_and_final_verdict_order(tmp_path):
    path, logic = fixture(tmp_path)
    runner = auto.HKJCAutoOrchestrator(path)
    steps = []
    def record(name, function):
        def call(*args, **kwargs):
            steps.append(name)
            return function(*args, **kwargs)
        return call
    with ExitStack() as stack:
        stack.enter_context(patch.object(auto, '_get_profile_scraper', return_value=None))
        for owner, name in ((auto, '_apply_sip_enhancements'),
                            (runner, '_apply_mainline_shape_robustness'),
                            (runner, '_apply_overlays'),
                            (auto, '_refresh_grade_transparency'),
                            (runner, '_apply_7d_official_ranking'),
                            (auto, 'ensure_verdict'),
                            (runner, '_finalize_shadow_profiles'),
                            (auto.race_summary, 'attach')):
            stack.enter_context(patch.object(owner, name, side_effect=record(name, getattr(owner, name))))
        assert runner.score_logic_data(path, logic)
    assert steps == ['_apply_sip_enhancements', '_apply_mainline_shape_robustness',
                     '_apply_overlays', '_refresh_grade_transparency', '_apply_7d_official_ranking',
                     'ensure_verdict', '_finalize_shadow_profiles', 'attach']

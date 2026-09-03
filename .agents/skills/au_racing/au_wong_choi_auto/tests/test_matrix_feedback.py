"""Regression cases from the 2026-09-02 AU matrix feedback."""
from datetime import datetime
import json
from pathlib import Path
from types import SimpleNamespace
import sys

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / '.agents/scripts'))
sys.path.insert(0, str(ROOT / '.agents/skills/au_racing'))

import pytest  # noqa: E402
from au_racing_engine.engine_core import RacingEngine  # noqa: E402
from au_racing_engine.matrix_mapper import map_features_to_matrix_scores  # noqa: E402
from au_racing_engine.renderer import _matrix_composition_line  # noqa: E402
import inject_fact_anchors as injector  # noqa: E402
import sb_horse_index as index  # noqa: E402


def form(place, field):
    engine = RacingEngine({'horse_name': 'Test', 'career_race_starts': 10, '_data': {}},
                          {'race_class': 'BM72'}, facts_section='')
    engine._official_entry_cache = [{'placing': str(place), 'field_size': field,
                                    'date': '2026-08-01', 'class': 'BM72'}]
    return engine._form_score()[0]


def test_winner_evidence_increases_with_rivals_but_is_not_always_full_marks():
    assert form(1, 3) == pytest.approx(80)
    assert form(1, 14) == pytest.approx(94.6666667)
    assert 60 < form(1, 2) < form(1, 3) < form(1, 14) < 100


def test_missing_field_and_non_winner_keep_their_old_rules():
    assert form(1, None) == 100
    assert form(3, 9) == 75
    assert form(2, 7) == 75


def test_formline_has_no_borrowed_recent_form_or_display_gain():
    for recent in (0, 60, 100):
        matrix = map_features_to_matrix_scores({'formline_score': 67, 'form_score': recent})
        assert matrix['form_line'] == 67


def test_rating_formula_explains_the_unallocated_neutral_share():
    features = {'rating_score': 60}
    auto = {'feature_scores': features, 'matrix_scores': map_features_to_matrix_scores(features)}
    line = _matrix_composition_line('class_weight', auto)
    assert '60 ＋ （Rating 分 60.00 −60）×70%' in line
    assert '＝ 60.0' in line
    assert '統一尺' not in line


def test_existing_index_uses_correct_venue_class_without_changing_asof(tmp_path):
    path = tmp_path / 'index.json'
    path.write_text(json.dumps({'rival': {'runs': [
        {'date': '2026-08-20', 'venue': 'Warwick Farm', 'class': '省賽'},
        {'date': '2026-09-02', 'venue': 'Canberra Acton', 'class': '省賽'},
    ]}}))
    rows = index.lookup(['Rival'], path, as_of='2026-09-02')['rival']['runs']
    assert len(rows) == 1
    assert rows[0]['class'] == 'Metro'
    assert index.infer_class('Canberra Acton') == '省賽'
    assert json.loads(path.read_text())['rival']['runs'][0]['class'] == '省賽'


def followup(monkeypatch, runs):
    monkeypatch.setattr(injector.subprocess, 'run', lambda *a, **k:
                        SimpleNamespace(stdout=json.dumps({'rival': {'runs': runs}}), returncode=0))
    return injector.compute_form_lines_via_api([{
        'is_trial': False, 'finish_pos': 2, 'result_line': '1-Rival (57kg)',
        'date_dt': datetime(2026, 8, 1), 'date': '2026-08-01',
        'venue': 'Test', 'race_no': 1,
    }])


def test_partial_placings_cannot_inflate_complete_run_place_rate(monkeypatch):
    runs = [{'date': f'2026-08-{day:02d}', 'finish': 8, 'class': '省賽'}
            for day in (2, 3, 4)]
    runs += [{'date': f'2026-08-{day:02d}', 'finish': 2, 'class': '省賽', 'partial': True}
             for day in (5, 6)]
    result = followup(monkeypatch, runs)
    assert '❌ 弱組' in '\n'.join(result['table_lines'])
    assert '見前三 2 次: 0 勝' in '\n'.join(result['table_lines'])


def test_followup_consumes_index_class_instead_of_a_second_venue_list(monkeypatch):
    result = followup(monkeypatch, [{'date': '2026-08-20', 'finish': 1,
                                    'venue': 'Warwick Farm', 'class': 'Metro'}])
    assert '✅✅ 超強組' in '\n'.join(result['table_lines'])


def test_formline_retains_proximity_and_dates_and_censors_target_day(monkeypatch):
    monkeypatch.setattr(injector, '_AS_OF', '2026-09-02')
    result = followup(monkeypatch, [
        {'date':'2026-08-20', 'finish':1, 'venue':'Warwick Farm', 'class':'Metro'},
        {'date':'2026-09-02', 'finish':1, 'venue':'Warwick Farm', 'class':'Metro'},
    ])
    evidence = result['evidence']
    assert evidence['as_of'] == '2026-09-02'
    assert evidence['rows'][0]['own_finish'] == 2
    assert [r['date'] for r in evidence['rows'][0]['followups']] == ['2026-08-20']


def test_preparation_is_separate_without_double_counting():
    from au_racing_engine.scoring import compose_matrix_score
    engine = RacingEngine({'horse_name':'Test', '_data': {'trial_count':2, 'trial_top3_count':2}},
                          {'race_number':1}, facts_section='')
    before = engine._jockey_horse_fit_score()[0]
    auto = engine.analyze_horse()
    features = auto['feature_scores']
    assert features['preparation_score'] > 60
    assert features['jockey_horse_fit_score'] + features['preparation_score'] - 60 == pytest.approx(before)
    old = {**features, 'jockey_horse_fit_score': before, 'preparation_score':60}
    assert compose_matrix_score(map_features_to_matrix_scores(features)) == pytest.approx(
        compose_matrix_score(map_features_to_matrix_scores(old)), abs=.01)
    assert not any(a['factor'] in engine._PREPARATION_FACTORS
                   for a in auto['jt_fit_detail']['adjustments'])


def test_quality_source_keeps_surface_and_true_class_separate_from_rating():
    from au_racing_engine.engine_core import _parse_formguide_entries
    rows = _parse_formguide_entries(
        'Canberra Acton R5 2026-08-21 1900m cond:Synthetic $35000 Damon Budler (1) 55kg '
        'margin:0L starters:9 finish:1/9 RaceClass:[OPEN BM79]\n', 'Sunburnt Country')
    assert rows[0]['race_class'] == 'OPEN BM79'
    assert rows[0]['going'] == 'Synthetic'
    assert rows[0]['venue'] == 'Canberra Acton'

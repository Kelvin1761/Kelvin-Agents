from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from au_racing_engine.preparation_cycle import preparation_cycle
from au_racing_engine.engine_core import RacingEngine
from au_racing_engine.renderer import _matrix_fact_lines, _status_cycle_display


def test_gunroom_is_second_up_not_an_ordinary_fourteen_day_gap():
    rows = [{'date':'2026-08-08','placing':'- (-1.5L)'},
            {'date':'2026-06-29','is_trial':True}, {'date':'2025-12-12','placing':'3/8'}]
    c = preparation_cycle(rows, '2026-08-22')
    assert c['stage'] == 'second_up'
    assert (c['prior_spell_days'],c['days_since_last_run'],c['completed_prep_runs']) == (239,14,1)
    assert c['return_finish'] is None  # Never invent fourth from a missing finish token.
    assert c['return_margin'] == 1.5
    assert '第二仗' in c['summary']


def test_bacetti_is_first_up_despite_recent_trials():
    rows = [{'date':'2026-08-25','kind':'TRIAL'}, {'date':'2026-04-01'}]
    c = preparation_cycle(rows,'2026-09-02')
    assert c['stage'] == 'first_up'
    assert c['prior_spell_days'] == 154


def test_future_invalid_and_duplicate_dates_do_not_change_cycle():
    rows = [{'date':'2026-08-08'},{'date':'2025-12-12'}]
    c = preparation_cycle(rows,'2026-08-22')
    assert preparation_cycle(rows + [{'date':'2026-08-22'},{'date':'2026-09-01'},
                                     {'date':'date'},{'date':'2026-08-08'}],'2026-08-22') == c
    assert preparation_cycle(rows,'')['stage'] == 'unknown'


def test_third_up_and_insufficient_history_are_distinct():
    rows = [{'date':'2026-08-08'},{'date':'2026-07-24'},{'date':'2025-12-12'}]
    assert preparation_cycle(rows,'2026-08-22')['stage'] == 'third_up'
    assert preparation_cycle(rows[:1],'2026-08-22')['stage'] == 'unknown'
    assert preparation_cycle([], '2026-08-22',career_starts=0)['stage'] == 'debut'


def test_cycle_metadata_changes_explanation_without_changing_any_score(monkeypatch):
    h={'horse_name':'Example','career_race_starts':5,'_data':{'latest_official_date':'2026-08-08'}}
    ctx={'date':'2026-08-22','race_class':'BM64'}
    e=RacingEngine(h,ctx)
    e._official_entry_cache=[{'date':'2026-08-08','placing':'4/8'},
                             {'date':'2025-12-12','placing':'3/8'}]
    actual=e.analyze_horse()
    assert actual['preparation_cycle']['stage'] == 'second_up'
    assert '239' in actual['core_logic']
    assert '正常間隔' not in actual['feature_notes']['health_score']
    monkeypatch.setattr(e,'_preparation_cycle',lambda:preparation_cycle([],''))
    legacy=e.analyze_horse()
    assert actual['feature_scores'] == legacy['feature_scores']
    assert actual['ability_score'] == legacy['ability_score']


def test_report_uses_dated_cycle_in_summary_and_matrix_with_legacy_fallback():
    horse = {'status_cycle': 'First-up', '_data': {'recent_form': '34'}}
    auto = {'preparation_cycle': preparation_cycle(
        [{'date': '2026-08-08'}, {'date': '2025-12-12'}], '2026-08-22')}
    assert _status_cycle_display(horse, auto) == '休後第二仗'
    lines = '\n'.join(_matrix_fact_lines('stability', horse, auto))
    assert '休後第二仗' in lines
    assert 'First-up' not in lines
    assert _status_cycle_display(horse)

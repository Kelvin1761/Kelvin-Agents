"""Experience cutoff must remove performance without deleting preparation."""
from copy import deepcopy
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

from au_auto_orchestrator import _build_field_summary  # noqa: E402
from au_racing_engine.engine_core import (  # noqa: E402
    RacingEngine, _pf_aggregates, performance_pf_metrics, trial_performance_applies,
)


def horse(starts=6):
    runs = [dict(run_kind='trial', l600_delta=-4., margin=0.,
                 source='sportsbet_race_context'),
            dict(run_kind='formal', l600_delta=1., margin=2.,
                 source='sportsbet_race_context')]
    return {'horse_name': 'Test', 'career_race_starts': starts,
            '_data': {'trial_count': 3, 'trial_top3_count': 3,
                      'timing_trial_600m_avg_speed': 18.,
                      'pf_metrics': {'pf_runs': runs,
                                     'pf_aggregates': _pf_aggregates(runs, 'sportsbet_race_context')}}}


@pytest.mark.parametrize('starts,applies', [(0, True), (2, True), (5, True),
                                          (6, False), (20, False), ('6', False),
                                          (None, True), ('unknown', True)])
def test_known_six_starts_is_the_boundary(starts, applies):
    assert trial_performance_applies(horse(starts)) is applies


def test_trial_score_is_neutral_and_does_not_warn_about_poor_performance():
    subject = RacingEngine(horse(), {'race_number': 1})
    score, note, source = subject._trial_score()
    assert score == 60 and source == 'disabled_neutral'
    assert '試閘表現不入能力分' in note
    assert 'trial_no_recent_top3' not in subject.risk_flags


def test_pf_filter_retains_formal_runs_and_raw_context():
    data = horse()
    original = deepcopy(data)
    filtered = performance_pf_metrics(data)
    assert filtered['pf_aggregates']['pf_run_count'] == 1
    assert filtered['pf_aggregates']['own_l600_delta_avg'] == 1.34
    assert filtered['pf_aggregates']['trial_run_count'] == 0
    assert data == original
    # EXP-20261016-77：L600 環境分一律唔計試閘行，少過 6 場都係（試閘速度改喺試閘備戰計）。
    assert performance_pf_metrics(horse(5))['pf_aggregates']['pf_run_count'] == 1


def test_all_trial_pf_becomes_missing_without_deleting_raw_rows():
    data = horse()
    data['_data']['pf_metrics']['pf_runs'] = data['_data']['pf_metrics']['pf_runs'][:1]
    assert performance_pf_metrics(data)['pf_aggregates'] == {}
    assert len(data['_data']['pf_metrics']['pf_runs']) == 1


def test_field_and_runner_use_the_same_filtered_speed_evidence():
    horses = {str(i): horse() for i in range(3)}
    for i, h in enumerate(horses.values()):
        h['_data']['pf_metrics']['pf_runs'][1]['l600_delta'] = float(i)
    ctx = {'field_summary': _build_field_summary(horses)}
    assert ctx['field_summary']['own_l600_delta_field_mean'] == pytest.approx(1.34)
    subject = RacingEngine(horses['1'], ctx)
    assert subject._pf_metrics()['pf_aggregates']['own_l600_delta_avg'] == 1.34


def test_preparation_bonus_is_retained_after_six_starts():
    subject = RacingEngine(horse(), {'race_number': 1})
    subject._jockey_horse_fit_score()
    score, _note, _source = subject._preparation_score()
    assert score > 60
    assert subject.data['trial_count'] == 3


def test_trial_600m_speed_field_no_longer_changes_form():
    """EXP-20261016-76：`timing_trial_600m_avg_speed` 嚟自 Racenet 逐駒 600m，Sportsbet 冇，語料 0% 有值；
    讀佢嘅「新馬試閘時間補充」已剷走，所以任何出賽數都唔再受呢個欄影響。"""
    def form(starts, speed):
        h = horse(starts)
        h['_data']['timing_trial_600m_avg_speed'] = speed
        h['_data']['recent_form'] = '1234'
        return RacingEngine(h, {'race_class': 'Maiden', 'distance': '1200m'})._form_score()[0]
    assert form(6, 18.) == form(6, None)
    assert form(5, 18.) == form(5, None)
    assert form(0, 18.) == form(0, None)

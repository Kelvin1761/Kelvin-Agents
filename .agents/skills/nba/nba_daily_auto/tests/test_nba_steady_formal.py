"""EXP-20261027-21: formal steady (B2) banker, its disclosure and stop-loss."""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

NBA = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(NBA))
import nba_steady_policy as steady


@pytest.fixture
def state(tmp_path, monkeypatch):
    path = tmp_path / 'steady_policy_state.json'
    monkeypatch.setenv('WONGCHOI_NBA_STEADY_STATE', str(path))
    return path


def records(profits, policy=steady.POLICY, prob=0.34):
    return [{'day': f'2026-11-{1 + i // 7:02d}', 'state': 'won' if p > 0 else 'lost', 'profit': p,
             'strategy_profile': policy, 'model_probability': prob} for i, p in enumerate(profits)]


def test_s1_cumulative_loss_pauses_once_and_never_resumes_itself(state):
    rows = records([-1] * 10)
    first, newly, metrics = steady.check(rows)
    assert newly and first['status'] == 'paused' and metrics['stop'].startswith('S1')
    again, newly_again, _ = steady.check(rows + records([1.5] * 30))
    assert again['status'] == 'paused' and not newly_again
    assert json.loads(state.read_text())['history'][0]['event'] == 'paused'


def test_s1_counts_only_policy_records_after_resume(state):
    old = records([-1] * 12, policy='banker-only-v1')
    assert steady.evaluate(old)['bets'] == 0
    steady.check(records([-1] * 10))
    steady.resume('Kelvin', 'reviewed', '2026-12-01')
    after, newly, metrics = steady.check(records([-1] * 10))
    assert after['status'] == 'active' and not newly and metrics['bets'] == 0


def test_s2_needs_sixty_bets_and_an_upper_bound_below_zero(state, monkeypatch):
    # Isolate S2 from S1: at flat $1, S2 can only bind first after a resume.
    monkeypatch.setattr(steady, 'STOP_UNITS', -1000)
    losing = [1.4, -1, -1] * 40                       # ROI -20%
    assert steady.evaluate(records(losing[:57]))['stop'] is None   # <60 bets: no CI test
    metrics = steady.evaluate(records(losing))
    assert metrics['roi_upper_ci'] < 0 and metrics['stop'].startswith('S2')
    assert steady.evaluate(records([1.5, -1] * 40))['stop'] is None


def test_s3_review_flags_hit_rate_shortfall_without_pausing(state):
    rows = records([4.0] * 8 + [-1] * 32, prob=0.40)   # 20% hit vs 40% model, 0u
    metrics = steady.evaluate(rows)
    assert metrics['stop'] is None and metrics['review'].startswith('S3')


def test_unreadable_state_fails_closed(state):
    state.write_text('{not json')
    assert steady.paused_reason() == 'state_unreadable'
    state.write_text(json.dumps({'status': 'maybe'}))
    assert steady.paused_reason() == 'state_invalid'


class _Log:
    def __init__(self):
        self.steps = []

    def step(self, name, status, **detail):
        self.steps.append((name, status, detail))


def _schedule():
    sys.path.insert(0, str(NBA / 'nba_daily_auto'))
    import nba_daily_schedule as schedule
    return schedule


def test_betting_card_discloses_negative_ev_and_pause(state):
    schedule = _schedule()
    no_bet = {'validation_status': 'blocked', 'warnings': ['no_validated_nba_combos'], 'recommendations': []}
    assert '模型預期 EV 為負' in schedule.nba_betting_message('2026-11-01', no_bet)
    assert '停損暫停中' not in schedule.nba_betting_message('2026-11-01', no_bet)
    state.write_text(json.dumps({'status': 'paused', 'reason': 'S1 累計 -10.50u ≤ -10u', 'history': []}))
    assert '停損暫停中：S1 累計 -10.50u ≤ -10u' in schedule.nba_betting_message('2026-11-01', no_bet)


def test_postgame_stop_check_pauses_and_notifies_once(state, monkeypatch):
    schedule = _schedule()
    import services.nba_tracking as tracking
    sent = []
    monkeypatch.setattr(tracking, 'export_tracking', lambda root: {'status': 'valid', 'records': records([-1] * 11)})
    monkeypatch.setattr(schedule, 'notify_once', lambda key, message, **kw: sent.append((key, message)))
    log = _Log()
    text = schedule._steady_stop_text('2026-11-02', log)
    assert '⛔ 暫停' in text and len(sent) == 1 and '--resume' in sent[0][1]
    schedule._steady_stop_text('2026-11-03', log)
    assert len(sent) == 1, 'pause notice must not repeat'
    assert log.steps[0][0] == 'steady_stop' and log.steps[0][2]['newly_paused'] is True


def test_postgame_stop_check_never_pauses_on_missing_tracking(state, monkeypatch):
    schedule = _schedule()
    import services.nba_tracking as tracking
    monkeypatch.setattr(tracking, 'export_tracking', lambda root: {'status': 'unavailable', 'records': []})
    assert '冇檢查' in schedule._steady_stop_text('2026-11-02', _Log())
    assert not state.exists()

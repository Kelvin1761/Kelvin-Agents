"""EXP-20261027-21: formal steady (B2) banker, its disclosure and stop-loss."""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

NBA = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(NBA))
sys.path.insert(0, str(NBA / 'nba_wong_choi/scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import nba_sgm_quote as q
import nba_steady_policy as steady
import generate_nba_reports as r
import validate_nba_output as v
from test_nba_sgm_quote_gate import inputs, post_price

META = {'away': {'abbr': 'BOS', 'name': 'Boston'}, 'home': {'abbr': 'LAL', 'name': 'LA'}}


@pytest.fixture
def state(tmp_path, monkeypatch):
    path = tmp_path / 'steady_policy_state.json'
    monkeypatch.setenv('WONGCHOI_NBA_STEADY_STATE', str(path))
    return path


def weak_legs():
    """Legs the model itself prices below the SGM quote: negative EV at @2.5."""
    odds, legs = inputs()
    for leg in legs:
        leg.update(estimated_prob=45, edge=-10.6, ev_pct=-19, hit_l10=70, hit_l10_count='7/10')
    return odds, legs


def report(monkeypatch, price, select):
    odds, legs = weak_legs()
    now = datetime.now(timezone.utc)
    odds['event_start_time'] = (now + timedelta(hours=2)).isoformat()
    calls = []
    monkeypatch.setattr(r, 'build_leg_candidates', lambda *args, **kwargs: [])
    monkeypatch.setattr(r, 'select_combo_1', lambda candidates, **gates: calls.append(gates) or select(legs))
    monkeypatch.setattr(r, 'quote_combo', lambda source, selected: q.quote_combo(source, selected, now=now, post=post_price(price)))
    capture = {}
    text = r.gen_full_report(META, {}, {}, {}, {}, [], now.isoformat(), capture=capture, sportsbet_odds=odds)
    return text, capture, calls


def records(profits, policy=steady.POLICY, prob=0.34):
    return [{'day': f'2026-11-{1 + i // 7:02d}', 'state': 'won' if p > 0 else 'lost', 'profit': p,
             'strategy_profile': policy, 'model_probability': prob} for i, p in enumerate(profits)]


def test_formal_combo_1_is_b2_and_publishes_disclosed_negative_ev(state, monkeypatch):
    text, capture, calls = report(monkeypatch, 2.5, lambda legs: legs)
    assert calls[0] == {'require_leg_ev': False, 'require_combo_ev': False}
    assert len(calls) == 4  # formal + B0/B1/B2 shadow
    assert capture['combos']['1'], 'negative-EV B2 combo with a verified >=2.0 quote must publish'
    assert r.compute_combo_ev(capture['combos']['1'])['combo_ev_pct'] < 0
    assert '組合賠率 @2.5' in text and '正式穩膽政策：banker-steady-b2-v1' in text
    assert '模型預期 EV 為負' in text and '固定 $1 平注' in text
    assert 'Kelly 注碼建議' not in text
    assert capture['strategy_profile'] == steady.POLICY
    assert v.check_fw11_combo_gates(text) == []


def test_price_floor_still_applies_without_ev_gate(state, monkeypatch):
    text, capture, _ = report(monkeypatch, 1.8, lambda legs: legs)
    assert not capture['combos']['1']
    assert capture['quote_attempts']['1']['rejected'] == 'actual_price_below_floor_or_expired'


def test_paused_policy_publishes_no_formal_combo(state, monkeypatch):
    state.write_text(json.dumps({'status': 'paused', 'reason': 'S1 累計 -10.20u ≤ -10u', 'history': []}))
    text, capture, calls = report(monkeypatch, 2.5, lambda legs: legs)
    assert not capture['combos']['1']
    assert '停損暫停中（S1 累計 -10.20u ≤ -10u）' in text
    # Formal selection is skipped; the three shadow arms still run so the
    # paused line stays measurable.
    assert len(calls) == 3


def test_firewall_relaxes_ev_only_for_disclosed_steady_reports():
    legacy = '**Combo EV%**: -12.0% ❌ NEGATIVE\n'
    assert any('非正 Combo EV' in issue for issue in v.check_fw11_combo_gates(legacy))
    marker = '> 📌 正式穩膽政策：banker-steady-b2-v1 —\n'
    assert any('冇顯示' in issue for issue in v.check_fw11_combo_gates(marker + legacy))
    assert v.check_fw11_combo_gates(marker + legacy + '模型預期 EV 為負\n') == []
    kelly = marker + legacy + '模型預期 EV 為負\n**🎯 Kelly 注碼建議**: 0.0% bankroll\n'
    assert any('Kelly' in issue for issue in v.check_fw11_combo_gates(kelly))
    floor = marker + '### 🛡️ 組合 1: Banker SGM — 組合賠率 @1.8\n模型預期 EV 為負\n'
    assert any('門檻' in issue for issue in v.check_fw11_combo_gates(floor))


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


def test_fw13_quote_check_accepts_disclosed_negative_ev_only_under_steady(state, monkeypatch, tmp_path):
    # Live 2026-10-28 dry run: FW-13's own positive-EV clause blocked every steady combo.
    odds, legs = weak_legs()
    now = datetime.now(timezone.utc)
    odds['event_start_time'] = (now + timedelta(hours=2)).isoformat()
    quoted = q.quote_combo(odds, legs, now=now, post=post_price(2.5))
    text = r.gen_combo_section('組合 1: test', '', '', quoted, steady=True)
    steady_text = f'> 📌 正式穩膽政策：{steady.POLICY} — {steady.DISCLAIMER}\n' + text
    report = tmp_path / 'Game_BOS_LAL_Full_Analysis.md'
    source = tmp_path / 'Sportsbet_Odds_BOS_LAL.json'
    source.write_text(json.dumps(odds))
    for body, expect_block in ((steady_text, False), (text, True)):
        report.write_text(body)
        Path(str(report) + '.market_legs.json').write_text(json.dumps(
            r.build_market_eval_sidecar(body, odds, {}, [], {'combos': {'1': quoted}}, 'hybrid')))
        issues = v.check_fw13_sgm_quotes(body, str(report), str(source), now=now)
        assert bool(issues) is expect_block, issues

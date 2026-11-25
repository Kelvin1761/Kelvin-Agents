"""Incident regressions: 2026-10-16 Gatton/Penola false success."""
import json
import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import au_daily_schedule as S
import au_healthcheck as H
from odds_quality import dashboard_odds_issues, has_snapshot, snapshot_day


def test_empty_placeholder_and_nonfinite_prices_do_not_prove_capture():
    key = "2026-10-16T10:00:00|morning-refresh"
    for prices in ({}, {"1": ["W", "P"]}, {"1": ["NaN", "1.4"]},
                   {"1": ["3", "Infinity"]}, {"1": [True, "1.4"]},
                   {"1": ["3", "-"]}, [], None):
        assert not has_snapshot({key: prices}, day="2026-10-16")
    assert has_snapshot({key: {"1": ["3", "1.4"]}}, day="2026-10-16")


def test_tag_cannot_override_date_or_malformed_timestamp():
    for key in ("2026-10-15T10:00:00|morning-refresh", "bad|morning-refresh"):
        assert not H.is_current_day_odds_snapshot(key, "2026-10-16")
    assert snapshot_day("2026-10-15T14:00:00+00:00|analysis") == "2026-10-16"


def test_missing_prices_are_visible_before_morning_deadline(tmp_path):
    folder = tmp_path / "2026-10-16 Gatton Race 1-1"
    folder.mkdir()
    (folder / "odds_history.json").write_text('{"1":{"2026-10-16T00:00:00|analysis":{}}}')
    issues = H.local_quality_issues("2026-10-16", root=tmp_path, require_morning=False)
    assert any("win/place odds" in issue for issue in issues)
    assert not any("11:00" in issue for issue in issues)


def test_refresh_call_without_prices_is_still_failed(tmp_path):
    folder = tmp_path / "2026-10-16 Penola Race 1-1"
    folder.mkdir()
    (folder / "10-16 Race 1 Racecard.md").write_text("card")
    runlog = MagicMock()
    with patch.object(S, "api_next_events", return_value=[]), patch.object(
        S, "events_by_day", return_value={"2026-10-16": {"Penola": {}}}
    ), patch.object(S, "refresh_one_meeting", return_value=False):
        assert not S.refresh_fill_today_odds(runlog, [folder], date(2026, 10, 16))


def test_missing_odds_change_success_exit_and_later_recovery_clears_it():
    runlog = MagicMock()
    runlog.data = {"meetings_processed": [], "steps": [
        {"step": "odds-snapshot", "meeting": "Gatton", "status": "missing"}]}
    with patch.object(S, "close_browser"):
        assert S.finish_run(runlog, True, False) == S.EXIT_TEMPORARY
        runlog.finish.assert_called_with("partial")
        runlog.data["steps"].append(
            {"step": "odds-snapshot", "meeting": "Gatton", "status": "ok"})
        assert S.finish_run(runlog, True, False) == S.EXIT_OK


def test_dashboard_checks_prices_per_race_and_runner():
    payload = {"meetings": [{"date": "2026-10-16", "venue": "Gatton", "region": "au"}],
               "races": {"2026-10-16|Gatton": {"races_by_analyst": {"Kelvin": [
                   {"race_number": 1, "horses": [{"market_win_odds": 3, "market_place_odds": 1.5}, {}]},
                   {"race_number": 2, "horses": [{}]}]}}}}
    issues = dashboard_odds_issues(payload, "2026-10-16")
    assert len(issues) == 2 and "1/2" in issues[0] and "0/1" in issues[1]
    assert dashboard_odds_issues(payload, "2026-10-17") == []


def test_live_odds_failure_is_not_reported_as_healthy():
    with patch.object(H, "read_live_dashboard", return_value=None):
        assert H.live_odds_issues("2026-10-16")


def _payload(meetings):
    """meetings = {venue: [[(win, place), ...] per race]}"""
    out = {"meetings": [], "races": {}}
    for venue, races in meetings.items():
        out["meetings"].append({"region": "AU", "date": "2026-11-25", "venue": venue})
        out["races"][f"2026-11-25|{venue}"] = {"races_by_analyst": {"auto": [
            {"race_number": i + 1, "horses": [{"market_win_odds": w, "market_place_odds": p} for w, p in race]}
            for i, race in enumerate(races)]}}
    return out


def test_unopened_meeting_is_not_a_real_issue():
    """2026-11-25：晚更睇下一日、細郊區場冇定額盤 —— 成個場次 0 價、其他場次正常 = 未開盤，唔令 run partial。"""
    from odds_quality import split_unopened_markets
    p = _payload({"Wyong": [[(3.0, 1.5), (5.0, 2.0)]], "Geelong": [[(None, None), (None, None)], [(None, None)]]})
    real, unopened = split_unopened_markets(p)
    assert unopened == ["2026-11-25|Geelong"] and real == []


def test_partly_priced_race_and_all_unpriced_stay_real():
    from odds_quality import split_unopened_markets
    partial = _payload({"Wyong": [[(3.0, 1.5), (None, None)]], "Geelong": [[(None, None)]]})
    real, unopened = split_unopened_markets(partial)
    assert unopened == [] and len(real) == 2            # 冇一個場次全部有價 → 唔可以證明抓價正常
    broken = _payload({"Wyong": [[(None, None)]], "Geelong": [[(None, None)]]})
    real, unopened = split_unopened_markets(broken)
    assert unopened == [] and len(real) == 2            # 全部冇價 = 抓價壞咗，照報

"""Metro meetings are analysed first, and a meeting that cannot be finished is
reported the moment we know — not in the end-of-run summary.

2026-11-01 Kelvin: 都會係重點，要排頭；做唔成一個馬場就即刻話我知，唔好
skip 咗等晒全部完先講。
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import au_daily_schedule as S  # noqa: E402

DAY = "2026-11-07"


def _plan(venue):
    return {"slug": venue.lower().replace(" ", "_"), "venue": venue,
            "meetingId": venue, "races": ["1", "2"], "going": ""}


def test_metro_then_provincial_then_country_then_first_jump():
    planned = [_plan(v) for v in ("Albury", "Kembla Grange", "Moe",
                                  "Randwick-Kensington", "Flemington", "Geelong")]
    starts = {"Albury": 100, "Moe": 50, "Kembla Grange": 300, "Geelong": 200,
              "Randwick-Kensington": 400, "Flemington": 350}
    order = [p["venue"] for p in S.priority_order(planned, starts)]
    assert order == ["Flemington", "Randwick-Kensington",   # 都會
                     "Geelong", "Kembla Grange",             # 省級
                     "Moe", "Albury"]                        # 鄉鎮


def test_unknown_venue_and_missing_start_go_last_within_their_tier():
    planned = [_plan("Nowhere Park"), _plan("Caulfield"), _plan("Sandown")]
    order = [p["venue"] for p in S.priority_order(planned, {"Sandown": 10})]
    assert order == ["Sandown", "Caulfield", "Nowhere Park"]


def _run(monkeypatch, tmp_path, outcomes, *, rounds=2):
    """outcomes: venue -> list of results per call ('ok' | 'temp' | 'boom')."""
    venues = list(outcomes)
    monkeypatch.setattr(S, "api_next_events", lambda runlog: [])
    monkeypatch.setattr(S, "events_by_day", lambda events: {
        DAY: {v: {"going": "", "status_codes": [], "races_seen": []} for v in venues}})
    monkeypatch.setattr(S, "api_day_meetings",
                        lambda runlog, day, starts=None, race_starts=None: venues)
    monkeypatch.setattr(S, "fetch_date_index", lambda runlog, day: {
        v.lower().replace(" ", "_"): {"meetingId": v, "races": ["1", "2"]} for v in venues})
    monkeypatch.setattr(S, "find_meeting_dir", lambda day, venue: None)
    monkeypatch.setattr(S, "record_race_start_times", lambda *a, **k: False)
    monkeypatch.setattr(S.time, "sleep", lambda s: None)
    monkeypatch.setattr(S, "reset_outbound_gate", lambda runlog: None)
    calls, alerts = [], []
    monkeypatch.setattr(S, "alert_now", lambda runlog, text: alerts.append(text))

    def analyse(runlog, day, plan):
        venue = plan["venue"]
        calls.append(venue)
        result = outcomes[venue].pop(0) if len(outcomes[venue]) > 1 else outcomes[venue][0]
        if result == "temp":
            raise S.TemporaryFailure("sportsbetform 403")
        if result == "boom":
            raise RuntimeError("parser exploded")
        return tmp_path / venue, True, True
    monkeypatch.setattr(S, "analyse_one_meeting", analyse)
    runlog = S.RunLog("evening", date(2026, 11, 6), tmp_path / "run.json", notify=False)
    S.step_analyse_next_day(runlog, date(2026, 11, 6), rounds=rounds,
                            round_gap=600, target_day=DAY)
    return calls, alerts, runlog


def test_analysis_runs_metro_first(monkeypatch, tmp_path):
    calls, alerts, runlog = _run(monkeypatch, tmp_path, {
        "Albury": ["ok"], "Gosford": ["ok"], "Rosehill Gardens": ["ok"]})
    assert calls == ["Rosehill Gardens", "Gosford", "Albury"]
    assert alerts == []
    order = [s for s in runlog.data["steps"] if s.get("status") == "order"]
    assert order and order[0]["meetings"][0] == "Rosehill Gardens（都會）"


def test_a_failed_meeting_is_reported_before_the_next_one_runs(monkeypatch, tmp_path):
    calls, alerts, _ = _run(monkeypatch, tmp_path, {
        "Randwick": ["boom"], "Albury": ["ok"]})
    assert calls == ["Randwick", "Albury"]
    assert len(alerts) == 1 and "Randwick（都會）" in alerts[0] and "parser exploded" in alerts[0]


def test_delay_is_reported_once_then_recovery(monkeypatch, tmp_path):
    calls, alerts, _ = _run(monkeypatch, tmp_path, {
        "Flemington": ["temp", "ok"], "Moe": ["ok"]}, rounds=3)
    assert calls == ["Flemington", "Moe", "Flemington"]
    assert alerts[0].startswith("⏳") and "Flemington（都會）" in alerts[0]
    assert "10 分鐘後再試" in alerts[0]
    assert alerts[1] == f"✅ {DAY}：補返 Flemington"
    assert len(alerts) == 2


def test_giving_up_names_every_meeting_left(monkeypatch, tmp_path):
    calls, alerts, _ = _run(monkeypatch, tmp_path, {
        "Caulfield": ["temp"], "Sale": ["temp"]}, rounds=2)
    assert alerts[0].startswith("⏳")                        # after round 1
    final = alerts[-1]
    assert final.startswith(f"❌ {DAY}：2 個場次今次做唔完")
    assert "Caulfield（都會）：sportsbetform 403" in final and "Sale（省級）" in final
    assert len(alerts) == 2


def test_alert_now_records_and_respects_no_notify(monkeypatch, tmp_path):
    pushed = []
    import au_notify
    monkeypatch.setattr(au_notify, "push", lambda text, **k: pushed.append(text) or ["ok"])
    quiet = S.RunLog("evening", date(2026, 11, 6), tmp_path / "q.json", notify=False)
    S.alert_now(quiet, "❌ x")
    assert pushed == [] and quiet.data["alerts"][0]["text"] == "❌ x"
    loud = S.RunLog("evening", date(2026, 11, 6), tmp_path / "l.json", notify=True)
    S.alert_now(loud, "❌ y")
    assert pushed == [f"{S.ALERT_TITLE}\n\n❌ y"]


def test_a_push_failure_never_fails_the_run(monkeypatch, tmp_path):
    import au_notify

    def explode(text, **k):
        raise OSError("telegram down")
    monkeypatch.setattr(au_notify, "push", explode)
    runlog = S.RunLog("evening", date(2026, 11, 6), tmp_path / "r.json", notify=True)
    S.alert_now(runlog, "❌ z")       # must not raise

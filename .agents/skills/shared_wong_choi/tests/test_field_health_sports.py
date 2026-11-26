"""NBA／網球欄位健康：攤平、統計、警報（死咗／變常數／成批少咗）、冷卻、排程接駁。"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1]))

import field_health_sports as F  # noqa: E402

REPO = HERE.parents[4]


def test_flatten_keeps_both_ids_and_skips_lists():
    d = {"a": 1, "profiles": {"serve_return": {"20833": {"hold": 0.6}, "87": {"hold": 0.5}}}, "xs": [1, 2]}
    assert F.flatten(d) == {"a": 1, "profiles.serve_return.<id1>.hold": 0.6, "profiles.serve_return.<id2>.hold": 0.5}


def test_profile_counts():
    rows = [{"x": 1.0, "y": "a", "captured_at": "t"}, {"x": None, "y": "a"}, {"x": 3.0}]
    p = {r["field"]: r for r in F.profile(rows)}
    assert "captured_at" not in p
    assert p["x"]["n"] == 3 and p["x"]["fill_rate"] == round(2 / 3, 4) and p["x"]["distinct"] == 2 and p["x"]["mean"] == 2.0
    assert p["y"]["n"] == 2 and p["y"]["distinct"] == 1 and p["y"]["mean"] is None


def _hist(field, days, **kw):
    d0 = date(2026, 11, 1)
    return [dict({"date": (d0 + timedelta(days=i)).isoformat(), "field": field, "n": 100, "fill_rate": 1.0,
                  "distinct": 20, "mean": 1.0}, **kw) for i in range(days)]


def test_alerts():
    day = "2026-11-15"
    h = _hist("dead_one", 14) + [{"date": day, "field": "dead_one", "n": 100, "fill_rate": 0.1, "distinct": 3, "mean": 1}]
    h += _hist("const_num", 14) + [{"date": day, "field": "const_num", "n": 80, "fill_rate": 1, "distinct": 1, "mean": 65.0}]
    h += _hist("const_cat", 14) + [{"date": day, "field": "const_cat", "n": 80, "fill_rate": 1, "distinct": 1, "mean": None}]
    h += _hist("gone", 14)
    h += _hist("always_empty", 14, fill_rate=0.0) + [{"date": day, "field": "always_empty", "n": 100, "fill_rate": 0, "distinct": 0, "mean": None}]
    h += _hist("few_days", 3) + [{"date": day, "field": "few_days", "n": 100, "fill_rate": 0.0, "distinct": 0, "mean": None}]
    got = {(a["field"], a["kind"]) for a in F.alerts("nba", day, h)}
    assert got == {("dead_one", "dead"), ("const_num", "constant"), ("gone", "shrunk")}


def test_cooldown_marks_only_after_send(tmp_path, monkeypatch):
    monkeypatch.setenv("WONGCHOI_CONTROL_STATE_ROOT", str(tmp_path))
    a = [{"field": "x", "kind": "dead", "detail": ""}]
    assert F.due_alerts("nba", "2026-11-10", a) == a
    assert F.due_alerts("nba", "2026-11-11", a) == a          # 未發成功＝未冷卻
    F.mark_sent("nba", "2026-11-10", a)
    assert F.due_alerts("nba", "2026-11-15", a) == []
    assert F.due_alerts("tennis", "2026-11-15", a) == a       # 每個 domain 分開
    assert F.due_alerts("nba", "2026-11-17", a) == a
    assert "死咗" in F.telegram_text("nba", "2026-11-17", a)


def test_write_day_replaces_same_date(tmp_path, monkeypatch):
    monkeypatch.setenv("WONGCHOI_CONTROL_STATE_ROOT", str(tmp_path))
    F.write_day("tennis", "2026-11-25", [{"field": "a", "n": 1, "fill_rate": 1, "distinct": 1, "mean": None, "sd": None}])
    F.write_day("tennis", "2026-11-25", [{"field": "b", "n": 1, "fill_rate": 1, "distinct": 1, "mean": None, "sd": None}])
    assert [r["field"] for r in F.load("tennis")] == ["b"]


def test_scheduler_wiring():
    nba = (REPO / ".agents/skills/nba/nba_daily_auto/nba_daily_schedule.py").read_text(encoding="utf-8")
    assert 'FIELD_HEALTH_SPORTS' in nba and '"--domain", "nba"' in nba
    ten = (REPO / "tennis-wong-choi/scripts/tennis_daily_schedule.py").read_text(encoding="utf-8")
    assert 'FIELD_HEALTH_SPORTS' in ten


def test_empty_day_alerts_when_usually_full():
    day = "2026-11-15"
    h = _hist("x", 14)
    got = F.alerts("nba", day, h)
    assert [a["kind"] for a in got] == ["empty"]
    assert F.alerts("nba", day, _hist("x", 6)) == [] or all(a["kind"] != "empty" for a in F.alerts("nba", day, _hist("x", 6)))

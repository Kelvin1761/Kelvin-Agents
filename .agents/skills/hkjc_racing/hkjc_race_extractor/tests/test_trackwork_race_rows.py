"""晨操表入面嘅「出賽」行唔係操練（EXP-20261029-01）.

HKJC 晨操頁會將比賽列埋落去（`出賽`, `1650M (霍宏聲) (5/12)`）。以前：
- 騎師喺比賽策騎過 = 「賽日騎師有參與操練」（1,591 個旗標入面 562 個淨係靠出賽行）；
- 賽後先抽嘅檔案包埋今仗本身，連名次；回放同 live 睇到唔同嘢。
- 「馬匹跑步機」行 details 寫「快操」就當咗快操。
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import extract_trackwork as xt  # noqa: E402


def _row(date, kind, details, type_raw=None):
    return {"date": date, "type": kind, "type_raw": type_raw or {"gallop": "快操", "other": "出賽"}.get(kind, kind),
            "location": "沙田 全天候", "details": details, "gear": "", "times": [], "sectionals": [],
            "final_time": None, "rider": xt.detect_rider(details), "rider_role": ""}


def test_riding_a_race_is_not_riding_trackwork():
    entries = [
        _row("2026-10-09", "gallop", "30.4 27.1 (57.5) (助手)"),
        _row("2026-10-21", "other", "1650M (霍宏聲) (5/12)"),
    ]
    digest = xt.make_digest({}, entries, 21, "霍宏聲")
    assert "賽日騎師有參與操練" not in digest["stability_positive_flags"]
    assert digest["workout_load_21d"]["active_days"] == 1
    assert xt.summarize_trackwork({}, entries, digest)["race_jockey_involved"] is False


def test_a_trial_ridden_by_the_race_jockey_still_counts():
    entries = [_row("2026-10-16", "trial", "第1組 (奧爾民) 1200M 三甲之星 25.1 22.9 22.3 (1.10.36)", "試閘")]
    digest = xt.make_digest({}, entries, 21, "奧爾民")
    assert "賽日騎師有參與操練" in digest["stability_positive_flags"]


def test_rows_on_race_day_are_dropped():
    html = ("<table><tr><td>28/10/2026</td><td>出賽</td><td>沙田 草地</td><td>1200M (潘頓) (1/12)</td><td></td></tr>"
            "<tr><td>28/10/2026</td><td>踱步</td><td>沙田 內圈</td><td>快踱一圈 (助手)</td><td></td></tr>"
            "<tr><td>27/10/2026</td><td>踱步</td><td>沙田 內圈</td><td>快踱一圈 (助手)</td><td></td></tr></table>")
    rows = xt.parse_trackwork_rows(html, {"trainer": ""}, dt.date(2026, 10, 28), 21)
    assert [r["date"] for r in rows] == ["2026-10-27"]


def test_treadmill_rows_are_not_gallops():
    assert xt.normalize_work_type("馬匹跑步機", "快操 (助手)") == "treadmill"
    assert xt.normalize_work_type("快操", "30.4 27.1 (57.5) (助手)") == "gallop"

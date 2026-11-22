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


def test_race_jockey_work_counts_gallops_trials_and_strips_claim():
    """賽日騎師親自快操／試閘（Kelvin 2026-11-19）：排位表「袁幸堯 (-7)」都要配到晨操「袁幸堯」；出賽行唔計。"""
    rows = [
        {**_row("2026-11-01", "gallop", "沙田 全天候 快操 (袁幸堯)"), "rider": "袁幸堯"},
        {**_row("2026-11-05", "trial", "1050M 試閘 (袁幸堯)", type_raw="試閘"), "rider": "袁幸堯"},
        {**_row("2026-11-07", "gallop", "快操 (助手)"), "rider": "助手"},
        {**_row("2026-11-08", "other", "1200M (袁幸堯) (2/12)"), "rider": "袁幸堯"},
    ]
    w = xt.race_jockey_work(rows, "袁幸堯 (-7)")
    assert w == {"any": 2, "gallops": 1, "trials": 1}
    assert xt.race_jockey_work(rows, "潘頓") == {"any": 0, "gallops": 0, "trials": 0}
    assert xt.race_jockey_work(rows, "") == {"any": 0, "gallops": 0, "trials": 0}


def test_trainer_work_counts_only_the_trainer_himself():
    """練馬師親自快操／試閘（Kelvin 2026-11-21）：只計騎手角色「練馬師」；副練馬師、助手、出賽行唔計。"""
    rows = [
        {**_row("2026-11-01", "gallop", "29.0 25.3 (54.3) (練馬師)"), "rider": "練馬師", "rider_role": "練馬師"},
        {**_row("2026-11-03", "gallop", "30.1 26.2 (56.3) (副練馬師)"), "rider": "副練馬師", "rider_role": "副練馬師"},
        {**_row("2026-11-05", "trotting", "快踱一圈 (練馬師)"), "rider": "練馬師", "rider_role": "練馬師"},
        {**_row("2026-11-07", "gallop", "快操 (助手)"), "rider": "助手", "rider_role": "助手"},
        {**_row("2026-11-08", "other", "1200M (練馬師) (3/12)", type_raw="出賽"), "rider": "練馬師", "rider_role": "練馬師"},
    ]
    assert xt.trainer_work(rows) == {"gallops": 1, "trials": 0}
    assert xt.trainer_work([]) == {"gallops": 0, "trials": 0}
    assert xt.classify_rider_role("練馬師", "29.0 25.3 (54.3) (練馬師)", "韋達") == "練馬師"


def test_page_trainer_reads_the_name_cell_not_the_details_link():
    """冇排位表時嘅後備馬匹列表：練馬師喺「馬名 練馬師 近績」格，唔係最後一格「詳情」（Kelvin 2026-11-21）。"""
    cells = ["1", "滿利時 游達榮 1/5", "06/11: 第9組 1200 從化", "20/11: 沙田 全天候 33.9 (助手)", "", "詳情"]
    assert xt.page_trainer(cells, "滿利時") == "游達榮"
    assert xt.page_trainer(["2", "哥得寶 賀賢 3/4", "", "詳情"], "哥得寶") == "賀賢"
    assert xt.page_trainer(["3", "新馬", "", "詳情"], "新馬") == ""
    assert xt.page_trainer(["4", "別匹 韋達 1/2", "詳情"], "唔對") == ""
    html = ('<table><tr><td>1</td><td><a href="/zh-hk/local/information/horse?horseid=HK_2024_K205">大輝煌</a> 羅富全 9/11</td>'
            '<td></td><td></td><td><a href="#">詳情</a></td></tr></table>')
    assert [(h["horse_name"], h["trainer"]) for h in xt.parse_horse_list(html)] == [("大輝煌", "羅富全")]

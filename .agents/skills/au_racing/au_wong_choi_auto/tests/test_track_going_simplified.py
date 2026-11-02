"""EXP-20261103-02：場地模組簡化 —— 行為同簡化前逐匹一樣（截斷紀錄、好地唔入分、上限）。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import pytest  # noqa: E402

from au_racing_engine import track_going as tg  # noqa: E402
from au_racing_engine.scoring import wet_form_feature  # noqa: E402


def test_truncated_record_is_flagged():
    assert tg.record("7:") == {**tg.record(""), "starts": 7, "complete": False}
    assert tg.record("N/A")["starts"] == 0
    assert tg.record("7:1-2-0")["places"] == 3 and tg.record("7:1-2-0")["complete"]


def test_truncated_records_keep_legacy_behaviour():
    # 場地分：截斷 = 冇紀錄
    assert tg.track_score(tg.records("4:", "12: | 軟地: 7: | 重地: 3:"), "Soft 6")[0] == 60.0
    # 濕地 overlay：截斷 = 「7 戰 0 上名」（改正過唔到 §7，見 EXP-20261103-02）
    assert wet_form_feature("Soft 6", "12: | 軟地: 7: | 重地: 3:") == pytest.approx(-3.7953)


def test_good_going_never_scores():
    recs = tg.records("", "10:5-3-1 | 軟地: 0:0-0-0 | 重地: 0:0-0-0")
    assert tg.track_score(recs, "Good 4")[0] == pytest.approx(60.0)


def test_wet_bucket_scores_today_only():
    recs = tg.records("", "0:0-0-0 | 軟地: 4:1-1-0 | 重地: 3:0-0-0")
    score, _same, parts = tg.track_score(recs, "Soft 6")
    assert [d for d, _ in parts] == [pytest.approx(1.6), tg.WEIGHTS["wet_win"]]
    assert tg.track_score(recs, "Heavy 8")[2] == [(tg.WEIGHTS["wet_nil_many"], "重地 3 戰未有前列")]


def test_same_track_cap():
    recs = tg.records("6:3-2-1", "")
    assert tg.track_score(recs, "Good 4")[0] == pytest.approx(60.0 + tg.WEIGHTS["same_cap"])


def test_overlay_and_detail_agree():
    line = "5:1-1-0 | 軟地: 6:2-2-1 | 重地: 3:2-0-0"
    for going in ("Soft 5", "Heavy 9"):
        assert tg.wet_overlay_detail(going, line)["value"] == wet_form_feature(going, line)
    assert tg.wet_overlay_detail("Good 4", line) is None

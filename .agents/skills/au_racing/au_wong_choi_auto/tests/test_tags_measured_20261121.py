"""EXP-20261121-34：由 HKJC 搬嘅 AU 標籤 —— 語氣跟量度、全部未入分、唔郁分數。"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from au_racing_engine import tags  # noqa: E402

TONES = {"quick_backup": "good", "old_horse": "bad", "first_up_nil": "bad", "second_up_nil": "bad",
         "first_up_good": "note", "second_up_good": "note", "top_weight": "note"}


def eng(*, stage="first_up", gap=120, first="6:2-2-0", second="6:0-2-0", age=None, flags=()):
    e = mock.Mock()
    e._preparation_cycle.return_value = {"stage": stage, "days_since_last_run": gap}
    from au_racing_engine.scoring import parse_record_line
    e._stage_stats.return_value = {"first_up": parse_record_line(first), "second_up": parse_record_line(second)}
    e.horse_data = {"age": age, "weight": 60.0}
    e.risk_flags = list(flags)
    return e


def keys(out):
    return {t["key"]: t for t in out}


def test_tone_matches_measurement_and_never_scored():
    for key, tone in TONES.items():
        ex, _n = tags.MEASURED[key]
        assert (tone == "good") == (ex > 0 and key == "quick_backup")
    got = keys(tags._cycle_tags(eng(first="6:2-2-0")))                 # 4/6 上名 → 好手
    assert got["first_up_good"]["tone"] == "note" and "高估" in got["first_up_good"]["why"]
    got = keys(tags._cycle_tags(eng(first="4:0-0-0")))
    assert got["first_up_nil"]["tone"] == "bad" and got["first_up_nil"]["label"] == "休後首仗未上過名（4戰）"
    got = keys(tags._cycle_tags(eng(stage="second_up", gap=6, second="3:0-0-0")))
    assert got["quick_backup"]["label"] == "相隔 6 日再出" and got["quick_backup"]["tone"] == "good"
    assert got["second_up_nil"]["tone"] == "bad"
    got = keys(tags._field_tags(eng(age=9, flags=("top_weight",))))
    assert got["old_horse"]["label"] == "9 歲老馬" and got["top_weight"]["label"] == "讓賽頂磅（60kg）"
    for out in (tags._cycle_tags(eng(first="4:0-0-0", gap=5)), tags._field_tags(eng(age=9, flags=("top_weight",)))):
        assert all(t["scored"] is False and "未入分" in t["why"] for t in out)


def test_thresholds():
    assert not tags._cycle_tags(eng(first="2:0-0-0"))                   # < 3 戰唔出
    assert not keys(tags._cycle_tags(eng(first="6:1-1-0")))             # 2/6 上名：唔係好手亦唔係 0
    assert not tags._cycle_tags(eng(stage="established_prep", gap=8))   # 唔係首仗／第二仗、> 7 日
    assert not tags._field_tags(eng(age=7))

"""賽道幾何生成器：horise 句式解析、來源次序、分歧記錄（唔使上網）。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(ROOT))

import fetch_au_track_geometry as F  # noqa: E402


def parse(text):
    return F._first(F.HORISE_CIRC, text), F._first(F.HORISE_STRAIGHT, text)


def test_horise_phrasings():
    assert parse("with a circumference of around 1,600m and a home straight measuring close to 300m.") == (1600, 300)
    assert parse("The circuit measures 1,735m in circumference and is known for its demanding 320m uphill home straight") == (1735, 320)
    assert parse("circumference of 1,900m and fairly tight turns. slightly uphill 475m home straight") == (1900, 475)


def test_horise_does_not_read_part_of_a_bigger_number_or_a_marker():
    # 2026-11-13：「1,600m and a home straight」曾經被讀成直路 600m；「600m into the home straight」唔係直路長度。
    assert F._first(F.HORISE_STRAIGHT, "a circumference of 1,600m and a home straight") is None
    assert F._first(F.HORISE_STRAIGHT, "they sprint from the 600m into the home straight") is None


def test_source_order_racinglife_then_horise_then_justhorseracing():
    rl = {"circumference_m": 2000, "straight_m": 400, "direction": "clockwise"}
    hz = {"circumference_m": 1840, "straight_m": 300, "direction": ""}
    jhr = {"circumference_m": 2030, "straight_m": 220, "direction": "anti-clockwise", "state": "SA", "note": "n"}
    assert F.merge("X", rl, jhr, hz)["straight_m"] == 400
    row = F.merge("Gawler", {}, jhr, hz)
    assert (row["circumference_m"], row["straight_m"]) == (1840, 300)
    assert row["sources"][0] == "horise"
    assert row["direction"] == "anticlockwise"  # horise 冇方向就用 justhorseracing 嘅
    assert row["conflict"] == {"horise": [1840, 300], "justhorseracing": [2030, 220]}
    assert F.merge("Y", {}, jhr, {})["straight_m"] == 220


def test_agreeing_sources_are_not_a_conflict():
    row = F.merge("Kilmore", {}, {"circumference_m": 1735, "straight_m": 320, "direction": "anticlockwise"},
                  {"circumference_m": 1735, "straight_m": 320, "direction": ""})
    assert row["conflict"] is None

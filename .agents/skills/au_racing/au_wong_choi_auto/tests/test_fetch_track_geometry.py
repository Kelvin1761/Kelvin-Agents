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


def _sb_page(venue, straight, circ):
    return (f"<div><h3>Track Details</h3><p>Conditions: Good 4</p><p>Track: {venue}, {venue}, Australia</p>"
            f"<p>Rail Position: True</p><p>Straight: <b>{straight}</b> metres</p><p>Circumference: {circ}</p></div>")


def test_sportsbet_cache_index_needs_consistent_plausible_pages(tmp_path, monkeypatch):
    for i in range(4):
        (tmp_path / f"w{i}.html").write_text(_sb_page("Warwick", 340, "1,750"))
    for i in range(4):  # Gunnedah 實測 200/200：周長唔合理 → 唔收
        (tmp_path / f"g{i}.html").write_text(_sb_page("Gunnedah", 200, 200))
    (tmp_path / "y0.html").write_text(_sb_page("York", 300, 1550))  # 得一頁 → 唔夠證據
    for i, val in enumerate([(300, 1700), (300, 1700), (350, 1800), (350, 1800)]):  # 唔一致 → 唔收
        (tmp_path / f"r{i}.html").write_text(_sb_page("Griffith", *val))
    monkeypatch.setattr(F, "_SB_INDEX", None)
    index = F.sportsbet_cache_index(tmp_path)
    assert index["warwick"]["straight_m"] == 340 and index["warwick"]["circumference_m"] == 1750
    assert "gunnedah" not in index and "york" not in index and "griffith" not in index


def test_sportsbet_only_fills_gaps(monkeypatch):
    monkeypatch.setattr(F, "_SB_INDEX", {"gawler": {"straight_m": 220, "circumference_m": 2000, "pages": 29, "share": 1.0},
                                         "warwick": {"straight_m": 340, "circumference_m": 1750, "pages": 22, "share": 1.0}})
    row = F.merge("Gawler", {}, {}, {"circumference_m": 1840, "straight_m": 300, "direction": ""})
    assert (row["circumference_m"], row["straight_m"]) == (1840, 300) and "sportsbet" not in row["sources"]
    row = F.merge("Warwick", {}, {}, {})
    assert (row["circumference_m"], row["straight_m"], row["sources"]) == (1750, 340, ["sportsbet"])

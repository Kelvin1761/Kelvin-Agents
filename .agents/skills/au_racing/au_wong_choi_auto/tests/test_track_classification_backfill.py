"""場地級別：RA `Meeting Type` 只補空格、副跑道承繼主場、改名場地用 alias。"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import backfill_track_classification_from_ra as B  # noqa: E402
from au_racing_engine.engine_core import _track_classification, _track_geometry_key  # noqa: E402


def test_sponsor_prefixes_and_aliases():
    assert B.ra_venue_name("bet365 Park Kilmore") == "Kilmore"
    assert B.ra_venue_name("Sportsbet-Ballarat Synthetic") == "Ballarat Synthetic"
    assert B.ra_venue_name("Thomas Farms RC Murray Bridge") == "Murray Bridge"
    assert B.ra_venue_name("Devonport Tapeta Synthetic") == "Devonport"
    assert _track_geometry_key("Illawarra Grange") == "kembla-grange"
    assert _track_geometry_key("Randwick-Kensington") == "kensington"


def test_majority_refuses_ties():
    assert B.majority(Counter({"Provincial": 4, "Metropolitan": 2})) == "Provincial"
    assert B.majority(Counter({"Metropolitan": 1, "Country": 1})) == ""


def test_backfill_only_fills_blanks_and_respects_parent():
    payload = {"venues": {
        "ballarat": {"classification": "Provincial"},
        "ballarat-synthetic": {"classification": ""},
        "flemington": {"classification": "Metropolitan"},
        "mildura": {"classification": ""},
    }}
    types = {
        "ballarat-synthetic": Counter({"Country": 5}),   # RA 用語唔同 → 唔好覆蓋主場承繼
        "flemington": Counter({"Country": 9}),            # 已有值 → 唔郁
        "mildura": Counter({"Country": 3}),
        "kyneton": Counter({"Country": 1}),               # 清單冇 → 新增
    }
    changed = {key for key, _, _ in B.backfill(payload, types)}
    assert changed == {"mildura", "kyneton"}
    venues = payload["venues"]
    assert venues["ballarat-synthetic"]["classification"] == ""
    assert venues["flemington"]["classification"] == "Metropolitan"
    assert venues["kyneton"]["circumference_m"] == 0  # 冇幾何 → 引擎幾何查詢照舊當冇
    assert "racingaustralia" in venues["mildura"]["classification_source"]


def test_engine_reads_classification_without_geometry_and_inherits():
    assert _track_classification("Caulfield Heath") == "Metropolitan"
    assert _track_classification("Ballarat Synthetic") == _track_classification("Ballarat")
    assert _track_classification("Kilmore") == "Country"

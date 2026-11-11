"""live_record_exclusions：live 預測紀錄無效嘅場次唔入表現統計。

2026-10-07 跑馬地最後一個快照係用回放模式評（悉尼日期 21:00 HKT 過咗日），
shadow ledger 45 行、場次 Logic／HKJC_Auto_Scoring.csv 都係嗰個壞版。
覆盤用嘅係 08:17 HKT 嗰個正確快照，所以覆盤唔使剔。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
SHARED = ROOT / ".agents" / "skills" / "shared_racing"
sys.path.insert(0, str(SHARED))

import live_record_exclusions as lre  # noqa: E402

BAD = "2026-10-07_HappyValley"


def test_real_registry_lists_the_10_07_meeting_with_its_evidence():
    entry = lre.exclusion("hkjc", Path("/anything") / BAD)
    assert entry is not None
    assert entry["bad_snapshot"] == "20261008T000539+1100"
    assert entry["detected_by"] and entry["decided"]
    assert not lre.is_excluded("au", BAD)
    assert not lre.is_excluded("hkjc", "2026-11-11_HappyValley")


def test_keep_filters_ledger_rows_by_meeting():
    rows = [{"meeting": BAD, "x": 1}, {"meeting": "2026-10-11_ShaTin", "x": 2}, {"x": 3}]
    assert [r["x"] for r in lre.keep("hkjc", rows)] == [2, 3]


@pytest.mark.parametrize("entry", [
    {"platform": "hkjc", "meeting": "m", "reason": "r", "detected_by": "c"},          # no decided
    {"platform": "nba", "meeting": "m", "reason": "r", "detected_by": "c", "decided": "d"},
])
def test_registry_entries_must_be_complete(tmp_path, entry):
    path = tmp_path / "x.json"
    path.write_text(json.dumps({"meetings": [entry]}), encoding="utf-8")
    with pytest.raises(ValueError):
        lre.load("hkjc", path)


def test_shadow_monitor_summary_skips_excluded_meeting():
    sys.path.insert(0, str(ROOT / ".agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts"))
    import hkjc_shadow_monitor as monitor

    def row(meeting, delta):
        metrics = {m: 0.0 for m in monitor.METRICS}
        return {"key": f"{meeting}::1::weight_refit_t02", "meeting": meeting, "race_number": 1,
                "venue": "ShaTin", "track": "Turf", "profile": "weight_refit_t02",
                "profile_applied": True, "baseline": metrics,
                "candidate": {m: delta for m in monitor.METRICS},
                "delta": {m: delta for m in monitor.METRICS}}

    clean = monitor.summarize([row("2026-10-11_ShaTin", 0.0)])
    mixed = monitor.summarize([row("2026-10-11_ShaTin", 0.0), row(BAD, 1.0)])
    assert mixed == clean
    assert monitor.settle_meeting(Path("/nonexistent") / BAD) == []


def test_published_mainline_reader_drops_excluded_meeting(tmp_path):
    sys.path.insert(0, str(ROOT / ".agents/skills/hkjc_racing/hkjc_reflector/scripts"))
    import review_auto_weighting as review

    for name in (BAD, "2026-10-11_ShaTin"):
        d = tmp_path / name
        d.mkdir()
        (d / "HKJC_Auto_Scoring.csv").write_text(
            "race_number,horse_number,rank,ability_score\n1,5,1,80\n1,6,2,70\n", encoding="utf-8")
    assert review.load_published_mainline_predictions(tmp_path / BAD) == {}
    assert review.load_published_mainline_predictions(tmp_path / "2026-10-11_ShaTin")

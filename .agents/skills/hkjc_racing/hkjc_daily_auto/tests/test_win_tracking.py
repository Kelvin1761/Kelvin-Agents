"""頭馬追蹤：首選來自最後一份 immutable 賽前快照，熱門來自官方最終獨贏派彩。"""
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hkjc_win_tracking as tracking  # noqa: E402


def _meeting(root: Path, name: str, ranks: dict, board: list) -> Path:
    meeting = root / name
    snap = meeting / "Prediction_Snapshots" / "20261111T100000+1100"
    snap.mkdir(parents=True)
    logic = {"horses": {str(n): {"python_auto": {"rank": r}} for n, r in ranks.items()}}
    path = snap / "Race_1_Logic.json"
    path.write_text(json.dumps(logic), encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    (snap / "manifest.json").write_text(json.dumps({
        "immutable_prediction_snapshot": True,
        "files": [{"name": "Race_1_Logic.json", "sha256": digest}]}), encoding="utf-8")
    results = {"1": {"results": [{"horse_no": str(n), "pos": str(p), "win_odds": str(o)} for n, p, o in board]}}
    (meeting / f"{name}_全日賽果.json").write_text(json.dumps(results, ensure_ascii=False), encoding="utf-8")
    return meeting


def test_top_pick_and_favourite_are_scored_separately(tmp_path):
    _meeting(tmp_path, "2026-11-11_HappyValley", {3: 1, 7: 2, 1: 3, 2: 4},
             [(7, 1, 2.1), (3, 2, 6.0), (1, 3, 9.0), (2, 4, 15.0)])
    rows = tracking.collect(tmp_path, date(2026, 11, 11))
    assert rows == [{"meeting": "2026-11-11_HappyValley", "race": 1, "top_won": False, "top_placed": True,
                     "fav_won": True, "fav_placed": True, "same_pick": False}]
    text = tracking.section(tmp_path, date(2026, 11, 11))
    assert "首選頭馬 0.0% vs 熱門 100.0%" in text and "1 場" in text


def test_meetings_before_start_and_without_snapshot_are_skipped(tmp_path):
    _meeting(tmp_path, "2026-11-08_ShaTin", {1: 1, 2: 2, 3: 3, 4: 4},
             [(1, 1, 2.0), (2, 2, 3.0), (3, 3, 4.0), (4, 4, 5.0)])
    (tmp_path / "2026-11-15_ShaTin").mkdir()
    assert tracking.collect(tmp_path, date(2026, 11, 11)) == []
    assert "未有完成場次" in tracking.section(tmp_path, date(2026, 11, 11))

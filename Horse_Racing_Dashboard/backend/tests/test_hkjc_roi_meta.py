"""HKJC ROI 分項嘅賽事資料（App 記錄冇路程／班次／賽道／騎練，靠呢份配對）。"""
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from services.hkjc_roi_meta import build_race_meta, race_class, venue_key


def test_class_spellings_collapse():
    assert race_class("C4") == "第四班"
    assert race_class("Class 3") == "第三班"
    assert race_class("第三班（條件限制）") == "第三班"
    assert race_class("G1") == race_class("一級賽") == "一級賽"
    assert race_class("GR") == "新馬賽"
    assert race_class("4") == "第四班"
    assert race_class("[FILL]") == ""                       # 壞值當未知，唔好變一行分項
    assert race_class("#### 第二部分：馬匹資料") == ""


def test_venue_key_matches_ledger_and_import_spellings():
    assert venue_key("HappyValley") == venue_key("Happy Valley") == venue_key("跑馬地") == "happyvalley"
    assert venue_key("Sha Tin") == venue_key("ShaTin") == "shatin"


def _logic(path: Path, analysis: dict, horses: dict):
    path.write_text(json.dumps({"race_analysis": analysis, "horses": horses}, ensure_ascii=False), encoding="utf-8")


def test_build_reads_logic_and_falls_back_to_racecard_for_track(tmp_path: Path):
    new = tmp_path / "2026-11-04_HappyValley"
    new.mkdir()
    _logic(new / "Race_1_Logic.json",
           {"distance": "1000m", "race_class": "第五班", "track": "Turf", "rail": "A"},
           {"7": {"horse_name": "喆喆友福", "jockey": "周俊樂", "trainer": "沈集成"}})
    old = tmp_path / "2026-07-01_ShaTin"
    old.mkdir()
    _logic(old / "Race_2_Logic.json", {"distance": "1600m", "race_class": "C4"},
           {"1": {"horse_name": "紅磚戰士", "jockey": "艾道拿", "trainer": "游達榮"}})
    (old / "07-01 Race 2 排位表.md").write_text("場次: 第2場\n場地: 草地\n賽道: C+3 賽道\n路程: 1600米\n", encoding="utf-8")
    (tmp_path / "not_a_meeting").mkdir()

    meta = build_race_meta(tmp_path)
    assert set(meta) == {"2026-11-04|happyvalley|1", "2026-07-01|shatin|2"}
    hv = meta["2026-11-04|happyvalley|1"]
    assert (hv["d"], hv["c"], hv["v"], hv["t"]) == ("1000", "第五班", "跑馬地", "草地 A")
    assert hv["h"]["7"] == ["周俊樂", "沈集成"]
    st = meta["2026-07-01|shatin|2"]
    assert (st["c"], st["t"]) == ("第四班", "草地 C+3")         # 舊 Logic 冇賽道 → 排位表補


def test_missing_root_is_empty(tmp_path: Path):
    assert build_race_meta(tmp_path / "nope") == {}

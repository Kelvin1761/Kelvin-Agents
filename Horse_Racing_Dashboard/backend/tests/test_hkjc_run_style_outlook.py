"""HKJC 預計跑法 label：直接讀引擎嘅 python_auto.run_style（Wong Choi 唯一跑法標準，Kelvin 2026-11-16）。"""
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
ENGINE = BACKEND.parents[1] / ".agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts"
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))

from hkjc_racing_engine import run_style as engine  # noqa: E402
from services.hkjc_insights import run_style as live_run_style  # noqa: E402
from services.parser_hkjc import parse_hkjc_analysis  # noqa: E402

OUTLOOK = {"label": "後上", "code": "B", "habit": 0.607, "consistency": "多變", "same": 2, "hit_rate": 52.0,
           "runs": [{"date": "2026-10-19", "frac": 0.583, "style": "守中"}, {"date": "2026-02-19", "frac": 0.786, "style": "後上"}]}


def test_live_insights_use_the_engine_standard():
    names = {"front": "放頭", "middle": "守中", "back": "後上"}
    for field in range(5, 15):
        for first in range(1, field + 1):
            assert names[live_run_style(first, field)] == engine.classify(engine.fraction(first, field))
    assert live_run_style(None, 12) is None


def _race(tmp_path: Path, horses: dict) -> Path:
    analysis = tmp_path / "Race_1_Auto_Analysis.md"
    analysis.write_text(
        "## 第1場\n\n**【No.1】 馬甲** | 騎師:潘頓 | 練馬師:蔡約翰 | 負磅:126 | 檔位:2\n\n"
        "#### 🧮 7D 評分矩陣逐項拆解\n\n內容。\n\n---\n\n"
        "**【No.2】 馬2** | 騎師:田泰安 | 練馬師:告東尼 | 負磅:124 | 檔位:5\n\n"
        "#### 🧮 7D 評分矩陣逐項拆解\n\n內容。\n",
        encoding="utf-8")
    (tmp_path / "Race_1_Logic.json").write_text(json.dumps({"horses": horses}, ensure_ascii=False), encoding="utf-8")
    return analysis


def test_parser_reads_engine_run_style(tmp_path: Path):
    analysis = _race(tmp_path, {"1": {"horse_name": "馬甲", "python_auto": {"run_style": OUTLOOK}},
                                "2": {"horse_name": "馬2", "python_auto": {"run_style": None},
                                      "_data": {"position_window": "第1仗(01/10/2026 沙田 1200): 沿途位=1-1-1 | "
                                                                   "第2仗(01/09/2026 沙田 1200): 沿途位=1-1-1"}}})
    race = parse_hkjc_analysis(str(analysis))
    by_no = {h.horse_number: h for h in race.horses}
    assert by_no[1].run_style_outlook == OUTLOOK
    # 冇引擎跑法（舊 Logic）→ 唔出 label，唔准退返用另一套計法
    assert by_no[2].run_style_outlook is None


def test_prerace_odds_use_last_snapshot_still_selling(tmp_path: Path):
    """Kelvin 2026-11-17：排名表顯示開跑前最後一個賠率（純參考，唔入評分）。"""
    from services.parser_hkjc import _load_prerace_odds
    snaps = [{"captured_at": "2026-11-18T18:00:00+08:00", "races": {"3": {"pre_race": True, "runners": {"8": {"win": 3.1, "place": 1.4}}}}},
             {"captured_at": "2026-11-18T19:30:00+08:00", "races": {"3": {"pre_race": True, "runners": {"8": {"win": 2.8, "place": 1.3}}}}},
             {"captured_at": "2026-11-18T19:45:00+08:00", "races": {"3": {"pre_race": False, "runners": {"8": {"win": 2.5, "place": 1.2}}}}}]
    (tmp_path / "HKJC_Odds_History.json").write_text(json.dumps({"snapshots": snaps}), encoding="utf-8")
    odds, at = _load_prerace_odds(tmp_path / "Race_3_Auto_Analysis.md", 3)
    assert odds == {8: (2.8, 1.3)} and at.startswith("2026-11-18T19:30")
    assert _load_prerace_odds(tmp_path / "Race_3_Auto_Analysis.md", 4) == ({}, None)

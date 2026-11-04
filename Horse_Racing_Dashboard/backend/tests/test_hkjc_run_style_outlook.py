"""HKJC 預計跑法 label（參考，唔入評分；Kelvin 2026-11-05）。"""
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from services.hkjc_insights import run_style as live_run_style
from services.parser_hkjc import parse_hkjc_analysis, run_style_outlook

WINDOW = ("第1仗(28/10/2026 沙田AWT 1200): 沿途位=7-6-5, XW=(1W3W), 名次=5 | "
          "第2仗(07/10/2026 跑馬地 1200): 沿途位=3-3-9, XW=(1W1W1W), 名次=9 | "
          "第3仗(16/09/2026 跑馬地 1200): 沿途位=2-1-4, XW=(4W2W2W), 名次=4 | "
          "第4仗(15/07/2026 跑馬地 1200): 沿途位=12-12-2, 名次=2")


def test_majority_of_last_three_runs_only():
    out = run_style_outlook(WINDOW, 12)
    assert [r["first_call"] for r in out["runs"]] == [7, 3, 2]      # 第 4 仗唔計
    assert out["label"] == "放頭" and out["consistency"] == "大致"
    assert out["hit_rate"] == 50.3


def test_same_classification_as_live_insights():
    # 即場形勢用 hkjc_insights.run_style；兩邊一定要同一個定義
    names = {"front": "放頭", "middle": "守中", "back": "後上"}
    for first in range(1, 15):
        window = f"第1仗(01/10/2026 沙田 1200): 沿途位={first}-1-1 | 第2仗(01/09/2026 沙田 1200): 沿途位={first}-1-1"
        out = run_style_outlook(window, 14)
        assert out["label"] == names[live_run_style(first, 14)]
        assert out["consistency"] == "穩定"


def test_no_majority_is_variable_and_too_few_runs_is_none():
    window = ("第1仗(01/10/2026 沙田 1200): 沿途位=1-1-1 | 第2仗(01/09/2026 沙田 1200): 沿途位=6-6-6 | "
              "第3仗(01/08/2026 沙田 1200): 沿途位=13-13-13")
    out = run_style_outlook(window, 14)
    assert out["label"] is None and out["consistency"] == "多變" and out["hit_rate"] is None
    assert run_style_outlook("第1仗(01/10/2026 沙田 1200): 沿途位=1-1-1", 14) is None
    assert run_style_outlook("", 14) is None


def test_parser_attaches_outlook_from_logic(tmp_path: Path):
    analysis = tmp_path / "Race_1_Auto_Analysis.md"
    analysis.write_text(
        "## 第1場\n\n**【No.1】 馬甲** | 騎師:潘頓 | 練馬師:蔡約翰 | 負磅:126 | 檔位:2\n\n"
        "#### 🧮 7D 評分矩陣逐項拆解\n\n內容。\n\n---\n\n"
        "**【No.2】 馬2** | 騎師:田泰安 | 練馬師:告東尼 | 負磅:124 | 檔位:5\n\n"
        "#### 🧮 7D 評分矩陣逐項拆解\n\n內容。\n",
        encoding="utf-8")
    horses = {str(n): {"horse_name": f"馬{n}", "_data": {}} for n in range(2, 13)}
    horses["1"] = {"horse_name": "馬甲", "_data": {"position_window": WINDOW}}
    horses["13"] = {"horse_name": "退出馬 (退出)", "_data": {}}
    (tmp_path / "Race_1_Logic.json").write_text(json.dumps({"horses": horses}, ensure_ascii=False), encoding="utf-8")
    race = parse_hkjc_analysis(str(analysis))
    horse = next(h for h in race.horses if h.horse_number == 1)
    assert horse.run_style_outlook["label"] == "放頭"
    assert horse.run_style_outlook["field"] == 12            # 退出馬唔計

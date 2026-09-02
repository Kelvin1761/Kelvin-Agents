"""跑法只有一個來源，而且冇證據唔准當守中。

2026-09-02 之前有四條路可以產生「跑法」：
  1. Sportsbet 加權走位證據 → `running_style_line`（唯一應該存在嘅來源）
  2. `race_shape_summary`（舊 Racenet 場面摘要）
  3. `facts_section` token 掃描（由敘述文字撈字，會撈到對手嘅跑法）
  4. `tactical_plan.expected_position` —— 我哋自己推嘅，冇證據時**由檔位**
     砌一個「守中」，然後又被 `_running_style()` 當 fallback 讀返，自己餵自己

再加上 `weighted_au_running_style()` 將「冇證據」同「跑法多變」一齊寫成守中，
令 68.7% 嘅 runner 頂住一個「守中」標籤。實測（EXP-20260902-01）：溝埋量
場內 AUC 0.5149，剔走之後 0.5489。

呢個測試守住：一個來源、三個狀態、冇證據就係冇。
"""
import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "scripts"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from au_racing_engine.engine_core import (  # noqa: E402
    RacingEngine,
    _expected_position_label,
)

REPO_ROOT = Path(__file__).resolve().parents[5]
INJECT = REPO_ROOT / ".agents" / "scripts" / "inject_fact_anchors.py"


def _engine(data):
    engine = RacingEngine.__new__(RacingEngine)
    engine.data = data
    engine.horse_data = {}
    engine.facts_section = (
        "近仗前領到底，其後守中；對手後上追上。前置 居中前 中後 後上 前領"
    )
    return engine


def _inject():
    spec = importlib.util.spec_from_file_location("_ifa_style_test", INJECT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["_ifa_style_test"] = module
    spec.loader.exec_module(module)
    return module


class TestRunStyleSingleSource(unittest.TestCase):
    def test_只認_sportsbet_嗰條_line(self):
        self.assertEqual(_engine({"running_style_line": "後上 / 後上"})._running_style(), "後上 / 後上")

    def test_唔准由敘述文字撈跑法(self):
        """facts_section 塞滿跑法字眼都唔可以撈 —— 嗰啲字可以係講對手。"""
        self.assertEqual(_engine({})._running_style(), "")

    def test_唔准回退去_race_shape_summary(self):
        self.assertEqual(_engine({"race_shape_summary": "前領"})._running_style(), "")

    def test_未知同多變唔算跑法(self):
        for line in ("未知 / 未知", "多變 / 多變"):
            with self.subTest(line=line):
                self.assertEqual(_engine({"running_style_line": line})._running_style(), "")

    def test_預計走位唔准由檔位砌出嚟(self):
        """舊版冇跑法證據就按檔位寫「守中 / 內欄」或「守中 / 居中」。"""
        self.assertEqual(_expected_position_label("未知 / 未知"), "")
        self.assertEqual(_expected_position_label(""), "")
        self.assertEqual(_expected_position_label("後上 / 後上"), "中後 / 後上")
        self.assertEqual(_expected_position_label("前置 / 跟前"), "前置 / 跟前")
        self.assertEqual(_expected_position_label("守中 / 守中"), "守中")

    def test_冇走位證據唔可以扮守中(self):
        module = _inject()
        profile = module.weighted_au_running_style([
            {"is_trial": False, "run_profile": {}, "settled": None},
            {"is_trial": False, "run_profile": {}, "settled": None},
        ])
        self.assertEqual(profile["style"], "unknown")
        self.assertEqual(profile["style_cn"], "未知")
        self.assertNotIn("守中", profile["style_cn"])

    def test_有證據但唔一致叫多變唔叫守中(self):
        module = _inject()
        profile = module.weighted_au_running_style([
            {"is_trial": False, "run_profile": {}, "settled": 1},
            {"is_trial": False, "run_profile": {}, "settled": 10},
            {"is_trial": False, "run_profile": {}, "settled": 5},
        ])
        self.assertEqual(profile["style"], "mixed")

    def test_真係守中先叫守中(self):
        module = _inject()
        profile = module.weighted_au_running_style([
            {"is_trial": False, "run_profile": {}, "settled": 5},
            {"is_trial": False, "run_profile": {}, "settled": 4},
            {"is_trial": False, "run_profile": {}, "settled": 6},
        ])
        self.assertEqual(profile["style"], "mid_pack")
        self.assertEqual(profile["style_cn"], "守中")

    def test_速度圖唔可以將唔知嘅馬掃入守中組(self):
        module = _inject()
        horses = [
            {"num": 1, "barrier": 3, "dossier_entries": []},
            {"num": 2, "barrier": 7, "dossier_entries": []},
        ]
        _block, speed_map = module.build_au_speed_map_block(horses, 1200, "Randwick", "Good 4")
        self.assertEqual(speed_map["mid_pack"], [])
        self.assertEqual(sorted(speed_map["unclassified"]), [1, 2])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import sys
import unittest
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]
ENGINE_DIR = ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts" / "racing_engine"
sys.path.insert(0, str(ENGINE_DIR))

from engine_core import RacingEngine
from renderer import render_race_markdown


def _analyze(horse: dict, race_context: dict) -> dict:
    facts_section = horse.get("_data", {}).get("facts_section", "")
    return RacingEngine(horse, race_context, facts_section=facts_section).analyze_horse()


def _facts_section() -> str:
    return "\n".join(
        [
            "- **🔗 賽績線**",
            "| 日期 | 賽事 | 名次 | 對手 | 下仗班次 | 對手後續成績 | 強度 |",
            "|---|---|---|---|---|---|---|",
            "| 2026-05-01 | Randwick R5 | 2 | 頭馬: Rival A | Group 3 | 出 2 次: 1 勝 | 強 |",
            "| 2026-04-15 | Rosehill R3 | 3 | 亞軍: Rival B | BM78 | 出 2 次: 0 勝 | 中強 |",
            "- **🔧 引擎與距離:** 引擎: Type C | 信心: 高 | 跑法: 中後 / 後上 | 今場 1400m (上 100m): 最佳 ← 今場 ✅",
            "| 1 | 正式 | 2026-05-01 | Randwick | 1400m | Good 4 | 8 | 2 | 升班 | 9-8-2 | 4 | 較快 | Genuine | 34.12 | 後上 | 中等 | Crowded late | 受阻 |",
            "| 2 | 正式 | 2026-04-15 | Rosehill | 1300m | Soft 6 | 10 | 3 | = | 10-9-3 | 5 | 較快 | Strong | 34.20 | 後上 | 中低 | Worked early | 外疊 |",
            "| 3 | 試閘 | 2026-03-28 | Randwick | 1050m | Good 4 | 4 | 1 | Trial | 4-3-1 | 3 | 較快 | Moderate | 33.90 | 跟前 | 低 | - | [-] |",
        ]
    )


def _race_context(going: str = "Good 4") -> dict:
    return {
        "distance": "1400m",
        "race_class": "BM78",
        "meeting_intelligence": {
            "going": going,
            "bias_summary": "內檔略有幫助，前中段落位重要。",
            "venue": "Randwick",
        },
        "track_profile": {
            "venue": "Randwick",
            "straight_m": 320,
            "circumference_m": 2224,
            "distance_note": "1400m 起步後搶位成本唔低。",
            "going_note": "濕地時前置消耗會放大。",
            "key_traits": ["Tight-turning", "On-Pace Bias"],
        },
    }


def _horse(overrides: dict | None = None) -> dict:
    horse = {
        "horse_name": "Alpha",
        "jockey": "J McDonald",
        "trainer": "C Waller",
        "weight": "56.0",
        "barrier": "3",
        "career_race_starts": "8",
        "status_cycle": "Third-up",
        "trend_summary": "近兩仗走勢上揚",
        "recent_form": "2134",
        "tactical_plan": {
            "expected_position": "中後 / 後上",
            "race_scenario": "先守中後列等直路前移出追勢。",
        },
        "_data": {
            "recent_form": "2134",
            "engine_line": "引擎: Type C | 信心: 高 | 跑法: 中後 / 後上 | 今場 1400m (上 100m): 最佳 ← 今場 ✅",
            "target_distance_line": "今場 1400m (上 100m): 最佳 ← 今場 ✅",
            "sectional_trend_line": "PI (定位→終點): 2, 4, 5 → 趨勢: 穩定\nL400 PI (400m→終點): 3, 5, 6 → 趨勢: 上升",
            "formline_line": "中強",
            "track_record_line": "同場: 2:1-1-0-0 | 同場同程: 1:1-0-0-0",
            "track_stats_line": "2:1-1-0-0",
            "going_stats_line": "好地: 5:2-1-1-0 | 軟地: 2:1-1-0-0 | 重地: 1:0-0-0-1",
            "stage_stats_line": "初出: 0:0-0-0 | 二出: 1:1-0-0",
            "trial_count": "2",
            "trial_top3_count": "2",
            "class_move": "升班",
            "consumption_summary": "加權累積消耗: 2.0 → 等級: 中低",
            "running_style_line": "中後 / 後上",
            "style_confidence_line": "高",
            "engine_type_line": "Type C",
            "engine_confidence_line": "高",
            "distance_profile_line": "1400m = 最佳",
            "raw_l400": "22.90",
            "facts_section": _facts_section(),
        },
    }
    if overrides:
        horse = deepcopy(horse)
        for key, value in overrides.items():
            if key == "_data":
                horse["_data"].update(value)
            elif key == "tactical_plan":
                horse["tactical_plan"].update(value)
            else:
                horse[key] = value
    return horse


class AuAutoOutputTests(unittest.TestCase):
    def test_core_logic_contains_evidence_chain_and_condition_branch(self) -> None:
        result = _analyze(_horse(), _race_context())
        core = result["core_logic"]

        self.assertIn("L400", core)
        self.assertIn("今次排 3 檔", core)
        self.assertIn("對手線", core)
        self.assertIn("若", core)

    def test_forgiveness_lifts_consistency_score(self) -> None:
        neutral_horse = _horse(
            {
                "recent_form": "8-9-7-6",
                "_data": {
                    "recent_form": "8-9-7-6",
                    "consumption_summary": "加權累積消耗: 2.6 → 等級: 中等",
                    "facts_section": "\n".join(
                        [
                            "- **🔗 賽績線**",
                            "| 日期 | 賽事 | 名次 | 對手 | 下仗班次 | 對手後續成績 | 強度 |",
                            "|---|---|---|---|---|---|---|",
                            "| 2026-05-01 | Randwick R5 | 8 | 頭馬: Rival A | Group 3 | 出 2 次: 1 勝 | 強 |",
                            "- **🔧 引擎與距離:** 引擎: Type C | 信心: 高 | 跑法: 中後 / 後上 | 今場 1400m (上 100m): 最佳 ← 今場 ✅",
                            "| 1 | 正式 | 2026-05-01 | Randwick | 1400m | Good 4 | 8 | 8 | 升班 | 10-10-8 | 1 | 一般 | Genuine | 34.50 | 後上 | 中等 | - | [-] |",
                            "| 2 | 正式 | 2026-04-15 | Rosehill | 1300m | Soft 6 | 10 | 9 | = | 11-10-9 | 1 | 一般 | Strong | 34.60 | 後上 | 中等 | - | [-] |",
                        ]
                    ),
                },
            }
        )
        forgiven_horse = deepcopy(neutral_horse)
        forgiven_horse["_data"]["facts_section"] = "\n".join(
            [
                "- **🔗 賽績線**",
                "| 日期 | 賽事 | 名次 | 對手 | 下仗班次 | 對手後續成績 | 強度 |",
                "|---|---|---|---|---|---|---|",
                "| 2026-05-01 | Randwick R5 | 8 | 頭馬: Rival A | Group 3 | 出 2 次: 1 勝 | 強 |",
                "- **🔧 引擎與距離:** 引擎: Type C | 信心: 高 | 跑法: 中後 / 後上 | 今場 1400m (上 100m): 最佳 ← 今場 ✅",
                "| 1 | 正式 | 2026-05-01 | Randwick | 1400m | Good 4 | 8 | 8 | 升班 | 10-10-8 | 1 | 一般 | Genuine | 34.50 | 後上 | 中等 | Crowded late | 受阻 |",
                "| 2 | 正式 | 2026-04-15 | Rosehill | 1300m | Soft 6 | 10 | 9 | = | 11-10-9 | 1 | 一般 | Strong | 34.60 | 後上 | 中等 | Worked early | 外疊 |",
            ]
        )

        neutral = _analyze(neutral_horse, _race_context())
        forgiven = _analyze(forgiven_horse, _race_context())

        self.assertGreater(forgiven["feature_scores"]["consistency_score"], neutral["feature_scores"]["consistency_score"])

    def test_verified_wet_runner_scores_better_on_heavy(self) -> None:
        verified = _analyze(_horse(), _race_context("Heavy 8"))
        unverified = _analyze(
            _horse({"_data": {"going_stats_line": "好地: 5:2-1-1-0 | 軟地: 0:0-0-0-0 | 重地: 0:0-0-0-0"}}),
            _race_context("Heavy 8"),
        )

        self.assertGreater(verified["feature_scores"]["track_score"], unverified["feature_scores"]["track_score"])

    def test_higher_class_followups_boost_formline_score(self) -> None:
        higher = _analyze(_horse(), _race_context())
        lower = _analyze(
            _horse(
                {
                    "_data": {
                        "facts_section": "\n".join(
                            [
                                "- **🔗 賽績線**",
                                "| 日期 | 賽事 | 名次 | 對手 | 下仗班次 | 對手後續成績 | 強度 |",
                                "|---|---|---|---|---|---|---|",
                                "| 2026-05-01 | Randwick R5 | 2 | 頭馬: Rival A | Maiden | 出 2 次: 0 勝 | 中組 |",
                                "| 2026-04-15 | Rosehill R3 | 3 | 亞軍: Rival B | BM64 | 出 2 次: 0 勝 | 中組 |",
                                "- **🔧 引擎與距離:** 引擎: Type C | 信心: 高 | 跑法: 中後 / 後上 | 今場 1400m (上 100m): 最佳 ← 今場 ✅",
                                "| 1 | 正式 | 2026-05-01 | Randwick | 1400m | Good 4 | 8 | 2 | 升班 | 9-8-2 | 4 | 較快 | Genuine | 34.12 | 後上 | 中等 | - | [-] |",
                            ]
                        ),
                        "formline_line": "中組",
                    }
                }
            ),
            _race_context(),
        )

        self.assertGreater(higher["feature_scores"]["formline_score"], lower["feature_scores"]["formline_score"])

    def test_rendered_report_uses_new_narrative_sections(self) -> None:
        horse_one = _horse()
        horse_two = _horse(
            {
                "horse_name": "Bravo",
                "jockey": "T Clark",
                "trainer": "J Pride",
                "barrier": "9",
                "weight": "58.0",
                "tactical_plan": {
                    "expected_position": "跟前 / 前置",
                    "race_scenario": "外檔下要推前搶位，否則轉彎前會白走。",
                },
                "_data": {
                    "recent_form": "5412",
                    "running_style_line": "跟前 / 前置",
                    "style_confidence_line": "中",
                    "raw_l400": "23.35",
                    "consumption_summary": "加權累積消耗: 3.2 → 等級: 中等偏高",
                },
            }
        )
        race_context = _race_context()
        horse_one["python_auto"] = _analyze(horse_one, race_context)
        horse_two["python_auto"] = _analyze(horse_two, race_context)
        logic = {
            "race_analysis": {
                "race_number": 1,
                "distance": "1400m",
                "race_class": "BM78",
                "meeting_intelligence": race_context["meeting_intelligence"],
                "track_profile": race_context["track_profile"],
            },
            "horses": {"1": horse_one, "2": horse_two},
        }

        report = render_race_markdown(logic)

        self.assertIn("#### 💡 核心邏輯與結論", report)
        self.assertIn("寬恕焦點", report)
        self.assertIn("最大競爭優勢", report)
        self.assertIn("若", report)


if __name__ == "__main__":
    unittest.main()

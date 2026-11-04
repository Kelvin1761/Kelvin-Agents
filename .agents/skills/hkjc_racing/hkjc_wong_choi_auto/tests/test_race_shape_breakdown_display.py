"""檔位與走位「評分構成」要講清楚計法，同分開「入分」／「只供參考」。

2026-11-05：跑馬地報告列咗檔位／走位匹配／近仗消耗三個分但冇講點加，
而真正入分嘅「個別谷草性能」完全冇印；走位匹配同近仗消耗其實冇入分。
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from hkjc_racing_engine.renderer import _race_shape_detail_lines


def detail(terms, formula="檔位分 64.0 + 0.45 × (谷草性能 63.8 − 60) = 65.7", rail="A"):
    return {"race_shape_detail": {"formula": formula, "terms": terms, "rail": rail,
                                  "draw": 64.0, "fit": 58.0, "trip": 60.7}}


class RaceShapeBreakdownDisplayTests(unittest.TestCase):
    def test_happy_valley_lists_surface_as_scored_and_fit_trip_as_reference(self):
        lines = _race_shape_detail_lines(detail([
            {"label": "檔位分", "score": 64.0, "scored": True, "why": ""},
            {"label": "個別谷草性能", "score": 63.8, "scored": True, "why": "有效樣本 4.8 仗"},
            {"label": "走位匹配分", "score": 58.0, "scored": False, "why": "歷史走位 PI 微跌"},
            {"label": "近仗消耗分", "score": 60.7, "scored": False, "why": ""},
        ]))
        text = "\n".join(lines)
        self.assertTrue(lines[0].strip().startswith("- 計法：檔位分 64.0"))
        scored, reference = text.split("只供參考（未入評分）")
        self.assertIn("個別谷草性能 63.8", scored)
        self.assertNotIn("走位匹配分", scored)
        self.assertIn("走位匹配分 58.0", reference)
        self.assertIn("近仗消耗分 60.7", reference)
        self.assertIn("今場賽道 A", reference)

    def test_rail_never_lands_under_scored_heading(self):
        # 沙田三項全部入分；賽道仍然要喺「只供參考」下面，唔可以跟住入分嗰組。
        lines = _race_shape_detail_lines(detail([
            {"label": "檔位分", "score": 65.0, "scored": True, "why": ""},
            {"label": "走位匹配分", "score": 65.0, "scored": True, "why": ""},
            {"label": "近仗消耗分", "score": 64.0, "scored": True, "why": ""},
        ], formula="檔位分 65.0×55% + 走位匹配分 65.0×25% + 近仗消耗分 64.0×20% = 64.8", rail="C+3"))
        text = "\n".join(lines)
        scored, reference = text.split("只供參考（未入評分）")
        self.assertNotIn("賽道", scored)
        self.assertIn("今場賽道 C+3", reference)

    def test_old_payload_without_formula_keeps_legacy_lines(self):
        lines = _race_shape_detail_lines({"race_shape_detail": {"draw": 64, "fit": 58, "trip": 61}})
        self.assertEqual(lines[0].strip(), "- 檔位分 64")


if __name__ == "__main__":
    unittest.main()

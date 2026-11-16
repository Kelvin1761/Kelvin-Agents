"""檔位 × 跑法組件（EXP-20261116-01）：只用嚴格早過今仗嘅跑法、≥2 仗先有跑法、場內置中、退回開關、shadow 同步。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from hkjc_racing_engine import draw_style as ds  # noqa: E402

TABLE = {"horses": {"L001": [["2026-10-01", 0.1], ["2026-11-01", 0.2], ["2026-11-15", 0.9]],
                    "L002": [["2026-10-20", 0.9], ["2026-10-30", 0.8]],
                    "L003": [["2026-10-20", 0.5]]}}
CTX = {"venue": "沙田", "track": "Turf", "distance": "1200m", "race_date": "2026-11-15"}


def horse(code, draw, raw=60.0):
    return {"horse_code": code, "barrier": draw,
            "python_auto": {"ability_score_raw": raw, "ability_score": 60.0, "grade": "B",
                            "shadow_profiles": {"x": {"ability_score_raw": raw, "ability_score": 60.0}}}}


class DrawStyleTest(unittest.TestCase):
    def test_style_strictly_before_and_min_runs(self):
        self.assertAlmostEqual(ds.habitual_position("L001", "2026-11-15", TABLE), 0.15)   # 唔用今仗 0.9
        self.assertIsNone(ds.habitual_position("L003", "2026-11-15", TABLE))             # 得 1 仗
        self.assertEqual(ds.style_class(0.15), "F")
        self.assertEqual(ds.style_class(0.85), "B")
        self.assertEqual(ds.style_class(None), "U")

    def test_groups(self):
        self.assertEqual(ds.group(CTX), "STS")
        self.assertEqual(ds.group(dict(CTX, distance="1000m")), "STRS")
        self.assertEqual(ds.group(dict(CTX, venue="跑馬地", distance="1650m")), "HVL")
        self.assertEqual(ds.group(dict(CTX, track="全天候跑道", distance="1800m")), "AWTL")
        self.assertIsNone(ds.group(dict(CTX, distance="")))

    def test_centred_and_direction(self):
        hs = {str(i): horse("L002", i) for i in range(1, 13)}
        adj, _ = ds.adjustments(hs, CTX, "2026-11-15", TABLE)
        self.assertAlmostEqual(sum(adj.values()), 0.0, places=9)
        self.assertGreater(adj["1"], adj["12"])        # 沙田短途後上馬：內檔好過外檔

    def test_apply_updates_raw_and_shadows_and_revert(self):
        hs = {"1": horse("L001", 1), "2": horse("L002", 12)}
        self.assertEqual(ds.apply(hs, CTX, TABLE), 2)
        a = hs["1"]["python_auto"]
        self.assertAlmostEqual(a["ability_score_raw"], 60.0 + a["draw_style_delta"], places=4)
        self.assertAlmostEqual(a["shadow_profiles"]["x"]["ability_score_raw"], a["ability_score_raw"], places=4)
        ds.ENABLED = False
        try:
            hs2 = {"1": horse("L001", 1), "2": horse("L002", 12)}
            self.assertEqual(ds.apply(hs2, CTX, TABLE), 0)
        finally:
            ds.ENABLED = True



class DrawTagTest(unittest.TestCase):
    """Kelvin 2026-11-17：檔位只出一個「內檔／中檔／外檔 優勢／劣勢」chip；跑法唔夾檔位另出扣分位。"""

    @staticmethod
    def _auto(dim, det, run_style=None):
        return {"grade_transparency": {"rows": [{"key": "race_shape", "impact": dim}]},
                "draw_style_detail": det, "run_style": run_style or {}}

    def test_one_draw_chip_and_style_not_named_when_not_special(self):
        from hkjc_racing_engine.tags import _draw_tags
        # 蓮冠皇（跑馬地 1200、1 檔、後上）：後上內檔 +3.0pp 低過內檔平均 → 唔寫「後上」
        det = {"group": "HVS", "style": "B", "draw": 1, "style_part": 0.676, "curve_part": 1.681}
        t = _draw_tags({"barrier": "1"}, self._auto(1.5, det))
        self.assertEqual([x["label"] for x in t], ["內檔優勢（1檔）"])
        self.assertAlmostEqual(t[0]["impact"], 3.86, places=2)
        self.assertIn("檔位分 +1.5", t[0]["why"])

    def test_style_named_when_it_beats_the_band(self):
        from hkjc_racing_engine.tags import _draw_tags
        # 跑馬地 1200 守中內檔 +6.3pp，高過內檔平均 ≥1pp →「內檔守中優勢」
        det = {"group": "HVS", "style": "M", "draw": 3, "style_part": 1.2, "curve_part": 0.3}
        t = _draw_tags({"barrier": "3"}, self._auto(1.0, det))
        self.assertEqual([x["label"] for x in t], ["內檔守中優勢（3檔）"])

    def test_misfit_style_is_a_separate_minus_chip(self):
        from hkjc_racing_engine.tags import _draw_tags
        # 沙田 1200 後上外檔 −4.4pp（外檔平均約 −3.2）：檔位本身有利但跑法唔夾 → 兩個 chip
        det = {"group": "STS", "style": "B", "draw": 10, "style_part": -0.9, "curve_part": 0.2}
        t = _draw_tags({"barrier": "10"}, self._auto(1.0, det))
        self.assertEqual([(x["label"], x["tone"]) for x in t],
                         [("外檔優勢（10檔）", "good"), ("跑法唔夾檔位（後上馬抽外檔）", "bad")])
        self.assertAlmostEqual(t[0]["impact"], 1.2, places=2)        # 跑法部分唔重複計
        # 檔位本身都唔利 → 合埋一個，寫埋跑法
        t = _draw_tags({"barrier": "10"}, self._auto(-1.0, det))
        self.assertEqual([x["label"] for x in t], ["外檔後上劣勢（10檔）"])

    def test_small_total_has_no_chip(self):
        from hkjc_racing_engine.tags import _draw_tags
        det = {"group": "STS", "style": "M", "draw": 6, "style_part": 0.2, "curve_part": -0.3}
        self.assertEqual(_draw_tags({"barrier": "6"}, self._auto(0.1, det)), [])


if __name__ == "__main__":
    unittest.main()

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



class DrawStyleTagTest(unittest.TestCase):
    def test_tag_only_when_material(self):
        from hkjc_racing_engine.tags import _draw_style_tag
        det = {"style": "B", "draw": 12, "style_part": -1.0, "curve_part": -0.5}
        t = _draw_style_tag({"draw_style_delta": -1.5, "draw_style_detail": det})
        self.assertEqual(t[0]["tone"], "bad")
        self.assertTrue(t[0]["scored"])
        self.assertIn("後上馬抽外檔", t[0]["label"])
        self.assertEqual(_draw_style_tag({"draw_style_delta": 0.5, "draw_style_detail": det}), [])


if __name__ == "__main__":
    unittest.main()

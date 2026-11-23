"""表現數字取代段速（EXP-20261123-10）：figW 換算、取代段速、場內置中、冇數用場均、日期嚴格早過今仗、退回開關。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from hkjc_racing_engine import performance_figure as pf  # noqa: E402
from hkjc_racing_engine import tags  # noqa: E402


def horse(code, weight, sec, raw=70.0):
    return {"horse_code": code, "weight": weight,
            "python_auto": {"ability_score_raw": raw, "ability_score": 60.0, "grade": "B",
                            "matrix_scores": {"sectional": sec}}}


class FigureTest(unittest.TestCase):
    def test_figure_w_converts_to_today_weight(self):
        runs = [(1.5, 135, 1.2, "2026-10-25"), (1.0, 135, 1.2, "2026-10-01")]
        base = pf.figure_w(runs, 135)
        self.assertAlmostEqual(base, (1.5 + 1.0 / 2) / 1.5, places=6)
        lighter = pf.figure_w(runs, 123)        # 輕 12 磅 → 快啲
        self.assertAlmostEqual(lighter - base, pf.BETA_LB * 12 * 1.2, places=6)
        self.assertIsNone(pf.figure_w(runs[:1], 123))   # 少過 2 仗
        self.assertIsNone(pf.figure_w(runs, None))

    def test_replaces_sectional_and_centres(self):
        table = {"A": [(1.6, 123, 1.2, "d"), (1.6, 123, 1.2, "d")], "B": [(1.0, 123, 1.2, "d"), (1.0, 123, 1.2, "d")]}
        hs = {"1": horse("A", 123, 60.0), "2": horse("B", 123, 90.0), "3": horse("Z", 123, 75.0)}
        adj = pf.adjustments(hs, "2026-11-22", table)
        self.assertAlmostEqual(sum(a for a, _ in adj.values()), 0.0, places=6)
        # 1 vs 2：段速差 −30 → 扣走 0.1285×(−30)，表現數字差 0.6 → 4.99×0.6
        self.assertAlmostEqual(adj["1"][0] - adj["2"][0], 0.1285 * 30 + pf.BETA_FIG * 0.6, places=4)
        self.assertIsNone(adj["3"][1]["figure"])            # 冇往績 = 場均＋缺失旗
        self.assertLess(adj["3"][1]["figure_added"], 0)

    def test_point_in_time_only(self):
        import pandas as pd
        rows = []
        for d, t1, t2 in (("2026-01-01", 70.0, 70.5), ("2026-02-01", 70.0, 70.4), ("2026-03-01", 69.0, 72.0)):
            for c, t in (("A", t1), ("B", t2)):
                rows.append({"race": f"{d}|ST|1", "date": d, "code": c, "w": 123, "time": t, "pos": 1 if t == min(t1, t2) else 2})
        R = pd.DataFrame(rows)
        R["season"] = 2025; R["t_win"] = R.groupby("race").time.transform("min"); R["beaten"] = R.time - R.t_win
        R["surface"] = "田草"; R["straight"] = False
        R["dist"] = 1200.0; R["km"] = 1.2; R["tkm"] = R.time / 1.2
        R["tkm_cap"] = (R.t_win + R.beaten.clip(upper=3)) / 1.2; R["hs"] = R.code + "|2025"
        pf._CACHE.clear()
        t = pf.figures_as_of("2026-03-01", R)
        self.assertEqual({run[3] for run in t["A"]}, {"2026-01-01", "2026-02-01"})   # 唔包今仗
        pf._CACHE.clear()

    def test_apply_tag_and_disable(self):
        hs = {"1": horse("A", 123, 60.0), "2": horse("B", 123, 90.0)}
        pf._CACHE["2026-11-22"] = {"A": [(1.6, 123, 1.2, "d"), (1.6, 123, 1.2, "d")],
                                   "B": [(1.0, 123, 1.2, "d"), (1.0, 123, 1.2, "d")]}
        try:
            self.assertEqual(pf.apply(hs, {"race_date": "2026-11-22"}), 2)
            self.assertIn("performance_figure_delta", hs["1"]["python_auto"])
            t = tags._performance_figure_tag(hs["1"]["python_auto"])
            self.assertTrue(t[0]["label"].startswith("表現數字：快過全場平均"))
            pf.ENABLED = False
            self.assertEqual(pf.apply({"1": horse("A", 123, 60.0)}, {"race_date": "2026-11-22"}), 0)
        finally:
            pf.ENABLED = True
            pf._CACHE.clear()


if __name__ == "__main__":
    unittest.main()

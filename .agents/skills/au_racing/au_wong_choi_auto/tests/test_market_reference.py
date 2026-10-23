#!/usr/bin/env python3
"""市場參考層（D1，Kelvin 2026-10-14）—— 純顯示，排名一定要 bit-identical。

R1 / EXP-20261014 Benter combiner：模型對最早賽前市場冇增量資訊
（α −0.112，CI 上限 +0.011），所以市場價**唔混入排名**，只喺報告另開一層顯示。

呢度釘死三樣嘢：
1. 有冇賠率（`_data.win_odds`／`place_odds`、`odds_history.json`），
   `python_auto`（分數、排名、grade）同 `Race_X_Auto_Scoring.csv` 都一模一樣。
2. 顯示用共用 `devig.py`：勝 power、位 odds_ratio、前三／前四 discounted Harville。
3. 引擎／評分 module 唔准 import 市場參考層（AST 掃，唔係 grep）。
"""
from __future__ import annotations

import ast
import json
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

TESTS = Path(__file__).resolve().parent
SCRIPTS = TESTS.parent / "scripts"
ENGINE = SCRIPTS / "au_racing_engine"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(TESTS))

from au_racing_engine import market_reference as M  # noqa: E402
from au_racing_engine.renderer import render_race_csv, render_race_markdown  # noqa: E402
import au_auto_orchestrator as ORCH  # noqa: E402
from test_auto_outputs import _horse, _race_context  # noqa: E402

# 贏盤 overround ≈ 1.18、位盤 ≈ 3.33（真實 Sportsbet 水平；低過 target 會被當套利盤拒絕）
ODDS = {"1": (1.90, 1.10), "2": (4.00, 1.45), "3": (7.00, 1.95), "4": (11.0, 2.60),
        "5": (15.0, 3.30), "6": (21.0, 4.40), "7": (31.0, 5.80), "8": (41.0, 7.50)}


def _logic(with_odds: bool) -> dict:
    variants = [
        {}, {"recent_form": "5412", "barrier": "9"}, {"recent_form": "8765", "barrier": "1"},
        {"recent_form": "1111", "barrier": "5"}, {"recent_form": "3322", "barrier": "7"},
        {"recent_form": "9x87", "barrier": "2"}, {"recent_form": "4444", "barrier": "8"},
        {"recent_form": "6253", "barrier": "4"},
    ]
    horses = {}
    for i, over in enumerate(variants, start=1):
        h = _horse({**over, "horse_name": f"Runner {i}"})
        if with_odds:
            win, place = ODDS[str(i)]
            h["_data"]["win_odds"] = win
            h["_data"]["place_odds"] = place
        horses[str(i)] = h
    ctx = _race_context()
    return {"race_analysis": {"race_number": 1, **ctx}, "horses": horses}


def _score(tmp: Path, logic: dict) -> dict:
    path = tmp / "Race_1_Logic.json"
    path.write_text(json.dumps(logic, ensure_ascii=False), encoding="utf-8")
    return ORCH.score_logic_data(path, logic_data=logic)


class RankingIsIdenticalWithAndWithoutOdds(unittest.TestCase):
    def test_python_auto_and_csv_bit_identical(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            # b 連 odds_history.json 都有 —— 最壞情況：顯示層有數可用。
            (Path(b) / M.ODDS_HISTORY).write_text(json.dumps({"1": {
                "2026-10-14T00:43:38|analysis": {k: [str(w), str(p)] for k, (w, p) in ODDS.items()}}}))
            without = _score(Path(a), _logic(with_odds=False))
            with_ = _score(Path(b), _logic(with_odds=True))
            for num in without["horses"]:
                self.assertEqual(
                    json.dumps(without["horses"][num]["python_auto"], sort_keys=True, default=str),
                    json.dumps(with_["horses"][num]["python_auto"], sort_keys=True, default=str),
                    f"馬 {num} 嘅 python_auto 因為有賠率而改變 —— 市場價漏咗入評分")
            self.assertEqual(render_race_csv(without), render_race_csv(with_))
            ranks = sorted((h["python_auto"]["rank"], n) for n, h in with_["horses"].items())
            self.assertEqual(len(ranks), 8)

    def test_rendering_does_not_mutate_the_logic(self):
        with tempfile.TemporaryDirectory() as tmp:
            logic = _score(Path(tmp), _logic(with_odds=True))
            before = json.dumps(logic, sort_keys=True, default=str)
            md = render_race_markdown(logic, meeting_dir=Path(tmp))
            self.assertEqual(before, json.dumps(logic, sort_keys=True, default=str))
            self.assertIn("📊 市場參考（分析時盤", md)

    def test_report_differs_only_by_market_lines(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            without = render_race_markdown(_score(Path(a), _logic(False)), meeting_dir=Path(a))
            with_ = render_race_markdown(_score(Path(b), _logic(True)), meeting_dir=Path(b))
            strip = lambda t: [ln for ln in t.splitlines()  # noqa: E731
                               if "市場盤（賽前）" not in ln and "市場參考" not in ln and ln.strip()]
            self.assertEqual(strip(without), strip(with_))
            self.assertNotIn("市場參考", without)


class DevigMethods(unittest.TestCase):
    def _horses(self, odds):
        return {str(i): {"_data": {"win_odds": w, "place_odds": p}}
                for i, (w, p) in enumerate(odds, start=1)}

    def test_sums_and_methods(self):
        ref = M.build_market_reference(self._horses(ODDS.values()))
        runners = ref["runners"]
        self.assertEqual(ref["places"], 3)
        self.assertAlmostEqual(sum(r["win_prob"] for r in runners.values()), 1.0, places=9)
        self.assertAlmostEqual(sum(r["place_prob"] for r in runners.values()), 3.0, places=9)
        self.assertAlmostEqual(sum(r["top3_prob"] for r in runners.values()), 3.0, places=9)
        self.assertAlmostEqual(sum(r["top4_prob"] for r in runners.values()), 4.0, places=9)
        wins = [w for w, _ in ODDS.values()]
        power = M.devig.devig(wins, "power").probabilities
        prop = M.devig.devig(wins, "proportional").probabilities
        self.assertAlmostEqual(runners["1"]["win_prob"], power[0], places=12)
        # power 畀大熱多過 proportional（X1：proportional 低估 <$2.0 大熱）
        self.assertGreater(runners["1"]["win_prob"], prop[0])
        places = [p for _, p in ODDS.values()]
        oratio = M.devig.devig(places, "odds_ratio", target_sum=3).probabilities
        self.assertAlmostEqual(runners["1"]["place_prob"], oratio[0], places=12)
        self.assertEqual([runners[k]["market_rank"] for k in sorted(runners, key=int)],
                         list(range(1, 9)))

    def test_harville_monotone_and_bounded(self):
        top3, top4 = M.harville_top_k([0.5, 0.3, 0.15, 0.05])
        self.assertEqual(top3, sorted(top3, reverse=True))
        self.assertTrue(all(0 <= a <= b <= 1 for a, b in zip(top3, top4)))
        self.assertTrue(all(abs(x - 1.0) < 1e-12 for x in top4))  # 4 匹 → 前四 = 1

    def test_earliest_snapshot_beats_rewritten_formguide(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / M.ODDS_HISTORY).write_text(json.dumps({"1": {
                "2026-10-14T10:19:06|morning-refresh": {"1": ["1.50", "1.10"], "2": ["3.0", "1.5"]},
                "2026-10-14T00:43:38|analysis": {"1": ["3.00", "1.40"], "2": ["1.40", "1.1"]},
            }}))
            horses = self._horses([(1.5, 1.1), (3.0, 1.5)])
            ref = M.build_market_reference(horses, Path(tmp), 1)
            self.assertEqual(ref["source"], "最早賽前盤 10-14 00:43")
            self.assertEqual(ref["runners"]["2"]["market_rank"], 1)

    def test_devig_runs_on_the_whole_book_then_conditions_on_todays_field(self):
        """退出馬嘅 1/o 一剷走，剩低 Σ(1/o) 會跌穿 1、扮套利盤（Rosehill R3 實測 0.946）。"""
        with tempfile.TemporaryDirectory() as tmp:
            snap = {k: [str(w), str(p)] for k, (w, p) in ODDS.items()}
            (Path(tmp) / M.ODDS_HISTORY).write_text(json.dumps({"1": {"2026-10-14T00:43:38|analysis": snap}}))
            today = {k: {"_data": {}} for k in ODDS if k not in {"1", "2"}}  # 兩匹大熱退出
            ref = M.build_market_reference(today, Path(tmp), 1)
            self.assertEqual(len(ref["runners"]), 6, ref["note"])
            self.assertAlmostEqual(sum(r["win_prob"] for r in ref["runners"].values()), 1.0, places=9)
            full = M.devig.devig([w for w, _ in ODDS.values()], "power").probabilities
            rest = sum(full[2:])
            self.assertAlmostEqual(ref["runners"]["3"]["win_prob"], full[2] / rest, places=12)
            self.assertEqual(ref["places"], 0, "盤同名單唔一致，位率唔計")
            self.assertIn("2 匹已退出", ref["note"])

    def test_scratched_runner_in_snapshot_is_ignored_and_unpriced_is_reported(self):
        horses = self._horses([(1.6, 1.2), (2.2, 1.5), (None, None)])
        ref = M.build_market_reference(horses)
        self.assertEqual(ref["priced"], 2)
        self.assertIn("1 匹冇贏盤價", ref["note"])
        self.assertEqual(ref["places"], 0, "≤4 匹冇位盤")

    def test_incomplete_win_book_does_not_publish_derived_probabilities(self):
        for size in (5, 8):
            for missing in (None, "-", float("nan"), float("inf"), 1.0):
                with self.subTest(size=size, missing=missing):
                    horses = self._horses(list(ODDS.values())[:size])
                    horses[str(size)]["_data"]["win_odds"] = missing
                    ref = M.build_market_reference(horses)
                    self.assertEqual(ref["field"], size)
                    self.assertEqual(ref["priced"], size - 1)
                    self.assertEqual(ref["runners"], {})
                    self.assertEqual(ref["places"], 0)
                    self.assertIn("1 匹冇贏盤價", ref["note"])
                    self.assertIsNone(M.horse_line(ref, "1"))

    def test_snapshot_missing_a_current_runner_does_not_use_later_formguide_prices(self):
        with tempfile.TemporaryDirectory() as tmp:
            snap = {k: list(v) for k, v in ODDS.items() if k != "8"}
            (Path(tmp) / M.ODDS_HISTORY).write_text(json.dumps({"1": {
                "2026-10-14T00:43:38|analysis": snap}}))
            ref = M.build_market_reference(self._horses(ODDS.values()), Path(tmp), 1)
        self.assertEqual(ref["priced"], 7)
        self.assertEqual(ref["runners"], {})
        self.assertEqual(ref["places"], 0)
        self.assertIn("1 匹冇贏盤價", ref["note"])

    def test_missing_place_price_only_suppresses_place_probabilities(self):
        horses = self._horses(ODDS.values())
        horses["8"]["_data"]["place_odds"] = None
        ref = M.build_market_reference(horses)
        self.assertEqual(ref["places"], 0)
        self.assertEqual(len(ref["runners"]), 8)
        self.assertTrue(all(r["place_prob"] is None for r in ref["runners"].values()))
        self.assertAlmostEqual(sum(r["win_prob"] for r in ref["runners"].values()), 1.0)

    def test_line_round_trips_through_dashboard_parser(self):
        dash = Path(__file__).resolve().parents[5] / "Horse_Racing_Dashboard" / "backend"
        sys.path.insert(0, str(dash))
        try:
            from services.parser_au import _parse_au_market_reference
        finally:
            sys.path.remove(str(dash))
        ref = M.build_market_reference(self._horses(ODDS.values()))
        got = _parse_au_market_reference(M.horse_line(ref, "1"))
        r = ref["runners"]["1"]
        self.assertEqual(got["market_rank"], 1)
        self.assertEqual(got["market_priced_runners"], 8)
        self.assertEqual(got["market_places_paid"], 3)
        self.assertEqual(got["market_reference_source"], "分析時盤")
        for key, field in (("market_win_prob", "win_prob"), ("market_place_prob", "place_prob"),
                           ("market_top3_prob", "top3_prob"), ("market_top4_prob", "top4_prob")):
            self.assertAlmostEqual(got[key], round(r[field], 3), places=3, msg=key)


class ScoringNeverImportsTheMarketLayer(unittest.TestCase):
    FORBIDDEN = {"market_reference", "devig", "_wc_shared_racing_devig"}

    def test_only_the_renderer_imports_it(self):
        offenders = []
        for path in sorted(ENGINE.glob("*.py")):
            if path.name in {"renderer.py", "market_reference.py"}:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""] + [a.name for a in node.names]
                if any(n.split(".")[-1] in self.FORBIDDEN for n in names):
                    offenders.append(path.name)
        self.assertEqual(offenders, [], "引擎／評分 module 唔准讀市場參考層（D1）")


if __name__ == "__main__":
    unittest.main()

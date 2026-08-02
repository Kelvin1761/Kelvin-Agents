"""Sportsbet 寫出嚟嘅 PF token 一定要落喺引擎真正讀嘅個 key。

背景：`run_line()` 本來寫 `PF[Last600: X]`。`_parse_pf_token` 的確識讀
`Last600:`，但佢入嘅係 `l600_time` —— **冇任何 leaf 讀呢個 key**。
`_pace_figure_score` 讀嘅係 `pf_aggregates['l600_delta_avg']`，只由
`L600 Delta:` 嚟。所以個 key 寫錯唔會報錯，只會令段速實速全場中性 60：
2026-08-01 Flemington 九場，96% 往績行有 PF，`pace_figure_score` evidence
0%、SD 0.00。呢個 test 就係封死呢條靜靜壞嘅路。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[5]
AU_RACING = ROOT / ".agents" / "skills" / "au_racing"
ENGINE = (ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto"
          / "scripts" / "racing_engine")
sys.path.insert(0, str(AU_RACING))
sys.path.insert(0, str(ENGINE))

from claw_sportsbet_form import parse_race, run_line  # noqa: E402
from engine_core import _parse_pf_token  # noqa: E402

PF_TOKEN = re.compile(r"PF\[([^\]]*)\]")


def _run(l600="34.44"):
    return {
        "header": {"track": "Flemington", "going": "Good", "date": "15/07/2026",
                   "race": "3", "dist": "1400"},
        "pos": "3", "field": "11", "margin": "0.42",
        "jockey": "E Pozman", "barrier": "10", "weight": "61.5",
        "prize": "130,000", "sp": "7.50", "l600": l600, "opponents": [],
    }


class PfTokenContractTest(unittest.TestCase):
    def _token(self, run):
        line, _ = run_line(run)
        m = PF_TOKEN.search(line)
        return m.group(1) if m else None

    def test_delta_lands_on_the_key_the_score_reads(self):
        token = self._token(_run())
        self.assertIsNotNone(token, "冇寫到 PF token —— 標準表查唔到 Flemington 1400m？")
        parsed = _parse_pf_token(token)
        self.assertIsNotNone(parsed["l600_delta"],
                             "delta 冇入到 l600_delta —— 段速實速會全場中性 60")

    def test_does_not_park_a_delta_under_the_rating_key(self):
        # `Last600:` 喺 live Formguide 係 PuntingForm 評分（29–93），唔係秒差。
        # 借佢個名擺個 delta 落去，等於將兩把尺溝埋。
        token = self._token(_run())
        self.assertIsNone(_parse_pf_token(token)["l600_time"])

    def test_faster_than_standard_is_negative(self):
        """符號要同引擎一致：`_pace_figure_score` 當**細**嘅 delta 係快。"""
        fast = _parse_pf_token(self._token(_run("30.00")))["l600_delta"]
        slow = _parse_pf_token(self._token(_run("40.00")))["l600_delta"]
        self.assertLess(fast, slow)

    def test_no_sectional_means_no_pf_token(self):
        self.assertIsNone(self._token(_run(None)))


class InRunningContractTest(unittest.TestCase):
    """走位：`Settled` 嗰截係可有可無，但唔可以令成個 In running 讀唔到。

    舊 regex 硬食 `In running 800m`，所以帶 Settled 嗰 33.8% 一條都 match 唔到，
    走位覆蓋率 56.4% → 22.6%，而且 Settled 成個掉咗 —— PI = Settled − Finish，
    冇佢段速分永遠中性 60。
    """

    WITH = ("Finished 3/11 0.42L $11,700 (of $130,000), Jockey E Pozman, "
            "Barrier 10, Weight 61.5kg In running Settled 11th, 800m 9th, 400m 5th")
    WITHOUT = ("Finished 3/11 0.42L $11,700 (of $130,000), Jockey E Pozman, "
               "Barrier 10, Weight 61.5kg In running 800m 9th, 400m 5th")

    def _run(self, body):
        html = ("<html><head><title>Flemington Race 5</title></head><body>"
                "<div>Flemington ( Good ) 15/07/2026 Race 3 1400m BM78</div>"
                f"<div>{body}</div></body></html>")
        runs = parse_race(html)["runs"]
        self.assertTrue(runs, "往績段完全讀唔到")
        return runs[0]

    def test_reads_positions_when_settled_is_present(self):
        r = self._run(self.WITH)
        self.assertEqual((r["p800"], r["p400"]), ("9th", "5th"))
        self.assertEqual(r["settled"], "11th")

    def test_still_reads_positions_when_settled_is_absent(self):
        r = self._run(self.WITHOUT)
        self.assertEqual((r["p800"], r["p400"]), ("9th", "5th"))
        self.assertIsNone(r["settled"])

    def test_settled_reaches_the_line_in_the_form_the_parser_wants(self):
        line, _ = run_line(self._run(self.WITH))
        self.assertRegex(line, r"\d+\w+@Settled")
        # inject_fact_anchors 用 `(\d+)\w+@Settled` 抽數字算 PI
        self.assertEqual(re.search(r"(\d+)\w+@Settled", line).group(1), "11")

    def test_no_settled_token_when_sportsbet_did_not_publish_one(self):
        line, _ = run_line(self._run(self.WITHOUT))
        self.assertNotIn("@Settled", line)


if __name__ == "__main__":
    unittest.main()

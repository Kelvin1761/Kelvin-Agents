"""騎師減磅／超磅由 Sportsbet 一路帶到 Racecard 同引擎（EXP-20261014-02）。

點解要鎖：Sportsbet 個 `W` 係**分配負磅**，減磅另寫喺 `J` 行（`Tom Orr (a-1.5)`）。
抽取層以前剝走個後綴，於是 21.6% 有減磅嘅馬一直被記錄成多揹 1.5–4kg，而引擎
`"(a)" in jockey` 嘅 note 幾乎從來冇觸發。

同時鎖住兩條界線：
  * Racecard `Weight:` 第一個數字**永遠**係分配負磅 —— 下游三個 regex 都攞第一個數字，
    而讓磅代理要嘅正正係讓磅官派嘅磅。
  * 冇調整嘅馬，`Weight:` 欄同舊格式逐字一樣。
"""
from __future__ import annotations

import re
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # .agents/skills/au_racing

import claw_sportsbet_form as claw  # noqa: E402
from au_racing_engine.engine_core import _load_racecard_profiles  # noqa: E402
from au_racing_engine.source_alignment import RACECARD_META_RE  # noqa: E402


def _runner_html(rows):
    cells = []
    for num, name, barrier, jockey, weight in rows:
        cells += [num, name, f"({barrier})", "T", "Some Trainer", "J", jockey, "W", weight,
                  "Prizemoney", "$1,000"]
    return "<html><body>" + "".join(f"<div>{c}</div>" for c in cells) + "</body></html>"


class ParseAllowanceTests(unittest.TestCase):
    def test_apprentice_claim_with_decimal(self) -> None:
        self.assertEqual(claw.parse_jockey_allowance("Anna Roper (a-1.5)"), -1.5)

    def test_apprentice_claim_integer(self) -> None:
        self.assertEqual(claw.parse_jockey_allowance("Jacob Stiff (a-3)"), -3.0)

    def test_raw_anchor_spacing(self) -> None:
        # 連結文字原樣有一大段空白
        self.assertEqual(claw.parse_jockey_allowance("Tom Orr               (a-1.5)"), -1.5)

    def test_no_claim(self) -> None:
        self.assertEqual(claw.parse_jockey_allowance("Adam Sewell"), 0.0)
        self.assertEqual(claw.parse_jockey_allowance("Warwick Satherley ( )"), 0.0)
        self.assertEqual(claw.parse_jockey_allowance(""), 0.0)
        self.assertEqual(claw.parse_jockey_allowance(None), 0.0)

    def test_unsigned_suffix_is_overweight_not_claim(self) -> None:
        # `(a0.5)` 出現喺 James McDonald 呢類資深騎師，52% 喺全場最低磅 = 超磅
        self.assertEqual(claw.parse_jockey_allowance("Chad Schofield (a0.5)"), 0.5)


class CarriedWeightTests(unittest.TestCase):
    def test_claim_reduces_carried(self) -> None:
        self.assertEqual(claw.carried_weight("59.5kg", -1.5), 58.0)
        self.assertEqual(claw.carried_weight(59.0, -3.0), 56.0)

    def test_overweight_increases_carried(self) -> None:
        self.assertEqual(claw.carried_weight("53.0kg", 0.5), 53.5)

    def test_no_claim_carried_equals_allotted(self) -> None:
        self.assertEqual(claw.carried_weight("60.0kg", 0.0), 60.0)

    def test_unknown_allotted(self) -> None:
        self.assertIsNone(claw.carried_weight("?", -1.5))

    def test_format_keeps_allotted_first_and_is_unchanged_without_claim(self) -> None:
        self.assertEqual(claw.format_weight_field("59.0kg", 0.0), "59.0kg")
        self.assertEqual(claw.format_weight_field("59.0kg", None), "59.0kg")
        self.assertEqual(claw.format_weight_field("?", -1.5), "?")
        self.assertEqual(claw.format_weight_field("59.5kg", -1.5),
                         "59.5kg (Claim 1.5kg, Carried 58kg)")
        self.assertEqual(claw.format_weight_field("53.0kg", 0.5),
                         "53.0kg (Overweight 0.5kg, Carried 53.5kg)")


class RunnerBlockTests(unittest.TestCase):
    def test_claim_is_read_from_j_line(self) -> None:
        html = _runner_html([
            ("3", "Claimer Horse", 5, "Anna Roper (a-1.5)", "59.5kg"),
            ("4", "Plain Horse", 2, "Adam Sewell", "59.0kg"),
            ("5", "Junior Horse", 9, "Jacob Stiff (a-3)", "59.0kg"),
        ])
        blocks = {b["name"]: b for b in claw.parse_runner_blocks(html, include_runs=False)}
        self.assertEqual(blocks["Claimer Horse"]["jockey_allowance_kg"], -1.5)
        self.assertEqual(blocks["Claimer Horse"]["stats"]["Weight"], "59.5kg")
        self.assertEqual(blocks["Plain Horse"]["jockey_allowance_kg"], 0.0)
        self.assertEqual(blocks["Junior Horse"]["jockey_allowance_kg"], -3.0)


class DownstreamParserTests(unittest.TestCase):
    META = ("Trainer: A Trainer | Jockey: Anna Roper | Weight: {w} | Age: 4yoG | Rating: 72")

    def test_racecard_meta_regex_reads_allotted_and_claim(self) -> None:
        line = self.META.format(w=claw.format_weight_field("59.5kg", -1.5))
        m = RACECARD_META_RE.match(line)
        self.assertIsNotNone(m)
        self.assertEqual(m.group("weight"), "59.5")
        self.assertEqual(m.group("allowance_label"), "Claim")
        self.assertEqual(m.group("allowance_kg"), "1.5")
        self.assertEqual(m.group("rating"), "72")
        self.assertEqual(m.group("jockey"), "Anna Roper")

    def test_racecard_meta_regex_without_claim(self) -> None:
        m = RACECARD_META_RE.match(self.META.format(w="59.0kg"))
        self.assertEqual(m.group("weight"), "59.0")
        self.assertIsNone(m.group("allowance_kg"))
        self.assertEqual(m.group("rating"), "72")

    def test_first_number_consumers_still_get_allotted(self) -> None:
        # inject_fact_anchors / au_backfill_weights / extract_formguide_data 嘅寫法
        line = self.META.format(w=claw.format_weight_field("59.5kg", -1.5))
        m = re.search(r"Weight:\s*(\d+\.?\d*)\s*(?:kg)?", line)
        self.assertEqual(float(m.group(1)), 59.5)
        # ra_fields 改 Rating 靠 rsplit —— 括號唔可以搶走 Rating
        self.assertEqual(line.rsplit("Rating:", 1)[1].strip(), "72")

    def test_engine_profile_carries_signed_allowance(self) -> None:
        racecard = "\n".join([
            "RACE 1 — 1200m | TEST HANDICAP",
            "=" * 60,
            "1. Claimer Horse (5)",
            self.META.format(w=claw.format_weight_field("59.5kg", -1.5)),
            "-" * 40,
            "2. Plain Horse (2)",
            self.META.format(w="59.0kg"),
            "-" * 40,
            "3. Heavy Jock (7)",
            self.META.format(w=claw.format_weight_field("53.0kg", 0.5)),
            "-" * 40,
        ]) + "\n"
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "10-14 Race 1 Racecard.md").write_text(racecard, encoding="utf-8")
            facts = d / "10-14 Race 1 Facts.md"
            facts.write_text("placeholder", encoding="utf-8")
            profiles = _load_racecard_profiles(facts, 1)
        by = {k: v for k, v in profiles.items()}
        claimer = next(v for k, v in by.items() if "claimer" in k)
        plain = next(v for k, v in by.items() if "plain" in k)
        heavy = next(v for k, v in by.items() if "heavy" in k)
        self.assertEqual(claimer["declared_weight"], 59.5)  # 分配負磅
        self.assertEqual(claimer["jockey_allowance_kg"], -1.5)
        self.assertEqual(claimer["horse_rating"], 72.0)
        self.assertEqual(plain["jockey_allowance_kg"], 0.0)
        self.assertEqual(heavy["jockey_allowance_kg"], 0.5)

    def test_allowance_is_not_a_scored_leaf(self) -> None:
        from au_racing_engine.matrix_mapper import MATRIX_FORMULAS
        leaves = {n for comps in MATRIX_FORMULAS.values() for n, _ in comps}
        self.assertFalse({"jockey_allowance_kg", "carried_weight", "claim_kg"} & leaves)


if __name__ == "__main__":
    unittest.main()

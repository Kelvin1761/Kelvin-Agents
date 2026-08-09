#!/usr/bin/env python3
"""馬群大細正規化（2026-07-31）嘅回歸測試。

覆蓋：
  1. `_parse_field_size` 嘅格式同污染防禦
  2. 有馬群大細時 `_form_score` 改用場內百分位；冇馬群大細時完全沿用絕對名次
  3. Benbulben 個案（6 匹跑第 4 唔再拿中性 base 60）
  4. `form_flattered` 風險旗
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "racing_engine"))

import pytest  # noqa: E402

from engine_core import RacingEngine, _parse_field_size, _record_rows  # noqa: E402

HEADER = (
    "| # | 類型 | 日期 | 場地 | 路程 | 場地狀況 | 檔位 | 名次 | 班次 | 跑位軌跡 "
    "| PI | 段速 | 早段步速 | L600/RT | 走位跑法 | 走位消耗 | 備註 | 寬恕認定 |\n"
    "|---|------|------|------|------|---------|------|------|------|---------"
    "|-----|------|---------|---------|---------|---------|------|----------|\n"
)


def facts(rows):
    body = "".join(
        f"| {i} | Maiden/SW | {date} | {venue} R1 | {dist}m | 6 | 5 | {placing} "
        f"| - | S3→8th3→4th3→F{str(placing).split('/')[0]} | +0 | - | - | - "
        f"| 守中 | 中低 | - | [需判定] |\n"
        for i, (date, venue, dist, placing) in enumerate(rows, 1)
    )
    return "### 馬匹 #1 Test\n" + HEADER + body


def engine_for(rows, *, race_class="BM62", distance="2400m"):
    block = facts(rows)
    horse = {"horse_name": "Test", "barrier": 5, "weight": 58.0,
             "career_race_starts": 14, "career_tag": "ESTABLISHED",
             "_data": {"facts_section": block, "career_record_line": "14:1-1-4"}}
    return RacingEngine(
        horse_data=horse,
        race_context={"race_class": race_class, "distance": distance},
        facts_section=block,
    )


class TestParseFieldSize:
    @pytest.mark.parametrize("cell,expected", [
        ("4/6 (-12.0L)", 6),
        ("6/12 (-9.05L)", 12),
        ("1/7", 7),
        ("2/2", 2),
        ("4 (-12.0L)", None),   # 舊格式：冇馬群大細
        ("-", None),
        ("", None),
        (None, None),
        ("7/6", None),          # 名次大過馬群 = 污染
        ("0/5", None),          # 名次 0 會令百分位變負 → 一定要拒
        ("4/1", None),          # 馬群 < 2
    ])
    def test_parse(self, cell, expected):
        assert _parse_field_size(cell) == expected

    def test_row_parsing_keeps_place_readable(self):
        """嵌入 `/N` 之後，舊 code 用 parse_float 仍然要抓到名次。"""
        from scoring import parse_float
        rows = _record_rows(facts([("2024-08-11", "Casterton", 3500, "4/6 (-12.0L)")]))
        assert len(rows) == 1
        assert parse_float(rows[0][7]) == 4.0


class TestFormScoreUsesFieldSize:
    def test_small_field_midpack_is_not_neutral(self):
        """6 匹跑第 4（百分位 .60）唔應該同 16 匹跑第 4（百分位 .20）一樣。"""
        small = engine_for([("2024-08-11", "Casterton", 3500, "4/6")])
        big = engine_for([("2024-08-11", "Casterton", 3500, "4/16")])
        small._form_score()
        big._form_score()
        assert small.form_detail["rows"][0]["base"] == 40
        assert big.form_detail["rows"][0]["base"] == 75
        assert small.form_detail["final"] < big.form_detail["final"]

    def test_big_field_sixth_is_no_longer_punished_as_last(self):
        """大場跑第 6（百分位 .36）舊階梯係 base 40，應該升到 60。"""
        eng = engine_for([("2024-08-02", "Swan Hill", 2400, "6/15")])
        eng._form_score()
        assert eng.form_detail["rows"][0]["base"] == 60

    def test_absent_field_size_preserves_legacy_ladder(self):
        """舊 meeting 冇 `/N` → 逐檔完全等於原本嘅絕對名次階梯。"""
        for placing, expected in (("1", 100), ("2", 85), ("3", 75),
                                  ("5", 60), ("6", 40)):
            eng = engine_for([("2024-08-02", "Swan Hill", 2400, placing)])
            eng._form_score()
            assert eng.form_detail["rows"][0]["base"] == expected, placing

    def test_field_size_persisted_on_row(self):
        eng = engine_for([("2024-08-11", "Casterton", 3500, "4/6")])
        eng._form_score()
        assert eng.form_detail["rows"][0]["field_size"] == 6


class TestFlatteredFlag:
    def test_flags_run_kept_at_60_despite_big_margin(self):
        """6/15 百分位 .36 → base 60（好睇），但輸 9L → 要標示。"""
        eng = engine_for([("2024-08-02", "Swan Hill", 2400, "6/15 (-9.0L)")])
        eng._form_score()
        assert eng.form_detail["rows"][0]["base"] == 60
        assert "form_flattered" in eng.risk_flags
        assert eng.form_detail["flattered_runs"] == 1

    def test_correctly_downgraded_run_needs_no_flag(self):
        """4/6 而家拿 base 40，分數已經反映現實 → 唔需要「被抬高」旗，
        但大敗場次仍然要計數畀報告用。"""
        eng = engine_for([("2024-08-11", "Casterton", 3500, "4/6 (-12.0L)")])
        eng._form_score()
        assert eng.form_detail["rows"][0]["base"] == 40
        assert "form_flattered" not in eng.risk_flags
        assert eng.form_detail["heavy_defeat_runs"] == 1

    def test_flags_big_margin_even_without_field_size(self):
        """冇馬群大細但輸 >5L 而名次好睇 → 一樣要標示。"""
        eng = engine_for([("2024-08-02", "Swan Hill", 2400, "5 (-9.05L)")])
        eng._form_score()
        assert "form_flattered" in eng.risk_flags

    def test_no_flag_for_genuine_close_finish(self):
        eng = engine_for([("2024-08-02", "Swan Hill", 2400, "2/12 (-0.4L)")])
        eng._form_score()
        assert "form_flattered" not in eng.risk_flags

    def test_flag_does_not_change_the_score(self):
        """標示唔入分：同一場加咗輸距括號，base 同 final 都唔應該變。"""
        plain = engine_for([("2024-08-02", "Swan Hill", 2400, "6/15")])
        flagged = engine_for([("2024-08-02", "Swan Hill", 2400, "6/15 (-9.0L)")])
        plain._form_score()
        flagged._form_score()
        assert plain.form_detail["final"] == flagged.form_detail["final"]
        assert "form_flattered" not in plain.risk_flags
        assert "form_flattered" in flagged.risk_flags


class TestBenbulbenCase:
    """2026-07-31 Geelong R7 #8：兩場 2024 年 Maiden，細場居後 + 大敗。"""

    ROWS = [("2024-08-11", "Casterton", 3500, "4/6 (-12.0L)"),
            ("2024-08-02", "Swan Hill", 2400, "6/12 (-9.05L)")]

    def test_flags_the_run_that_field_size_upgraded(self):
        """Swan Hill 6/12 係馬群大細將 base 由 40 升到 60 嗰場，同時輸 9.05L
        —— 最需要標示嘅正是佢。Casterton 4/6 已經被正確降到 base 40，唔需要旗。"""
        eng = engine_for(self.ROWS)
        eng._form_score()
        bases = [row["base"] for row in eng.form_detail["rows"]]
        assert bases == [40, 60]                       # 一降一升
        assert "form_flattered" in eng.risk_flags
        assert eng.form_detail["flattered_runs"] == 1

    def test_score_moves_the_right_way_overall(self):
        """加馬群大細之後，整體近績分要跌（唔可以因為 6/12 升就淨升）。"""
        legacy = engine_for([("2024-08-11", "Casterton", 3500, "4 (-12.0L)"),
                             ("2024-08-02", "Swan Hill", 2400, "6 (-9.05L)")])
        new = engine_for(self.ROWS)
        legacy._form_score()
        new._form_score()
        assert new.form_detail["final"] < legacy.form_detail["final"]

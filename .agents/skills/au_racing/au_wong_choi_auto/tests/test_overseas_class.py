"""EXP-20261102-11：英愛港法 `CLn`（1 最高）唔可以當澳洲 Class（1 最低）讀。"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from au_racing_engine import overseas  # noqa: E402
from au_racing_engine.engine_core import exact_race_class_level, horse_proven_class_level  # noqa: E402

HEADER = ("| # | 類型 | 日期 | 場地 | 路程 | 場地狀況 | 檔位 | 名次 | 班次 | 跑位軌跡 | PI | 段速 | 早段步速 | L600/RT "
          "| 走位跑法 | 走位消耗 | 備註 | 寬恕認定 | 獎金 | Sportsbet原始班次 |\n|" + "---|" * 20 + "\n")


def row(n, venue, placing, label):
    return (f"| {n} | 正式 | 2026-06-1{n} | {venue} R5 | 2000m | Good | 3 | {placing} | = | F1 | - | 未知 | - | - | - | - "
            f"| - | [-] | 200000 | {label} |\n")


def test_uk_class_one_is_listed_not_bottom():
    assert overseas.normalise_class("CL1", "royal ascot", True) == "LR"
    assert exact_race_class_level(overseas.normalise_class("CL1", "newmarket", True)) > exact_race_class_level("BM78")


def test_australian_class_one_untouched():
    assert overseas.normalise_class("CL1", "kembla grange", False) == "CL1"


def test_perth_ascot_only_overseas_when_horse_raced_abroad():
    assert overseas.normalise_class("CL1", "ascot", False) == "CL1"
    assert overseas.normalise_class("CL1", "ascot", True) == "LR"


def test_hong_kong_class_three():
    assert overseas.normalise_class("CL3 HCP", "sha tin", False) == "BM80"


def test_proven_class_rewards_uk_group_winner_over_au_class_one_winner():
    uk = HEADER + row(1, "Royal Ascot", "1/12", "CL1") + row(2, "Ascot", "2/10", "CL1")
    au = HEADER + row(1, "Kembla Grange", "1/12", "CL1") + row(2, "Ascot", "2/10", "CL1")
    assert horse_proven_class_level(uk) > horse_proven_class_level(au)


def test_mostly_europe_needs_half_of_recent_runs():
    assert overseas.mostly_europe(["goodwood", "ascot", "newbury", "caulfield"])
    assert not overseas.mostly_europe(["caulfield", "flemington", "randwick", "goodwood"])
    assert not overseas.mostly_europe(["sha tin", "sha tin", "happy valley"])   # 香港獎金高，唔替代
    assert not overseas.mostly_europe([])

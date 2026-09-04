"""Do not claim a today-vs-last comparison when today's weight is unpublished.

HKJC releases 排位體重 on raceday morning, so a pre-race run has none. The
function still prepended nothing and then reported `diffs[0]` -- last start vs
the one before -- as 今仗較上仗, and `_candidate_health_risk_score` matched
急劇變化 / 顯著轉重轉輕 off that stale pair. Measured 2026-09-04 on the
2026-09-06 ShaTin card: 30 of 114 runners with a trend were classified from it.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scrape_hkjc_horse_profile.py"
_spec = importlib.util.spec_from_file_location("_hkjc_profile_under_test", SCRIPT)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)
compute_weight_trend = mod.compute_weight_trend


def _entries(*weights):
    return [{"declared_weight": w} for w in weights]


def test_a_big_last_to_previous_jump_is_not_reported_as_today():
    """1210 vs 1190 is +20lb between two PAST starts, not today vs last."""
    out = compute_weight_trend(_entries(1210, 1190, 1190, 1192), None)
    assert "急劇變化" not in out["trend"]
    assert "今仗" not in out.get("detail", "")
    assert out["today_weight_known"] is False


def test_the_same_history_with_today_published_still_reports_it():
    """Once the weight is out the comparison is real and must not be lost."""
    out = compute_weight_trend(_entries(1190, 1190, 1192), today_weight=1210)
    assert out["trend"] == "🔴急劇變化"
    assert "今仗較上仗+20lb" in out["detail"]
    assert out["today_weight_known"] is True


@pytest.mark.parametrize("today,expected", [
    (1201, "🟠顯著轉重"),
    (1179, "🟠顯著轉輕"),
])
def test_the_moderate_band_also_needs_today(today, expected):
    history = _entries(1190, 1190, 1191)
    assert compute_weight_trend(history, today_weight=today)["trend"] == expected
    # Same history, weight unpublished -> falls through to the trend branches.
    unknown = compute_weight_trend(_entries(today, 1190, 1190, 1191), None)
    assert "顯著" not in unknown["trend"]


def test_multi_start_trends_do_not_need_today():
    """These describe history; they were never a today-vs-last claim."""
    rising = compute_weight_trend(_entries(1120, 1116, 1112, 1108), None)
    assert rising["trend"] == "📈持續增磅"
    steady = compute_weight_trend(_entries(1150, 1152, 1151, 1149), None)
    assert steady["trend"] == "📊穩定"


def test_too_little_history_is_still_reported_as_such():
    out = compute_weight_trend(_entries(1150), None)
    assert out["trend"] == "數據不足"
    assert out["today_weight_known"] is False

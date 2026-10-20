"""FW-04 must not treat a decimal point as a sentence end.

2026-10-12 CHI_DEN was blocked for "命中率 **81" repeated 9 times: nine
different legs with 81.0% / 81.2% / 81.8% hit rates, split at the ".".
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from validate_nba_output import check_fw04_padding  # noqa: E402


def _leg(rate: str, player: str) -> str:
    return (
        f"**Leg — {player} PTS**\n"
        f"📊 **MC 模擬 (10,000次)**: 命中率 **{rate}%** | MC Edge: +13.9% ✅\n\n"
    )


def test_distinct_decimal_hit_rates_are_not_padding() -> None:
    content = "".join(
        _leg(rate, f"Player {i}")
        for i, rate in enumerate(["81.0", "81.2", "81.8", "81.4", "81.6", "81.9"])
    )
    assert check_fw04_padding(content) == []


def test_real_padding_is_still_blocked() -> None:
    sentence = "呢場比賽雙方實力非常接近而且節奏好快所以大分機會好高，加上兩隊防守都一般。"
    issues = check_fw04_padding(sentence * 5)
    assert issues and "FW-04" in issues[0]


def test_period_before_text_still_splits_sentences() -> None:
    sentence = "This filler sentence is repeated far too many times here. "
    assert check_fw04_padding(sentence * 5)


# ── Opening night 2026-10-21: every player falls back to the same sample ──
def _card(player: str, team: str, stat: str) -> str:
    return (
        f"#### {player} ({team}) — {stat}\n"
        "資料來源：2025-26 / Playoffs；真實樣本 10 場；截止 10/19/2026。\n"
        f"L10 走勢 {player} 穩定。\n\n"
    )


def test_identical_provenance_lines_are_not_padding() -> None:
    # the sentence runs from the card header through the provenance line
    content = "".join(_card(f"P{i}", "NYK", "PTS") for i in range(7))
    same_header = "".join(
        "#### Same (NYK) — PTS\n資料來源：2025-26 / Playoffs；真實樣本 10 場；截止 10/19/2026。\n"
        for _ in range(7)
    )
    assert check_fw04_padding(content) == []
    assert check_fw04_padding(same_header) == []


def test_non_provenance_repetition_still_blocks_next_to_provenance() -> None:
    padding = "呢個球員近期表現非常穩定而且冇任何傷病影響所以值得考慮落注而且市場賠率亦都合理。"
    content = "".join(_card(f"P{i}", "NYK", "PTS") + padding + "\n" for i in range(5))
    issues = check_fw04_padding(content)
    assert any("FW-04" in i and "表現非常穩定" in i for i in issues)

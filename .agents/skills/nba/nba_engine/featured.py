"""大細盤精選（EXP-20261110-01）：每場一注、每日最多 10 注嘅紙上盤 forward 測試。

Sportsbet 嘅球員大細盤（O/U .5 線）兩邊有價，抽水大約係 milestone 盤嘅一半。每條 O/U 線嘅模型機率
借用同一球員、同一 stat 嘅 milestone 腿：over X.5 == 「ceil(X.5)+」，所以 P(over) = 嗰條腿嘅 p_final。
edge = 模型機率 − 去水機率（去水 = 兩邊隱含機率按比例除返 1）。每場揀 edge 最高嗰一邊，edge ≥ 5pp 先出；
同日超過 10 場就按 edge 取頭 10 注（`daily_top`）。

規則喺 EXP-20261110-01 協議凍結；呢度只係紙上盤，唔會落注，亦唔會影響 B2／SGM。
"""
from __future__ import annotations

import math

from .legs import CATEGORY, LABEL, MARKET

RULE = "nba-featured-ou-v1"
MIN_EDGE = 0.05
MAX_PRICE = 3.0
DAILY_LIMIT = 10


def candidates(odds: dict, legs: list) -> list[dict]:
    """Every scoreable side of every two-way line in one game (both sides, one row each)."""
    by_leg = {(l.player, l.stat, l.line): l for l in legs}
    out = []
    for category, by_player in (odds.get("player_props_two_way") or {}).items():
        stat = CATEGORY.get(category)
        if stat is None:
            continue
        for player, lines in (by_player or {}).items():
            for line_text, prices in (lines or {}).items():
                try:
                    ou = float(line_text)
                    over, under = float(prices["over"]), float(prices["under"])
                except (KeyError, TypeError, ValueError):
                    continue
                if ou.is_integer() or over < 1.01 or under < 1.01:
                    continue
                leg = by_leg.get((player, stat, float(math.ceil(ou))))
                if leg is None or leg.p_final is None or leg.availability != "ok":
                    continue
                fair_over = (1 / over) / (1 / over + 1 / under)
                for side, price, p_model, fair in (("over", over, leg.p_final, fair_over),
                                                   ("under", under, 1 - leg.p_final, 1 - fair_over)):
                    out.append({
                        "rule": RULE, "player": player, "team": leg.team, "market": MARKET[stat],
                        "stat": LABEL[stat], "ou_line": ou, "side": side, "price": price,
                        "other_price": under if side == "over" else over,
                        "p_model": round(p_model, 4), "p_fair": round(fair, 4),
                        "edge": round(p_model - fair, 4), "milestone_line": leg.line,
                    })
    return out


def game_pick(odds: dict, legs: list) -> dict | None:
    """The one featured bet of this game, or None. Ties break on a fixed key, never on order."""
    pool = [c for c in candidates(odds, legs) if c["edge"] >= MIN_EDGE and c["price"] <= MAX_PRICE]
    if not pool:
        return None
    return max(pool, key=lambda c: (c["edge"], c["player"], c["market"], -c["ou_line"], c["side"]))


def daily_top(picks: list[dict], limit: int = DAILY_LIMIT) -> list[dict]:
    """Same-day cap shared by the card, the dashboard and the evaluation."""
    ranked = sorted(picks, key=lambda c: (-c["edge"], str(c.get("game_tag")), c["player"]))
    return ranked[:limit]


def describe(pick: dict) -> str:
    side = "大" if pick["side"] == "over" else "細"
    return f"{pick['player']} {pick['stat']} {side} {pick['ou_line']:g}"

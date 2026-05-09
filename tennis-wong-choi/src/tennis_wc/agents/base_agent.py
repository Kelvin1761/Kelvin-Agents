from __future__ import annotations


class BaseAgent:
    """Stage 5 placeholder. Agents may only read validated feature snapshots."""

    name = "base"

    def review(self, feature_snapshot: dict, pricing: dict | None = None, filter_result: dict | None = None) -> dict:
        raise NotImplementedError


def value(payload, default=None):
    if isinstance(payload, dict) and "value" in payload:
        return payload["value"]
    return payload if payload is not None else default


def pct(number: float | None) -> str:
    if number is None:
        return "N/A"
    return f"{number * 100:.1f}%"


def sample(payload: dict, key: str = "sample_size") -> int | None:
    raw = payload.get(key) or payload.get("matches")
    return value(raw)


def edge_label(score_a: float | None, score_b: float | None, player_a: str = "Player A", player_b: str = "Player B") -> str:
    if score_a is None or score_b is None:
        return "Neutral"
    if abs(score_a - score_b) < 0.03:
        return "Neutral"
    return player_a if score_a > score_b else player_b

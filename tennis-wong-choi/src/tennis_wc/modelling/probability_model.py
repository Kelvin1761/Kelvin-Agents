from __future__ import annotations

from dataclasses import dataclass

from tennis_wc.features.elo import elo_probability


WEIGHTS = {
    "surface_elo_edge": 0.22,
    "overall_elo_edge": 0.10,
    "serve_return_edge": 0.20,
    "recent_form_edge": 0.10,
    "opponent_rank_bucket_edge": 0.10,
    "tournament_level_edge": 0.08,
    "round_performance_edge": 0.05,
    "big_match_edge": 0.05,
    "fatigue_edge": 0.05,
    "injury_penalty": 0.05,
}


@dataclass(frozen=True)
class Component:
    name: str
    probability: float
    weight: float
    reason: str
    warnings: tuple[str, ...] = ()


def _value(payload, default=None):
    if isinstance(payload, dict) and "value" in payload:
        return payload["value"]
    return payload if payload is not None else default


def _clamp(value: float, low: float = 0.05, high: float = 0.95) -> float:
    return max(low, min(high, value))


def _rate_component(a_rate: float | None, b_rate: float | None, name: str, weight: float) -> Component:
    if a_rate is None or b_rate is None:
        return Component(name, 0.5, weight, f"{name}: missing rate, neutralised", ("missing_rate",))
    return Component(name, _clamp(0.5 + (a_rate - b_rate) / 2), weight, f"{name}: compared shrinked rates")


def select_relevant_rank_bucket(opponent_rank: int | None) -> str:
    if opponent_rank is None:
        return "UNKNOWN"
    if opponent_rank <= 10:
        return "TOP_10"
    if opponent_rank <= 25:
        return "TOP_25"
    if opponent_rank <= 50:
        return "TOP_50"
    if opponent_rank <= 100:
        return "TOP_100"
    if opponent_rank <= 200:
        return "RANK_101_200"
    return "RANK_201_PLUS"


def _bucket_rate(player: dict, bucket: str) -> float | None:
    bucket_payload = player.get("opponent_rank_buckets", {}).get(bucket, {})
    return _value(bucket_payload.get("shrinked_win_rate")) or _value(bucket_payload.get("win_rate"))


def _component_probabilities(feature_snapshot: dict) -> list[Component]:
    a = feature_snapshot["player_a"]
    b = feature_snapshot["player_b"]

    a_surface_elo = _value(a.get("surface_elo"))
    b_surface_elo = _value(b.get("surface_elo"))
    a_overall_elo = _value(a.get("overall_elo"))
    b_overall_elo = _value(b.get("overall_elo"))

    components: list[Component] = []
    if a_surface_elo is not None and b_surface_elo is not None:
        components.append(
            Component(
                "surface_elo_edge",
                elo_probability(float(a_surface_elo), float(b_surface_elo)),
                WEIGHTS["surface_elo_edge"],
                "Surface Elo probability from API-fed player stats",
            )
        )
    else:
        components.append(Component("surface_elo_edge", 0.5, WEIGHTS["surface_elo_edge"], "Missing surface Elo", ("missing_surface_elo",)))

    if a_overall_elo is not None and b_overall_elo is not None:
        components.append(
            Component(
                "overall_elo_edge",
                elo_probability(float(a_overall_elo), float(b_overall_elo)),
                WEIGHTS["overall_elo_edge"],
                "Overall Elo probability from API-fed player stats",
            )
        )
    else:
        components.append(Component("overall_elo_edge", 0.5, WEIGHTS["overall_elo_edge"], "Missing overall Elo", ("missing_overall_elo",)))

    a_hold = _value(a.get("tournament_level_stats", {}).get("hold_rate"))
    a_break = _value(a.get("tournament_level_stats", {}).get("break_rate"))
    b_hold = _value(b.get("tournament_level_stats", {}).get("hold_rate"))
    b_break = _value(b.get("tournament_level_stats", {}).get("break_rate"))
    if None not in {a_hold, a_break, b_hold, b_break}:
        a_srv_ret = (float(a_hold) + float(a_break)) / 2
        b_srv_ret = (float(b_hold) + float(b_break)) / 2
        components.append(Component("serve_return_edge", _clamp(0.5 + (a_srv_ret - b_srv_ret)), WEIGHTS["serve_return_edge"], "Serve/return proxy from tournament-level stats"))
    else:
        components.append(Component("serve_return_edge", 0.5, WEIGHTS["serve_return_edge"], "Serve/return API fields incomplete", ("missing_serve_return",)))

    a_recent = _value(a.get("opponent_rank_buckets", {}).get("TOP_100", {}).get("shrinked_win_rate"))
    b_recent = _value(b.get("opponent_rank_buckets", {}).get("TOP_100", {}).get("shrinked_win_rate"))
    components.append(_rate_component(a_recent, b_recent, "recent_form_edge", WEIGHTS["recent_form_edge"]))

    a_rank = _value(a.get("current_rank"))
    b_rank = _value(b.get("current_rank"))
    components.append(
        _rate_component(
            _bucket_rate(a, select_relevant_rank_bucket(b_rank)),
            _bucket_rate(b, select_relevant_rank_bucket(a_rank)),
            "opponent_rank_bucket_edge",
            WEIGHTS["opponent_rank_bucket_edge"],
        )
    )
    components.append(
        _rate_component(
            _value(a.get("tournament_level_stats", {}).get("shrinked_win_rate")),
            _value(b.get("tournament_level_stats", {}).get("shrinked_win_rate")),
            "tournament_level_edge",
            WEIGHTS["tournament_level_edge"],
        )
    )
    components.append(
        _rate_component(
            _value(a.get("round_stats", {}).get("shrinked_win_rate")),
            _value(b.get("round_stats", {}).get("shrinked_win_rate")),
            "round_performance_edge",
            WEIGHTS["round_performance_edge"],
        )
    )
    components.append(
        _rate_component(
            _value(a.get("big_match_stats", {}).get("win_rate")),
            _value(b.get("big_match_stats", {}).get("win_rate")),
            "big_match_edge",
            WEIGHTS["big_match_edge"],
        )
    )
    components.append(Component("fatigue_edge", 0.5, WEIGHTS["fatigue_edge"], "Fatigue data unavailable in Stage 4; neutralised", ("fatigue_unknown",)))
    components.append(Component("injury_penalty", 0.5, WEIGHTS["injury_penalty"], "Injury/news data unavailable in Stage 4; neutralised", ("injury_unknown",)))
    return components


def predict_match_probability(feature_snapshot: dict) -> dict:
    components = _component_probabilities(feature_snapshot)
    active_components = [component for component in components if _is_active_component(component)]
    if not active_components:
        active_components = components
    weighted_probability = sum(component.probability * component.weight for component in active_components)
    total_weight = sum(component.weight for component in active_components)
    probability_a = _clamp(weighted_probability / total_weight, 0.02, 0.98)
    return {
        "player_a_probability": probability_a,
        "player_b_probability": 1 - probability_a,
        "active_weight": total_weight,
        "components": [
            {
                "name": component.name,
                "probability": component.probability,
                "weight": component.weight,
                "active": _is_active_component(component),
                "reason": component.reason,
                "warnings": list(component.warnings),
            }
            for component in components
        ],
    }


def _is_active_component(component: Component) -> bool:
    inactive_warnings = {
        "missing_rate",
        "missing_surface_elo",
        "missing_overall_elo",
        "missing_serve_return",
        "fatigue_unknown",
        "injury_unknown",
    }
    return not any(warning in inactive_warnings for warning in component.warnings)

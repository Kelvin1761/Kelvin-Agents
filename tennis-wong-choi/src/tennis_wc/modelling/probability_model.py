from __future__ import annotations

import math
from dataclasses import dataclass

from tennis_wc.features.elo import elo_probability


# Display/diagnostic weights (used for the component breakdown shown in reports).
# NOTE: these are NO LONGER a linear-average weighting. The combiner is a
# logit-space model: a proven Elo backbone plus modest nudge adjustments so that
# neutral (0.5) components contribute nothing instead of diluting strong signals.
WEIGHTS = {
    "surface_elo_edge": 0.22,
    "overall_elo_edge": 0.10,
    "serve_return_edge": 0.20,
    "recent_form_edge": 0.10,
    "opponent_rank_bucket_edge": 0.10,
    "tournament_level_edge": 0.08,
    "round_performance_edge": 0.05,
    "big_match_edge": 0.05,
    "pressure_edge": 0.06,
    "head_to_head_edge": 0.03,
    "fatigue_edge": 0.05,
    "injury_penalty": 0.05,
}

# Backbone: the walk-forward-calibrated Elo blend (0.65 surface + 0.35 overall)
# scores ~62% favourite accuracy on 11.5k historical matches on its own. It is
# the trusted base probability; everything else only nudges it.
ELO_BACKBONE_WEIGHTS = {
    "surface_elo_edge": 0.65,
    "overall_elo_edge": 0.35,
}

# Nudge gains in logit units per unit of (component_probability - 0.5). A neutral
# component (0.5) adds 0. Gains are deliberately modest so secondary signals
# adjust the Elo base rather than override it. serve/return carries the most
# weight because hold/break is the strongest non-Elo match signal.
NUDGE_GAINS = {
    "serve_return_edge": 1.10,
    "recent_form_edge": 0.55,
    "opponent_rank_bucket_edge": 0.55,
    "tournament_level_edge": 0.35,
    "round_performance_edge": 0.20,
    "big_match_edge": 0.20,
    "pressure_edge": 0.30,
    "head_to_head_edge": 0.45,
    "fatigue_edge": 0.30,
    "injury_penalty": 0.0,
}

# Cap the total nudge so secondary signals cannot fully override the Elo base.
_MAX_TOTAL_NUDGE = 1.20


def _logit(probability: float) -> float:
    p = min(max(probability, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def _sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-value))


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


def _provenance_warnings(payload) -> tuple[str, ...]:
    if isinstance(payload, dict):
        provenance = payload.get("provenance") or {}
        return tuple(provenance.get("warnings") or ())
    return ()


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
    # Prefer the shrinked rate; fall back to raw only when it is genuinely
    # absent. A legitimate 0.0 must NOT be treated as missing (the old `or`
    # discarded a real 0.0 win rate and defeated the shrinkage step).
    shrinked = _value(bucket_payload.get("shrinked_win_rate"))
    if shrinked is not None:
        return shrinked
    return _value(bucket_payload.get("win_rate"))


def _component_probabilities(feature_snapshot: dict) -> list[Component]:
    a = feature_snapshot["player_a"]
    b = feature_snapshot["player_b"]

    a_surface_elo = _value(a.get("surface_elo"))
    b_surface_elo = _value(b.get("surface_elo"))
    a_overall_elo = _value(a.get("overall_elo"))
    b_overall_elo = _value(b.get("overall_elo"))
    surface_elo_warnings = tuple(
        sorted(set([*_provenance_warnings(a.get("surface_elo")), *_provenance_warnings(b.get("surface_elo"))]))
    )
    overall_elo_warnings = tuple(
        sorted(set([*_provenance_warnings(a.get("overall_elo")), *_provenance_warnings(b.get("overall_elo"))]))
    )

    components: list[Component] = []
    if a_surface_elo is not None and b_surface_elo is not None:
        components.append(
            Component(
                "surface_elo_edge",
                elo_probability(float(a_surface_elo), float(b_surface_elo)),
                WEIGHTS["surface_elo_edge"],
                "Surface Elo probability from stored player rating",
                surface_elo_warnings,
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
                "Overall Elo probability from stored player rating",
                overall_elo_warnings,
            )
        )
    else:
        components.append(Component("overall_elo_edge", 0.5, WEIGHTS["overall_elo_edge"], "Missing overall Elo", ("missing_overall_elo",)))

    a_hold = _value(a.get("tournament_level_stats", {}).get("hold_rate"))
    a_break = _value(a.get("tournament_level_stats", {}).get("break_rate"))
    b_hold = _value(b.get("tournament_level_stats", {}).get("hold_rate"))
    b_break = _value(b.get("tournament_level_stats", {}).get("break_rate"))
    if None not in {a_hold, a_break, b_hold, b_break}:
        # hold_rate = fraction of own service games held; break_rate = fraction of
        # opponent service games broken (return games won). Their average is the
        # player's overall game-win rate. Map the rate DIFFERENCE the same way as
        # every other rate component (0.5 + diff/2) so this 0.20-weight signal is
        # not twice as sensitive as the rest (the missing /2 was a scaling bug).
        a_srv_ret = (float(a_hold) + float(a_break)) / 2
        b_srv_ret = (float(b_hold) + float(b_break)) / 2
        components.append(Component("serve_return_edge", _clamp(0.5 + (a_srv_ret - b_srv_ret) / 2), WEIGHTS["serve_return_edge"], "Serve/return proxy from tournament-level stats"))
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
    # Round metadata is unreliable for many fixtures (provisional Sportsbet
    # fixtures carry no confirmed round). When the round is UNKNOWN,
    # calculate_round_stats silently buckets on the player's OTHER unknown-round
    # history, producing a win-rate that has nothing to do with real round
    # context. Treat that as no signal instead of letting a heuristic nudge the
    # price — this matches the report's own "未有可靠來源前唔應該用 heuristic" gate.
    round_code = str(_value(feature_snapshot.get("match_context", {}).get("round")) or "").upper()
    if not round_code or round_code == "UNKNOWN":
        components.append(
            Component(
                "round_performance_edge",
                0.5,
                WEIGHTS["round_performance_edge"],
                "Round metadata unconfirmed; neutralised",
                ("round_unknown",),
            )
        )
    else:
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
    components.append(
        _rate_component(
            _value(a.get("pressure_stats", {}).get("pressure_score")),
            _value(b.get("pressure_stats", {}).get("pressure_score")),
            "pressure_edge",
            WEIGHTS["pressure_edge"],
        )
    )
    h2h_a = _value(a.get("head_to_head", {}).get("win_rate"))
    h2h_b = _value(b.get("head_to_head", {}).get("win_rate"))
    h2h_matches = min(
        int(_value(a.get("head_to_head", {}).get("sample_size"), 0) or 0),
        int(_value(b.get("head_to_head", {}).get("sample_size"), 0) or 0),
    )
    if h2h_a is not None and h2h_b is not None and h2h_matches >= 3:
        components.append(_rate_component(h2h_a, h2h_b, "head_to_head_edge", WEIGHTS["head_to_head_edge"]))
    else:
        components.append(Component("head_to_head_edge", 0.5, WEIGHTS["head_to_head_edge"], "H2H sample below 3; neutralised", ("low_h2h_sample",)))
    a_rest = _value(a.get("fatigue", {}).get("rest_days"))
    b_rest = _value(b.get("fatigue", {}).get("rest_days"))
    if a_rest is not None and b_rest is not None:
        rest_diff = max(-7.0, min(7.0, float(a_rest) - float(b_rest)))
        components.append(Component("fatigue_edge", _clamp(0.5 + rest_diff * 0.015, 0.40, 0.60), WEIGHTS["fatigue_edge"], "Rest-days differential from match history"))
    else:
        components.append(Component("fatigue_edge", 0.5, WEIGHTS["fatigue_edge"], "Fatigue rest-days unavailable; neutralised", ("fatigue_unknown",)))
    components.append(Component("injury_penalty", 0.5, WEIGHTS["injury_penalty"], "Injury/news data unavailable in Stage 4; neutralised", ("injury_unknown",)))
    return components


def _combine_components(components: list[Component]) -> tuple[float, float, float]:
    """
    Logit-space combiner: a calibrated Elo backbone plus modest nudges.

    Returns (probability_a, elo_base_logit, total_nudge).

    Why not a linear average of probabilities? Every component is anchored at
    0.5, so averaging ten components (most neutral) drags a strong Elo edge back
    toward a coin flip and renormalising over active components made *sparser*
    data look *more* confident. Here neutral (0.5) components contribute exactly
    0 in logit space, so they neither dilute nor inflate. The Elo blend is the
    trusted base; secondary signals only nudge it.
    """
    by_name = {component.name: component for component in components}

    # --- Elo backbone (renormalised over whichever Elo components are present) ---
    base_logit = 0.0
    backbone_weight = 0.0
    for name, weight in ELO_BACKBONE_WEIGHTS.items():
        component = by_name.get(name)
        if component is None or not _is_active_component(component):
            continue
        base_logit += weight * _logit(component.probability)
        backbone_weight += weight
    if backbone_weight > 0:
        base_logit /= backbone_weight  # average of available Elo logits

    # --- Nudges from secondary signals (neutral components add 0) ---
    total_nudge = 0.0
    for name, gain in NUDGE_GAINS.items():
        if gain == 0.0:
            continue
        component = by_name.get(name)
        if component is None or not _is_active_component(component):
            continue
        total_nudge += gain * (component.probability - 0.5)
    total_nudge = max(-_MAX_TOTAL_NUDGE, min(_MAX_TOTAL_NUDGE, total_nudge))

    # When the Elo backbone is missing, fall back to the nudges alone (still
    # shrunk because each gain is modest and there is no strong base).
    probability_a = _clamp(_sigmoid(base_logit + total_nudge), 0.02, 0.98)
    return probability_a, base_logit, total_nudge


def predict_match_probability(feature_snapshot: dict) -> dict:
    components = _component_probabilities(feature_snapshot)
    active_components = [component for component in components if _is_active_component(component)]
    probability_a, base_logit, total_nudge = _combine_components(components)
    total_weight = sum(component.weight for component in active_components)
    return {
        "player_a_probability": probability_a,
        "player_b_probability": 1 - probability_a,
        "active_weight": total_weight,
        "elo_base_logit": round(base_logit, 6),
        "total_nudge_logit": round(total_nudge, 6),
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
        "round_unknown",
    }
    return not any(warning in inactive_warnings for warning in component.warnings)

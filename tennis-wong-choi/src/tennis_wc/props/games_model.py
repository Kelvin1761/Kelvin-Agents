"""Total-match-games prop model.

Unlike aces (a per-player serve stat in history), total games is not stored per
player, so we calibrate on the tennisdata xlsx (~19,406 completed matches) using
the one predictor available BOTH there and live: match COMPETITIVENESS. Closer
matches go long (more third sets, tighter sets) -> more games.

  closeness = 1 - |2*p_fav - 1|         (1 = coin-flip, 0 = lock)
  predicted_mean = MEAN_BY_CLOSENESS[(best_of, closeness_bucket)]
  P(total > line) = interp(GAMES_CURVE, ratio = line / predicted_mean)

Both tables are embedded below; rebuild with scripts/build_games_calibration.py.
v1 uses competitiveness + best_of only. Serve-dominance (hold rates) is a known
second-order driver and a future enhancement -- the scorecard will show whether
this simpler model already beats the market before we add complexity.
"""
from __future__ import annotations

from tennis_wc.props.ace_model import price_two_way, TwoWayProp

# E[total games] by (best_of, closeness bucket of 0.2). Fit on 19,406 matches.
MEAN_BY_CLOSENESS: dict[tuple[int, float], float] = {
    (3, 0.0): 17.84, (3, 0.2): 20.11, (3, 0.4): 21.79, (3, 0.6): 22.89,
    (3, 0.8): 23.31, (3, 1.0): 23.41,
    (5, 0.0): 29.79, (5, 0.2): 33.84, (5, 0.4): 36.49, (5, 0.6): 38.63,
    (5, 0.8): 38.29, (5, 1.0): 40.30,
}
# ratio = line / predicted_mean -> realised P(total games > line). n>=300/bucket.
GAMES_CURVE: list[tuple[float, float]] = [
    (0.60, 0.9899), (0.65, 0.9588), (0.70, 0.9038), (0.75, 0.8216),
    (0.80, 0.7390), (0.85, 0.6521), (0.90, 0.5645), (0.95, 0.4846),
    (1.00, 0.4261), (1.05, 0.3822), (1.10, 0.3300), (1.15, 0.2877),
    (1.20, 0.2449), (1.25, 0.1965), (1.30, 0.1596), (1.35, 0.1255),
    (1.40, 0.0877), (1.45, 0.0591),
]
_GAMES_LINE_RATIO = 1.45  # curve is trustworthy out to 1.45x the mean


def predict_total_games(match_prob: float | None, best_of: int = 3) -> float | None:
    """Expected total match games from the favourite's win probability."""
    if match_prob is None:
        return None
    p = float(match_prob)
    closeness = 1.0 - abs(2 * p - 1)
    bucket = round(closeness * 5) / 5
    bo = 5 if best_of == 5 else 3
    return MEAN_BY_CLOSENESS.get((bo, bucket)) or MEAN_BY_CLOSENESS.get((bo, 0.6))


def price_games_two_way(match_id: int, market_key: str, line: float,
                        over_odds: float, under_odds: float,
                        match_prob: float | None, best_of: int = 3,
                        temper: float = 0.0) -> TwoWayProp | None:
    pred = predict_total_games(match_prob, best_of)
    if pred is None:
        return None
    return price_two_way(match_id, market_key, "match_games", line, over_odds,
                         under_odds, pred, GAMES_CURVE,
                         factors={"match_prob": match_prob, "best_of": best_of},
                         within_range_ratio=_GAMES_LINE_RATIO, temper=temper)

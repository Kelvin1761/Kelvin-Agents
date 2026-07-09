"""Prop probability recalibration -- keeps displayed EV honest.

The ace/games curves are calibrated on history, but LIVE props are a selected
subsample (books only offer ace lines on big servers, etc.), so the raw model
probability can be over-confident at the extremes (observed: model 70% -> 50%
realised on a tiny sample). Over-confident P => over-stated EV, and EV drives
staking, so this matters.

Fix = a TEMPER applied to the model probability before edge/EV:
    tempered = 0.5 + (p - 0.5) * (1 - strength)
strength in [0,1); larger = pull toward a coin flip = less confident = lower EV.

The strength is chosen from the live scorecard, and is DELIBERATELY conservative
until we have enough settled props to trust our own edge (avoids overfitting a
correction to n=12):

  * n < MIN_SETTLED             -> DEFAULT_STRENGTH (0.15): mild haircut, unproven.
  * n >= MIN_SETTLED, model Brier clearly < market -> LOW_STRENGTH (0.05): our
    edge is validated, trust it more (EV can stand almost as-is).
  * n >= MIN_SETTLED, model NOT better than market -> HIGH_STRENGTH (0.35): the
    model is not beating the market, so shrink hard (EV was fantasy).

So EV self-corrects as real results arrive, instead of being hand-tuned now.
"""
from __future__ import annotations

MIN_SETTLED = 120
DEFAULT_STRENGTH = 0.15
LOW_STRENGTH = 0.05
HIGH_STRENGTH = 0.35
_BRIER_MARGIN = 0.01


def temper_probability(prob: float, strength: float) -> float:
    strength = max(0.0, min(0.95, strength))
    return 0.5 + (prob - 0.5) * (1.0 - strength)


def current_strength(conn) -> float:
    """Pick the temper strength from the live model-vs-market scorecard."""
    try:
        from tennis_wc.props.settlement import model_vs_market_scorecard
        sc = model_vs_market_scorecard(conn)
    except Exception:
        return DEFAULT_STRENGTH
    n = sc.get("settled", 0)
    model, market = sc.get("model"), sc.get("market")
    if n < MIN_SETTLED or not model or not market:
        return DEFAULT_STRENGTH
    if model["brier"] < market["brier"] - _BRIER_MARGIN:
        return LOW_STRENGTH        # validated edge -> trust model
    if market["brier"] < model["brier"] - _BRIER_MARGIN:
        return HIGH_STRENGTH       # model loses to market -> shrink hard
    return DEFAULT_STRENGTH


def strength_note(strength: float, conn=None) -> str:
    n = None
    try:
        from tennis_wc.props.settlement import model_vs_market_scorecard
        n = model_vs_market_scorecard(conn).get("settled") if conn is not None else None
    except Exception:
        pass
    tag = {LOW_STRENGTH: "已驗證·輕", DEFAULT_STRENGTH: "未驗證·保守",
           HIGH_STRENGTH: "跑輸市場·大幅收"}.get(strength, "自訂")
    base = f"EV 已用校準機率（temper {strength:.0%}｜{tag}）"
    return base + (f"；已結算 {n} 條" if n is not None else "")

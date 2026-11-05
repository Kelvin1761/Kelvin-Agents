from __future__ import annotations


def segment_risk(tour: str | None, level: str | None) -> tuple[str, float]:
    """
    Classify a match segment into a risk label + a LIGHT model-probability
    discount.

    The book skews toward WTA / smaller events; those segments are
    higher-variance and the Elo is noisier (thin lower-tier data), so the
    model's edges there are the least reliable. We DON'T drop them — we flag
    them and shrink the model probability a little toward the market price so
    they rank slightly lower and stake a little less. Discount is intentionally
    light.

    This is the single source of truth for segment risk. It is applied once, at
    pricing time (see `pricing.price_match_snapshot`), so the single-bet card,
    the bet filter, the stake, and the predictions-backed combos all agree. The
    raw market-path combo pool applies it separately because it never passes
    through the pricing layer.
    """
    lvl = str(level or "").upper().replace(" ", "_")
    if not lvl or lvl in {"UNKNOWN", "未確認"} or any(k in lvl for k in ("CHALLENGER", "ITF", "FUTURES", "UTR", "125")):
        return ("⚠高波動/低數據", 0.12)
    if "GRAND_SLAM" in lvl or "1000" in lvl or "FINALS" in lvl or "500" in lvl:
        return ("", 0.0)
    if "250" in lvl:
        return ("中波動(250)", 0.05)
    return ("中波動", 0.05)


def apply_segment_risk(prob: float, edge: float, no_vig: float | None, discount: float) -> tuple[float, float]:
    """Light shrink of the model probability toward the no-vig market price for
    high-risk segments (edge *= 1-discount). No-op when discount is 0 or no
    market price is available."""
    if discount <= 0 or no_vig is None:
        return prob, edge
    adj_prob = no_vig + (prob - no_vig) * (1 - discount)
    return adj_prob, edge * (1 - discount)

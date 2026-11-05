"""Market side of a price: de-vig, and how far to trust the model over it.

``family_weight`` is the per-family share of the model in the blended
probability, learnt from settled point-in-time props before ``as_of_date``:
the least-squares slope of (result - market) on (model - market), shrunk by
n / (n + 100). Under 20 settled rows it is 0.10. The blend only sizes a bet;
whether a side is value is decided on the raw model (see pricing.families).
"""
from __future__ import annotations

DEFAULT_MODEL_WEIGHT = 0.10
MIN_WEIGHT_SAMPLE = 20
WEIGHT_EVIDENCE_PRIOR = 100.0
MIN_SOURCE_QUALITY = 0.65


def devig(a_odds: float, b_odds: float) -> float:
    """Fair probability of side A from a two-way price (proportional)."""
    a, b = 1.0 / a_odds, 1.0 / b_odds
    return a / (a + b)


def blend(raw_probability: float, market_probability: float, model_weight: float) -> float:
    weight = max(0.0, min(1.0, float(model_weight)))
    raw = max(0.001, min(0.999, float(raw_probability)))
    market = max(0.001, min(0.999, float(market_probability)))
    return market + weight * (raw - market)


def family_weight(conn, family: str, as_of_date: str) -> float:
    from tennis_wc.pricing.families import family_for_market
    from tennis_wc.store.evidence import read_evidence
    from tennis_wc.store.results import result_agreement_clause

    rows = conn.execute(f"""
        SELECT p.market_key, p.model_prob_raw, p.market_prob_fair, p.result_status,
               p.feed_market_name, p.pricing_evidence_json
        FROM prop_tracker p JOIN matches m ON m.id = p.match_id
        WHERE p.result_status IN ('WON','LOST')
          AND p.is_point_in_time = 1
          AND {result_agreement_clause('p')}
          AND p.model_prob_raw IS NOT NULL AND p.market_prob_fair IS NOT NULL
          AND p.side = 'over'
          AND (p.prop_scope != 'player_first_set' OR p.subject_player_id = m.player_a_id)
          AND p.match_date < ? AND julianday(p.settled_at) < julianday(?)
        ORDER BY p.match_date, p.id
        """, (as_of_date, as_of_date)).fetchall()
    numerator = denominator = 0.0
    n = 0
    for row in rows:
        if family_for_market(row["market_key"]) != family:
            continue
        if _legacy_contract_excluded(row):
            continue
        evidence = read_evidence(row["pricing_evidence_json"])
        quality = evidence.get("source_quality") if evidence else None
        if quality is None or float(quality) < MIN_SOURCE_QUALITY:
            continue
        raw = float(row["model_prob_raw"])
        market = float(row["market_prob_fair"])
        actual = 1.0 if row["result_status"] == "WON" else 0.0
        residual = raw - market
        numerator += (actual - market) * residual
        denominator += residual * residual
        n += 1
    if n < MIN_WEIGHT_SAMPLE:
        return DEFAULT_MODEL_WEIGHT
    raw_weight = max(0.0, min(1.0, numerator / denominator)) if denominator else 0.0
    return round(raw_weight * n / (n + WEIGHT_EVIDENCE_PRIOR), 6)


def _legacy_contract_excluded(row) -> bool:
    """Old match-total rows whose contract could not be verified (prop-contract-v1)."""
    from tennis_wc.pricing.families import family_for_market

    key = str(row["market_key"] or "").lower()
    if key == "total_games" and not row["feed_market_name"]:
        return True
    return (family_for_market(key) == "match_total_games"
            and bool(row["feed_market_name"])
            and family_for_market("", row["feed_market_name"]) == "player_total_games")

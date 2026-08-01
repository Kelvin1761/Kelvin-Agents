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

from dataclasses import dataclass

from tennis_wc.props.registry import family_for_market

MIN_SETTLED = 120
DEFAULT_STRENGTH = 0.15
LOW_STRENGTH = 0.05
HIGH_STRENGTH = 0.35
_BRIER_MARGIN = 0.01

# A new family gets only a small research weight.  Once 20 quality-qualified
# outcomes exist, the weight is learned from prior rows only.  The 100-row
# denominator is a pre-registered evidence shrink: a spectacular coefficient
# on ten observations must not be treated like one learned on hundreds.
DEFAULT_MODEL_WEIGHT = 0.10
MIN_WEIGHT_SAMPLE = 20
WEIGHT_EVIDENCE_PRIOR = 100.0


@dataclass(frozen=True)
class FamilyReliability:
    family: str
    as_of_date: str | None
    settled: int
    raw_weight: float
    model_weight: float
    model_brier: float | None
    market_brier: float | None

    @property
    def evidence_ratio(self) -> float:
        return min(1.0, self.settled / MIN_SETTLED)


def blend_with_market(raw_probability: float, market_probability: float,
                      model_weight: float) -> float:
    """Reliability-weighted probability used for value and EV.

    Unlike the old coin-flip temper, this always shrinks along the line from
    the odds-blind model to the de-vigged market.  It therefore cannot cross the
    market and manufacture an opinion on the opposite side.
    """
    weight = max(0.0, min(1.0, float(model_weight)))
    raw = max(0.001, min(0.999, float(raw_probability)))
    market = max(0.001, min(0.999, float(market_probability)))
    return market + weight * (raw - market)


def family_reliability(conn, family: str, as_of_date: str | None = None) -> FamilyReliability:
    """Fit a causal model-vs-market residual weight for one prop family.

    The coefficient minimises Brier loss for
    ``market + weight * (raw_model - market)``.  Only canonical, settled,
    quality-qualified rows strictly before ``as_of_date`` are eligible, so a
    historical replay never sees its own or future outcomes.
    """
    try:
        params: list = []
        date_clause = ""
        if as_of_date:
            date_clause = "AND p.match_date < ?"
            params.append(as_of_date)
        rows = conn.execute(
            f"""
            WITH quality AS (
                SELECT match_id, MIN(data_quality_score) AS score
                FROM feature_snapshots GROUP BY match_id
            )
            SELECT p.match_id, p.match_date, p.market_key, p.model_prob_raw,
                   p.market_prob_fair, p.result_status, q.score AS data_quality,
                   p.subject_player_id, m.player_a_id, m.player_b_id
            FROM prop_tracker p
            JOIN matches m ON m.id=p.match_id
            LEFT JOIN quality q ON q.match_id=p.match_id
            WHERE p.result_status IN ('WON','LOST')
              AND p.model_prob_raw IS NOT NULL
              AND p.market_prob_fair IS NOT NULL
              AND p.side='over'
              AND (p.prop_scope!='player_first_set'
                   OR p.subject_player_id=m.player_a_id)
              {date_clause}
            ORDER BY p.match_date,p.id
            """,
            tuple(params),
        ).fetchall()
    except Exception:
        rows = []
    serve_count_families = {
        "player_aces", "match_total_aces", "player_double_faults"
    }
    serve_quality_cache: dict[tuple[int, str, str], float] = {}

    def serve_quality(row, row_family: str) -> float:
        if row_family == "match_total_aces":
            player_ids = (row["player_a_id"], row["player_b_id"])
            column = "ace_count"
        elif row_family == "player_aces":
            subject = row["subject_player_id"]
            opponent = (
                row["player_b_id"]
                if subject == row["player_a_id"] else row["player_a_id"]
            )
            player_ids = (subject, opponent)
            column = "ace_count"
        else:
            player_ids = (row["subject_player_id"],)
            column = "double_fault_count"
        counts = []
        for player_id in player_ids:
            if player_id is None:
                return 0.0
            key = (int(player_id), str(row["match_date"]), column)
            if key not in serve_quality_cache:
                serve_quality_cache[key] = conn.execute(
                    f"SELECT COUNT(*) FROM (SELECT 1 FROM player_match_history "
                    f"WHERE player_id=? AND match_date<? AND {column} IS NOT NULL "
                    "ORDER BY match_date DESC LIMIT 15)",
                    (player_id, row["match_date"]),
                ).fetchone()[0] / 15.0
            counts.append(serve_quality_cache[key])
        return min(counts, default=0.0)

    sample = []
    for row in rows:
        row_family = family_for_market(row["market_key"])
        if row_family != family:
            continue
        quality = float(row["data_quality"] or 0)
        if quality > 1:
            quality /= 100
        # Serve-count models use their own causal history profiles and do not
        # consume the match feature snapshot.  Grade them on the exact serve
        # history available before that match, not an unrelated quality score.
        if (
            serve_quality(row, row_family) >= 0.65
            if row_family in serve_count_families else quality >= 0.65
        ):
            sample.append(row)
    n = len(sample)
    if not sample:
        return FamilyReliability(
            family, as_of_date, 0, DEFAULT_MODEL_WEIGHT, DEFAULT_MODEL_WEIGHT,
            None, None,
        )
    numerator = denominator = model_error = market_error = 0.0
    for row in sample:
        raw = float(row["model_prob_raw"])
        market = float(row["market_prob_fair"])
        actual = 1.0 if row["result_status"] == "WON" else 0.0
        residual = raw - market
        numerator += (actual - market) * residual
        denominator += residual * residual
        model_error += (raw - actual) ** 2
        market_error += (market - actual) ** 2
    raw_weight = max(0.0, min(1.0, numerator / denominator)) if denominator else 0.0
    if n < MIN_WEIGHT_SAMPLE:
        model_weight = DEFAULT_MODEL_WEIGHT
    else:
        model_weight = raw_weight * n / (n + WEIGHT_EVIDENCE_PRIOR)
    return FamilyReliability(
        family=family,
        as_of_date=as_of_date,
        settled=n,
        raw_weight=round(raw_weight, 6),
        model_weight=round(model_weight, 6),
        model_brier=round(model_error / n, 6),
        market_brier=round(market_error / n, 6),
    )


def reliability_note(profile: FamilyReliability) -> str:
    if profile.settled < MIN_WEIGHT_SAMPLE:
        state = "樣本不足"
    elif (
        profile.model_brier is not None and profile.market_brier is not None
        and profile.model_brier < profile.market_brier - 0.005
    ):
        state = "模型有初步增量"
    else:
        state = "市場較可靠"
    return (
        f"{profile.family}: 模型權重 {profile.model_weight:.0%}｜"
        f"先前已結算 {profile.settled}｜{state}"
    )


def temper_probability(prob: float, strength: float) -> float:
    strength = max(0.0, min(0.95, strength))
    return 0.5 + (prob - 0.5) * (1.0 - strength)


def current_strength(conn) -> float:
    """Pick the temper strength from the live model-vs-market scorecard.

    Reads the RAW scorecard on purpose. Until 2026-07-25 the stored "model"
    probability WAS the tempered one, so this function chose a haircut by looking
    at numbers that already had that haircut baked in -- a feedback loop that could
    never report the model getting better or worse on its own merits. Grading the
    odds-blind column makes the decision independent of its own output.
    """
    try:
        from tennis_wc.props.settlement import model_vs_market_scorecard
        sc = model_vs_market_scorecard(conn, use_raw=True)
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

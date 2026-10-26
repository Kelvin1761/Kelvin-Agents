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

from tennis_wc.evaluation.corpus import point_in_time_clause
from tennis_wc.database.result_consensus import result_agreement_clause
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
    unverified_quality_rows: int = 0
    contract_excluded_rows: int = 0

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

    2026-08-26: `as_of_date` was never enough. It keeps a REPLAY honest about
    match dates, and says nothing about when the row was written -- and 9,594 of
    13,658 rows were written by one backfill run after their results were known.
    Those rows had been supplying most of the evidence behind every learned
    weight, so the weights were fitted on prices chosen with hindsight. Only
    provably pre-match rows are eligible now (`evaluation/corpus.py`); expect
    far smaller samples and more families sitting on DEFAULT_MODEL_WEIGHT, which
    is the honest state rather than a regression.
    """
    from tennis_wc.props.pricing_evidence import read_evidence

    columns = {row['name'] for row in conn.execute('PRAGMA table_info(prop_tracker)')}
    receipt = 'p.pricing_evidence_json' if 'pricing_evidence_json' in columns else 'NULL'
    params: list = []
    date_clause = ""
    if as_of_date:
        date_clause = "AND p.match_date < ? AND julianday(p.settled_at) < julianday(?)"
        params.extend((as_of_date, as_of_date))
    rows = conn.execute(
        f"""
        SELECT p.id,p.feed_market_name,p.match_id,p.match_date,p.market_key,p.model_prob_raw,
               p.market_prob_fair,p.result_status,{receipt} AS pricing_evidence_json
        FROM prop_tracker p
        JOIN matches m ON m.id=p.match_id
        WHERE p.result_status IN ('WON','LOST')
          AND {point_in_time_clause('p')}
          AND {result_agreement_clause('p')}
          AND p.model_prob_raw IS NOT NULL AND p.market_prob_fair IS NOT NULL
          AND p.side='over'
          AND (p.prop_scope!='player_first_set' OR p.subject_player_id=m.player_a_id)
          {date_clause}
        ORDER BY p.match_date,p.id
        """, tuple(params),
    ).fetchall()
    from tennis_wc.props.evidence_contract import verified_contract_rows
    rows, contract_audit = verified_contract_rows(rows)
    excluded = len(contract_audit['excluded']) if family == 'match_total_games' else 0
    sample = []
    unverified = 0
    for row in rows:
        if family_for_market(row['market_key']) != family:
            continue
        evidence = read_evidence(row['pricing_evidence_json'])
        quality = evidence.get('source_quality') if evidence else None
        # Legacy rows retain their raw scorecard, but later rebuilds cannot
        # manufacture evidence of the quality actually used when priced.
        if quality is None:
            unverified += 1
        if quality is not None and float(quality) >= 0.65:
            sample.append(row)
    n = len(sample)
    if not sample:
        return FamilyReliability(
            family, as_of_date, 0, DEFAULT_MODEL_WEIGHT, DEFAULT_MODEL_WEIGHT,
            None, None, unverified, excluded,
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
        unverified_quality_rows=unverified,
        contract_excluded_rows=excluded,
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
        f"先前已結算 {profile.settled}｜{state}｜品質證據未核實 {profile.unverified_quality_rows}"
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

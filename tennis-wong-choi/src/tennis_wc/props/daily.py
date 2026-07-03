"""Daily ace-prop pricing entry point: read Sportsbet's offered 'N+' ace ladders
for a date, price them with the calibrated model, log every surfaced prop to
prop_tracker (PENDING), and return structured results for the report."""
from __future__ import annotations

from dataclasses import dataclass, field

from tennis_wc.props import ace_model
from tennis_wc.props.settlement import record_prop

_ACE_MARKET = "total_aces_in_the_match"


@dataclass
class MatchAceProps:
    match_id: int
    match_label: str
    predicted_mean: float
    legs: list  # PricedAceLeg
    anchor: object | None = None
    factors: dict = field(default_factory=dict)


def _offered_ace_lines(conn, match_date: str) -> dict[int, dict[float, float]]:
    """{match_id: {line: latest decimal_odds}} for the ace market on a date."""
    rows = conn.execute(
        """
        SELECT mo.match_id, mo.line, mo.odds, mo.id
        FROM market_odds_snapshots mo
        JOIN matches m ON m.id = mo.match_id
        WHERE m.match_date = ? AND mo.market_key = ? AND mo.line IS NOT NULL
        ORDER BY mo.id ASC
        """,
        (match_date, _ACE_MARKET),
    ).fetchall()
    out: dict[int, dict[float, float]] = {}
    for r in rows:
        out.setdefault(r["match_id"], {})[float(r["line"])] = float(r["odds"])  # later id wins
    return out


def _match_meta(conn, match_id: int) -> dict | None:
    return conn.execute(
        """
        SELECT m.id, m.player_a_id, m.player_b_id, m.match_date,
               pa.name AS a_name, pb.name AS b_name,
               (SELECT tl.surface FROM tournament_levels tl
                 WHERE tl.tournament_id = m.tournament_id AND tl.surface IS NOT NULL
                 ORDER BY tl.id DESC LIMIT 1) AS surface
        FROM matches m
        JOIN players pa ON pa.id = m.player_a_id
        JOIN players pb ON pb.id = m.player_b_id
        WHERE m.id = ?
        """,
        (match_id,),
    ).fetchone()


def price_ace_props_for_date(conn, match_date: str, log: bool = True) -> list[MatchAceProps]:
    """Price every match that has an ace ladder on match_date. Logs surfaced
    props to prop_tracker unless log=False (used by tests)."""
    offered = _offered_ace_lines(conn, match_date)
    results: list[MatchAceProps] = []
    for match_id, lines in offered.items():
        meta = _match_meta(conn, match_id)
        if not meta:
            continue
        legs = ace_model.price_ace_legs(
            conn, match_id, meta["player_a_id"], meta["player_b_id"],
            meta["match_date"], meta["surface"], lines,
        )
        if not legs:
            continue
        label = f"{meta['a_name']} vs {meta['b_name']}"
        anchor = ace_model.anchor_leg(legs)
        mp = MatchAceProps(
            match_id=match_id, match_label=label,
            predicted_mean=legs[0].predicted_mean, legs=legs, anchor=anchor,
            factors=legs[0].factors,
        )
        results.append(mp)
        if log:
            for lg in legs:
                # log the value legs + the anchor (avoid flooding with every rung)
                if not (lg.is_value or (anchor is not None and lg.line == anchor.line)):
                    continue
                record_prop(
                    conn, match_id=match_id, match_date=match_date, match_label=label,
                    market_key=_ACE_MARKET, line=lg.line, selection=f"{int(lg.line)}+",
                    decimal_odds=lg.decimal_odds, model_prob=lg.model_prob,
                    market_prob_fair=lg.market_prob_fair, blended_prob=lg.blended_prob,
                    edge=lg.edge, ev=lg.ev, predicted_mean=lg.predicted_mean,
                    stake_units=1.0, is_value=lg.is_value,
                )
    if log:
        conn.commit()
    results.sort(key=lambda m: -(m.anchor.blended_prob if m.anchor else 0))
    return results

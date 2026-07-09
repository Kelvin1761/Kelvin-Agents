"""Daily ace-prop pricing entry point.

Prices three ace market families off the soft book (Sportsbet) for a date:
  * total_aces_in_the_match  -> one-way 'N+' ladder (legacy, flat de-vig)
  * total_aces_<X>_5         -> MATCH total O/U (clean two-way de-vig)
  * total_<player>_aces_<X>_5 -> single-PLAYER O/U (truest NBA prop)

Every priced two-way market is logged to prop_tracker: the OVER side always
(so the model-vs-market scorecard has data regardless of whether we bet), plus
the VALUE side (over or under) when the model flags edge. Under is where the
model tends to see value (it thinks aces come in below the book's line)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from tennis_wc.props import ace_model
from tennis_wc.props import games_model
from tennis_wc.props.settlement import record_prop

_LADDER_MARKET = "total_aces_in_the_match"
_MATCH_OU = re.compile(r"^total_aces_\d+_5$")
_PLAYER_OU = re.compile(r"^total_(?P<name>[a-z0-9_]+)_aces_\d+_5$")
_MATCH_GAMES_OU = re.compile(r"^total_match_games_\d+_5$")


@dataclass
class AcePropBoard:
    match_id: int
    match_label: str
    predicted_match_mean: float
    ladder_legs: list = field(default_factory=list)     # PricedAceLeg (over-only N+)
    match_ou: list = field(default_factory=list)        # TwoWayProp (aces)
    player_ou: list = field(default_factory=list)        # TwoWayProp (player aces)
    games_ou: list = field(default_factory=list)        # TwoWayProp (total match games)
    predicted_games: float | None = None
    anchor: object | None = None


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _match_meta(conn, match_id: int):
    return conn.execute(
        """
        SELECT m.id, m.player_a_id, m.player_b_id, m.match_date,
               pa.name AS a_name, pb.name AS b_name,
               (SELECT tl.surface FROM tournament_levels tl
                 WHERE tl.tournament_id = m.tournament_id AND tl.surface IS NOT NULL
                 ORDER BY tl.id DESC LIMIT 1) AS surface
        FROM matches m JOIN players pa ON pa.id = m.player_a_id
                       JOIN players pb ON pb.id = m.player_b_id
        WHERE m.id = ?
        """,
        (match_id,),
    ).fetchone()


def _rows_for_date(conn, match_date: str):
    return conn.execute(
        """
        SELECT mo.match_id, mo.market_key, mo.market_name, mo.selection_name,
               mo.line, mo.odds, mo.id
        FROM market_odds_snapshots mo JOIN matches m ON m.id = mo.match_id
        WHERE m.match_date = ? AND (mo.market_key = ? OR mo.market_key LIKE 'total_%aces_%'
                                    OR mo.market_key LIKE 'total_match_games_%')
        ORDER BY mo.id ASC
        """,
        (match_date, _LADDER_MARKET),
    ).fetchall()


def _match_prob_map(conn, match_date: str) -> dict:
    """Latest model match-win probability per match (for games competitiveness)."""
    rows = conn.execute(
        """
        SELECT p.match_id, p.model_probability
        FROM predictions p JOIN matches m ON m.id = p.match_id
        WHERE m.match_date = ? AND p.id IN (SELECT MAX(id) FROM predictions GROUP BY match_id)
        """,
        (match_date,),
    ).fetchall()
    return {r["match_id"]: r["model_probability"] for r in rows if r["model_probability"] is not None}


def _two_way_odds(rows):
    """Group two-way O/U rows -> {(match_id, market_key, line): {'over':o, 'under':o, 'name':mn}}."""
    ou: dict = {}
    for r in rows:
        name = str(r["selection_name"] or "")
        low = name.lower()
        if r["line"] is None:
            continue
        side = "over" if low.startswith("over") else ("under" if low.startswith("under") else None)
        if side is None:
            continue
        key = (r["match_id"], r["market_key"], float(r["line"]))
        ou.setdefault(key, {"market_name": r["market_name"]})[side] = float(r["odds"])  # later id wins
    return ou


def _ladder_odds(rows):
    """{match_id: {line: odds}} for the legacy one-way N+ ladder."""
    out: dict = {}
    for r in rows:
        if r["market_key"] != _LADDER_MARKET or r["line"] is None:
            continue
        out.setdefault(r["match_id"], {})[float(r["line"])] = float(r["odds"])
    return out


def _resolve_player(market_name: str, meta) -> tuple[int | None, str]:
    """Map a 'Total <Player> Aces X.5' market to player_a/b via name match."""
    m = re.match(r"total\s+(.*?)\s+aces", market_name.strip(), re.I)
    who = _norm(m.group(1)) if m else ""
    if not who:
        return None, ""
    a, b = _norm(meta["a_name"]), _norm(meta["b_name"])
    # substring either way to tolerate accents/initials
    if who and (who in a or a in who):
        return meta["player_a_id"], meta["a_name"]
    if who and (who in b or b in who):
        return meta["player_b_id"], meta["b_name"]
    return None, ""


def _log_two_way(conn, match_date, label, tw: "ace_model.TwoWayProp",
                 scope: str, subject_player_id):
    """Log the over side (scorecard) + the value side (bet) for a two-way prop."""
    fair_over = tw.fair_prob_over
    # over-side row (always; stake only if over is the value side)
    over_is_val = tw.value_side == "over"
    record_prop(conn, match_id=tw.match_id, match_date=match_date, match_label=label,
                market_key=tw.market_key, line=tw.line, selection=f"Over {tw.line}",
                side="over", prop_scope=scope, subject_player_id=subject_player_id,
                decimal_odds=tw.over_odds, model_prob=tw.model_prob_over,
                market_prob_fair=fair_over,
                blended_prob=tw.blended_prob if over_is_val else round(1 - (1 - tw.model_prob_over), 4),
                edge=tw.edge if over_is_val else 0.0, ev=tw.ev if over_is_val else 0.0,
                predicted_mean=tw.predicted_mean, stake_units=1.0 if over_is_val else 0.0,
                is_value=over_is_val)
    if tw.value_side == "under":
        record_prop(conn, match_id=tw.match_id, match_date=match_date, match_label=label,
                    market_key=tw.market_key, line=tw.line, selection=f"Under {tw.line}",
                    side="under", prop_scope=scope, subject_player_id=subject_player_id,
                    decimal_odds=tw.under_odds, model_prob=round(1 - tw.model_prob_over, 4),
                    market_prob_fair=round(1 - fair_over, 4), blended_prob=tw.blended_prob,
                    edge=tw.edge, ev=tw.ev, predicted_mean=tw.predicted_mean,
                    stake_units=1.0, is_value=True)


def price_ace_props_for_date(conn, match_date: str, log: bool = True) -> list[AcePropBoard]:
    from tennis_wc.props import calibration
    rows = _rows_for_date(conn, match_date)
    ladder = _ladder_odds(rows)
    two_way = _two_way_odds(rows)
    prob_map = _match_prob_map(conn, match_date)
    temper = calibration.current_strength(conn)  # keeps EV honest until validated
    match_ids = {r["match_id"] for r in rows}
    boards: list[AcePropBoard] = []
    for mid in match_ids:
        meta = _match_meta(conn, mid)
        if not meta:
            continue
        a = ace_model.player_ace_profile(conn, meta["player_a_id"], meta["match_date"], meta["surface"])
        b = ace_model.player_ace_profile(conn, meta["player_b_id"], meta["match_date"], meta["surface"])
        if a.n < ace_model._MIN_HISTORY or b.n < ace_model._MIN_HISTORY:
            continue
        match_mean = ace_model.predict_match_ace_mean(a, b)
        label = f"{meta['a_name']} vs {meta['b_name']}"
        board = AcePropBoard(match_id=mid, match_label=label, predicted_match_mean=match_mean)
        # legacy N+ ladder
        if mid in ladder:
            board.ladder_legs = ace_model.price_ace_legs(
                conn, mid, meta["player_a_id"], meta["player_b_id"],
                meta["match_date"], meta["surface"], ladder[mid])
            board.anchor = ace_model.anchor_leg(board.ladder_legs)
        # two-way markets
        for (m_id, mk, line), od in two_way.items():
            if m_id != mid or "over" not in od or "under" not in od:
                continue
            if _MATCH_OU.match(mk):
                tw = ace_model.price_two_way(mid, mk, "match", line, od["over"], od["under"],
                                             match_mean, ace_model.MATCH_ACE_CURVE, temper=temper)
                if tw:
                    board.match_ou.append(tw)
                    if log:
                        _log_two_way(conn, match_date, label, tw, "match", None)
            elif _PLAYER_OU.match(mk):
                pid, pname = _resolve_player(od["market_name"], meta)
                if pid is None:
                    continue
                subj = a if pid == meta["player_a_id"] else b
                opp = b if pid == meta["player_a_id"] else a
                pmean = ace_model.predict_player_ace_mean(subj, opp)
                tw = ace_model.price_two_way(mid, mk, pname, line, od["over"], od["under"],
                                             pmean, ace_model.PLAYER_ACE_CURVE, temper=temper)
                if tw:
                    board.player_ou.append(tw)
                    if log:
                        _log_two_way(conn, match_date, label, tw, "player", pid)
            elif _MATCH_GAMES_OU.match(mk):
                tw = games_model.price_games_two_way(
                    mid, mk, line, od["over"], od["under"], prob_map.get(mid), best_of=3, temper=temper)
                if tw:
                    board.predicted_games = tw.predicted_mean
                    board.games_ou.append(tw)
                    if log:
                        _log_two_way(conn, match_date, label, tw, "match_games", None)
        # log legacy ladder value legs + anchor (over-only)
        if log and board.ladder_legs:
            for lg in board.ladder_legs:
                if not (lg.is_value or (board.anchor is not None and lg.line == board.anchor.line)):
                    continue
                record_prop(conn, match_id=mid, match_date=match_date, match_label=label,
                            market_key=_LADDER_MARKET, line=lg.line, selection=f"{int(lg.line)}+",
                            side="over", prop_scope="match", subject_player_id=None,
                            decimal_odds=lg.decimal_odds, model_prob=lg.model_prob,
                            market_prob_fair=lg.market_prob_fair, blended_prob=lg.blended_prob,
                            edge=lg.edge, ev=lg.ev, predicted_mean=lg.predicted_mean,
                            stake_units=1.0 if lg.is_value else 0.0, is_value=lg.is_value)
        if board.ladder_legs or board.match_ou or board.player_ou or board.games_ou:
            boards.append(board)
    if log:
        conn.commit()
    boards.sort(key=lambda x: -sum(1 for t in (x.match_ou + x.player_ou + x.games_ou) if t.value_side))
    return boards

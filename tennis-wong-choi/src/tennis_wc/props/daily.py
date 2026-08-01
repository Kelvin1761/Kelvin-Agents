"""Daily evidence-gated tennis prop pricing entry point.

The Sportsbet feed is treated as a market inventory.  Supported ace, player
count, set-outcome and player-handicap families are priced and logged, but a
new family remains ``RESEARCH_ONLY`` until its own scorecard and ROI evidence
passes the strategy gate.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from tennis_wc.props import ace_model
from tennis_wc.props import games_model
from tennis_wc.props import player_model
from tennis_wc.props import registry
from tennis_wc.props import strategy
from tennis_wc.props.settlement import record_prop
from tennis_wc.modelling import set_distribution

_LADDER_MARKET = "total_aces_in_the_match"
_MATCH_OU = re.compile(r"^total_aces_\d+_5$")
_PLAYER_OU = re.compile(r"^total_(?P<name>[a-z0-9_]+)_aces_\d+_5$")
_MATCH_GAMES_OU = re.compile(r"^total_match_games_\d+_5$")


@dataclass
class AcePropBoard:
    match_id: int
    match_label: str
    predicted_match_mean: float | None
    ladder_legs: list = field(default_factory=list)     # PricedAceLeg (over-only N+)
    match_ou: list = field(default_factory=list)        # TwoWayProp (aces)
    player_ou: list = field(default_factory=list)        # TwoWayProp (player aces)
    double_fault_ou: list = field(default_factory=list)  # TwoWayProp
    player_games_ou: list = field(default_factory=list)  # TwoWayProp
    win_a_set: list = field(default_factory=list)        # BinaryProp
    first_set_winner: list = field(default_factory=list) # HeadToHeadProp
    game_handicap: list = field(default_factory=list)    # SpreadProp
    set_handicap: list = field(default_factory=list)     # SpreadProp
    exact_set_score: list = field(default_factory=list)  # ExactSetScoreProp
    games_ou: list = field(default_factory=list)        # TwoWayProp (total match games)
    predicted_games: float | None = None
    anchor: object | None = None


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _match_meta(conn, match_id: int):
    return conn.execute(
        """
        SELECT m.id, m.player_a_id, m.player_b_id, m.match_date, m.tour,
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


def _games_bettable() -> bool:
    """Total-match-games props are PRICED and LOGGED but never staked.

    Settled evidence as of 2026-07-25 (after backfilling 390 missing results):
    match_total_games is the worst family we run -- 11 settled, 36.4% hit,
    ROI -33.3%, while player_aces (+6.2%) and match_total_aces (+0.6%) are
    around breakeven. The games model is also biased: across 53 settled games
    props it predicted 23.34 games vs 25.23 actual (median -2.55), i.e. it
    systematically under-predicts, so its OVER/UNDER calls are skewed.

    Keep pricing them: the rows still feed the model-vs-market scorecard, so the
    family can earn its way back with evidence instead of a guess. It just must
    not reach the betting card while it is the one family reliably losing money.
    """
    return False


def _aces_gradeable(tour: str | None) -> bool:
    """Only ATP ace props can currently be graded: actual ace counts come from
    the TML/Sackmann season files (ATP only — 41 of 43 stuck-PENDING props were
    WTA aces) and result score_json carries no ace fields. Games props are
    gradeable for BOTH tours (score_json games coverage). Value bets must never
    be surfaced on a market we cannot settle — ungradeable props stay priced
    and logged (stake 0) so they can settle retroactively if a source appears."""
    return str(tour or "").upper() == "ATP"


def _strip_value(tw: "ace_model.TwoWayProp") -> "ace_model.TwoWayProp":
    tw.value_side = None
    tw.value_odds = None
    tw.edge = 0.0
    tw.ev = min(float(tw.ev or 0.0), 0.0)
    return tw


def _strip_structured_value(prop):
    """Keep a priced row for scorekeeping but remove its paper-bet signal."""
    if hasattr(prop, "value_side"):
        prop.value_side = None
        prop.value_odds = None
    if hasattr(prop, "value_player_id"):
        prop.value_player_id = None
        prop.value_name = None
        prop.value_odds = None
        if hasattr(prop, "value_handicap"):
            prop.value_handicap = None
    if hasattr(prop, "edge"):
        prop.edge = 0.0
    if hasattr(prop, "ev"):
        prop.ev = min(float(prop.ev or 0.0), 0.0)
    for selection in getattr(prop, "selections", []) or []:
        selection.is_value = False
        selection.edge = 0.0
        selection.ev = min(float(selection.ev or 0.0), 0.0)
    return prop


def _rows_for_date(conn, match_date: str):
    return conn.execute(
        """
        SELECT mo.match_id, mo.market_key, mo.market_name, mo.selection_name,
               mo.line, mo.odds, mo.id
        FROM market_odds_snapshots mo JOIN matches m ON m.id = mo.match_id
        WHERE m.match_date = ? AND (
            mo.market_key = ?
            OR lower(mo.market_name) LIKE '%aces%'
            OR lower(mo.market_name) LIKE '%double fault%'
            OR lower(mo.market_name) LIKE '%total games%'
            OR lower(mo.market_name) LIKE '%win at least %set%'
            OR lower(mo.market_name) IN ('set 1 winner', 'first set winner', '1st set winner')
            OR mo.market_key IN ('game_handicap', 'set_handicap')
            OR (mo.market_key = 'set_betting' AND lower(mo.market_name) = 'set betting')
        )
        ORDER BY mo.id ASC
        """,
        (match_date, _LADDER_MARKET),
    ).fetchall()


def _match_prob_map(conn, match_date: str) -> dict:
    """Latest player-A win probability per match."""
    rows = conn.execute(
        """
        SELECT p.match_id,
               CASE WHEN p.selection_player_id = m.player_a_id
                    THEN p.model_probability ELSE 1.0 - p.model_probability END AS p_a
        FROM predictions p JOIN matches m ON m.id = p.match_id
        WHERE m.match_date = ? AND p.id IN (SELECT MAX(id) FROM predictions GROUP BY match_id)
        """,
        (match_date,),
    ).fetchall()
    return {r["match_id"]: r["p_a"] for r in rows if r["p_a"] is not None}


def _two_way_odds(rows):
    """Group two-way O/U rows without merging two named-player markets."""
    ou: dict = {}
    for r in rows:
        name = str(r["selection_name"] or "")
        low = name.lower()
        if r["line"] is None:
            continue
        side = "over" if low.startswith("over") else ("under" if low.startswith("under") else None)
        if side is None:
            continue
        key = (r["match_id"], r["market_key"], r["market_name"], float(r["line"]))
        ou.setdefault(key, {"market_name": r["market_name"]})[side] = float(r["odds"])  # later id wins
    return ou


def _yes_no_odds(rows):
    out: dict = {}
    for r in rows:
        tokens = str(r["selection_name"] or "").lower().split()
        if not tokens or tokens[-1] not in {"yes", "no"}:
            continue
        key = (r["match_id"], r["market_key"], r["market_name"])
        out.setdefault(key, {"market_name": r["market_name"]})[tokens[-1]] = float(r["odds"])
    return out


def _head_to_head_odds(rows, meta):
    out: dict = {}
    a_norm, b_norm = _norm(meta["a_name"]), _norm(meta["b_name"])
    for row in rows:
        if registry.family_for_market(row["market_key"], row["market_name"]) != "first_set_winner":
            continue
        selection = _norm(row["selection_name"])
        side = "a" if selection == a_norm else ("b" if selection == b_norm else None)
        if side is None:
            continue
        key = (row["match_id"], row["market_key"], row["market_name"])
        out.setdefault(key, {})[side] = float(row["odds"])
    return out


def _spread_odds(rows, meta, family: str):
    """Group complementary player handicap selections.

    Only half-lines with explicit player names are accepted.  This excludes
    three-way integer handicaps and set-specific game handicaps, both of which
    need push/conditional settlement rules that do not belong in this contract.
    """
    out: dict = {}
    a_norm, b_norm = _norm(meta["a_name"]), _norm(meta["b_name"])
    for row in rows:
        if registry.family_for_market(row["market_key"], row["market_name"]) != family:
            continue
        if row["line"] is None:
            continue
        handicap = float(row["line"])
        if abs(abs(handicap) % 1.0 - 0.5) > 1e-9:
            continue
        raw_selection = str(row["selection_name"] or "")
        player_text = re.sub(r"\s*\([+-]?\d+(?:\.\d+)?\)\s*$", "", raw_selection)
        selection = _norm(player_text)
        side = "a" if selection == a_norm else ("b" if selection == b_norm else None)
        if side is None:
            continue
        key = (row["match_id"], family, abs(handicap))
        bucket = out.setdefault(key, {"market_name": row["market_name"]})
        bucket["market_name"] = row["market_name"]
        bucket[side] = {
            "odds": float(row["odds"]),
            "handicap": handicap,
        }
    return {
        key: value
        for key, value in out.items()
        if "a" in value
        and "b" in value
        and abs(value["a"]["handicap"] + value["b"]["handicap"]) < 1e-9
    }


def _exact_set_score_odds(rows, meta):
    """Return complete four-way BO3 Set Betting markets for one fixture."""
    out: dict = {}
    a_norm, b_norm = _norm(meta["a_name"]), _norm(meta["b_name"])
    for row in rows:
        if registry.family_for_market(row["market_key"], row["market_name"]) != "player_exact_set_score":
            continue
        parsed = re.match(r"^(.*?)\s+2-([01])$", str(row["selection_name"] or "").strip())
        if not parsed:
            continue
        player = _norm(parsed.group(1))
        side = "a" if player == a_norm else ("b" if player == b_norm else None)
        if side is None:
            continue
        code = f"{side}2{parsed.group(2)}"
        out.setdefault(row["match_id"], {})[code] = float(row["odds"])
    return {
        match_id: odds
        for match_id, odds in out.items()
        if set(odds) == {"a20", "a21", "b20", "b21"}
    }


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


def _resolve_named_player(market_name: str, family: str, meta) -> tuple[int | None, str]:
    patterns = {
        "player_aces": r"(?:total\s+)?(.*?)\s+aces(?:\s+\d|$)",
        "player_double_faults": r"(?:total\s+)?(.*?)\s+double faults?(?:\s+\d|$)",
        "player_total_games": r"^(.*?)\s+total games(?:\s+\d|$)",
        "player_win_a_set": r"^(.*?)\s+to win at least (?:one|1) set",
    }
    match = re.search(patterns.get(family, r"$^"), market_name.strip(), re.I)
    who = _norm(match.group(1)) if match else ""
    if not who:
        return None, ""
    for pid_key, name_key in (
        ("player_a_id", "a_name"), ("player_b_id", "b_name")
    ):
        candidate = _norm(meta[name_key])
        if who in candidate or candidate in who:
            return meta[pid_key], meta[name_key]
    return None, ""


def _log_two_way(conn, match_date, label, tw: "ace_model.TwoWayProp",
                 scope: str, subject_player_id):
    """Log the over side (scorecard) + the value side (bet) for a two-way prop.

    Two probabilities are stored per row: `model_prob` is the staking-side
    (tempered) number, `model_prob_raw` is the odds-blind model output that the
    scorecard grades. They used to be the same value, which made the scorecard
    unable to see the model's real skill."""
    fair_over = tw.fair_prob_over
    tempered_over = tw.tempered_prob_over or tw.model_prob_over
    # over-side row (always; stake only if over is the value side)
    over_is_val = tw.value_side == "over"
    record_prop(conn, match_id=tw.match_id, match_date=match_date, match_label=label,
                market_key=tw.market_key, line=tw.line, selection=f"Over {tw.line}",
                side="over", prop_scope=scope, subject_player_id=subject_player_id,
                decimal_odds=tw.over_odds, model_prob=tempered_over,
                model_prob_raw=tw.model_prob_over,
                temper_strength=tw.temper_strength,
                market_prob_fair=fair_over,
                blended_prob=tw.blended_prob if over_is_val else tempered_over,
                edge=tw.edge if over_is_val else 0.0, ev=tw.ev if over_is_val else 0.0,
                predicted_mean=tw.predicted_mean, stake_units=1.0 if over_is_val else 0.0,
                is_value=over_is_val)
    if tw.value_side == "under":
        record_prop(conn, match_id=tw.match_id, match_date=match_date, match_label=label,
                    market_key=tw.market_key, line=tw.line, selection=f"Under {tw.line}",
                    side="under", prop_scope=scope, subject_player_id=subject_player_id,
                    decimal_odds=tw.under_odds, model_prob=round(1 - tempered_over, 4),
                    model_prob_raw=round(1 - tw.model_prob_over, 4),
                    temper_strength=tw.temper_strength,
                    market_prob_fair=round(1 - fair_over, 4), blended_prob=tw.blended_prob,
                    edge=tw.edge, ev=tw.ev, predicted_mean=tw.predicted_mean,
                    stake_units=1.0, is_value=True)


def _log_binary(conn, match_date, label, binary, subject_player_id):
    yes_is_value = binary.value_side == "yes"
    record_prop(
        conn, match_id=binary.match_id, match_date=match_date, match_label=label,
        market_key=binary.market_key, line=0.5, selection="Yes", side="over",
        prop_scope="player_win_set", subject_player_id=subject_player_id,
        decimal_odds=binary.yes_odds, model_prob=binary.tempered_prob_yes,
        model_prob_raw=binary.model_prob_yes,
        temper_strength=binary.temper_strength,
        market_prob_fair=binary.fair_prob_yes,
        blended_prob=binary.blended_prob if yes_is_value else binary.tempered_prob_yes,
        edge=binary.edge if yes_is_value else 0.0,
        ev=binary.ev if yes_is_value else 0.0, predicted_mean=binary.model_prob_yes,
        stake_units=1.0 if yes_is_value else 0.0, is_value=yes_is_value,
    )
    if binary.value_side == "no":
        record_prop(
            conn, match_id=binary.match_id, match_date=match_date, match_label=label,
            market_key=binary.market_key, line=0.5, selection="No", side="under",
            prop_scope="player_win_set", subject_player_id=subject_player_id,
            decimal_odds=binary.no_odds, model_prob=round(1-binary.tempered_prob_yes, 4),
            model_prob_raw=round(1-binary.model_prob_yes, 4),
            temper_strength=binary.temper_strength,
            market_prob_fair=round(1-binary.fair_prob_yes, 4),
            blended_prob=binary.blended_prob, edge=binary.edge, ev=binary.ev,
            predicted_mean=binary.model_prob_yes, stake_units=1.0, is_value=True,
        )


def _log_head_to_head(conn, match_date, label, prop):
    a_value = prop.value_player_id == prop.player_a_id
    record_prop(
        conn, match_id=prop.match_id, match_date=match_date, match_label=label,
        market_key=f"first_set_winner_{prop.player_a_id}", line=0.5,
        selection=prop.player_a_name, side="over", prop_scope="player_first_set",
        subject_player_id=prop.player_a_id, decimal_odds=prop.a_odds,
        model_prob=prop.tempered_prob_a, model_prob_raw=prop.model_prob_a,
        temper_strength=prop.temper_strength, market_prob_fair=prop.fair_prob_a,
        blended_prob=prop.blended_prob if a_value else prop.tempered_prob_a,
        edge=prop.edge if a_value else 0.0, ev=prop.ev if a_value else 0.0,
        predicted_mean=prop.model_prob_a, stake_units=1.0 if a_value else 0.0,
        is_value=a_value,
    )
    if prop.value_player_id == prop.player_b_id:
        record_prop(
            conn, match_id=prop.match_id, match_date=match_date, match_label=label,
            market_key=f"first_set_winner_{prop.player_b_id}", line=0.5,
            selection=prop.player_b_name, side="over",
            prop_scope="player_first_set", subject_player_id=prop.player_b_id,
            decimal_odds=prop.b_odds, model_prob=round(1-prop.tempered_prob_a, 4),
            model_prob_raw=round(1-prop.model_prob_a, 4),
            temper_strength=prop.temper_strength,
            market_prob_fair=round(1-prop.fair_prob_a, 4),
            blended_prob=prop.blended_prob, edge=prop.edge, ev=prop.ev,
            predicted_mean=round(1-prop.model_prob_a, 4), stake_units=1.0,
            is_value=True,
        )


def _log_spread(conn, match_date, label, prop, scope: str):
    """Log player-A cover canonically and player-B only when it is value.

    Both rows settle against player A's raw margin.  Player A covers when the
    margin is over ``-a_handicap``; player B covers on the complementary under.
    This keeps exactly one odds-blind scorecard observation per market.
    """
    threshold = -float(prop.a_handicap)
    a_value = prop.value_player_id == prop.player_a_id
    record_prop(
        conn, match_id=prop.match_id, match_date=match_date, match_label=label,
        market_key=prop.market_key, line=threshold,
        selection=f"{prop.player_a_name} ({prop.a_handicap:+g})", side="over",
        prop_scope=scope, subject_player_id=prop.player_a_id,
        decimal_odds=prop.a_odds, model_prob=prop.tempered_prob_a_cover,
        model_prob_raw=prop.model_prob_a_cover,
        temper_strength=prop.temper_strength,
        market_prob_fair=prop.fair_prob_a_cover,
        blended_prob=prop.blended_prob if a_value else prop.tempered_prob_a_cover,
        edge=prop.edge if a_value else 0.0, ev=prop.ev if a_value else 0.0,
        predicted_mean=prop.predicted_margin,
        stake_units=1.0 if a_value else 0.0, is_value=a_value,
    )
    if prop.value_player_id == prop.player_b_id:
        record_prop(
            conn, match_id=prop.match_id, match_date=match_date, match_label=label,
            market_key=prop.market_key, line=threshold,
            selection=f"{prop.player_b_name} ({prop.b_handicap:+g})", side="under",
            prop_scope=scope, subject_player_id=prop.player_a_id,
            decimal_odds=prop.b_odds,
            model_prob=round(1-prop.tempered_prob_a_cover, 4),
            model_prob_raw=round(1-prop.model_prob_a_cover, 4),
            temper_strength=prop.temper_strength,
            market_prob_fair=round(1-prop.fair_prob_a_cover, 4),
            blended_prob=prop.blended_prob, edge=prop.edge, ev=prop.ev,
            predicted_mean=prop.predicted_margin, stake_units=1.0, is_value=True,
        )


def _log_exact_set_score(conn, match_date, label, prop):
    """Log all four mutually exclusive outcomes for multiclass scorekeeping."""
    for selection in prop.selections:
        record_prop(
            conn, match_id=prop.match_id, match_date=match_date, match_label=label,
            market_key=(
                f"player_exact_set_score_{selection.player_id}_"
                f"{selection.sets_lost}"
            ),
            line=0.5,
            selection=f"{selection.player_name} 2-{selection.sets_lost}",
            side="over", prop_scope="player_exact_set_score",
            subject_player_id=selection.player_id,
            decimal_odds=selection.odds, model_prob=selection.tempered_prob,
            model_prob_raw=selection.model_prob,
            temper_strength=prop.temper_strength,
            market_prob_fair=selection.fair_prob,
            blended_prob=selection.blended_prob,
            edge=selection.edge, ev=selection.ev,
            predicted_mean=selection.model_prob,
            stake_units=1.0 if selection.is_value else 0.0,
            is_value=selection.is_value,
        )


def price_ace_props_for_date(conn, match_date: str, log: bool = True) -> list[AcePropBoard]:
    from tennis_wc.props import calibration
    rows = _rows_for_date(conn, match_date)
    ladder = _ladder_odds(rows)
    two_way = _two_way_odds(rows)
    yes_no = _yes_no_odds(rows)
    prob_map = _match_prob_map(conn, match_date)
    reliability: dict[str, calibration.FamilyReliability] = {}

    def model_weight(family: str) -> float:
        if family not in reliability:
            reliability[family] = calibration.family_reliability(
                conn, family, as_of_date=match_date
            )
        return reliability[family].model_weight
    rows_by_match: dict[int, list] = {}
    for row in rows:
        rows_by_match.setdefault(int(row["match_id"]), []).append(row)
    match_ids = set(rows_by_match)
    boards: list[AcePropBoard] = []
    for mid in match_ids:
        meta = _match_meta(conn, mid)
        if not meta:
            continue
        if "/" in str(meta["a_name"] or "") or "/" in str(meta["b_name"] or ""):
            continue  # current player-prop models are singles-only
        match_rows = rows_by_match[mid]
        ace_rows = [
            row for row in match_rows
            if registry.family_for_market(row["market_key"], row["market_name"])
            in {"player_aces", "match_total_aces"}
        ]
        a = b = None
        match_mean = None
        if ace_rows or mid in ladder:
            a = ace_model.player_ace_profile(
                conn, meta["player_a_id"], meta["match_date"], meta["surface"]
            )
            b = ace_model.player_ace_profile(
                conn, meta["player_b_id"], meta["match_date"], meta["surface"]
            )
            if a.n >= ace_model._MIN_HISTORY and b.n >= ace_model._MIN_HISTORY:
                match_mean = ace_model.predict_match_ace_mean(a, b)
        label = f"{meta['a_name']} vs {meta['b_name']}"
        board = AcePropBoard(match_id=mid, match_label=label, predicted_match_mean=match_mean)
        quality_row = conn.execute(
            "SELECT MIN(data_quality_score) FROM feature_snapshots WHERE match_id=?",
            (mid,),
        ).fetchone()
        feature_quality = strategy.normalise_data_quality(
            quality_row[0] if quality_row else None
        )
        derived_quality_ok = feature_quality >= strategy.MIN_DATA_QUALITY
        # v2 serve-dominance input for the games model (walk-forward safe).
        hold_sum = games_model.combined_hold(
            conn, meta["player_a_id"], meta["player_b_id"], meta["match_date"])
        # legacy N+ ladder
        if mid in ladder and match_mean is not None:
            board.ladder_legs = ace_model.price_ace_legs(
                conn, mid, meta["player_a_id"], meta["player_b_id"],
                meta["match_date"], meta["surface"], ladder[mid])
            if not _aces_gradeable(meta["tour"]) or min(a.n, b.n) < 10:
                for lg in board.ladder_legs:
                    lg.is_value = False
            board.anchor = ace_model.anchor_leg(board.ladder_legs)
        # two-way markets
        for (m_id, mk, market_name, line), od in two_way.items():
            if m_id != mid or "over" not in od or "under" not in od:
                continue
            family = registry.family_for_market(mk, market_name)
            if family == "match_total_aces":
                if match_mean is None:
                    continue
                tw = ace_model.price_two_way(mid, mk, "match", line, od["over"], od["under"],
                                             match_mean, ace_model.match_curve_for_surface(meta["surface"]),
                                             factors={"a_history_n": a.n, "b_history_n": b.n},
                                             model_weight=model_weight(family))
                if tw:
                    if (not _aces_gradeable(meta["tour"])
                            or min(a.n, b.n) < 10):
                        tw = _strip_value(tw)
                    board.match_ou.append(tw)
                    if log:
                        _log_two_way(conn, match_date, label, tw, "match", None)
            elif family == "player_aces":
                if a is None or b is None or match_mean is None:
                    continue
                pid, pname = _resolve_named_player(market_name, family, meta)
                if pid is None:
                    continue
                subj = a if pid == meta["player_a_id"] else b
                opp = b if pid == meta["player_a_id"] else a
                pmean = ace_model.predict_player_ace_mean(subj, opp)
                tw = ace_model.price_two_way(mid, mk, pname, line, od["over"], od["under"],
                                             pmean, ace_model.player_curve_for_surface(meta["surface"]),
                                             factors={"subject_history_n": subj.n,
                                                      "opponent_history_n": opp.n},
                                             model_weight=model_weight(family))
                if tw:
                    if (not _aces_gradeable(meta["tour"])
                            or min(subj.n, opp.n) < 10):
                        tw = _strip_value(tw)
                    board.player_ou.append(tw)
                    if log:
                        _log_two_way(conn, match_date, label, tw, "player", pid)
            elif family == "player_double_faults":
                pid, pname = _resolve_named_player(market_name, family, meta)
                if pid is None:
                    continue
                profile = player_model.count_profile(
                    conn, pid, meta["match_date"], "double_fault_count",
                    surface=meta["surface"],
                )
                tw = player_model.price_count_two_way(
                    mid, f"player_double_faults_{pid}_{line:g}", pname, line,
                    od["over"], od["under"], profile,
                    model_weight=model_weight(family),
                )
                if tw:
                    board.double_fault_ou.append(tw)
                    if log:
                        _log_two_way(
                            conn, match_date, label, tw, "player_double_faults", pid
                        )
            elif family == "player_total_games":
                pid, pname = _resolve_named_player(market_name, family, meta)
                if pid is None or prob_map.get(mid) is None:
                    continue
                p_side = prob_map[mid] if pid == meta["player_a_id"] else 1-prob_map[mid]
                total_mean = games_model.predict_total_games(
                    prob_map[mid], best_of=3, hold_sum=hold_sum
                )
                if total_mean is None:
                    continue
                raw_over, player_mean = player_model.player_games_over_probability(
                    line, total_mean, p_side
                )
                # Reuse the generic two-way carrier; a one-point synthetic curve
                # avoids pretending the ace calibration applies to games.
                tw = ace_model.price_two_way(
                    mid, f"player_total_games_{pid}_{line:g}", pname, line,
                    od["over"], od["under"], player_mean,
                    [(line / player_mean, raw_over), (line / player_mean + 0.001, raw_over)],
                    factors={"match_probability": p_side, "total_games_mean": total_mean},
                    within_range_ratio=9.0, model_weight=model_weight(family),
                )
                if tw:
                    if not derived_quality_ok:
                        tw = _strip_value(tw)
                    # price_two_way recalculates at the same ratio, so raw_over
                    # remains the explicit player-games research estimate.
                    board.player_games_ou.append(tw)
                    if log:
                        _log_two_way(conn, match_date, label, tw, "player_games", pid)
            elif (
                family == "match_total_games"
                and "set " not in market_name.lower()
                and "1st set" not in market_name.lower()
                and "2nd set" not in market_name.lower()
                and "3rd set" not in market_name.lower()
            ):
                tw = games_model.price_games_two_way(
                    mid, mk, line, od["over"], od["under"], prob_map.get(mid), best_of=3,
                    hold_sum=hold_sum, model_weight=model_weight(family))
                if tw:
                    if not _games_bettable():
                        tw = _strip_value(tw)
                    board.predicted_games = tw.predicted_mean
                    board.games_ou.append(tw)
                    if log:
                        _log_two_way(conn, match_date, label, tw, "match_games", None)
        for (m_id, mk, market_name), od in yes_no.items():
            if m_id != mid or "yes" not in od or "no" not in od:
                continue
            family = registry.family_for_market(mk, market_name)
            if family != "player_win_a_set" or prob_map.get(mid) is None:
                continue
            pid, pname = _resolve_named_player(market_name, family, meta)
            if pid is None:
                continue
            p_side = prob_map[mid] if pid == meta["player_a_id"] else 1-prob_map[mid]
            raw_yes = set_distribution.win_at_least_one_set_probability(p_side)
            binary = player_model.price_probability_two_way(
                mid, f"player_win_a_set_{pid}", pname,
                od["yes"], od["no"], raw_yes,
                model_weight=model_weight(family),
                factors={"match_probability": p_side},
            )
            if binary:
                if not derived_quality_ok:
                    binary = _strip_structured_value(binary)
                board.win_a_set.append(binary)
                if log:
                    _log_binary(conn, match_date, label, binary, pid)
        for (m_id, mk, _market_name), od in _head_to_head_odds(match_rows, meta).items():
            if m_id != mid or "a" not in od or "b" not in od or prob_map.get(mid) is None:
                continue
            raw_a = set_distribution.first_set_win_probability(prob_map[mid])
            prop = player_model.price_head_to_head(
                mid, mk, meta["player_a_id"], meta["a_name"],
                meta["player_b_id"], meta["b_name"], od["a"], od["b"], raw_a,
                model_weight=model_weight("first_set_winner"),
                factors={"match_probability_a": prob_map[mid]},
            )
            if prop:
                if not derived_quality_ok:
                    prop = _strip_structured_value(prop)
                board.first_set_winner.append(prop)
                if log:
                    _log_head_to_head(conn, match_date, label, prop)
        exact_odds = _exact_set_score_odds(match_rows, meta).get(mid)
        if exact_odds and prob_map.get(mid) is not None:
            prop = player_model.price_exact_set_score(
                mid, "player_exact_set_score", meta["player_a_id"], meta["a_name"],
                meta["player_b_id"], meta["b_name"], exact_odds, prob_map[mid],
                model_weight=model_weight("player_exact_set_score"),
                factors={"match_probability_a": prob_map[mid]},
            )
            if prop:
                if not derived_quality_ok:
                    prop = _strip_structured_value(prop)
                board.exact_set_score.append(prop)
                if log:
                    _log_exact_set_score(conn, match_date, label, prop)
        for (m_id, _family, abs_line), od in _spread_odds(
            match_rows, meta, "player_game_handicap"
        ).items():
            if m_id != mid or prob_map.get(mid) is None:
                continue
            total_mean = games_model.predict_total_games(
                prob_map[mid], best_of=3, hold_sum=hold_sum
            )
            if total_mean is None:
                continue
            raw_a_cover, margin_mean = player_model.game_handicap_cover_probability(
                od["a"]["handicap"], total_mean, prob_map[mid]
            )
            prop = player_model.price_spread_two_way(
                mid, f"player_game_handicap_{abs_line:g}",
                meta["player_a_id"], meta["a_name"],
                meta["player_b_id"], meta["b_name"],
                od["a"]["handicap"], od["b"]["handicap"],
                od["a"]["odds"], od["b"]["odds"], raw_a_cover,
                margin_mean, model_weight=model_weight("player_game_handicap"),
                factors={
                    "match_probability_a": prob_map[mid],
                    "expected_total_games": total_mean,
                    "source_market": od["market_name"],
                },
            )
            if prop:
                if not derived_quality_ok:
                    prop = _strip_structured_value(prop)
                board.game_handicap.append(prop)
                if log:
                    _log_spread(conn, match_date, label, prop, "player_game_margin")
        for (m_id, _family, abs_line), od in _spread_odds(
            match_rows, meta, "player_set_handicap"
        ).items():
            if m_id != mid or prob_map.get(mid) is None:
                continue
            raw_a_cover, margin_mean = player_model.set_handicap_cover_probability(
                od["a"]["handicap"], prob_map[mid]
            )
            prop = player_model.price_spread_two_way(
                mid, f"player_set_handicap_{abs_line:g}",
                meta["player_a_id"], meta["a_name"],
                meta["player_b_id"], meta["b_name"],
                od["a"]["handicap"], od["b"]["handicap"],
                od["a"]["odds"], od["b"]["odds"], raw_a_cover,
                margin_mean, model_weight=model_weight("player_set_handicap"),
                factors={
                    "match_probability_a": prob_map[mid],
                    "source_market": od["market_name"],
                },
            )
            if prop:
                if not derived_quality_ok:
                    prop = _strip_structured_value(prop)
                board.set_handicap.append(prop)
                if log:
                    _log_spread(conn, match_date, label, prop, "player_set_margin")
        # log legacy ladder value legs + anchor (over-only)
        if log and board.ladder_legs:
            for lg in board.ladder_legs:
                if not (lg.is_value or (board.anchor is not None and lg.line == board.anchor.line)):
                    continue
                record_prop(conn, match_id=mid, match_date=match_date, match_label=label,
                            market_key=_LADDER_MARKET, line=lg.line, selection=f"{int(lg.line)}+",
                            side="over", prop_scope="match", subject_player_id=None,
                            # The N+ ladder never applied a temper, so its model_prob
                            # was always the raw curve output -- record it as such.
                            decimal_odds=lg.decimal_odds, model_prob=lg.model_prob,
                            model_prob_raw=lg.model_prob, temper_strength=0.0,
                            market_prob_fair=lg.market_prob_fair, blended_prob=lg.blended_prob,
                            edge=lg.edge, ev=lg.ev, predicted_mean=lg.predicted_mean,
                            stake_units=1.0 if lg.is_value else 0.0, is_value=lg.is_value)
        if (
            board.ladder_legs or board.match_ou or board.player_ou
            or board.double_fault_ou or board.player_games_ou
            or board.win_a_set or board.first_set_winner
            or board.game_handicap or board.set_handicap
            or board.exact_set_score or board.games_ou
        ):
            boards.append(board)
    if log:
        conn.commit()
    boards.sort(
        key=lambda x: -sum(
            1 for t in (
                x.match_ou + x.player_ou + x.double_fault_ou
                + x.player_games_ou + x.win_a_set
                + x.first_set_winner + x.game_handicap
                + x.set_handicap + x.exact_set_score + x.games_ou
            ) if (
                getattr(t, "value_side", None)
                or getattr(t, "value_player_id", None) is not None
            )
        )
    )
    return boards

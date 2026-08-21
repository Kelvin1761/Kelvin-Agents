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
from tennis_wc.features import snapshot_quality
from tennis_wc.props import strategy
from tennis_wc.props.settlement import record_prop
from tennis_wc.modelling import set_distribution

_LADDER_MARKET = "total_aces_in_the_match"
_MATCH_OU = re.compile(r"^total_aces_\d+_5$")
_PLAYER_OU = re.compile(r"^total_(?P<name>[a-z0-9_]+)_aces_\d+_5$")
_MATCH_GAMES_OU = re.compile(r"^total_match_games_\d+_5$")
# A best-of-three winner takes at most 7+6+7 = 20 games and the loser 6+7+6 =
# 19, so a genuine player-games line sits well below this. Anything higher is a
# match total that resolved to a player's market name.
MAX_PLAYER_GAMES_LINE = 15.5


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
    first_set_match: list = field(default_factory=list)  # FirstSetMatchProp
    first_set_game_handicap: list = field(default_factory=list) # SpreadProp
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
               (SELECT t.name FROM tournaments t WHERE t.id = m.tournament_id)
                   AS tournament_name,
               -- The structured level, which is what _tier_of prefers: 65.8%
               -- of TOUR-labelled value bets sit on events whose "name" is a
               -- bare numeric id.
               (SELECT tl.level FROM tournament_levels tl
                 WHERE tl.tournament_id = m.tournament_id
                 ORDER BY tl.id DESC LIMIT 1) AS tournament_level,
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


# Tournament tiers whose props are PRICED and LOGGED but never staked.
#
# ITF measured on 482 settled fixtures (2026-08-10): our match probability
# scores Brier 0.2330 against the market's 0.1838 and AUC 0.6496 against
# 0.7971. Bootstrapped, the gap is +0.0492 with a 95% CI of [+0.035, +0.063]
# and P(model not worse) = 0.000 -- the tightest and most one-sided result in
# the whole review. ITF matches carry big skill mismatches the book prices
# easily, while our ITF ratings are built from a corpus that only starts in
# 2026-01. Betting into a market that is measurably better informed than us is
# a choice to pay the takeout.
#
# This reverses the decision earlier the same day to open ITF for betting. That
# was made because ITF had become SETTLEABLE; settleable is not the same as
# beatable, and the measurement above is what distinguishes them. Pricing
# continues so the tier can earn its way back once its ratings mature -- the
# scorecard keeps scoring it either way.
# An allow-list, not a block-list. The first version blocked ITF and let
# everything else through, and the very first recommendation the system then
# produced was a UTR exhibition -- a tier that never even reached the 40-fixture
# minimum to be measured, on a leg where the model claimed 55.6% against the
# market's 20.6%. A 35-point disagreement with the book is a modelling failure
# far more often than an edge.
#
# A tier earns a place here by being MEASURED and not worse than the market:
#   TOUR        456 fixtures, model Brier 0.2287 vs market 0.2601
#   CHALLENGER  139 fixtures, model 0.2074 vs market 0.1977, gap +0.0097 (n.s.)
#   ITF         482 fixtures, model 0.2330 vs market 0.1838 -- measurably worse
#   UTR          -- never reached 40 settled fixtures; unmeasured, so unbettable
BETTABLE_TIERS = frozenset({"TOUR", "CHALLENGER"})


# `888-2026`, `188-2026`: an external id in the name column, which is what
# two thirds of TOUR-labelled value bets were riding on.
_UNINFORMATIVE_NAME = re.compile(r"^\s*\d+\s*-\s*\d{4}\s*$")


def _tier_of(tournament_name: str | None, level: str | None = None) -> str:
    """Tier from the structured level where there is one, else from the name.

    UNKNOWN is deliberately not TOUR: an event that cannot be shown to belong
    to a tier we have measured must not be staked, and the allow-list only
    admits tiers we have.

    The level is preferred because the name is a display string and often is
    not one. Audited 2026-08-11 over every fixture since 2026-05-10: **65.8% of
    the value bets on TOUR-labelled events sit on tournaments whose "name" is a
    bare numeric id** -- `888-2026` with 320 value bets, `188-2026` with 232 --
    and the name rule was calling them TOUR purely because they did not spell
    ITF. `tournament_levels.level` knows what they are: ATP_500, ATP_250,
    GRAND_SLAM, WTA_250.

    They ARE tour events, so this changes nothing today: on the same audit the
    two rules disagree on **zero** value bets wherever the level is known, in
    either direction. The point is which field is load-bearing. A rail that
    happens to hold because a string did not contain "ITF" is not a rail.

    What it does not fix, and what is left deliberately visible: 70 value bets
    sit on numerically-named events whose level is UNKNOWN too. They are staked
    as TOUR on no evidence at all. Excluding them changes what gets bet, so it
    needs a replay rather than an opinion.
    """
    resolved = str(level or "").strip().upper()
    if resolved and resolved != "UNKNOWN":
        if "ITF" in resolved or "FUTURE" in resolved:
            return "ITF"
        if "UTR" in resolved:
            return "UTR"
        if "CHALLENGER" in resolved:
            return "CHALLENGER"
        return "TOUR"
    name = str(tournament_name or "").strip().upper()
    if not name:
        return "UNKNOWN"
    if "ITF" in name or "FUTURES" in name:
        return "ITF"
    if "UTR" in name:
        return "UTR"
    if "CHALLENGER" in name:
        return "CHALLENGER"
    # A name that is only an id carries no tier information, and with no level
    # either there is nothing placing the event at all. "An event that cannot
    # be shown to belong to a tier we have measured must not be staked" is what
    # UNKNOWN already meant; falling through to TOUR contradicted it and staked
    # 70 value bets on events nothing places. A name like "ATP Umag" does place
    # it, level or no level, and keeps its TOUR.
    if _UNINFORMATIVE_NAME.match(name):
        return "UNKNOWN"
    return "TOUR"


def _tier_bettable(tournament_name: str | None, level: str | None = None) -> bool:
    return _tier_of(tournament_name, level) in BETTABLE_TIERS


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


def _rows_for_date(conn, match_date: str, earliest_only: bool = False):
    """Offered markets for the date.

    ``earliest_only`` keeps the FIRST snapshot of each selection instead of the
    last.  The scraper re-reads a match while it is being played -- match 113
    holds 48 snapshots of one selection between 10:20 and 13:54, and one
    set-betting selection ranges from 1.26 to 41.0 across its snapshots -- so
    "later id wins" can price a prop on in-running or post-match odds.  That is
    harmless for today's card, where only pre-match snapshots exist yet, but it
    silently contaminates any replay of a finished day, which is exactly what
    the evidence base is built from.
    """
    earliest_filter = (
        """
        AND mo.id = (
            SELECT MIN(x.id) FROM market_odds_snapshots x
            WHERE x.match_id = mo.match_id AND x.market_key = mo.market_key
              AND IFNULL(x.market_name,'') = IFNULL(mo.market_name,'')
              AND IFNULL(x.selection_name,'') = IFNULL(mo.selection_name,'')
              AND IFNULL(x.line,-999999) = IFNULL(mo.line,-999999)
        )
        """
        if earliest_only
        else ""
    )
    return conn.execute(
        f"""
        SELECT mo.match_id, mo.market_key, mo.market_name, mo.selection_name,
               mo.line, mo.odds, mo.id
        FROM market_odds_snapshots mo JOIN matches m ON m.id = mo.match_id
        WHERE m.match_date = ? {earliest_filter} AND (
            mo.market_key = ?
            OR lower(mo.market_name) LIKE '%aces%'
            OR lower(mo.market_name) LIKE '%double fault%'
            OR lower(mo.market_name) LIKE '%total games%'
            OR lower(mo.market_name) LIKE '%win at least %set%'
            OR lower(mo.market_name) IN ('set 1 winner', 'first set winner', '1st set winner')
            OR mo.market_key IN ('game_handicap', 'set_handicap')
            OR mo.market_key IN (
                'to_win_1st_set_and_win_match',
                'to_lose_1st_set_and_win_match'
            )
            OR (mo.market_key = 'set_betting' AND lower(mo.market_name) = 'set betting')
        )
        ORDER BY mo.id ASC
        """,
        (match_date, _LADDER_MARKET),
    ).fetchall()


def _serve_based_player_games(conn, meta, subject_id, line, p_side, total_mean):
    """(P(over), predicted player games, priced_by_simulator).

    The match-probability curve stays as the fallback: serve history resolves
    for both sides on 70.1% of the fixtures we stake and nothing at all on the
    rest, so this has to degrade rather than refuse to price.

    It reads ``_holds_for`` rather than estimating the hold itself. It used to
    do its own, with the hand-set weights hard-coded, so this file held two
    definitions of "the hold for this match" -- and when the estimator changed
    underneath them, `player_total_games` came back bit-identical while every
    other family moved. One definition, one place.
    """
    distribution = _player_games_distribution(
        conn, meta, subject_id, trials=1500
    )
    if distribution is None:
        over, mean = player_model.player_games_over_probability(
            line, total_mean, p_side)
        return over, mean, False
    over = distribution.player_games_over(float(line), player="a")
    mean = sum(distribution.games_a) / distribution.trials
    return max(0.03, min(0.97, over)), round(mean, 3), True


# `player_win_a_set` is two bets wearing one name. The "yes" side backs a
# player to take a set; the "no" side backs a 2-0 sweep, which is a long-odds
# tail bet with a different distribution and a different failure mode. Split by
# side, "yes" runs +7.54% then +10.43% across the two windows and "no" swings
# +40.84% to -20.95% -- not a broken estimate, a coin flip with a long tail.
#
# Restricting to "yes", replayed over all 44 dates: the family goes from 370
# settled at +13.08% to 221 at +8.62%, and the two windows go from disagreeing
# in sign (+19.71% train, -3.02% holdout) to agreeing within 1.6pp (+9.09%,
# +7.53%). Whole-board drawdown falls from -57.97u to -47.01u and the family
# moves off PROBE onto EARLY_MAIN because its recent window turns from -1.6% to
# +10.4%. A worse headline and a better proposition.
#
# The criterion is variance across windows, not level -- picking a side after
# watching the other one fail is selection, and the reason this is not that is
# that "yes" is stable in BOTH windows independently.
WIN_A_SET_OVER_ONLY = True


# Games and sets props whose match has no usable serve profile on BOTH sides
# fall back to the closed forms the serve plan was written to replace. They are
# still priced and logged; they are no longer staked.
#
# The closed form was already measured to be the weaker predictor before any of
# this: stage 4 scored it out of sample on 357 held-out player_total_games
# props at Brier 0.2554 and AUC 0.5224 against the simulator's 0.2485 and
# 0.5742. Splitting the 1,449 settled bets by which path priced them says that
# difference reaches the money:
#
#                  n     ROI    earlier   later    P(ROI<=0)
#   simulator   1,251  +10.12%  +11.22%   +5.81%     0.000
#   closed form   198   -5.12%   -1.33%  -21.07%     0.734
#
# and the closed form is the losing half in three of the four families with
# volume, on both tiers, and on three of four surfaces. Its own bootstrap
# cannot separate 198 bets from zero -- the argument is the 15pp contrast and
# the prediction score that precedes it, not that -5.12% is significant.
#
# Same shape of decision as ITF: excluded on measured model skill, with the ROI
# observed afterwards rather than used to pick the slice. Pricing continues so
# the path can earn its way back if the serve corpus ever covers it.
STAKE_CLOSED_FORM_FALLBACK = False


# Which estimator turns two serve/return profiles into a hold probability.
#   True  -> the ridge fitted on 59,804 walk-forward matches by
#            scripts/fit_hold_ml.py (see props/hold_coefficients.py)
#   False -> the two hand-set weights
#
# OFF, and the reason is not that the fitted model is worse at its job. It is
# much better at it: out of sample it captures 27.0% of the achievable variance
# in per-game hold against the hand-set model's 11.7% and a rolling average's
# 8.1%, on every tier, every surface and every history depth, at P(no
# improvement) = 0.000. On the 580 priced fixtures with both holds it moves the
# hold GAP by more than 0.02 on 412 of them.
#
# It still loses money. Replayed over all 44 dates, one variable changed:
#
#                    hand-set          fitted
#   whole record     +7.79% (1,754)    +4.96% (1,672)
#   drawdown         -57.97u           -45.07u
#
# The held-out window alone reads the other way (-2.57% -> +4.28%), and that is
# the tempting number. It is not the right one HERE, and the reason is specific:
# the coefficients were fitted on data ending 2026-05-09, so the whole replay --
# both windows -- is already out of sample for them. There is no contaminated
# window to discount. Judged over all 1,754 bets rather than the last 353, the
# fitted estimator is worse.
#
# Per-bet, the mechanism is unambiguous. Of the props both variants stake --
# 1,475 of them -- the outcome differs on ZERO: stakes are flat, so a changed
# probability changes nothing unless it changes SELECTION. The whole effect is
# the 279 props the hand-set model backs and this one does not (+13.45% train,
# -37.03% holdout) against the 197 it backs instead (-29.82% train, +6.97%
# holdout). A difference whose sign reverses between two adjacent windows is
# not an edge that one of them happened to hide.
#
# Kept, wired and tested rather than deleted: the estimator is right and the
# value filter is what cannot use it. Flip this when the selection layer stops
# reading model-minus-market disagreement as its only signal.
USE_FITTED_HOLD = False


def _holds_for(conn, meta, subject_id, *, use_fitted: bool | None = None):
    """(subject hold, opponent hold) or None when either side is unmodellable."""
    from tennis_wc.features.serve_return import serve_return_profile
    from tennis_wc.props.hold_model import estimate_hold, estimate_hold_fitted

    opponent_id = (
        meta["player_b_id"] if subject_id == meta["player_a_id"] else meta["player_a_id"]
    )
    server = serve_return_profile(
        conn, subject_id, meta["match_date"], surface=meta["surface"]
    )
    returner = serve_return_profile(
        conn, opponent_id, meta["match_date"], surface=meta["surface"]
    )
    fitted = USE_FITTED_HOLD if use_fitted is None else bool(use_fitted)
    if fitted:
        subject = estimate_hold_fitted(server, returner)
        opponent = estimate_hold_fitted(returner, server)
    else:
        subject = estimate_hold(server, returner, return_weight=0.35, elo_weight=0.04)
        opponent = estimate_hold(returner, server, return_weight=0.35, elo_weight=0.04)
    if not (subject.is_usable and opponent.is_usable):
        return None
    return round(subject.probability, 3), round(opponent.probability, 3)


def _game_handicap_distribution(conn, meta, subject_id, *, trials: int = 1500):
    """Holdout-selected joint distribution for full-match game handicaps.

    On the frozen 2026-08-07 holdout, fitted holds plus 0.06 match-day hold-gap
    dispersion improved raw Brier from 0.2445 to 0.2185 (382 canonical props),
    including the hard-court subset.  Market Brier remained better at 0.2066,
    so this is a shadow-model improvement, not permission to stake the family.
    """
    return _fitted_joint_distribution(conn, meta, subject_id, trials=trials)


def _player_games_distribution(conn, meta, subject_id, *, trials: int = 1500):
    """Holdout-selected player-games distribution (Brier 0.2734 -> 0.2665)."""
    return _fitted_joint_distribution(conn, meta, subject_id, trials=trials)


def _fitted_joint_distribution(conn, meta, subject_id, *, trials: int):
    from tennis_wc.props.match_simulator import (
        FITTED_HOLD_GAP_DISPERSION,
        simulate_match,
    )

    holds = _holds_for(conn, meta, subject_id, use_fitted=True)
    if holds is None:
        return None
    return simulate_match(
        holds[0], holds[1], trials=trials,
        dispersion=FITTED_HOLD_GAP_DISPERSION,
    )


def _set_joint_probabilities(player_a_match_probability: float) -> dict:
    """One BO3 outcome table shared by every full-match set prop."""
    outcomes = set_distribution.outcome_distribution(
        float(player_a_match_probability)
    )
    return {
        "outcomes": outcomes,
        "win_a_set_a": 1.0 - float(outcomes["b20"]),
        "win_a_set_b": 1.0 - float(outcomes["a20"]),
    }


def _match_prob_map(conn, match_date: str) -> dict:
    """Latest player-A win probability per match, excluding the no-signal ones.

    ``_combine_components`` returns ``sigmoid(0) == 0.5`` exactly when no Elo
    backbone component and no nudge is active -- the model saying it knows
    nothing about this fixture.  That value carried no marker, so seven of the
    nine prop families priced off it as though it were a view: 24.3% of stored
    predictions are exactly 0.5000, and 616 props were priced on them.  A
    genuine estimate landing on 0.5 to fourteen decimal places is vanishingly
    unlikely, so the exact value is a reliable signature of the fallback.
    """
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
    return {
        r["match_id"]: r["p_a"]
        for r in rows
        if r["p_a"] is not None and abs(float(r["p_a"]) - 0.5) > 1e-12
    }


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
        bucket = ou.setdefault(key, {"market_name": r["market_name"]})
        bucket[side] = float(r["odds"])  # later id wins
        # The feed's own words for this selection. Kept because our market_key
        # is synthesised and cannot be looked up again, so without this a bet
        # has no closing price -- see record_prop's feed_* arguments.
        bucket[f"{side}_name"] = name
    return ou


def _yes_no_odds(rows):
    out: dict = {}
    for r in rows:
        tokens = str(r["selection_name"] or "").lower().split()
        if not tokens or tokens[-1] not in {"yes", "no"}:
            continue
        key = (r["match_id"], r["market_key"], r["market_name"])
        bucket = out.setdefault(key, {"market_name": r["market_name"]})
        bucket[tokens[-1]] = float(r["odds"])
        bucket[f"{tokens[-1]}_name"] = str(r["selection_name"] or "")
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
        bucket = out.setdefault(key, {"market_name": row["market_name"]})
        bucket[side] = float(row["odds"])
        bucket[f"{side}_name"] = str(row["selection_name"] or "")
    return out


def _first_set_match_odds(rows, meta):
    """Combine Sportsbet's two partial markets into one four-way table."""
    out: dict[int, dict] = {}
    a_norm, b_norm = _norm(meta["a_name"]), _norm(meta["b_name"])
    for row in rows:
        market_key = str(row["market_key"] or "")
        if market_key not in {
            "to_win_1st_set_and_win_match",
            "to_lose_1st_set_and_win_match",
        }:
            continue
        raw_name = str(row["selection_name"] or "")
        player_text = re.sub(r"\s+yes\s*$", "", raw_name, flags=re.I)
        selection = _norm(player_text)
        side = "a" if selection == a_norm else ("b" if selection == b_norm else None)
        if side is None:
            continue
        first_result = "win" if market_key.startswith("to_win_") else "lose"
        out.setdefault(int(row["match_id"]), {})[f"{side}_{first_result}"] = {
            "odds": float(row["odds"]),
            "selection_name": raw_name,
            "market_key": market_key,
            "market_name": str(row["market_name"] or ""),
        }
    required = {"a_win", "a_lose", "b_win", "b_lose"}
    return {
        match_id: outcomes
        for match_id, outcomes in out.items()
        if set(outcomes) == required
    }


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
        # The feed's own key and selection text, kept so the bet can be priced
        # again at the close -- our synthesised market_key cannot be looked up.
        bucket["market_key"] = row["market_key"]
        bucket[f"{side}_name"] = raw_selection
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


def _feed_identity(feed, market_key, side_key, line=None):
    """(feed_market_key, feed_market_name, feed_selection_name, feed_line).

    The bookmaker's own words, carried onto the tracker row so a bet can be
    priced again at the close. Our `market_key` is synthesised, so nothing in
    market_odds_snapshots matches it, and closing-line value therefore existed
    for the match-winner path and for zero props -- while props are the only
    thing being staked.

    The market NAME is part of the identity and not decoration. Sportsbet
    reuses `winner_related` across several markets -- the same reason
    family_for_market cannot work from the key alone -- so a closing-price
    lookup on (match_id, key, selection) matched a DIFFERENT market and
    reported +74.66% CLV on a bet that had not moved. Caught by the rule that a
    number too good to be true is a bug until shown otherwise.

    Returns Nones rather than a guess when the feed did not supply a name for
    that side. A wrong identifier here resolves to some other selection's
    closing price, which is worse than having none.
    """
    if not isinstance(feed, dict) or not market_key:
        return None, None, None, None
    name = feed.get(f"{side_key}_name") if side_key else None
    if not name:
        return None, None, None, None
    return (str(market_key), feed.get("market_name"), str(name),
            (float(line) if line is not None else None))


def _log_two_way(conn, match_date, label, tw: "ace_model.TwoWayProp",
                 scope: str, subject_player_id, feed=None, feed_market_key=None):
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
                is_value=over_is_val,
                **dict(zip(("feed_market_key", "feed_market_name", "feed_selection_name", "feed_line"),
                           _feed_identity(feed, feed_market_key, "over", tw.line))))
    if tw.value_side == "under":
        record_prop(conn, match_id=tw.match_id, match_date=match_date, match_label=label,
                    market_key=tw.market_key, line=tw.line, selection=f"Under {tw.line}",
                    side="under", prop_scope=scope, subject_player_id=subject_player_id,
                    decimal_odds=tw.under_odds, model_prob=round(1 - tempered_over, 4),
                    model_prob_raw=round(1 - tw.model_prob_over, 4),
                    temper_strength=tw.temper_strength,
                    market_prob_fair=round(1 - fair_over, 4), blended_prob=tw.blended_prob,
                    edge=tw.edge, ev=tw.ev, predicted_mean=tw.predicted_mean,
                    stake_units=1.0, is_value=True,
                    **dict(zip(("feed_market_key", "feed_market_name", "feed_selection_name", "feed_line"),
                               _feed_identity(feed, feed_market_key, "under", tw.line))))


def _log_binary(conn, match_date, label, binary, subject_player_id,
                feed=None, feed_market_key=None):
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
        **dict(zip(("feed_market_key", "feed_market_name", "feed_selection_name", "feed_line"),
                   _feed_identity(feed, feed_market_key, "yes"))),
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


def _log_head_to_head(conn, match_date, label, prop,
                      feed=None, feed_market_key=None):
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
        **dict(zip(("feed_market_key", "feed_market_name", "feed_selection_name", "feed_line"),
                   _feed_identity(feed, feed_market_key, "a"))),
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
            **dict(zip(("feed_market_key", "feed_market_name",
                        "feed_selection_name", "feed_line"),
                       _feed_identity(feed, feed_market_key, "b"))),
            is_value=True,
        )


def _log_spread(conn, match_date, label, prop, scope: str,
                feed=None, feed_market_key=None):
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
        **dict(zip(("feed_market_key", "feed_market_name", "feed_selection_name", "feed_line"),
                   _feed_identity(feed, feed_market_key, "a", prop.a_handicap))),
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
            **dict(zip(("feed_market_key", "feed_market_name", "feed_selection_name", "feed_line"),
                       _feed_identity(feed, feed_market_key, "b", prop.b_handicap))),
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


def _log_first_set_match(conn, match_date, label, prop, feed):
    """Log all four outcomes; only win-first rows may carry paper stake."""
    for selection in prop.selections:
        source = feed[selection.outcome]
        result_key = "win_first" if selection.first_set_won else "lose_first"
        record_prop(
            conn, match_id=prop.match_id, match_date=match_date,
            match_label=label,
            market_key=(
                f"player_first_set_match_{selection.player_id}_{result_key}"
            ),
            line=0.5,
            selection=(
                f"{selection.player_name} "
                f"{'Win' if selection.first_set_won else 'Lose'} 1st Set & Win Match"
            ),
            side="over", prop_scope="player_first_set_match",
            subject_player_id=selection.player_id,
            decimal_odds=selection.odds,
            model_prob=selection.tempered_prob,
            model_prob_raw=selection.model_prob,
            temper_strength=prop.temper_strength,
            market_prob_fair=selection.fair_prob,
            blended_prob=selection.blended_prob,
            edge=selection.edge, ev=selection.ev,
            predicted_mean=selection.model_prob,
            stake_units=1.0 if selection.is_value else 0.0,
            is_value=selection.is_value,
            feed_market_key=source["market_key"],
            feed_market_name=source["market_name"],
            feed_selection_name=source["selection_name"],
            feed_line=None,
        )


def price_ace_props_for_date(conn, match_date: str, log: bool = True,
                             earliest_odds: bool = False) -> list[AcePropBoard]:
    """Price every supported family for one date.

    ``earliest_odds`` must be set when re-pricing a finished day: see
    :func:`_rows_for_date`.  Leaving it off there prices the evidence base on
    odds the market only reached once the match was under way.
    """
    from tennis_wc.props import calibration
    rows = _rows_for_date(conn, match_date, earliest_only=earliest_odds)
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
        set_joint = (
            _set_joint_probabilities(prob_map[mid])
            if prob_map.get(mid) is not None else None
        )
        first_set_match_feed = _first_set_match_odds(match_rows, meta).get(mid)
        first_set_spreads = _spread_odds(
            match_rows, meta, "player_first_set_game_handicap"
        )
        first_set_distribution = None
        if first_set_match_feed or first_set_spreads:
            first_set_distribution = _fitted_joint_distribution(
                conn, meta, meta["player_a_id"], trials=1500
            )
        feature_quality = strategy.normalise_data_quality(
            snapshot_quality.match_quality(conn, mid)
        )
        tier_bettable = _tier_bettable(
            meta["tournament_name"], meta["tournament_level"])
        derived_quality_ok = (
            feature_quality >= strategy.MIN_DATA_QUALITY and tier_bettable
        )
        # v2 serve-dominance input for the games model (walk-forward safe).
        hold_sum = games_model.combined_hold(
            conn, meta["player_a_id"], meta["player_b_id"], meta["match_date"])
        # legacy N+ ladder
        if mid in ladder and match_mean is not None:
            board.ladder_legs = ace_model.price_ace_legs(
                conn, mid, meta["player_a_id"], meta["player_b_id"],
                meta["match_date"], meta["surface"], ladder[mid],
                model_weight=model_weight("player_aces"))
            if (not _aces_gradeable(meta["tour"]) or min(a.n, b.n) < 10
                    or not tier_bettable):
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
                            or min(a.n, b.n) < 10 or not tier_bettable):
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
                distribution = _player_games_distribution(
                    conn, meta, pid, trials=1500
                )
                use_exposure = distribution is not None and subj.ace_rate is not None
                if use_exposure:
                    expected_service_games = sum(
                        ga + gb for ga, gb in zip(
                            distribution.games_a, distribution.games_b
                        )
                    ) / (2.0 * distribution.trials)
                    pmean = ace_model.predict_player_ace_exposure_mean(
                        subj, opp, expected_service_games
                    )
                    raw_over = ace_model.negative_binomial_over_probability(
                        line, pmean
                    )
                    factors = {
                        "subject_history_n": subj.n,
                        "opponent_history_n": opp.n,
                        "expected_service_games": round(expected_service_games, 3),
                        "subject_ace_rate": subj.ace_rate,
                        "opponent_conceded_ace_rate": opp.conceded_ace_rate,
                        "count_distribution": "negative_binomial_size_3",
                        "joint_model": "fitted_hold_sigma_006",
                    }
                else:
                    pmean = ace_model.predict_player_ace_mean(subj, opp)
                    raw_over = None
                    factors = {
                        "subject_history_n": subj.n,
                        "opponent_history_n": opp.n,
                        "joint_model": "legacy_per_match_fallback",
                    }
                tw = ace_model.price_two_way(mid, mk, pname, line, od["over"], od["under"],
                                             pmean, ace_model.player_curve_for_surface(meta["surface"]),
                                             factors=factors,
                                             model_weight=model_weight(family),
                                             raw_probability_over=raw_over)
                if tw:
                    if (not _aces_gradeable(meta["tour"])
                            or min(subj.n, opp.n) < 10 or not tier_bettable):
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
                if line > MAX_PLAYER_GAMES_LINE:
                    # A match total wearing a player's name. In a best-of-three
                    # a player can win at most about 21 games (7+6+7), so a book
                    # never centres a player line at 19.5 -- and the settled
                    # record proves it: at that line the actual values run to 29,
                    # which one player cannot reach. 68 props came through this
                    # way and the serve model found them by inverting at both
                    # tails, predicting 0.0-0.1 where 66.7% landed.
                    continue
                p_side = prob_map[mid] if pid == meta["player_a_id"] else 1-prob_map[mid]
                total_mean = games_model.predict_total_games(
                    prob_map[mid], best_of=3, hold_sum=hold_sum
                )
                if total_mean is None:
                    continue
                # Serve-based pricing where both players have serve history,
                # falling back to the match-probability curve otherwise. Out of
                # sample on 357 held-out props the simulator scores Brier 0.2485
                # and AUC 0.5742 against this curve's 0.2554 and 0.5224, and
                # beats the market on ordering (0.5480). It reads no odds.
                raw_over, player_mean, from_simulator = _serve_based_player_games(
                    conn, meta, pid, line, p_side, total_mean
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
                    if not derived_quality_ok or not (
                        from_simulator or STAKE_CLOSED_FORM_FALLBACK
                    ):
                        tw = _strip_value(tw)
                    # price_two_way recalculates at the same ratio, so raw_over
                    # remains the explicit player-games research estimate.
                    board.player_games_ou.append(tw)
                    if log:
                        _log_two_way(conn, match_date, label, tw, "player_games", pid,
                                     feed=od, feed_market_key=mk)
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
            raw_yes = (
                set_joint["win_a_set_a"]
                if pid == meta["player_a_id"] else set_joint["win_a_set_b"]
            )
            binary = player_model.price_probability_two_way(
                mid, f"player_win_a_set_{pid}", pname,
                od["yes"], od["no"], raw_yes,
                model_weight=model_weight(family),
                factors={
                    "match_probability": p_side,
                    "joint_model": "empirical_bo3_outcomes",
                },
            )
            if binary:
                if not derived_quality_ok:
                    binary = _strip_structured_value(binary)
                if WIN_A_SET_OVER_ONLY and binary.value_side == "no":
                    binary = _strip_structured_value(binary)
                board.win_a_set.append(binary)
                if log:
                    _log_binary(conn, match_date, label, binary, pid,
                                feed=od, feed_market_key=mk)
        for (m_id, mk, _market_name), od in _head_to_head_odds(match_rows, meta).items():
            if m_id != mid or "a" not in od or "b" not in od or prob_map.get(mid) is None:
                continue
            holds = _holds_for(conn, meta, meta["player_a_id"])
            if holds is None:
                raw_a = set_distribution.first_set_win_probability(prob_map[mid])
            else:
                from tennis_wc.props.match_simulator import simulate_match

                raw_a = max(0.03, min(0.97, simulate_match(
                    holds[0], holds[1], trials=1500).first_set_winner("a")))
            prop = player_model.price_head_to_head(
                mid, mk, meta["player_a_id"], meta["a_name"],
                meta["player_b_id"], meta["b_name"], od["a"], od["b"], raw_a,
                model_weight=model_weight("first_set_winner"),
                factors={"match_probability_a": prob_map[mid]},
                family="first_set_winner",
            )
            if prop:
                if not derived_quality_ok or not (
                    holds is not None or STAKE_CLOSED_FORM_FALLBACK
                ):
                    prop = _strip_structured_value(prop)
                board.first_set_winner.append(prop)
                if log:
                    _log_head_to_head(conn, match_date, label, prop,
                                      feed=od, feed_market_key=mk)
        if first_set_match_feed and first_set_distribution is not None:
            prop = player_model.price_first_set_match_outcomes(
                mid, "player_first_set_match",
                meta["player_a_id"], meta["a_name"],
                meta["player_b_id"], meta["b_name"],
                {
                    key: value["odds"]
                    for key, value in first_set_match_feed.items()
                },
                first_set_distribution.first_set_match_outcomes(),
                model_weight=model_weight("player_first_set_match"),
                factors={
                    "joint_model": "fitted_hold_sigma_006",
                    "market_contract": "four_outcome_devig",
                },
            )
            if prop:
                if not derived_quality_ok:
                    prop = _strip_structured_value(prop)
                board.first_set_match.append(prop)
                if log:
                    _log_first_set_match(
                        conn, match_date, label, prop, first_set_match_feed
                    )
        exact_odds = _exact_set_score_odds(match_rows, meta).get(mid)
        if exact_odds and prob_map.get(mid) is not None:
            prop = player_model.price_exact_set_score(
                mid, "player_exact_set_score", meta["player_a_id"], meta["a_name"],
                meta["player_b_id"], meta["b_name"], exact_odds, prob_map[mid],
                model_weight=model_weight("player_exact_set_score"),
                factors={
                    "match_probability_a": prob_map[mid],
                    "joint_model": "empirical_bo3_outcomes",
                },
                outcome_probs=set_joint["outcomes"],
            )
            if prop:
                # NOT gated on the simulator path: exact set score has no
                # simulator path to fall back FROM -- it is priced from the
                # match probability either way. Reading `holds` here would
                # have read whatever the first-set loop above left behind,
                # which is a different match's answer to a different question.
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
            distribution = _game_handicap_distribution(
                conn, meta, meta["player_a_id"], trials=1500
            )
            if distribution is not None:
                raw_a_cover = max(0.03, min(0.97,
                    distribution.game_handicap_cover(float(od["a"]["handicap"]), "a")))
                margin_mean = round(distribution.expected_margin(), 3)
            else:
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
                    "joint_model": (
                        "fitted_hold_sigma_006"
                        if distribution is not None else "closed_form_fallback"
                    ),
                },
            )
            if prop:
                if not derived_quality_ok or not (
                    distribution is not None or STAKE_CLOSED_FORM_FALLBACK
                ):
                    prop = _strip_structured_value(prop)
                board.game_handicap.append(prop)
                if log:
                    _log_spread(conn, match_date, label, prop, "player_game_margin",
                                feed=od, feed_market_key=od.get("market_key"))
        for (m_id, _family, abs_line), od in first_set_spreads.items():
            if m_id != mid or first_set_distribution is None:
                continue
            raw_a_cover = max(0.03, min(
                0.97,
                first_set_distribution.first_set_game_handicap_cover(
                    float(od["a"]["handicap"]), "a"
                ),
            ))
            margin_mean = round(
                first_set_distribution.expected_first_set_margin(), 3
            )
            prop = player_model.price_spread_two_way(
                mid, f"player_first_set_game_handicap_{abs_line:g}",
                meta["player_a_id"], meta["a_name"],
                meta["player_b_id"], meta["b_name"],
                od["a"]["handicap"], od["b"]["handicap"],
                od["a"]["odds"], od["b"]["odds"], raw_a_cover,
                margin_mean,
                model_weight=model_weight("player_first_set_game_handicap"),
                factors={
                    "source_market": od["market_name"],
                    "joint_model": "fitted_hold_sigma_006",
                },
            )
            if prop:
                if not derived_quality_ok:
                    prop = _strip_structured_value(prop)
                board.first_set_game_handicap.append(prop)
                if log:
                    _log_spread(
                        conn, match_date, label, prop,
                        "player_first_set_game_margin", feed=od,
                        feed_market_key=od.get("market_key"),
                    )
        for (m_id, _family, abs_line), od in _spread_odds(
            match_rows, meta, "player_set_handicap"
        ).items():
            if m_id != mid or prob_map.get(mid) is None:
                continue
            raw_a_cover, margin_mean = player_model.set_handicap_cover_probability(
                od["a"]["handicap"], prob_map[mid],
                outcome_probs=set_joint["outcomes"],
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
                    "joint_model": "empirical_bo3_outcomes",
                },
            )
            if prop:
                if not derived_quality_ok:
                    prop = _strip_structured_value(prop)
                board.set_handicap.append(prop)
                if log:
                    _log_spread(conn, match_date, label, prop, "player_set_margin",
                                feed=od, feed_market_key=od.get("market_key"))
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
            or board.first_set_match or board.first_set_game_handicap
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
                + x.first_set_match + x.first_set_game_handicap
                + x.set_handicap + x.exact_set_score + x.games_ou
            ) if (
                getattr(t, "value_side", None)
                or getattr(t, "value_player_id", None) is not None
            )
        )
    )
    return boards

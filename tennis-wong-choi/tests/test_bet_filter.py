from __future__ import annotations


def test_bet_filter_placeholder_imports():
    from tennis_wc.betting.bet_filter import classify_edge

    assert classify_edge(0.01) == "NO_BET"
    assert classify_edge(0.03) == "WATCHLIST"
    assert classify_edge(0.04) == "SMALL_BET"
    assert classify_edge(0.06) == "STANDARD_BET"
    assert classify_edge(0.09) == "STRONG_BET"


# --------------------------------------------------------------------------- #
# Tier allow-list on the match-winner path (added 2026-08-26)
# --------------------------------------------------------------------------- #
def _bettable_inputs(tournament: str | None,
                     level: str | None = None) -> tuple[dict, dict]:
    snapshot = {
        "data_quality": {"score": 90, "is_valid": True, "errors": [], "warnings": []}
    }
    if tournament is not None or level is not None:
        snapshot["match_context"] = {
            "tournament": {"value": tournament},
            "level": {"value": level},
        }
    pricing = {
        "current_market_odds": 2.0, "minimum_acceptable_odds": 1.5, "edge": 0.06,
        "model_probability": 0.56, "errors": [], "model": {"components": []},
    }
    return snapshot, pricing


def test_match_winner_bets_obey_the_same_tier_allow_list_as_props():
    """The props path refuses ITF and UTR on measured grounds -- Brier 0.2330
    against the market's 0.1838 over 482 fixtures, gap +0.0492 CI [+0.035,
    +0.063] -- and that evidence is about the match probability itself. The
    match-winner path never got it: 165 of 472 BET decisions were ITF and 13
    were UTR, 38% of everything the filter passed.
    """
    from tennis_wc.betting.bet_filter import apply_bet_filter

    for tournament in ("ITF W15 Antalya", "M15 Monastir Futures",
                       "UTR Men Kawaguchi JPN"):
        result = apply_bet_filter(*_bettable_inputs(tournament))
        assert result["decision"] == "NO_BET", tournament
        assert any(r.startswith("tier_not_bettable")
                   for r in result["hard_no_bet_reasons"])


def test_bettable_tiers_still_pass_the_filter():
    """The gate must not quietly close the whole book."""
    from tennis_wc.betting.bet_filter import apply_bet_filter

    for tournament in ("National Bank Open", "WTA Berlin",
                       "ATP Challenger 75 Lexington"):
        assert apply_bet_filter(*_bettable_inputs(tournament))["decision"] == "BET", \
            tournament


def test_an_unclassifiable_tournament_is_refused_not_assumed_bettable():
    """An allow-list, not a block-list -- the same reason the props path was
    written that way after its first recommendation turned out to be a UTR
    exhibition. Resolving the 1,803 fixtures whose tour is UNKNOWN is what
    should reopen this cohort, not relaxing the gate."""
    from tennis_wc.betting.bet_filter import apply_bet_filter

    assert apply_bet_filter(*_bettable_inputs(None))["decision"] == "NO_BET"
    assert apply_bet_filter(*_bettable_inputs(""))["decision"] == "NO_BET"


def test_the_structured_level_decides_when_the_name_is_an_external_id():
    """26 tournaments the filter passed carry a bare id as their name --
    `421-2026`, `188-2026` -- across 390 BET decisions, and those are
    GRAND_SLAM, ATP_1000 and ATP_250 events. A name-only tier test refuses the
    best events on the board."""
    from tennis_wc.betting.bet_filter import apply_bet_filter

    for level in ("GRAND_SLAM", "ATP_1000", "ATP_250", "WTA_250"):
        result = apply_bet_filter(*_bettable_inputs("421-2026", level))
        assert result["decision"] == "BET", (level, result["hard_no_bet_reasons"])

    # And the level cannot launder a tier we refuse.
    assert apply_bet_filter(*_bettable_inputs("421-2026", "ITF"))["decision"] == "NO_BET"


def test_context_fields_are_read_through_their_datapoint_wrapper():
    """Every `match_context` entry is a datapoint, so a plain `.get()` returns
    the wrapper and any string test on it silently reads UNKNOWN."""
    from tennis_wc.betting.bet_filter import _context_value

    snapshot = {"match_context": {"tournament": {"value": "WTA Berlin"},
                                  "level": {"value": "WTA_500"}}}
    assert _context_value(snapshot, "tournament") == "WTA Berlin"
    assert _context_value(snapshot, "level") == "WTA_500"
    assert _context_value({"match_context": {"tournament": "WTA Berlin"}},
                          "tournament") == "WTA Berlin"
    assert _context_value({}, "tournament") == ""


# --------------------------------------------------------------------------- #
# Rank as a hard input requirement (added 2026-08-27)
# --------------------------------------------------------------------------- #
def test_a_missing_rank_is_signalled_by_the_model_at_all():
    """`select_relevant_rank_bucket(None)` returns "UNKNOWN" and the component
    reads that bucket's win rate, so a fixture with no rank produced a nudge as
    though it had learned something -- with no warning anywhere. `current_rank`
    is one of only four inputs that is not a re-slice of past results."""
    from tennis_wc.modelling.probability_model import _component_probabilities

    def _side(rank):
        return {
            "current_rank": {"value": rank},
            "opponent_rank_buckets": {
                b: {"shrinked_win_rate": {"value": 0.5}}
                for b in ("UNKNOWN", "TOP_10", "TOP_25", "TOP_50", "TOP_100",
                          "RANK_101_200", "RANK_201_PLUS")
            },
        }

    both = _component_probabilities({"player_a": _side(30), "player_b": _side(40)})
    warned = {w for c in both for w in c.warnings}
    assert not any(w.startswith("missing_current_rank") for w in warned)

    one = _component_probabilities({"player_a": _side(30), "player_b": _side(None)})
    warned = {w for c in one for w in c.warnings}
    assert "missing_current_rank_b" in warned


def test_a_fixture_with_no_rank_cannot_become_a_bet():
    """Gated for measurement before profit: on the 49.5% of fixtures where the
    independent inputs are present the model draws level with the market
    (Delta log-loss +0.0161, CI [-0.0063, +0.0379]); on the rest it loses by
    +0.0639. One ROI over both makes that unanswerable."""
    from tennis_wc.betting.bet_filter import apply_bet_filter

    snapshot, pricing = _bettable_inputs("National Bank Open", "ATP_250")
    assert apply_bet_filter(snapshot, pricing)["decision"] == "BET"

    pricing = dict(pricing)
    pricing["model"] = {"components": [
        {"warnings": ["missing_current_rank_b"]},
    ]}
    result = apply_bet_filter(snapshot, pricing)
    assert result["decision"] == "NO_BET"
    assert "missing_rank_inputs" in result["hard_no_bet_reasons"]


def test_missing_inputs_and_thin_inputs_are_named_separately():
    """"We hold nothing to price this with" and "what we hold looks thin" call
    for different fixes, and folding them together is how the rank gap stayed
    invisible for months."""
    from tennis_wc.betting.bet_filter import apply_bet_filter

    snapshot, pricing = _bettable_inputs("National Bank Open", "ATP_250")
    pricing = dict(pricing)
    pricing["model"] = {"components": [{"warnings": ["missing_current_rank_a"]}]}
    reasons = apply_bet_filter(snapshot, pricing)["hard_no_bet_reasons"]
    assert "missing_rank_inputs" in reasons
    assert "data_quality_score_below_65" not in reasons

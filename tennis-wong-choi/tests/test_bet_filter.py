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

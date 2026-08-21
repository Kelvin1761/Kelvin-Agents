"""The live odds provider must say what it SAW, not only what it returned.

`SportsbetOddsProvider` is what the 09:00 card job runs -- `get_odds_provider()`
returns it, not the scrape fallback -- and it had seven silent `continue`s and no
counter on any of them. An empty return was indistinguishable from "the book is
not open yet", which is exactly the ambiguity that ran the pipeline three days
dark while every log line looked normal.
"""
from __future__ import annotations

import logging

import pytest

from tennis_wc.providers.sportsbet_provider import (
    MATCH_WINNER_TOKENS,
    SportsbetOddsProvider,
)


def _provider() -> SportsbetOddsProvider:
    # Built without __init__ so the test needs no API key or base URL: the
    # counting under test is pure parsing.
    provider = SportsbetOddsProvider.__new__(SportsbetOddsProvider)
    provider.bookmaker_name = "Sportsbet"
    return provider


def _fixture():
    return {"game_masterID": "g1", "sport": "tennis",
            "team_names": {"home_team": "Learner Tien",
                           "away_team": "Frances Tiafoe"}}


def _market(name, odds):
    return {"type": "moneyline", "name": name, "odds": odds,
            "selection_name": name}


def test_a_parseable_fixture_produces_a_row():
    provider = _provider()
    body = {"odds_data": {"Learner Tien": _market("Learner Tien", 2.10),
                          "Frances Tiafoe": _market("Frances Tiafoe", 1.75)}}
    rows = provider._normalise_wagerwise_fixture(_fixture(), body)
    assert len(rows) == 1
    assert rows[0]["player_a_odds"] == 2.10
    assert rows[0]["player_b_odds"] == 1.75


def test_a_renamed_market_is_counted_and_named_not_passed_over():
    """The failure that looks exactly like a closed book."""
    provider = _provider()
    import collections

    drops: collections.Counter = collections.Counter()
    body = {"odds_data": {
        "Result": {"type": "outright_result", "odds": 2.10},
        "Result2": {"type": "outright_result", "odds": 1.75},
    }}
    assert provider._normalise_wagerwise_fixture(_fixture(), body, drops) == []
    reason = next(iter(drops))
    assert "markets_present_none_matched" in reason
    for token in MATCH_WINNER_TOKENS:
        assert token in reason


def test_no_markets_at_all_is_a_different_reason_from_a_renamed_one():
    """These need opposite responses: wait, versus fix the parser."""
    provider = _provider()
    import collections

    drops: collections.Counter = collections.Counter()
    assert provider._normalise_wagerwise_fixture(
        _fixture(), {"odds_data": {}}, drops) == []
    assert list(drops) == ["no_markets_in_odds_data"]


def test_a_selection_matching_neither_team_is_counted():
    provider = _provider()
    import collections

    drops: collections.Counter = collections.Counter()
    body = {"odds_data": {"Someone Else": _market("Someone Else", 2.10),
                          "Another Person": _market("Another Person", 1.75)}}
    assert provider._normalise_wagerwise_fixture(_fixture(), body, drops) == []
    assert list(drops) == ["selection_name_did_not_match_either_team"]


def test_a_non_dict_market_entry_does_not_raise():
    provider = _provider()
    body = {"odds_data": {"junk": "not a dict",
                          "Learner Tien": _market("Learner Tien", 2.10),
                          "Frances Tiafoe": _market("Frances Tiafoe", 1.75)}}
    assert len(provider._normalise_wagerwise_fixture(_fixture(), body)) == 1


def test_input_present_and_output_empty_logs_a_warning(caplog):
    """The one combination that must never be quiet."""
    provider = _provider()
    import collections

    with caplog.at_level(logging.WARNING):
        provider._record_parse_stats(
            55, collections.Counter({"markets_present_none_matched_x": 55}), [])
    assert provider.last_parse_stats == {
        "fixtures_in_response": 55, "rows_parsed": 0,
        "drops": {"markets_present_none_matched_x": 55},
    }
    assert "55 fixtures in the response and 0 rows parsed" in caplog.text
    assert "not a closed book" in caplog.text


def test_a_genuinely_empty_response_is_not_reported_as_a_parser_problem(caplog):
    """An empty listing IS a legitimate output at 18:00. Do not cry wolf."""
    provider = _provider()
    import collections

    with caplog.at_level(logging.WARNING):
        provider._record_parse_stats(0, collections.Counter(), [])
    assert provider.last_parse_stats["fixtures_in_response"] == 0
    assert "parser problem" not in caplog.text


def test_stats_are_published_even_on_a_successful_run():
    provider = _provider()
    import collections

    provider._record_parse_stats(60, collections.Counter({"x": 5}), [{}] * 55)
    assert provider.last_parse_stats["fixtures_in_response"] == 60
    assert provider.last_parse_stats["rows_parsed"] == 55

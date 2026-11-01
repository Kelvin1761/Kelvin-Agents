"""Rule context boundaries and forwarding, independent of player outcomes."""
import itertools
from dataclasses import replace
import pytest

from tennis_wc.research_kernel.rule_kernel import SetRule, match_win_probability
from tennis_wc.research_kernel.rule_resolver import DRAW, UnsupportedRules, resolve_slam_rules


def resolve(event="ausopen", year=2024, tour="ATP", draw=DRAW):
    return resolve_slam_rules(event=event, year=year, tour=tour, draw=draw)


@pytest.mark.parametrize("event,year,expected", [
    ("ausopen", 2011, (None, None)), ("ausopen", 2018, (None, None)),
    ("ausopen", 2019, (6, 10)), ("ausopen", 2024, (6, 10)),
    ("frenchopen", 2011, (None, None)), ("frenchopen", 2021, (None, None)),
    ("frenchopen", 2022, (6, 10)), ("frenchopen", 2024, (6, 10)),
    ("wimbledon", 2011, (None, None)), ("wimbledon", 2018, (None, None)),
    ("wimbledon", 2019, (12, 7)), ("wimbledon", 2021, (12, 7)),
    ("wimbledon", 2022, (6, 10)), ("wimbledon", 2024, (6, 10)),
    ("usopen", 2011, (6, 7)), ("usopen", 2021, (6, 7)),
    ("usopen", 2022, (6, 10)), ("usopen", 2024, (6, 10)),
])
@pytest.mark.parametrize("tour,best_of", [("ATP", 5), ("WTA", 3)])
def test_source_transition_boundaries(event, year, expected, tour, best_of):
    rules = resolve(event, year, tour)
    assert rules.best_of == best_of
    assert rules.deciding == SetRule(*expected)
    assert rules.ordinary == SetRule(6, 7)
    assert rules.source_urls and rules.registry_sha256 and rules.rule_id


@pytest.mark.parametrize("kwargs", [
    {"year": 2010}, {"year": 2025}, {"year": 2026}, {"year": True}, {"year": 2024.0},
    {"year": "2024"}, {"year": None}, {"event": "Australian Open"}, {"event": "AO"},
    {"event": None}, {"event": []}, {"tour": "atp"}, {"tour": "mixed"}, {"tour": []},
    {"draw": "qualifying"}, {"draw": "doubles"}, {"draw": "juniors"}, {"draw": None},
])
def test_unknown_or_ambiguous_context_is_rejected(kwargs):
    with pytest.raises(UnsupportedRules):
        resolve(**kwargs)


@pytest.mark.parametrize("tour", ["ATP", "WTA"])
def test_cancelled_edition_is_not_a_supported_hypothetical_match(tour):
    with pytest.raises(UnsupportedRules, match="cancelled edition"):
        resolve("wimbledon", 2020, tour)


def test_first_server_and_deciding_rule_forwarding():
    for event, year, tour, first in itertools.product(
            ["ausopen", "frenchopen", "wimbledon", "usopen"], [2018, 2019, 2021, 2022],
            ["ATP", "WTA"], [True, False]):
        rules = resolve(event, year, tour)
        result = rules.match_probability(.72, .58, first_a=first)
        expected = match_win_probability(.72, .58, best_of=rules.best_of, first_a=first,
                                         ordinary_rule=SetRule(6, 7), deciding_rule=rules.deciding)
        assert result == expected
    rules = resolve("wimbledon", 2019)
    assert rules.match_probability(.72, .58, first_a=True) != replace(
        rules, deciding=SetRule(6, 10)).match_probability(.72, .58, first_a=True)


def test_corrupt_packaged_registry_cannot_be_used(monkeypatch, tmp_path):
    from tennis_wc.research_kernel import rule_resolver
    (tmp_path/"slam_rules.json").write_text("{}")
    rule_resolver._registry.cache_clear()
    monkeypatch.setattr(rule_resolver, "files", lambda _: tmp_path)
    try:
        with pytest.raises(RuntimeError, match="fingerprint mismatch"):
            resolve()
    finally:
        rule_resolver._registry.cache_clear()

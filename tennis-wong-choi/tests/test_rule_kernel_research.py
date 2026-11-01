"""Research kernel contract: mass, infinite tail and explicit rule distinctions."""
import pytest

from tennis_wc.research_kernel.rule_kernel import SetRule, match_win_probability, set_law


RULES = [SetRule(6, 7), SetRule(6, 10), SetRule(12, 7), SetRule(None, None)]


@pytest.mark.parametrize("rule", RULES)
@pytest.mark.parametrize("first", [False, True])
def test_set_mass_service_order_and_swap(rule, first):
    law = set_law(.72, .58, first_a=first, rule=rule)
    swapped = set_law(.58, .72, first_a=not first, rule=rule)
    win = lambda x: sum(p for (winner, _), p in x.winner_server_masses().items() if winner)
    assert law.total_mass() == pytest.approx(1, abs=1e-12)
    assert win(law)+win(swapped) == pytest.approx(1, abs=1e-12)
    if rule.trigger_games is not None:
        scores = {(a, b) for a, b, _ in law.scores}
        assert (rule.trigger_games+1, rule.trigger_games) in scores
        assert ((7, 6) in scores) == (rule.trigger_games == 6)
    for (winner, server), p in law.winner_server_masses().items():
        assert 0 <= p <= 1 and type(server) is bool


def test_advantage_tail_is_not_truncated_or_renormalized():
    law = set_law(.75, .75, first_a=True, rule=SetRule(None, None))
    assert law.tail is not None and law.tail.mass > 0
    assert not any((a, b) in {(7, 6), (6, 7)} for a, b, _ in law.scores)
    tail = law.tail
    assert sum(tail.winner_mass(w) for w in (False, True)) == pytest.approx(tail.mass)
    assert tail.games_over(13.5) == tail.mass
    assert tail.games_over(15.5) == pytest.approx(tail.mass*tail.split_pair)
    assert tail.score_mass(0, True) == pytest.approx(tail.mass*tail.a_pair)
    assert law.games_over(25.5) > 0  # genuine long sets retain their probability
    assert law.games_over(-1) == pytest.approx(1)


@pytest.mark.parametrize("best_of", [3, 5])
@pytest.mark.parametrize("rule", RULES)
def test_match_swap_and_average_first_server_symmetry(best_of, rule):
    ordinary = SetRule(6, 7)
    def p(a, b, first):
        return match_win_probability(a, b, best_of=best_of, first_a=first,
                                     ordinary_rule=ordinary, deciding_rule=rule)
    assert p(.72, .58, True)+p(.58, .72, False) == pytest.approx(1, abs=1e-12)
    assert (p(.6, .6, True)+p(.6, .6, False))/2 == pytest.approx(.5, abs=1e-12)


def test_cache_cannot_bypass_invalid_input_or_first_server_types():
    rule = SetRule(6, 7)
    set_law(.6, .6, first_a=True, rule=rule)
    with pytest.raises(ValueError):
        set_law(.6, .6, first_a=1, rule=rule)
    for value in [0, 1, float("nan"), float("inf"), True, "0.6", {}]:
        with pytest.raises(ValueError):
            set_law(value, .6, first_a=True, rule=rule)
    with pytest.raises(ValueError):
        SetRule(6.0, 7)
    with pytest.raises(ValueError):
        SetRule(12, 10)

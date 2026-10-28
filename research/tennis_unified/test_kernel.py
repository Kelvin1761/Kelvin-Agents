"""Rule invariants and independently known probability identities."""
import pytest

from research.tennis_unified.kernel import hold_probability, match_probability, server_is_a, set_distribution, tiebreak_probability


def test_tiebreak_serves_one_two_two_and_continues_indefinitely():
    assert [server_is_a(i, True) for i in range(9)] == [True, False, False, True, True, False, False, True, True]
    assert [server_is_a(i, False) for i in range(9)] == [False, True, True, False, False, True, True, False, False]


@pytest.mark.parametrize('target', [7, 10])
def test_tiebreak_swap_complement_and_symmetric_players(target):
    for first in (True, False):
        assert tiebreak_probability(.6, .6, first_a=first, target=target) == pytest.approx(.5, abs=1e-12)
        assert (tiebreak_probability(.72, .58, first_a=first, target=target)
                + tiebreak_probability(.58, .72, first_a=not first, target=target)) == pytest.approx(1., abs=1e-12)


def test_standard_game_deuce_closed_form():
    assert hold_probability(.5) == pytest.approx(.5, abs=1e-12)
    assert hold_probability(.6) == pytest.approx(.7357292307692308)
    assert hold_probability(.6)+hold_probability(.4) == pytest.approx(1.)


@pytest.mark.parametrize('best_of', [3, 5])
def test_match_and_set_terminal_mass_conservation(best_of):
    for first in (True, False):
        distribution = dict(set_distribution(.75, .75, first, .5))
        assert sum(distribution.values()) == pytest.approx(1., abs=1e-12)
        assert all((max(a, b) >= 6 and abs(a-b) >= 2) or sorted((a, b)) == [6, 7] for a, b in distribution)
    assert match_probability(.75, .75, best_of=best_of) == pytest.approx(.5, abs=1e-12)


def test_seven_and_ten_point_tiebreaks_are_not_interchangeable():
    assert tiebreak_probability(.72, .58, target=10) > tiebreak_probability(.72, .58, target=7)

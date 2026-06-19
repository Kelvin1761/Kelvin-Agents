from __future__ import annotations

from tennis_wc.modelling import market_models as mm


def test_expected_total_games_in_sane_range():
    # Two solid holders, mild favourite, BO3 -> ~22-26 games.
    eg = mm.expected_total_games(0.78, 0.75, 0.60, 3)
    assert 21.0 <= eg <= 27.0
    # BO5 produces clearly more games.
    assert mm.expected_total_games(0.80, 0.80, 0.55, 5) > eg


def test_total_games_over_probability_monotonic_in_line():
    eg = mm.expected_total_games(0.78, 0.75, 0.60, 3)
    p_low = mm.total_games_over_probability(20.5, eg, 3)
    p_high = mm.total_games_over_probability(24.5, eg, 3)
    assert p_low > p_high  # higher line -> lower P(over)
    assert 0.0 < p_high < p_low < 1.0


def test_expected_sets_decreases_with_dominance():
    assert mm.expected_sets(0.5, 3) >= mm.expected_sets(0.85, 3)
    assert 2.0 <= mm.expected_sets(0.85, 3) <= 2.6
    assert mm.expected_sets(0.5, 5) > mm.expected_sets(0.5, 3)


def test_shrunk_ace_mean_pulls_short_samples_toward_prior():
    # A short history of very high aces is shrunk toward the ATP prior (6.26).
    raw_high = mm.shrunk_ace_mean([12, 12, 11, 13, 12, 10, 11, 12, 12, 11], "ATP", 3)
    assert raw_high is not None
    assert 6.26 < raw_high < 12.0  # shrunk below the raw ~11.6
    # WTA prior is much lower.
    wta = mm.shrunk_ace_mean([3] * 12, "WTA", 3)
    assert wta < 4.0
    # Best-of-5 scales the mean up.
    assert mm.shrunk_ace_mean([6] * 20, "ATP", 5) > mm.shrunk_ace_mean([6] * 20, "ATP", 3)


def test_shrunk_ace_mean_none_on_empty():
    assert mm.shrunk_ace_mean([], "ATP", 3) is None


def test_game_handicap_cover_probability_bounds():
    p = mm.game_handicap_cover_probability(-3.5, True, 0.80, 0.75, 0.65, 3)
    assert 0.0 < p < 1.0
    # Giving more games away lowers the cover probability.
    p_easier = mm.game_handicap_cover_probability(-1.5, True, 0.80, 0.75, 0.65, 3)
    assert p_easier > p

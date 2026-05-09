from __future__ import annotations


def test_bet_filter_placeholder_imports():
    from tennis_wc.betting.bet_filter import classify_edge

    assert classify_edge(0.01) == "NO_BET"
    assert classify_edge(0.03) == "WATCHLIST"
    assert classify_edge(0.04) == "SMALL_BET"
    assert classify_edge(0.06) == "STANDARD_BET"
    assert classify_edge(0.09) == "STRONG_BET"

from __future__ import annotations


def test_market_implied_probability():
    from tennis_wc.features.market import implied_probability
    from tennis_wc.betting.edge import calculate_edge

    assert implied_probability(2.0) == 0.5
    assert round(calculate_edge(0.55, 0.50), 3) == 0.05

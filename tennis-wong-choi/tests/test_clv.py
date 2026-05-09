from __future__ import annotations


def test_clv_placeholder_imports():
    from tennis_wc.betting.clv import calculate_clv, clv_label

    assert round(calculate_clv(2.1, 2.0), 3) == 0.05
    assert clv_label(0.01) == "POSITIVE"

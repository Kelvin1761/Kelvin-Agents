from __future__ import annotations


def test_staking_placeholder_imports():
    from tennis_wc.betting.staking import stake_for_decision

    assert stake_for_decision("SMALL_BET") == 0.25
    assert stake_for_decision("STANDARD_BET", ["low_sample"]) == 0.375

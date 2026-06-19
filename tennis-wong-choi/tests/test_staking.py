from __future__ import annotations

import os


def test_non_bet_bands_stake_zero():
    from tennis_wc.betting.staking import stake_for_decision

    assert stake_for_decision("NO_BET", 0.6, 2.0) == 0.0
    assert stake_for_decision("WATCHLIST", 0.6, 2.0) == 0.0


def test_half_kelly_sizes_and_floors_at_one_unit():
    os.environ["MAX_STAKE_UNITS"] = "5.0"
    os.environ["MIN_STAKE_UNITS"] = "1.0"
    os.environ["KELLY_FRACTION"] = "0.5"
    os.environ["STAKE_ROUND_INCREMENT"] = "0.5"
    os.environ["DEFAULT_BANKROLL_UNITS"] = "100"
    from tennis_wc.betting.staking import stake_for_decision

    # Strong +EV (p=0.60 @ 2.00): full Kelly 0.20, half 0.10 -> 10u, capped at 5u.
    assert stake_for_decision("STANDARD_BET", 0.60, 2.00) == 5.0
    # Thin +EV (p=0.52 @ 2.00): full 0.04, half 0.02 -> 2u.
    assert stake_for_decision("SMALL_BET", 0.52, 2.00) == 2.0
    # Every recommended bet is at least the 1u floor.
    assert stake_for_decision("SMALL_BET", 0.505, 2.00) >= 1.0


def test_negative_ev_at_price_stakes_zero():
    from tennis_wc.betting.staking import stake_for_decision

    # p=0.70 but only 1.40 on offer (fair odds ~1.43) -> -EV at price -> 0.
    assert stake_for_decision("STRONG_BET", 0.70, 1.40) == 0.0


def test_risk_adjustments_reduce_stake():
    from tennis_wc.betting.staking import kelly_stake_units

    base = kelly_stake_units(0.60, 2.00)
    reduced = kelly_stake_units(0.60, 2.00, ["low_sample"])
    assert reduced <= base

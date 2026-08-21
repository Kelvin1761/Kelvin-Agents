"""Stage 1: walk-forward serve and return profiles."""
from __future__ import annotations


def _setup(tmp_path, monkeypatch):
    from conftest import configure_test_db

    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.database.db import get_connection

    init_db()
    conn = get_connection()
    for pid, name in ((1, "A"), (2, "B")):
        conn.execute(
            "INSERT INTO players (id, name, tour, source_provider, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?)", (pid, name, "ATP", "test", "now", "now"))
    return conn


def _history(conn, pid, day, *, hold, ret=0.35, surface="hard", opponent_elo=1500.0,
             bp_faced=4.0, bp_saved=2.0, bp_chances=5.0, bp_converted=2.0, ace=6.0):
    conn.execute(
        """INSERT INTO player_match_history
           (provider_match_id, player_id, opponent_id, tour, match_date,
            tournament_external_id, tournament_level, round, format, won,
            source_provider, raw_response_id, created_at, surface,
            hold_rate, break_rate, return_points_won_pct,
            first_serve_points_won_pct, second_serve_points_won_pct,
            ace_count, double_fault_count, break_points_faced, break_points_saved,
            break_points_chances, break_points_converted, opponent_elo)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (f"H{pid}-{day}", pid, 99, "ATP", day, "T1", "ATP250", "R1", "BO3", 1,
         "test", 0, "now", surface, hold, 0.2, ret, 0.72, 0.52, ace, 2.0,
         bp_faced, bp_saved, bp_chances, bp_converted, opponent_elo),
    )


def test_profile_reads_only_matches_before_the_date(tmp_path, monkeypatch):
    """The whole point of an as-of feature: no row from the match or later."""
    from tennis_wc.features.serve_return import serve_return_profile

    conn = _setup(tmp_path, monkeypatch)
    for day, hold in (("2026-01-01", 0.60), ("2026-02-01", 0.62), ("2026-03-01", 0.64),
                      ("2026-04-01", 0.66), ("2026-05-01", 0.68), ("2026-06-01", 0.99)):
        _history(conn, 1, day, hold=hold)
    conn.commit()

    # 2026-06-01 is the match being priced; its own row must not be read.
    profile = serve_return_profile(conn, 1, "2026-06-01")
    assert profile.matches == 5
    assert abs(profile.serve["hold_rate"] - 0.64) < 1e-9
    assert profile.is_usable

    # Nothing before the first match at all.
    assert not serve_return_profile(conn, 1, "2025-12-31").is_usable


def test_thin_history_is_reported_not_hidden(tmp_path, monkeypatch):
    """Half the priced board has no serve history; a caller must be able to tell."""
    from tennis_wc.features.serve_return import serve_return_profile, MIN_SAMPLES

    conn = _setup(tmp_path, monkeypatch)
    for index in range(MIN_SAMPLES - 1):
        _history(conn, 1, f"2026-01-0{index + 1}", hold=0.70)
    conn.commit()

    profile = serve_return_profile(conn, 1, "2026-06-01")
    assert profile.matches == MIN_SAMPLES - 1
    assert profile.serve["hold_rate"] is not None   # the value exists
    assert not profile.is_usable                    # and is not to be trusted


def test_surface_narrows_the_window_but_never_empties_it(tmp_path, monkeypatch):
    """Surface is recorded on 46.2% of rows; a filter would empty half the board."""
    from tennis_wc.features.serve_return import serve_return_profile

    conn = _setup(tmp_path, monkeypatch)
    for index in range(8):
        _history(conn, 1, f"2026-01-{index + 1:02d}", hold=0.60, surface="hard")
    for index in range(6):
        _history(conn, 1, f"2026-02-{index + 1:02d}", hold=0.80, surface="clay")
    conn.commit()

    clay = serve_return_profile(conn, 1, "2026-06-01", surface="clay")
    assert clay.surface == "clay" and clay.matches == 6
    assert abs(clay.serve["hold_rate"] - 0.80) < 1e-9

    # Too few on grass: fall back to the pooled window rather than return nothing.
    grass = serve_return_profile(conn, 1, "2026-06-01", surface="grass")
    assert grass.surface is None and grass.matches == 14
    assert grass.is_usable


def test_break_point_ratios_come_with_their_denominator(tmp_path, monkeypatch):
    """A save rate is only as good as the number of break points behind it."""
    from tennis_wc.features.serve_return import serve_return_profile

    conn = _setup(tmp_path, monkeypatch)
    for index in range(6):
        _history(conn, 1, f"2026-01-0{index + 1}", hold=0.70,
                 bp_faced=4.0, bp_saved=3.0, bp_chances=8.0, bp_converted=2.0)
    conn.commit()

    profile = serve_return_profile(conn, 1, "2026-06-01")
    assert abs(profile.serve["break_point_save_rate"] - 0.75) < 1e-9
    assert profile.serve["break_points_faced"] == 4.0
    assert abs(profile.returning["break_point_conversion_rate"] - 0.25) < 1e-9
    assert profile.returning["break_points_chances"] == 8.0


def test_opponent_strength_travels_with_the_rates(tmp_path, monkeypatch):
    """78% hold against ITF opposition is not 78% against a tour returner."""
    from tennis_wc.features.serve_return import serve_return_profile

    conn = _setup(tmp_path, monkeypatch)
    for index in range(6):
        _history(conn, 1, f"2026-01-0{index + 1}", hold=0.78, opponent_elo=1400.0)
    conn.commit()

    assert serve_return_profile(conn, 1, "2026-06-01").opponent_elo_mean == 1400.0


def test_hold_model_reduces_to_the_rolling_average_at_zero_weights():
    """The baseline the extra features have to beat, expressed in the model.

    Stage 2's fitted weights (0.35 return, 0.04 Elo) beat that baseline out of
    sample on 4,152 matches with P(no improvement) = 0.010 -- and by 0.00066
    against an actual hold SD of 0.1768, which is 0.37% of one standard
    deviation. Real and far too small to move a price against a 5-7% takeout.
    """
    from tennis_wc.features.serve_return import ServeReturnProfile
    from tennis_wc.props.hold_model import estimate_hold

    def profile(hold, return_points, opponent_elo, matches=20):
        return ServeReturnProfile(
            player_id=1, as_of_date="2026-06-01", matches=matches,
            serve={"hold_rate": hold},
            returning={"return_points_won_pct": return_points},
            opponent_elo_mean=opponent_elo, surface=None,
        )

    server = profile(0.78, 0.34, 1600.0)
    returner = profile(0.70, 0.44, 1700.0)

    flat = estimate_hold(server, returner, return_weight=0.0, elo_weight=0.0)
    assert flat.probability == 0.78, "zero weights must be the rolling average"

    fitted = estimate_hold(server, returner, return_weight=0.35, elo_weight=0.04)
    assert fitted.probability < flat.probability, "a better returner lowers hold"
    assert fitted.return_adjustment < 0 and fitted.strength_adjustment < 0

    # A server with no usable history falls back and says so.
    thin = profile(0.78, 0.34, 1600.0, matches=2)
    assert not estimate_hold(thin, returner).is_usable


def test_simulator_reproduces_the_settled_record():
    """Checked before pricing, so a simulator bug cannot look like an edge.

    The original version of this test asserted that equal holds of 0.75 give a
    mean total of 25.16, "the settled record's mean match total". Re-measured
    on 2026-08-10 that record reads **22.49** over 1,954 completed best-of-three
    matches, and 22.92 over the bettable tiers -- 25.16 belonged to some other
    population. So the test compared the most competitive matchup there is
    against a number that was not the average it claimed to be, and passed the
    simulator while it over-predicted the total by 0.9 to 1.3 games on every
    surface once fed the model's own asymmetric holds.

    Two lessons are pinned below: an even matchup must produce MORE games than
    the all-matches average, not equal to it, and the property that actually
    broke -- the mix of two-set and three-set matches -- is now asserted
    directly.
    """
    import statistics
    from tennis_wc.props.match_simulator import simulate_match

    even = simulate_match(0.75, 0.75, trials=3000)
    total = statistics.mean(a + b for a, b in zip(even.games_a, even.games_b))
    # Above the 22.49 all-matches average, because an even match is the longest
    # kind there is, and inside touching distance of it. The old bound of
    # 24.5-25.8 was not wrong about the simulator, only about what it was being
    # compared to.
    assert 22.9 <= total <= 25.8, total
    assert abs(even.expected_margin()) < 0.25, "equal holds cannot favour a side"

    # The defect the dispersion parameter exists to fix: without it the
    # simulator makes matches too competitive. Measured over 996 settled
    # matches, 60.9% finish in two sets against a fixed-hold 55.2%.
    def straight_rate(distribution):
        return sum(
            1 for a, b in zip(distribution.sets_a, distribution.sets_b)
            if min(a, b) == 0
        ) / distribution.trials

    from tennis_wc.props.match_simulator import FITTED_HOLD_GAP_DISPERSION

    fixed = simulate_match(0.80, 0.72, trials=4000, dispersion=0.0)
    dispersed = simulate_match(0.80, 0.72, trials=4000,
                               dispersion=FITTED_HOLD_GAP_DISPERSION)
    assert straight_rate(dispersed) > straight_rate(fixed) + 0.03, (
        f"{straight_rate(fixed):.3f} -> {straight_rate(dispersed):.3f}"
    )
    assert statistics.mean(
        a + b for a, b in zip(dispersed.games_a, dispersed.games_b)
    ) < statistics.mean(
        a + b for a, b in zip(fixed.games_a, fixed.games_b)
    ), "more two-set matches means fewer games"

    lopsided = simulate_match(0.90, 0.60, trials=3000)
    assert lopsided.expected_margin() > 4.0
    assert lopsided.player_wins_a_set("a") > 0.95
    assert statistics.mean(
        a + b for a, b in zip(lopsided.games_a, lopsided.games_b)
    ) < total, "a one-sided match is shorter"

    # Deterministic: a price must not move because a simulation was reseeded.
    assert (simulate_match(0.8, 0.7, trials=500).games_a
            == simulate_match(0.8, 0.7, trials=500).games_a)

    # Monotone in the server's hold.
    weak = simulate_match(0.70, 0.75, trials=2000).player_games_over(9.5)
    strong = simulate_match(0.85, 0.75, trials=2000).player_games_over(9.5)
    assert strong > weak


def test_fitted_hold_model_uses_the_whole_profile():
    """The fitted estimator reads columns the hand-set one cannot express.

    Fitted on 59,804 walk-forward matches, the largest coefficient by far is
    the RETURNER's return-points-won rate at -0.750 -- the hand-set model used
    -0.35 for the same term, less than half -- and first- and second-serve
    points won carry more weight between them (+0.349, +0.186) than the
    server's own hold rate (+0.209), which is the only serve column the
    hand-set model reads at all.
    """
    from tennis_wc.features.serve_return import ServeReturnProfile
    from tennis_wc.props.hold_model import (
        estimate_hold, estimate_hold_fitted, fitted_feature_names,
        fitted_feature_row,
    )
    from tennis_wc.props import hold_coefficients

    assert set(fitted_feature_names()) == set(hold_coefficients.COEFFICIENTS), (
        "the feature contract and the exported coefficients have diverged; "
        "rerun scripts/fit_hold_ml.py --write"
    )

    def profile(hold, first_serve, return_points, matches=25):
        return ServeReturnProfile(
            player_id=1, as_of_date="2026-06-01", matches=matches,
            serve={"hold_rate": hold, "first_serve_points_won_pct": first_serve},
            returning={"return_points_won_pct": return_points},
            opponent_elo_mean=1600.0, surface=None,
        )

    # Two servers with the SAME hold rate and different first-serve returns.
    returner = profile(0.70, 0.66, 0.40)
    weak_first_serve = profile(0.78, 0.62, 0.34)
    strong_first_serve = profile(0.78, 0.76, 0.34)

    assert (estimate_hold(weak_first_serve, returner, return_weight=0.35,
                          elo_weight=0.04).probability
            == estimate_hold(strong_first_serve, returner, return_weight=0.35,
                             elo_weight=0.04).probability), (
        "the hand-set model cannot see first-serve points won"
    )
    assert (estimate_hold_fitted(strong_first_serve, returner).probability
            > estimate_hold_fitted(weak_first_serve, returner).probability)

    # A returner it knows nothing about must not read as an average returner
    # by accident: the row carries a present/absent flag.
    row = fitted_feature_row(weak_first_serve, None)
    names = fitted_feature_names()
    assert row[names.index("returner_profile_present")] == 0.0
    assert row[names.index("returner.return_points_won_pct")] == 0.36

    # An unusable server still refuses to price rather than defaulting.
    thin = profile(0.78, 0.70, 0.34, matches=2)
    assert not estimate_hold_fitted(thin, returner).is_usable


def test_fitted_hold_falls_back_when_the_export_is_stale():
    """A coefficient file that no longer matches the features must degrade."""
    from tennis_wc.features.serve_return import ServeReturnProfile
    from tennis_wc.props import hold_coefficients
    from tennis_wc.props.hold_model import estimate_hold, estimate_hold_fitted

    def profile(hold, return_points):
        return ServeReturnProfile(
            player_id=1, as_of_date="2026-06-01", matches=25,
            serve={"hold_rate": hold}, returning={"return_points_won_pct": return_points},
            opponent_elo_mean=1600.0, surface=None,
        )

    server, returner = profile(0.78, 0.34), profile(0.70, 0.44)
    original = hold_coefficients.COEFFICIENTS
    hold_coefficients.COEFFICIENTS = {"a_column_that_no_longer_exists": 1.0}
    try:
        fallback = estimate_hold_fitted(server, returner)
    finally:
        hold_coefficients.COEFFICIENTS = original
    assert fallback.probability == estimate_hold(
        server, returner, return_weight=0.35, elo_weight=0.04
    ).probability

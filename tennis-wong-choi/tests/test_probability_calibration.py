"""Platt scaling: rescale confidence, never reorder, never look ahead."""
from __future__ import annotations

import math

from tennis_wc.modelling import probability_calibration as calib


def _overconfident(n: int = 800):
    """Scores that rank well but are pushed too far from 0.5.

    True probability p, reported as sigmoid(1.8 * logit(p)) -- the shape the
    nudges produce: better ordering, worse prices.
    """
    samples = []
    for i in range(n):
        true_p = 0.05 + 0.9 * ((i * 37) % n) / n
        reported = 1.0 / (1.0 + math.exp(-1.8 * math.log(true_p / (1 - true_p))))
        outcome = 1.0 if ((i * 7919) % 1000) / 1000.0 < true_p else 0.0
        samples.append((reported, outcome))
    return samples


def test_fit_pulls_an_overconfident_score_back():
    samples = _overconfident()
    fitted = calib.fit(samples)

    assert fitted.slope < 1.0, "an overconfident score needs a slope below 1"
    assert fitted.sample == len(samples)

    def brier(pairs):
        return sum((p - y) ** 2 for p, y in pairs) / len(pairs)

    raw = brier(samples)
    calibrated = brier([(calib.apply(p, fitted), y) for p, y in samples])
    assert calibrated < raw, "calibration must improve Brier on its own fit"


def test_calibration_cannot_reorder():
    """A monotone map is the whole point: ranking is what the nudges got right."""
    fitted = calib.fit(_overconfident())
    probabilities = [0.05, 0.2, 0.4, 0.5, 0.6, 0.8, 0.95]
    mapped = [calib.apply(p, fitted) for p in probabilities]
    assert mapped == sorted(mapped)
    assert all(0.0 < value < 1.0 for value in mapped)


def test_a_small_sample_returns_the_identity():
    """A slope fitted on fifty matches is noise wearing a coefficient."""
    small = _overconfident()[: calib.MIN_CALIBRATION_SAMPLE - 1]
    fitted = calib.fit(small)

    assert fitted.is_identity
    assert calib.apply(0.73, fitted) == 0.73


def test_a_degenerate_fit_falls_back_rather_than_inverting():
    # Outcomes anti-correlated with the score would fit a negative slope, which
    # is not a calibration result -- it is a failure.
    samples = [(0.9, 0.0)] * 400 + [(0.1, 1.0)] * 400
    fitted = calib.fit(samples)
    assert fitted.is_identity


def test_fit_as_of_only_sees_earlier_matches(tmp_path, monkeypatch):
    from conftest import configure_test_db

    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.database.db import get_connection

    init_db()
    conn = get_connection()
    for pid in (1, 2):
        conn.execute(
            "INSERT INTO players (id, name, tour, source_provider, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?)", (pid, f"P{pid}", "ATP", "test", "now", "now"))
    for i in range(300):
        day = "2026-01-%02d" % ((i % 28) + 1) if i < 250 else "2026-07-01"
        conn.execute(
            """INSERT INTO matches (id, provider_match_id, tour, match_date, tournament_id,
                   player_a_id, player_b_id, round, source_provider, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (i + 1, f"M{i}", "ATP", day, 1, 1, 2, "R1", "test", "now", "now"))
        conn.execute(
            "INSERT INTO match_results (match_id, winner_player_id, score_json, "
            "source_provider, raw_response_id, created_at) VALUES (?,?,?,?,NULL,'now')",
            (i + 1, 1 if i % 2 == 0 else 2, "{}", "test"))
        conn.execute(
            "INSERT INTO predictions (match_id, feature_set_version, selection_player_id, "
            "selection_name, model_probability, decision, stake_units, confidence, risk, "
            "pricing_json, created_at) VALUES (?,'v1',1,'P1',?, 'NO_BET',0,'low','low','{}','now')",
            (i + 1, 0.8 if i % 2 == 0 else 0.2))
    conn.commit()

    early = calib.fit_as_of(conn, "2026-02-01")
    assert early.sample == 250, "only matches before the date may be used"
    assert early.fitted_through == "2026-02-01"

    later = calib.fit_as_of(conn, "2026-08-01")
    assert later.sample == 300

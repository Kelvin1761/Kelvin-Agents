"""The wait-time harness must not read its own noise.

`required_n = (1.96 sd / roi)^2` is so sensitive to the ROI in the denominator
that letting each subset supply its own made the table incoherent: odds<=5.0
came out needing 839 bets while odds<=3.0 -- a strict subset of it -- needed
1,766. That is ROI noise squared and inverted, presented as a finding about
variance, and it points straight at whichever band got lucky.
"""
from __future__ import annotations

import importlib.util
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "measure_edge_significance", ROOT / "scripts" / "measure_edge_significance.py")
harness = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(harness)


def _bets(n, odds, win_rate, start="2026-05-01"):
    """A deterministic run of `n` bets at fixed odds with a fixed hit rate."""
    out = []
    wins = round(n * win_rate)
    for i in range(n):
        out.append({
            "date": f"2026-0{5 + i % 4}-01",
            "odds": odds,
            "pnl": (odds - 1) if i < wins else -1.0,
        })
    return out


def test_required_n_ignores_the_subsets_own_roi():
    """Two subsets with the same variance must need the same sample, however
    differently they happened to run."""
    lucky = _bets(200, 2.0, 0.60)
    unlucky = _bets(200, 2.0, 0.40)
    a = harness.summarise(lucky)
    b = harness.summarise(unlucky)
    assert a["roi_pct"] > 0 > b["roi_pct"], "fixtures must actually differ in ROI"
    assert a["required_n"] == b["required_n"]


def test_required_n_falls_as_variance_falls():
    """This is the question the table exists to answer: shorter odds carry less
    variance per bet, so the same edge proves itself in fewer bets."""
    short = harness.summarise(_bets(300, 1.5, 0.70))
    long = harness.summarise(_bets(300, 6.0, 0.20))
    assert short["per_bet_sd"] < long["per_bet_sd"]
    assert short["required_n"] < long["required_n"]


def test_required_n_matches_the_closed_form():
    bets = _bets(300, 2.0, 0.55)
    r = harness.summarise(bets)
    expected = (harness.Z_95 * r["per_bet_sd"] / harness.ASSUMED_ROI) ** 2
    assert abs(r["required_n"] - round(expected)) <= 1


def test_the_assumed_effect_is_stated_in_the_output():
    """A reader must be able to see which effect the wait was computed against;
    otherwise the number looks like a measurement rather than an assumption."""
    r = harness.summarise(_bets(200, 2.0, 0.55))
    assert r["assumed_roi_pct"] == harness.ASSUMED_ROI * 100


def test_a_generous_assumption_shortens_the_wait_and_says_so():
    lean = harness.summarise(_bets(200, 2.0, 0.55), assumed_roi=0.02)
    rich = harness.summarise(_bets(200, 2.0, 0.55), assumed_roi=0.10)
    assert lean["required_n"] > rich["required_n"]


def test_a_small_sample_returns_only_its_size():
    assert harness.summarise(_bets(10, 2.0, 0.5)) == {"n": 10}


def test_a_losing_run_is_reported_as_crossing_zero_not_significant():
    r = harness.summarise(_bets(400, 2.0, 0.40))
    assert r["roi_pct"] < 0
    assert r["significant"] is False


def test_the_bootstrap_is_seeded():
    bets = _bets(300, 2.0, 0.55)
    assert harness.summarise(bets) == harness.summarise(bets)


# --------------------------------------------------------------------------- #
# The weekly page must carry it, and must survive it failing
# --------------------------------------------------------------------------- #
def test_the_weekly_review_survives_a_broken_harness(monkeypatch):
    """A decision that depends on somebody remembering a monthly script does not
    get made, so the number goes on the weekly page. But research code must
    never take an operational report down with it -- the short-favourite wiring
    learned that the hard way when only the inner try/except was in place."""
    from tennis_wc.reports import weekly_review

    def explode():
        raise RuntimeError("harness is broken")

    monkeypatch.setattr(weekly_review, "_edge_significance_progress", explode)
    assert weekly_review._safe_edge_significance_progress() is None


def test_the_weekly_review_reports_the_assumed_effect(monkeypatch):
    """The wait is computed against an assumption, and the page has to say so --
    otherwise `3,306 注` reads as a measurement."""
    from tennis_wc.reports import weekly_review

    monkeypatch.setattr(weekly_review, "_edge_significance_progress", lambda: {
        "n": 686, "roi_pct": 6.12, "ci_low_pct": -5.12, "ci_high_pct": 16.87,
        "significant": False, "need": 3306, "months": 9.4,
        "capped_months": 6.6, "assumed_roi_pct": 5.0,
    })
    block = weekly_review._safe_edge_significance_progress()
    assert block["assumed_roi_pct"] == 5.0
    assert block["need"] == 3306


# --------------------------------------------------------------------------- #
# Only predictions written before the start may count
# --------------------------------------------------------------------------- #
import sqlite3  # noqa: E402

_SCHEMA = """
CREATE TABLE matches (id INTEGER PRIMARY KEY, tournament_id INTEGER, match_date TEXT,
    start_time_utc TEXT, player_a_id INTEGER, player_b_id INTEGER);
CREATE TABLE tournaments (id INTEGER PRIMARY KEY, name TEXT);
CREATE TABLE tournament_levels (id INTEGER PRIMARY KEY, tournament_id INTEGER, level TEXT);
CREATE TABLE match_results (id INTEGER PRIMARY KEY, match_id INTEGER, winner_player_id INTEGER);
CREATE TABLE odds_snapshots (id INTEGER PRIMARY KEY, match_id INTEGER, market TEXT,
    player_a_odds REAL, player_b_odds REAL, source_provider TEXT);
CREATE TABLE predictions (id INTEGER PRIMARY KEY, match_id INTEGER, selection_player_id INTEGER,
    model_probability REAL, decision TEXT, created_at TEXT);
"""


def _db(predictions, start="2026-09-20T10:00:00Z", winner=1):
    """One ATP 250 match, player 1 vs 2 at 2.50 / 1.55, with the given predictions."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    conn.execute("INSERT INTO tournaments VALUES (1, 'ATP Test')")
    conn.execute("INSERT INTO tournament_levels VALUES (1, 1, 'ATP_250')")
    conn.execute("INSERT INTO matches VALUES (1, 1, '2026-09-20', ?, 1, 2)", (start,))
    conn.execute("INSERT INTO match_results VALUES (1, 1, ?)", (winner,))
    conn.execute("INSERT INTO odds_snapshots VALUES (1, 1, 'match_winner', 2.5, 1.55, 'sportsbet')")
    for i, (created_at, prob) in enumerate(predictions, start=1):
        conn.execute("INSERT INTO predictions VALUES (?, 1, 1, ?, 'BET', ?)", (i, prob, created_at))
    return conn


def test_a_prediction_written_after_the_start_never_counts():
    """The 2026-10-09 finding: the latest row per selection was often written with
    the ball in the air, and all of the harness's profit lived in those rows."""
    excluded = {}
    bets = harness.load(_db([("2026-09-20T11:00:00Z", 0.60)]), excluded)
    assert bets == []
    assert excluded == {"post_start": 1}


def test_a_match_with_no_start_time_never_counts():
    excluded = {}
    bets = harness.load(_db([("2026-09-19T22:00:00Z", 0.60)], start=None), excluded)
    assert bets == []
    assert excluded == {"unverifiable": 1}


def test_a_late_reprice_does_not_hide_the_pre_match_prediction():
    """Filter first, then take the latest: a match re-priced after the start still
    contributes the last prediction that could actually have been bet."""
    bets = harness.load(_db([
        ("2026-09-19T22:00:00Z", 0.60),   # pre-match, EV>0 at 2.50
        ("2026-09-20T11:00:00Z", 0.10),   # after the start, EV<0 -- must be ignored
    ]))
    assert len(bets) == 1
    assert bets[0]["pnl"] == 1.5
    assert bets[0]["decision"] == "BET"


def test_mock_book_prices_are_never_the_earliest_price():
    conn = _db([("2026-09-19T22:00:00Z", 0.60)])
    conn.execute("DELETE FROM odds_snapshots")
    conn.execute("INSERT INTO odds_snapshots VALUES (1, 1, 'match_winner', 9.0, 1.05, 'mock')")
    conn.execute("INSERT INTO odds_snapshots VALUES (2, 1, 'match_winner', 2.5, 1.55, 'sportsbet')")
    bets = harness.load(conn)
    assert [b["odds"] for b in bets] == [2.5]

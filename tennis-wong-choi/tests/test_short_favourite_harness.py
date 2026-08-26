"""The short-favourite harness must refuse to answer before it can.

The cohort's whole history is 254 observations with a CI crossing zero, and the
one place the model was not beaten is exactly where a premature verdict would
be most expensive.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

_spec = importlib.util.spec_from_file_location(
    "measure_short_favourites", ROOT / "scripts" / "measure_short_favourites.py")
harness = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(harness)


def _rows(n: int, model: float, market: float, won: int) -> list[dict]:
    return [{"match_date": "2026-08-01", "tour": "ATP", "odds": 1.5,
             "overround": 1.07, "model": model, "market": market, "won": won}
            for _ in range(n)]


def test_a_small_sample_gets_no_verdict_however_clean_the_direction():
    """P(model better) = 1.000 on 100 rows is still 100 rows."""
    rows = _rows(100, model=0.9, market=0.5, won=1)
    gap = harness._paired_gap(rows)
    assert gap["probability_model_better"] == 1.0
    assert "NOT ENOUGH DATA" in harness._verdict(gap, min_sample=600)


def test_a_large_clean_sample_does_get_a_verdict():
    rows = _rows(700, model=0.9, market=0.5, won=1)
    gap = harness._paired_gap(rows)
    assert harness._verdict(gap, min_sample=600).startswith("MODEL AHEAD")


def test_a_large_sample_going_the_other_way_says_so():
    rows = _rows(700, model=0.1, market=0.5, won=1)
    assert harness._verdict(harness._paired_gap(rows),
                            min_sample=600).startswith("MARKET AHEAD")


def test_a_dead_heat_is_undecided_not_a_loss_for_the_model():
    """With the two identical, every resampled mean is exactly 0.0, so a
    tail-probability test reads P(model better) = 0.0 and calls a perfect tie
    MARKET AHEAD. An interval of [0, 0] does not clear zero either way."""
    rows = _rows(350, model=0.6, market=0.6, won=1) + \
        _rows(350, model=0.6, market=0.6, won=0)
    gap = harness._paired_gap(rows)
    assert gap["probability_model_better"] == 0.0
    assert harness._verdict(gap, min_sample=600).startswith("UNDECIDED")


def test_a_lean_the_probability_test_would_promote_stays_undecided():
    """The exact case the CI rule exists for.

    480 wins and 220 losses at model 0.70 against market 0.60 gives
    P(model better) = 0.973 -- clear of the 0.95 bar -- with a CI of
    [-0.0298, +0.0005] that still contains zero. A probability-only rule
    promotes that; the real cohort sits at P=0.748 and would eventually drift
    into the same trap.
    """
    rows = _rows(480, model=0.70, market=0.60, won=1) + \
        _rows(220, model=0.70, market=0.60, won=0)
    gap = harness._paired_gap(rows)
    assert gap["probability_model_better"] >= harness.DECISIVE_PROBABILITY
    assert gap["ci_low"] < 0 < gap["ci_high"], gap
    assert harness._verdict(gap, min_sample=600).startswith("UNDECIDED")


def test_the_bootstrap_is_seeded_so_a_rerun_cannot_move_the_gate():
    rows = _rows(300, model=0.7, market=0.55, won=1)
    first = harness._paired_gap(rows)
    second = harness._paired_gap(rows)
    assert first == second


def test_overround_bands_expose_a_thin_margin_masquerading_as_an_edge():
    """"We are better here" and "the book is barely trying here" produce the
    same log-loss gap. Measured, the margin is flat (1.0716 at 1.0-1.4 against
    1.0768 at 3+), which is what makes the cohort worth watching."""
    rows = [{"match_date": "2026-08-01", "tour": "ATP", "odds": 1.2,
             "overround": 1.02, "model": 0.8, "market": 0.8, "won": 1}] * 30
    rows += [{"match_date": "2026-08-01", "tour": "ATP", "odds": 4.0,
              "overround": 1.15, "model": 0.2, "market": 0.2, "won": 0}] * 30
    bands = {b["band"]: b for b in harness._overround_by_band(rows)}
    assert bands["1-1.4"]["mean_overround"] < bands["3-99"]["mean_overround"]


# --------------------------------------------------------------------------- #
# Forward monitoring: the lead has to be on a page somebody reads
# --------------------------------------------------------------------------- #
def test_the_weekly_review_reports_the_cohort_progress(tmp_path, monkeypatch):
    """A lead that is only checked when somebody remembers to check it dies
    quietly. This is the only open one left, so its sample count and current
    verdict go on the page that gets sent."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from conftest import configure_test_db

    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.reports import weekly_review

    init_db()
    monkeypatch.setattr(
        weekly_review, "_short_favourite_progress",
        lambda: {"n": 254, "need": 600, "delta": -0.01125,
                 "probability": 0.748, "verdict": "NOT ENOUGH DATA (n=254, need 600)"},
    )
    rendered = weekly_review.render_weekly_review("2026-08-26")
    assert "254/600" in rendered
    assert "NOT ENOUGH DATA" in rendered
    assert "領先" in rendered, "a negative delta means the model is ahead"


def test_a_broken_harness_cannot_take_the_weekly_page_down(tmp_path, monkeypatch):
    """Research code must not be load-bearing for the operational report."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from conftest import configure_test_db

    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.reports import weekly_review

    init_db()
    monkeypatch.setattr(
        weekly_review, "_short_favourite_progress",
        lambda: (_ for _ in ()).throw(RuntimeError("harness exploded")),
    )
    try:
        weekly_review.render_weekly_review("2026-08-26")
    except RuntimeError:
        raise AssertionError("the weekly page must survive a broken harness")

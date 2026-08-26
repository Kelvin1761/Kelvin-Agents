"""Coherence is decided by disagreement against margin, not by significance.

The pooled log-loss comparison in this harness clears its interval
(-0.00517, CI [-0.01009, -0.00066]) and the direction is still not tradeable,
because the book agrees with itself to a fifth of its own overround. A
significance test alone would have promoted it.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

_spec = importlib.util.spec_from_file_location(
    "measure_market_coherence", ROOT / "scripts" / "measure_market_coherence.py")
harness = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(harness)


def _identity(name: str, rows: list[dict]) -> dict:
    return {"name": name, "rows": rows}


def _row(anchor: float, derived: float, margin: float, won=None, date=None) -> dict:
    return {"match_id": 1, "won": won, "anchor": anchor, "derived": derived,
            "margin": margin, "odds_a": 2.0, "odds_b": 2.0, "match_date": date}


# --------------------------------------------------------------------------- #
# De-vig
# --------------------------------------------------------------------------- #
def test_power_devig_returns_a_normalised_distribution():
    probs = harness.power_devig([6.25, 6.25, 1.83, 3.75])
    assert abs(sum(probs) - 1.0) < 1e-6
    assert all(0 < p < 1 for p in probs)


def test_power_devig_takes_less_off_the_longshot_than_proportional():
    """The margin is loaded onto longshots, and assuming it is spread evenly
    invents a signal: proportional de-vig selected 326 bets at average odds
    5.79 where the power form selected 69 at 3.77."""
    odds = [1.5, 5.0, 8.0, 20.0]
    power = harness.power_devig(odds)
    total = sum(1 / o for o in odds)
    proportional = [(1 / o) / total for o in odds]
    assert power[-1] < proportional[-1], "longshot must be shaded further down"
    assert power[0] > proportional[0], "favourite must keep more"


# --------------------------------------------------------------------------- #
# The decision rule
# --------------------------------------------------------------------------- #
def test_a_disagreement_below_the_margin_is_not_tradeable():
    rows = [_row(0.50, 0.515, 0.0749) for _ in range(100)]
    report = harness.coherence(_identity("x", rows))
    assert report["ratio_to_margin"] < 1.0
    assert report["tradeable"] is False


def test_a_disagreement_above_the_margin_is_tradeable():
    """The rule must be able to say yes, or it is not a test."""
    rows = [_row(0.50, 0.62, 0.05) for _ in range(100)]
    report = harness.coherence(_identity("x", rows))
    assert report["ratio_to_margin"] >= 1.0
    assert report["tradeable"] is True


def test_significance_alone_does_not_make_it_tradeable():
    """A tiny, real, well-measured gap is still not a trade."""
    rows = [_row(0.50, 0.53, 0.0749, won=1, date=f"2026-08-{1 + i % 28:02d}")
            for i in range(400)]
    report = harness.coherence(_identity("x", rows))
    assert report["pooled"]["probability_derived_better"] > 0.95
    assert report["tradeable"] is False


def test_the_split_half_is_reported_so_a_decayed_edge_cannot_hide():
    """The whole pooled effect sat in the earlier half: first -0.01047
    (P=0.999), second +0.00012 (P=0.472)."""
    rows = [_row(0.50, 0.60, 0.07, won=1, date="2026-06-01") for _ in range(150)]
    rows += [_row(0.50, 0.50, 0.07, won=1, date="2026-08-01") for _ in range(150)]
    report = harness.coherence(_identity("x", rows))
    assert report["first_half"]["delta_logloss"] < report["second_half"]["delta_logloss"]
    assert report["second_half"]["delta_logloss"] == 0.0


def test_an_ungraded_identity_still_reports_coherence():
    """`both players won a set` is not a stored settled field, and coherence
    does not need an outcome -- arithmetic is enough."""
    rows = [_row(0.40, 0.394, 0.0891) for _ in range(50)]
    report = harness.coherence(_identity("x", rows))
    assert "pooled" not in report
    assert report["ratio_to_margin"] < 1.0

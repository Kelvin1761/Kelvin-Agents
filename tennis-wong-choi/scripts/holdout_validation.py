#!/usr/bin/env python3
"""Score a fitted coefficient on data it has never seen.

Every measurement in this rebuild so far has been in-sample in one specific
way: the game-margin slope of 11.26 was fitted on the settled matches and then
the replay was scored over the same period.  A coefficient graded on its own
training data will always look at least as good as the one it replaced, so that
comparison cannot tell us whether the change generalises.

This splits the record chronologically, refits the slope on the EARLY window
only, and scores both the old and the refitted slope on the LATE window alone.

Usage:
  PYTHONPATH=src .venv/bin/python scripts/holdout_validation.py --split 2026-07-30
"""
from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path
import sqlite3
import statistics
import sys

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR / "src"))

from tennis_wc.evaluation.corpus import point_in_time_clause  # noqa: E402


def _margin_rows(conn, before: str | None = None, since: str | None = None):
    """(model probability, actual game margin) for settled, completed matches."""
    where = ["r.winner_player_id IS NOT NULL", "m.player_a_id <> m.player_b_id"]
    params: list = []
    if before:
        where.append("m.match_date < ?")
        params.append(before)
    if since:
        where.append("m.match_date >= ?")
        params.append(since)
    rows = conn.execute(
        f"""
        SELECT r.score_json,
               (SELECT CASE WHEN p.selection_player_id = m.player_a_id
                            THEN p.model_probability ELSE 1.0 - p.model_probability END
                  FROM predictions p WHERE p.match_id = m.id
                 ORDER BY p.id DESC LIMIT 1) AS model_p
        FROM matches m JOIN match_results r ON r.match_id = m.id
        WHERE {" AND ".join(where)}
        """,
        tuple(params),
    ).fetchall()
    out = []
    for row in rows:
        if row["model_p"] is None or not row["score_json"]:
            continue
        try:
            score = json.loads(row["score_json"])
        except (TypeError, ValueError):
            continue
        a, b = score.get("player_a_games"), score.get("player_b_games")
        if a is None or b is None or score.get("retired"):
            continue
        out.append((float(row["model_p"]), float(a) - float(b)))
    return out


def _fit_slope(pairs) -> tuple[float, float, int]:
    """Weighted least squares of margin on (probability - 0.5), by bucket.

    Bucketing first stops a handful of extreme probabilities from setting the
    slope for everything.
    """
    buckets = collections.defaultdict(list)
    for probability, margin in pairs:
        buckets[round(probability * 10) / 10].append(margin)
    points = [
        (key, statistics.mean(values), len(values))
        for key, values in sorted(buckets.items())
        if len(values) >= 20
    ]
    if len(points) < 3:
        return 0.0, 0.0, len(pairs)
    weight = sum(n for _, _, n in points)
    mean_x = sum((k - 0.5) * n for k, _, n in points) / weight
    mean_y = sum(m * n for _, m, n in points) / weight
    numerator = sum(n * ((k - 0.5) - mean_x) * (m - mean_y) for k, m, n in points)
    denominator = sum(n * ((k - 0.5) - mean_x) ** 2 for k, _, n in points)
    slope = numerator / denominator if denominator else 0.0
    return slope, mean_y - slope * mean_x, len(pairs)


def _margin_error(pairs, slope: float, intercept: float = 0.0) -> float:
    """Mean absolute error of the predicted margin, in games."""
    if not pairs:
        return float("nan")
    return sum(
        abs((intercept + slope * (probability - 0.5)) - margin)
        for probability, margin in pairs
    ) / len(pairs)


def _window_composition(conn, split: str) -> dict:
    """What each window is MADE OF, before any of its numbers are read.

    A chronological split is only "one strategy over time" when the population
    either side of it is the same. In tennis it is not: the tour runs clay ->
    grass -> hard, so a date split is a SURFACE split. Measured at
    2026-07-30 the earlier window was 37.9% clay and 37.7% grass and the later
    one was 73.5% hard and 0% grass, and reading the two as before-and-after
    reversed the verdict on a hold model that was in fact no better on any
    surface. The audit had already recorded the same trap for ITF -- 8.5% of
    the earlier window against 49.1% of the later -- and it recurred on surface
    without anyone noticing.

    So this prints first, and every window number below it should be read
    through it.
    """
    from tennis_wc.props.daily import _tier_of

    rows = conn.execute(
        """
        SELECT p.match_date,
               COALESCE((SELECT tl.surface FROM tournament_levels tl
                          WHERE tl.tournament_id = m.tournament_id
                            AND tl.surface IS NOT NULL
                          ORDER BY tl.id DESC LIMIT 1), 'unknown') AS surface,
               t.name AS tournament_name,
               m.source_provider,
               CASE WHEN m.start_time_utc IS NULL THEN 0 ELSE 1 END AS timeable
        FROM prop_tracker p
        JOIN matches m ON m.id = p.match_id
        LEFT JOIN tournaments t ON t.id = m.tournament_id
        WHERE p.result_status IN ('WON','LOST') AND p.stake_units > 0
          AND p.is_value = 1 AND {pit}
        """.format(pit=point_in_time_clause('p'))
    ).fetchall()
    out: dict = {}
    for label, keep in (("train", lambda d: d < split),
                        ("holdout", lambda d: d >= split)):
        window = [row for row in rows if keep(row["match_date"] or "")]
        total = len(window) or 1
        surfaces = collections.Counter(row["surface"] for row in window)
        tiers = collections.Counter(
            _tier_of(row["tournament_name"]) for row in window)
        # Which PATH created the fixture, and whether its price can be placed
        # in time at all. Found 2026-08-11 to split the record in two with
        # opposite results -- -1.73% on the fixtures whose odds carry a matching
        # event id, +17.01% on the ones where the link is name-matching only --
        # and no tool printed it, so nobody could have noticed.
        sources = collections.Counter(row["source_provider"] for row in window)
        timeable = sum(1 for row in window if row["timeable"])
        out[label] = {
            "settled_bets": len(window),
            "surface_share": {k: round(v / total, 3)
                              for k, v in surfaces.most_common()},
            "tier_share": {k: round(v / total, 3) for k, v in tiers.most_common()},
            "fixture_source_share": {k: round(v / total, 3)
                                     for k, v in sources.most_common()},
            "price_timing_verifiable_share": round(timeable / total, 3),
        }
    warnings = []
    shares = [set(out[w]["surface_share"]) for w in ("train", "holdout")]
    missing = (shares[0] | shares[1]) - (shares[0] & shares[1])
    if missing:
        warnings.append(f"surfaces present in only one window: {sorted(missing)}")
    for window_label in ("train", "holdout"):
        verifiable = out[window_label]["price_timing_verifiable_share"]
        if verifiable < 0.9:
            warnings.append(
                f"{window_label}: only {verifiable:.0%} of bets have a match start "
                "time, so the rest cannot be shown to be priced before the off"
            )
    out["warning"] = warnings or None
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=PROJECT_DIR / "tennis_wc.db")
    parser.add_argument("--split", required=True,
                        help="First date of the held-out window, YYYY-MM-DD.")
    parser.add_argument("--old-slope", type=float, default=6.15,
                        help="The slope the borrowed share curve implied.")
    args = parser.parse_args()

    from tennis_wc.props.player_model import _GAME_MARGIN_SLOPE

    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    train = _margin_rows(conn, before=args.split)
    test = _margin_rows(conn, since=args.split)
    train_slope, train_intercept, _ = _fit_slope(train)
    full_slope, _, _ = _fit_slope(train + test)

    # Paired bootstrap on the SAME test matches: resampling matches rather than
    # comparing two independent averages keeps the comparison honest about how
    # much of the gap is just which fixtures landed in the window.
    import random

    rng = random.Random(20260810)
    errors = [
        (abs(args.old_slope * (p - 0.5) - m),
         abs(train_intercept + train_slope * (p - 0.5) - m))
        for p, m in test
    ]
    diffs = []
    for _ in range(2000):
        sample = [errors[rng.randrange(len(errors))] for _ in errors]
        diffs.append(
            sum(old for old, _ in sample) / len(sample)
            - sum(new for _, new in sample) / len(sample)
        )
    diffs.sort()

    roi_windows = {}
    try:
        from tennis_wc.props.settlement import (
            model_vs_market_scorecard,
            prop_roi_report,
        )

        write_conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
        write_conn.row_factory = sqlite3.Row
        for label, kwargs in (
            ("train", {"as_of_date": args.split}),
            ("holdout", {"since_date": args.split}),
        ):
            report = prop_roi_report(write_conn, **kwargs)
            scorecard = model_vs_market_scorecard(write_conn, **kwargs)
            roi_windows[label] = {
                "overall": {
                    "settled": report["overall"]["settled"],
                    "roi": report["overall"]["roi"],
                },
                "by_family": {
                    family: {"settled": stats["settled"], "roi": stats["roi"]}
                    for family, stats in
                    (report.get("by_family_formal_profile") or {}).items()
                    if stats.get("settled")
                },
                "scorecard": {
                    "settled": scorecard.get("settled"),
                    "model_brier": (scorecard.get("model") or {}).get("brier"),
                    "market_brier": (scorecard.get("market") or {}).get("brier"),
                    "by_family": {
                        family: {
                            "settled": stats.get("settled"),
                            "model_brier": (stats.get("model") or {}).get("brier"),
                            "market_brier": (stats.get("market") or {}).get("brier"),
                        }
                        for family, stats in
                        (scorecard.get("by_family") or {}).items()
                    },
                },
            }
    except Exception as exc:
        roi_windows = {"error": str(exc)}

    payload = {
        "split": args.split,
        # Deliberately first in the payload: the composition decides whether
        # any of the numbers under it mean what they look like.
        "window_composition": _window_composition(conn, args.split),
        "train_matches": len(train),
        "test_matches": len(test),
        "slope_fitted_on_train_only": round(train_slope, 3),
        "slope_fitted_on_everything": round(full_slope, 3),
        "slope_currently_shipped": _GAME_MARGIN_SLOPE,
        "test_mean_absolute_error_games": {
            "old_slope": round(_margin_error(test, args.old_slope), 4),
            "train_fitted_slope": round(
                _margin_error(test, train_slope, train_intercept), 4
            ),
            "shipped_slope": round(_margin_error(test, _GAME_MARGIN_SLOPE), 4),
        },
        "train_mean_absolute_error_games": {
            "old_slope": round(_margin_error(train, args.old_slope), 4),
            "train_fitted_slope": round(
                _margin_error(train, train_slope, train_intercept), 4
            ),
        },
        "holdout_improvement_games": {
            "point_estimate": round(diffs[len(diffs) // 2], 4),
            "ci_95": [round(diffs[int(len(diffs) * 0.025)], 4),
                      round(diffs[int(len(diffs) * 0.975)], 4)],
            "probability_no_improvement": round(
                sum(1 for d in diffs if d <= 0) / len(diffs), 4
            ),
        },
        "roi_by_window": roi_windows,
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

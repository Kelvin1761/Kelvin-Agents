#!/usr/bin/env python3
"""Fit the hold estimate on the serve/return corpus and export coefficients.

Stage 2 fitted two weights by grid search over one column each. This fits the
whole profile -- both players' serve and return rates, break-point rates, the
opposition quality each rate was earned against, and how many matches back
each rate is -- as a ridge regression, and writes the result to
``src/tennis_wc/props/hold_coefficients.py`` as plain floats.

Three things this deliberately does NOT do:

* it does not learn from prop outcomes. A few hundred settled bets over 44
  days will overfit any model with real capacity; the hold rate has 59,804
  walk-forward training matches and is the quantity every games and sets
  family is a function of;
* it does not use a boosted tree. One was measured (400 iterations,
  HistGradientBoostingRegressor) and scored within 0.003 of the ridge on every
  population large enough to read, so it would cost the daily path numpy and
  scikit-learn at runtime plus a pickled artifact to version, for nothing;
* it does not use surface. See ``hold_model.fitted_feature_row``.

Walk-forward discipline is enforced twice: the rolling windows are advanced
only after a whole date has been scored, and the result is asserted identical
to ``features.serve_return.serve_return_profile`` on a random sample before
anything is written.

Usage:
  PYTHONPATH=src .venv/bin/python scripts/fit_hold_ml.py --split 2026-05-10
"""
from __future__ import annotations

import argparse
import collections
import json
import math
from pathlib import Path
import random
import sqlite3
import sys

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR / "src"))

from tennis_wc.features.serve_return import (  # noqa: E402
    DEFAULT_WINDOW, MIN_SAMPLES, ServeReturnProfile, _RETURN_COLUMNS,
    _SERVE_COLUMNS, serve_return_profile,
)
from tennis_wc.props.hold_model import (  # noqa: E402
    estimate_hold, fitted_feature_names, fitted_feature_row,
)

HISTORY_COLUMNS = (*_SERVE_COLUMNS, *_RETURN_COLUMNS, "opponent_elo")
OUTPUT = PROJECT_DIR / "src" / "tennis_wc" / "props" / "hold_coefficients.py"


def _mean(values):
    usable = [v for v in values if v is not None]
    return sum(usable) / len(usable) if usable else None


class _Windows:
    """Per-player rolling windows over the history seen so far.

    ``serve_return_profile`` issues two window scans per sample; at 65k samples
    that is 130k scans of a 346k-row table. This produces the same window in
    one pass, and the equivalence is asserted rather than assumed -- a fast
    reimplementation of a walk-forward window is exactly the kind of thing that
    quietly starts including the match it is predicting.
    """

    def __init__(self, window: int = DEFAULT_WINDOW):
        self._pooled = collections.defaultdict(
            lambda: collections.deque(maxlen=window)
        )
        self._by_surface = collections.defaultdict(
            lambda: collections.deque(maxlen=window)
        )

    def observe(self, player_id, surface, row) -> None:
        self._pooled[player_id].append(row)
        if surface:
            self._by_surface[(player_id, str(surface).lower())].append(row)

    def profile(self, player_id, as_of_date, surface=None) -> ServeReturnProfile:
        rows = None
        used_surface = None
        if surface:
            candidate = self._by_surface.get((player_id, str(surface).lower()))
            if candidate is not None and len(candidate) >= MIN_SAMPLES:
                rows, used_surface = list(candidate), str(surface).lower()
        if rows is None:
            rows = list(self._pooled.get(player_id) or ())
        serve = {name: _mean(r[name] for r in rows) for name in _SERVE_COLUMNS}
        returning = {name: _mean(r[name] for r in rows) for name in _RETURN_COLUMNS}
        faced, saved = serve.get("break_points_faced"), serve.get("break_points_saved")
        serve["break_point_save_rate"] = (
            saved / faced if faced and saved is not None and faced > 0 else None
        )
        chances = returning.get("break_points_chances")
        converted = returning.get("break_points_converted")
        returning["break_point_conversion_rate"] = (
            converted / chances if chances and converted is not None and chances > 0
            else None
        )
        return ServeReturnProfile(
            player_id=int(player_id), as_of_date=str(as_of_date), matches=len(rows),
            serve=serve, returning=returning,
            opponent_elo_mean=_mean(r["opponent_elo"] for r in rows),
            surface=used_surface,
        )


def build_samples(conn, since: str):
    windows = _Windows()
    samples = []
    pending: list[dict] = []
    current_date = None
    columns = ", ".join(HISTORY_COLUMNS)
    cursor = conn.execute(
        f"""
        SELECT player_id, opponent_id, match_date, surface, {columns}
        FROM player_match_history
        WHERE hold_rate IS NOT NULL
        ORDER BY match_date ASC, id ASC
        """
    )
    for row in cursor:
        row = dict(row)
        if current_date is not None and row["match_date"] != current_date:
            for done in pending:
                windows.observe(done["player_id"], done["surface"],
                                {name: done[name] for name in HISTORY_COLUMNS})
            pending = []
        current_date = row["match_date"]
        pending.append(row)
        if row["match_date"] < since or row["opponent_id"] is None:
            continue
        server = windows.profile(row["player_id"], row["match_date"], row["surface"])
        if not server.is_usable:
            continue
        returner = windows.profile(row["opponent_id"], row["match_date"], row["surface"])
        samples.append({
            "date": row["match_date"],
            "player_id": row["player_id"],
            "surface": row["surface"],
            "server": server,
            # Kept whether or not it is usable: both estimators check
            # ``is_usable`` themselves and must see the same input.
            "returner": returner,
            "y": float(row["hold_rate"]),
        })
    return samples


def verify_windows(conn, samples, count: int, seed: int = 20260810) -> int:
    rng = random.Random(seed)
    mismatched = 0
    for sample in rng.sample(samples, min(count, len(samples))):
        reference = serve_return_profile(
            conn, sample["player_id"], sample["date"], surface=sample["surface"]
        )
        mine = sample["server"]
        if reference.matches != mine.matches:
            mismatched += 1
            continue
        for column in _SERVE_COLUMNS:
            a, b = reference.serve.get(column), mine.serve.get(column)
            if (a is None) != (b is None) or (a is not None and abs(a - b) > 1e-9):
                mismatched += 1
                break
    return mismatched


def _paired_bootstrap(errors_a, errors_b, seed=20260810, trials=2000):
    rng = random.Random(seed)
    n = len(errors_a)
    diffs = []
    for _ in range(trials):
        idx = [rng.randrange(n) for _ in range(n)]
        diffs.append(sum(errors_a[i] for i in idx) / n
                     - sum(errors_b[i] for i in idx) / n)
    diffs.sort()
    return {
        "mean_improvement": round(sum(diffs) / len(diffs), 6),
        "ci_95": [round(diffs[int(trials * 0.025)], 6),
                  round(diffs[int(trials * 0.975)], 6)],
        "probability_no_improvement": round(
            sum(1 for d in diffs if d <= 0) / trials, 4),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, default=PROJECT_DIR / "tennis_wc.db")
    ap.add_argument("--since", default="2024-01-01",
                    help="first date kept as a training row; earlier history still fills the windows")
    ap.add_argument("--split", default="2026-05-10",
                    help="first date of the held-out window (default: the day the prop board starts)")
    ap.add_argument("--verify", type=int, default=60)
    ap.add_argument("--write", action="store_true",
                    help="write src/tennis_wc/props/hold_coefficients.py")
    args = ap.parse_args()

    import numpy as np
    from sklearn.linear_model import RidgeCV

    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    samples = build_samples(conn, args.since)
    train = [s for s in samples if s["date"] < args.split]
    test = [s for s in samples if s["date"] >= args.split]
    print(f"samples {len(samples)}  train {len(train)} "
          f"({train[0]['date']}..{train[-1]['date']})  "
          f"test {len(test)} ({test[0]['date']}..{test[-1]['date']})")

    mismatched = verify_windows(conn, samples, args.verify)
    print(f"walk-forward window equivalence: "
          f"{args.verify - mismatched}/{args.verify} identical to serve_return_profile")
    if mismatched:
        print("ABORT: the streaming window does not reproduce serve_return_profile")
        return 1

    names = list(fitted_feature_names())
    X = np.array([fitted_feature_row(s["server"], s["returner"]) for s in train])
    y = np.array([s["y"] for s in train])
    X_test = np.array([fitted_feature_row(s["server"], s["returner"]) for s in test])
    y_test = np.array([s["y"] for s in test])

    model = RidgeCV(alphas=np.logspace(-3, 4, 30)).fit(X, y)
    fitted = np.clip(model.predict(X_test), 0.30, 0.98)
    rolling = np.array([s["server"].serve.get("hold_rate") or 0.75 for s in test])
    handset = np.array([
        estimate_hold(s["server"], s["returner"],
                      return_weight=0.35, elo_weight=0.04).probability
        for s in test
    ])

    # A single match's realised hold rate is roughly ten Bernoulli trials, so
    # most of its variance cannot be predicted by anything. Scoring against
    # that floor says what share of the ACHIEVABLE variance each model gets;
    # scoring against zero error says only that tennis is noisy.
    floor = float(np.mean(y_test * (1 - y_test) / 10.0))
    total = float(np.var(y_test))
    metrics = {}
    print(f"\nrealised hold mean {y_test.mean():.4f} sd {y_test.std():.4f}; "
          f"binomial floor rmse {math.sqrt(floor):.4f} "
          f"({100*(total-floor)/total:.1f}% of variance is achievable)")
    print(f"{'model':>12} {'MAE':>9} {'RMSE':>9} {'R2_vs_floor':>12}  P(no improvement)")
    for label, prediction in (("rolling", rolling), ("hand-set", handset),
                              ("fitted", fitted)):
        mse = float(np.mean((prediction - y_test) ** 2))
        r2 = (total - mse) / (total - floor)
        boot = (None if label == "rolling" else _paired_bootstrap(
            list(np.abs(rolling - y_test)), list(np.abs(prediction - y_test))))
        metrics[label] = {
            "mae": round(float(np.mean(np.abs(prediction - y_test))), 6),
            "rmse": round(math.sqrt(mse), 6),
            "r2_vs_binomial_floor": round(r2, 4),
            "bootstrap_vs_rolling": boot,
        }
        print(f"{label:>12} {metrics[label]['mae']:9.5f} "
              f"{metrics[label]['rmse']:9.5f} {r2:12.4f}  "
              f"{'--' if boot is None else boot['probability_no_improvement']}")

    coefficients = {name: float(c) for name, c in zip(names, model.coef_)}
    intercept = float(model.intercept_)

    def pure_python(row):
        value = intercept + sum(coefficients[n] * v for n, v in zip(names, row))
        return min(0.98, max(0.30, value))

    worst = max(abs(pure_python(row) - p) for row, p in zip(X_test, fitted))
    print(f"\nexported coefficients vs the fitted model: "
          f"worst absolute difference {worst:.2e}")
    if worst > 1e-9:
        print("ABORT: the export does not reproduce the model that was measured")
        return 1

    if not args.write:
        print("\n(dry run -- pass --write to update hold_coefficients.py)")
        print(json.dumps({"intercept": intercept, "alpha": float(model.alpha_),
                          "coefficients": coefficients}, indent=2))
        return 0

    lines = [
        '"""Fitted hold-model coefficients. GENERATED -- do not edit by hand.',
        "",
        "Written by ``scripts/fit_hold_ml.py``. Refit it rather than adjusting a",
        "number here: the feature order is declared by",
        "``hold_model.fitted_feature_names`` and the two must agree or",
        "``estimate_hold_fitted`` falls back to the hand-set estimator.",
        '"""',
        "from __future__ import annotations",
        "",
        f"TRAINED_FROM = {train[0]['date']!r}",
        f"TRAINED_THROUGH = {args.split!r}",
        f"TRAINING_ROWS = {len(train)}",
        f"HOLDOUT_ROWS = {len(test)}",
        f"RIDGE_ALPHA = {float(model.alpha_)!r}",
        "",
        "# Out-of-sample on the held-out window, MAE and the share of the",
        "# achievable (above-binomial-floor) variance explained.",
        "HOLDOUT_METRICS = " + json.dumps(metrics, indent=4).replace("null", "None"),
        "",
        f"INTERCEPT = {intercept!r}",
        "",
        "COEFFICIENTS = {",
    ]
    for name in names:
        lines.append(f"    {name!r}: {coefficients[name]!r},")
    lines.append("}")
    OUTPUT.write_text("\n".join(lines) + "\n")
    print(f"wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

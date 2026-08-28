#!/usr/bin/env python3
"""Which secondary signal is costing us clay? Measured answer: none of them.

MEASUREMENT ONLY. Nothing reads this to decide a bet.

WHAT THE DEFICIT IS

Scored on the population a bet is actually chosen from -- tier-bettable
(TOUR/CHALLENGER), graded, both sides carrying an as-of rank and Elo -- the
model is level with the market on hard and grass and loses on clay:

    hard    n=316  model AUC 0.6895  market 0.7056   log-loss 0.6429 / 0.6252
    clay    n=312            0.6520          0.7198            0.6754 / 0.6057
    grass   n=202            0.6495          0.6125            0.6883 / 0.6925

Clay is a RANKING deficit, not a calibration one: temperature scaling moves its
log-loss only 0.6708 -> 0.6666 against a market at 0.6126, while the AUC gap to
the market is 0.053 against 0.010 on hard.

THE HYPOTHESIS THIS REFUTED

A first pass reconstructed the Elo backbone from `elo_history.rating_as_of`
today, treated `logit(stored) - logit(backbone)` as "the nudge", and found that
scaling that residual to zero improved clay by Delta log-loss -0.0307,
CI [-0.0551, -0.0072], monotone in the scale factor. Read as "the nine nudges
are costing us clay", it looked like a clean surface-conditional fix.

It was leakage. `player_elo_history` is DERIVED from `player_match_history`,
which has grown to 361,200 rows since those predictions were made -- so a
rating recomputed for a date in June is built from matches that predate June but
were ingested afterwards. Every date filter passes and the information set is
still larger than the model had. Scaling the residual to zero was not removing
nudges; it was swapping the model's Elo for a better-informed Elo.

Rebuilding the components from each fixture's STORED feature snapshot -- which
is what this script does, and what a test pins against
`predict_match_probability` -- gives the opposite answer:

    clay, removing ONE nudge          every one is null or HURTS
      head_to_head_edge               +0.0051  [+0.0029, +0.0074]
      serve_return_edge               +0.0036  [+0.0016, +0.0055]
      opponent_rank_bucket_edge       +0.0028  [+0.0011, +0.0045]
      tournament_level_edge           +0.0018  [+0.0005, +0.0031]
    clay, removing ALL NINE           +0.0140  [+0.0081, +0.0201]  HURTS

So the nudges are the only thing making clay less bad, and the deficit has
another cause. REJECTED -- do not re-open without a harness that reproduces the
shipped probability.

WHAT IT DOES

Rebuilds each fixture's components from its stored feature snapshot, reproduces
the shipped combiner, then removes one nudge (or all of them) and reports the
paired change per surface. Hard and grass are printed as controls: a clay fix
that moves them is moving stones, not fixing anything.

Usage:
    PYTHONPATH=src .venv/bin/python scripts/ablate_surface_nudges.py
    PYTHONPATH=src .venv/bin/python scripts/ablate_surface_nudges.py --json
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import random
import sqlite3
import sys

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR / "src"))

from tennis_wc.modelling.probability_model import (  # noqa: E402
    ELO_BACKBONE_WEIGHTS,
    NUDGE_GAINS,
    _component_probabilities,
    _is_active_component,
    _MAX_TOTAL_NUDGE,
)
from tennis_wc.props.daily import _tier_bettable  # noqa: E402

BOOTSTRAP_SEED = 20260829
BOOTSTRAP_RESAMPLES = 4000
MIN_SAMPLE = 100
SURFACES = ("clay", "hard", "grass")

_FIXTURES_SQL = """
WITH first_odds AS (
    SELECT match_id, MIN(id) AS snapshot_id
    FROM odds_snapshots
    WHERE match_id IS NOT NULL AND market = 'match_winner'
    GROUP BY match_id
)
SELECT m.id, m.match_date, m.player_a_id, m.player_b_id, m.tour, m.round,
       r.winner_player_id, o.player_a_odds, o.player_b_odds,
       t.name AS tournament_name,
       (SELECT tl.level FROM tournament_levels tl
         WHERE tl.tournament_id = m.tournament_id
         ORDER BY tl.id DESC LIMIT 1) AS level,
       LOWER(COALESCE((SELECT tl.surface FROM tournament_levels tl
         WHERE tl.tournament_id = m.tournament_id AND tl.surface IS NOT NULL
         ORDER BY tl.id DESC LIMIT 1), 'unknown')) AS surface
FROM matches m
JOIN match_results r ON r.match_id = m.id
JOIN first_odds f ON f.match_id = m.id
JOIN odds_snapshots o ON o.id = f.snapshot_id
LEFT JOIN tournaments t ON t.id = m.tournament_id
WHERE r.winner_player_id IS NOT NULL
ORDER BY m.match_date, m.id
"""


def _logit(p: float) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def _sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def _latest_snapshot(conn, match_id: int, player_id: int) -> dict | None:
    """The newest surviving feature snapshot for one side.

    Retention blanks superseded BODIES and keeps the rows, so a blanked body has
    to be skipped rather than parsed.
    """
    row = conn.execute(
        """
        SELECT features_json FROM feature_snapshots
        WHERE match_id = ? AND player_id = ? AND features_json != ''
        ORDER BY id DESC LIMIT 1
        """,
        (match_id, player_id),
    ).fetchone()
    if not row:
        return None
    try:
        payload = json.loads(row[0])
    except (TypeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


DROP_ALL = "__ALL__"


def combine(components, dropped: str | None = None) -> float:
    """The shipped combiner, with one nudge (or all of them) removed.

    Reproduced rather than imported because the point is to vary NUDGE_GAINS,
    and the shipped function reads the module-level dict. A test asserts this
    copy still matches `predict_match_probability` for `dropped=None`.

    `dropped=DROP_ALL` needs its own branch. Passing a sentinel that matches no
    nudge NAME drops nothing at all -- the first version did exactly that and
    reported the all-off row as a null result while looking like it worked.
    """
    by_name = {c.name: c for c in components}
    base_logit = 0.0
    backbone_weight = 0.0
    for name, weight in ELO_BACKBONE_WEIGHTS.items():
        component = by_name.get(name)
        if component is None or not _is_active_component(component):
            continue
        base_logit += weight * _logit(component.probability)
        backbone_weight += weight
    if backbone_weight > 0:
        base_logit /= backbone_weight

    total_nudge = 0.0
    for name, gain in NUDGE_GAINS.items():
        if gain == 0.0 or name == dropped or dropped == DROP_ALL:
            continue
        component = by_name.get(name)
        if component is None or not _is_active_component(component):
            continue
        total_nudge += gain * (component.probability - 0.5)
    total_nudge = max(-_MAX_TOTAL_NUDGE, min(_MAX_TOTAL_NUDGE, total_nudge))
    return min(max(_sigmoid(base_logit + total_nudge), 0.02), 0.98)


def load(conn) -> list[dict]:
    out: list[dict] = []
    for row in conn.execute(_FIXTURES_SQL).fetchall():
        if row["surface"] not in SURFACES:
            continue
        if not _tier_bettable(row["tournament_name"], row["level"]):
            continue
        odds_a, odds_b = row["player_a_odds"], row["player_b_odds"]
        if not odds_a or not odds_b or odds_a <= 1 or odds_b <= 1:
            continue
        a = _latest_snapshot(conn, row["id"], row["player_a_id"])
        b = _latest_snapshot(conn, row["id"], row["player_b_id"])
        if a is None or b is None:
            continue
        snapshot = {
            "player_a": a, "player_b": b,
            "match_context": {"surface": {"value": row["surface"]},
                              "tour": {"value": row["tour"]},
                              "round": {"value": row["round"]}},
        }
        try:
            components = _component_probabilities(snapshot)
        except Exception:
            continue
        out.append({
            "surface": row["surface"],
            "date": row["match_date"],
            "components": components,
            "won_a": 1 if row["winner_player_id"] == row["player_a_id"] else 0,
            "market_a": (1 / odds_a) / ((1 / odds_a) + (1 / odds_b)),
        })
    return out


def _loss(p: float, won: int) -> float:
    p = min(max(p, 1e-9), 1 - 1e-9)
    return -(won * math.log(p) + (1 - won) * math.log(1 - p))


def paired(rows: list[dict], dropped: str | None) -> dict:
    """Paired bootstrap of (ablated - shipped) log-loss. Negative = removing it
    helps."""
    diffs = [
        _loss(combine(r["components"], dropped), r["won_a"])
        - _loss(combine(r["components"], None), r["won_a"])
        for r in rows
    ]
    n = len(diffs)
    if n < MIN_SAMPLE:
        return {"n": n}
    rng = random.Random(BOOTSTRAP_SEED)
    means = sorted(
        sum(rng.choice(diffs) for _ in range(n)) / n
        for _ in range(BOOTSTRAP_RESAMPLES)
    )
    lo = means[int(0.025 * BOOTSTRAP_RESAMPLES)]
    hi = means[int(0.975 * BOOTSTRAP_RESAMPLES) - 1]
    return {
        "n": n,
        "delta": round(sum(diffs) / n, 5),
        "ci_low": round(lo, 5),
        "ci_high": round(hi, 5),
        "helps": bool(hi < 0),
        "hurts": bool(lo > 0),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(PROJECT_DIR / "tennis_wc.db"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = load(conn)
    conn.close()

    by_surface = {s: [r for r in rows if r["surface"] == s] for s in SURFACES}
    report: dict = {"fixtures": {s: len(v) for s, v in by_surface.items()}, "ablations": {}}
    for name in sorted(NUDGE_GAINS):
        report["ablations"][name] = {
            s: paired(v, name) for s, v in by_surface.items()
        }
    report["all_nudges_off"] = {
        s: paired(v, DROP_ALL) for s, v in by_surface.items()
    }

    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    print("removing ONE nudge at a time; negative = removing it HELPS")
    print("fixtures: " + "  ".join(f"{s} {len(v)}" for s, v in by_surface.items()))
    print()
    header = f"  {'nudge':28s} {'gain':>5s}"
    for s in SURFACES:
        header += f" | {s + ' Δ':>9s} {'95% CI':>19s}"
    print(header)
    for name in sorted(NUDGE_GAINS):
        line = f"  {name:28s} {NUDGE_GAINS[name]:5.2f}"
        for s in SURFACES:
            r = report["ablations"][name][s]
            if "delta" not in r:
                line += f" | {'n too few':>9s} {'':>19s}"
                continue
            mark = " *" if r["helps"] else ("  " if not r["hurts"] else " x")
            line += f" | {r['delta']:+9.4f} [{r['ci_low']:+.4f},{r['ci_high']:+.4f}]{mark}"
        print(line)
    line = f"  {'(ALL NINE OFF)':28s} {'':>5s}"
    for s in SURFACES:
        r = report["all_nudges_off"][s]
        if "delta" not in r:
            line += f" | {'n too few':>9s} {'':>19s}"
            continue
        mark = " *" if r["helps"] else ("  " if not r["hurts"] else " x")
        line += f" | {r['delta']:+9.4f} [{r['ci_low']:+.4f},{r['ci_high']:+.4f}]{mark}"
    print(line)
    print()
    print("  * = removing it significantly helps this surface")
    print("  x = removing it significantly hurts (it is earning its keep)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

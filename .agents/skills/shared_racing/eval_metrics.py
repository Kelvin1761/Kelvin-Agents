#!/usr/bin/env python3
"""Canonical ranking-evaluation metrics shared by the AU and HKJC Wong Choi engines.

One ruler for every backtest, calibration, and reflector report. Historically the
repo carried at least four different "Good" definitions:

- positional Good  — model picks 1 and 2 both finish in the actual top 3
                     (HKJC walk-forward `good`, AU full-archive rescore `Good`);
- any-2 Good       — any 2 of the model top 3 finish in the actual top 3
                     (AU cached walk-forward `good`, cumulative, includes Gold);
- exclusive labels — Gold / Good / Pass / 1 Hit / Miss, mutually exclusive
                     (unified race reflector meeting reports);
- assorted ad-hoc percentages derived from the above on different samples.

This module computes ALL of them from one place, so a report can state exactly
which definition a number uses, and AU vs HKJC comparisons are apples-to-apples.

Inputs are deliberately engine-agnostic: an ordered list of model picks (horse
identifiers, best first) and the set of identifiers that actually finished in
the top 3 (dead-heat safe: may contain more than 3), plus the winner.
"""
from __future__ import annotations

import hashlib
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

EXCLUSIVE_LABELS = ("Gold", "Good", "Pass", "1 Hit", "Miss")

# Every KPI above is binary on "did the pick make the top 3", which records
# nothing about HOW WRONG a miss was — a top pick beaten a length into 4th and
# one that runs 11th of 14 score identically. Competitiveness metrics close that
# gap using the pick's finishing percentile within its own field, so a 7-runner
# country maiden and an 18-runner Flemington handicap stay comparable:
#     pct = (finish_pos - 1) / (field_size - 1)      0.0 = won, 1.0 = last
COMPETITIVE_PCT = 1.0 / 3.0   # beat two-thirds of the field = ran with the leaders
BLOWOUT_PCT = 2.0 / 3.0       # finished in the back third = never in the race


def exclusive_label(top3_hits: int, top2_hits: int) -> str:
    """Mutually exclusive reflector label.

    Mirrors `performance_label_from_rows` in
    `.agents/skills/shared_racing/race_reflector/scripts/unified_reflector_core.py`:
    a race whose only hit is the model's 3rd pick counts as Miss, not 1 Hit.
    """
    if top3_hits == 3:
        return "Gold"
    if top2_hits == 2:
        return "Good"
    if top3_hits >= 2:
        return "Pass"
    if top2_hits >= 1:
        return "1 Hit"
    return "Miss"


def race_metrics(
    picks: Sequence[Any],
    actual_top3: Iterable[Any],
    winner: Any = None,
    actual_pos: Mapping[Any, int] | None = None,
    field_size: int | None = None,
) -> dict:
    """Per-race metrics under every definition in use.

    picks       — model ranking, best first (at least the top 3 where available).
    actual_top3 — identifiers that finished in the official top 3.
    winner      — identifier of the official winner (falls back to actual_pos).
    actual_pos  — optional {identifier: finish position} for winner-rank / MRR,
                  the legacy HKJC order-issue flag, and competitiveness.
    field_size  — runners that actually completed; defaults to len(actual_pos).
                  Needed to make finishing percentiles field-size neutral.
    """
    picks = list(picks)
    actual_set = set(actual_top3)
    # Dead-heat safe winner set: every identifier at official position 1.
    if actual_pos:
        winners = {horse for horse, pos in actual_pos.items() if pos == 1}
        if winner is not None:
            winners.add(winner)
    else:
        winners = {winner} if winner is not None else set()
    top3_picks = picks[:3]
    hits = sum(1 for horse in top3_picks if horse in actual_set)
    top2_hits = sum(1 for horse in picks[:2] if horse in actual_set)

    winner_rank = None
    for index, horse in enumerate(picks, 1):
        if horse in winners:
            winner_rank = index
            break

    order_issue = False
    if actual_pos is not None and len(picks) >= 4:
        order_issue = min(actual_pos.get(picks[2], 99), actual_pos.get(picks[3], 99)) < min(
            actual_pos.get(picks[0], 99), actual_pos.get(picks[1], 99)
        )

    # --- competitiveness: how wrong is a miss, not just whether it missed ---
    size = field_size or (len(actual_pos) if actual_pos else 0)
    pick_pcts: list[float | None] = []
    if actual_pos and size > 1:
        for horse in top3_picks:
            pos = actual_pos.get(horse)
            pick_pcts.append(None if pos is None else (pos - 1) / (size - 1))
    else:
        pick_pcts = [None] * len(top3_picks)
    known = [pct for pct in pick_pcts if pct is not None]
    top_pct = pick_pcts[0] if pick_pcts else None
    top2_pcts = [pct for pct in pick_pcts[:2] if pct is not None]

    return {
        "picks": picks,
        "hits": hits,
        "top2_hits": top2_hits,
        # competitiveness (None whenever positions/field size are unavailable)
        "field_size": size or None,
        "pick_positions": [actual_pos.get(h) if actual_pos else None for h in top3_picks],
        "pick_percentiles": pick_pcts,
        "top_pick_pct": top_pct,
        "mean_top3_pct": (sum(known) / len(known)) if known else None,
        "top_pick_competitive": None if top_pct is None else top_pct <= COMPETITIVE_PCT,
        "top_pick_blowout": None if top_pct is None else top_pct >= BLOWOUT_PCT,
        "top2_both_competitive": (
            all(pct <= COMPETITIVE_PCT for pct in top2_pcts) if len(top2_pcts) == 2 else None
        ),
        "top2_any_blowout": (
            any(pct >= BLOWOUT_PCT for pct in top2_pcts) if top2_pcts else None
        ),
        # cumulative KPIs
        "gold": hits == 3,
        "good_positional": len(picks) >= 2 and picks[0] in actual_set and picks[1] in actual_set,
        "good_any2": hits >= 2,
        "pass_any1": hits >= 1,
        "champion": bool(picks) and picks[0] in winners,
        "winner_in_top3": any(horse in winners for horse in top3_picks),
        "order_issue": order_issue,
        # winner-rank quality
        "winner_rank": winner_rank,
        "reciprocal_rank": (1.0 / winner_rank) if winner_rank else 0.0,
        # exclusive reflector label
        "exclusive_label": exclusive_label(hits, top2_hits),
    }


def summarize_races(race_rows: Sequence[Mapping[str, Any]]) -> dict:
    """Aggregate per-race dicts from `race_metrics` into counts and rates."""
    races = len(race_rows)
    denominator = max(1, races)
    counts = {
        "gold": sum(bool(row["gold"]) for row in race_rows),
        "good_positional": sum(bool(row["good_positional"]) for row in race_rows),
        "good_any2": sum(bool(row["good_any2"]) for row in race_rows),
        "pass_any1": sum(bool(row["pass_any1"]) for row in race_rows),
        "champion": sum(bool(row["champion"]) for row in race_rows),
        "winner_in_top3": sum(bool(row["winner_in_top3"]) for row in race_rows),
        "order_issue": sum(bool(row["order_issue"]) for row in race_rows),
    }
    hit_distribution = Counter(int(row["hits"]) for row in race_rows)
    label_counts = Counter(row["exclusive_label"] for row in race_rows)
    top3_slots = sum(min(3, len(row["picks"])) for row in race_rows)
    top3_hits = sum(int(row["hits"]) for row in race_rows)

    # Competitiveness aggregates are scored only over races that supplied
    # positions and a field size, so a mixed sample can't silently dilute them.
    def _flag(key: str) -> dict:
        scored = [row for row in race_rows if row.get(key) is not None]
        hit = sum(bool(row[key]) for row in scored)
        return {"races": len(scored), "count": hit,
                "rate": (hit / len(scored)) if scored else None}

    def _mean(key: str) -> float | None:
        values = [float(row[key]) for row in race_rows if row.get(key) is not None]
        return (sum(values) / len(values)) if values else None

    return {
        "races": races,
        "counts": counts,
        "rates": {key: value / denominator for key, value in counts.items()},
        "hit_distribution": {f"{hits}hit": hit_distribution.get(hits, 0) for hits in range(4)},
        "exclusive_labels": {label: label_counts.get(label, 0) for label in EXCLUSIVE_LABELS},
        "top3_precision": top3_hits / max(1, top3_slots),
        "mrr": sum(float(row["reciprocal_rank"]) for row in race_rows) / denominator,
        "competitiveness": {
            "top_pick_competitive": _flag("top_pick_competitive"),
            "top_pick_blowout": _flag("top_pick_blowout"),
            "top2_both_competitive": _flag("top2_both_competitive"),
            "top2_any_blowout": _flag("top2_any_blowout"),
            "mean_top_pick_pct": _mean("top_pick_pct"),
            "mean_top3_pct": _mean("mean_top3_pct"),
        },
    }


def git_commit(repo_root: Path | str | None = None) -> str:
    try:
        return (
            subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=str(repo_root) if repo_root else None,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            or "unknown"
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def build_manifest(
    race_ids: Sequence[Any],
    dates: Sequence[str] = (),
    meetings: Sequence[Any] = (),
    going_mix: Mapping[str, int] | None = None,
    repo_root: Path | str | None = None,
    extra: Mapping[str, Any] | None = None,
) -> dict:
    """Reproducibility manifest for a benchmark run.

    `race_ids` must uniquely identify each evaluated race (e.g. (meeting, race_no));
    the sample hash changes whenever the evaluated set changes.
    """
    canonical = "\n".join(sorted(str(race_id) for race_id in race_ids))
    manifest = {
        "engine_commit": git_commit(repo_root),
        "race_count": len(race_ids),
        "meeting_count": len(set(meetings)) if meetings else None,
        "date_range": [min(dates), max(dates)] if dates else None,
        "going_mix": dict(going_mix) if going_mix else None,
        "sample_hash": hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16],
    }
    if extra:
        manifest.update(extra)
    return manifest

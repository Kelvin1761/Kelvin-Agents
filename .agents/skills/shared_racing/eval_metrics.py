#!/usr/bin/env python3
"""Canonical ranking-evaluation metrics shared by the AU and HKJC Wong Choi engines.

One ruler for every backtest, calibration, and reflector report. Historically the
repo carried at least four different "Good" definitions. AU now exposes one
positional Good and one cumulative Pass:

- positional Good  — model picks 1 and 2 both finish in the actual top 3
                     (HKJC walk-forward `good`, AU full-archive rescore `Good`);
- Pass             — any 2 of the model top 3 finish in the actual top 3;
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
import math
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


def _competitive_cutoff(field_size: int) -> int:
    """Observed contender tier used for ranking diagnostics.

    The tier is the leading third of the field, with a minimum of three and a
    maximum of five runners.  This keeps a six-runner Griffin race from calling
    most of the field competitive while recognising that a 14-runner handicap
    commonly has plausible secondary contenders beyond the official placings.
    """
    return min(5, max(3, math.ceil(field_size / 3)))


def _ndcg_at_k(
    picks: Sequence[Any],
    actual_pos: Mapping[Any, int],
    *,
    cutoff: int,
    k: int,
) -> float:
    """Normalised ranking quality for the observed competitive tier."""

    def relevance(horse: Any) -> float:
        position = actual_pos.get(horse)
        if position is None or position > cutoff:
            return 0.0
        return float(cutoff + 1 - position)

    def dcg(values: Sequence[float]) -> float:
        return sum((2.0**value - 1.0) / math.log2(index + 2.0) for index, value in enumerate(values))

    observed = [relevance(horse) for horse in picks[:k]]
    ideal = sorted((relevance(horse) for horse in actual_pos), reverse=True)[:k]
    ideal_score = dcg(ideal)
    return dcg(observed) / ideal_score if ideal_score > 0 else 0.0


def exclusive_label(top3_hits: int, top2_hits: int, gold: bool | None = None) -> str:
    """Mutually exclusive reflector label.

    Mirrors `performance_label_from_rows` in
    `.agents/skills/shared_racing/race_reflector/scripts/unified_reflector_core.py`:
    a race whose only hit is the model's 3rd pick counts as Miss, not 1 Hit.

    `gold` lets the caller pass the capture-at-4 definition (see `race_metrics`).
    Left None it falls back to the strict 3-of-3 reading, so callers that only
    have hit counts — the HKJC reflector among them — keep their old labels.
    """
    if gold if gold is not None else (top3_hits == 3):
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
    top3_capture_at4_count = sum(1 for horse in picks[:4] if horse in actual_set)
    top3_capture_at5_count = sum(1 for horse in picks[:5] if horse in actual_set)
    actual_top3_count = len(actual_set)
    top3_capture_at4 = top3_capture_at4_count / actual_top3_count if actual_top3_count else None
    top3_capture_at5 = top3_capture_at5_count / actual_top3_count if actual_top3_count else None

    rank_lookup = {horse: index for index, horse in enumerate(picks, 1)}
    actual_top3_ranks = [rank_lookup.get(horse) for horse in actual_set]
    known_top3_ranks = [rank for rank in actual_top3_ranks if rank is not None]
    top3_mean_model_rank = (
        sum(known_top3_ranks) / len(known_top3_ranks)
        if known_top3_ranks and len(known_top3_ranks) == len(actual_top3_ranks)
        else None
    )
    top3_worst_model_rank = (
        max(known_top3_ranks)
        if known_top3_ranks and len(known_top3_ranks) == len(actual_top3_ranks)
        else None
    )

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
    competitive_cutoff = _competitive_cutoff(size) if actual_pos and size > 1 else None
    competitive_set = (
        {horse for horse, position in actual_pos.items() if position <= competitive_cutoff}
        if actual_pos and competitive_cutoff is not None
        else set()
    )
    competitive_hits_at5 = len(set(picks[:5]) & competitive_set)
    competitive_recall_at5 = (
        competitive_hits_at5 / len(competitive_set) if competitive_set else None
    )
    competitive_precision_at5 = (
        competitive_hits_at5 / min(5, len(picks)) if competitive_set and picks else None
    )
    ndcg_at5 = (
        _ndcg_at_k(picks, actual_pos, cutoff=competitive_cutoff, k=5)
        if actual_pos and competitive_cutoff is not None
        else None
    )

    top3_all_within_top4_flag = (
        top3_capture_at4_count == actual_top3_count if actual_top3_count else None
    )
    return {
        "picks": picks,
        "hits": hits,
        "top2_hits": top2_hits,
        "actual_top3_count": actual_top3_count,
        "top3_capture_at4_count": top3_capture_at4_count,
        "top3_capture_at5_count": top3_capture_at5_count,
        "top3_capture_at4": top3_capture_at4,
        "top3_capture_at5": top3_capture_at5,
        "top3_all_within_top4": top3_all_within_top4_flag,
        "top3_all_within_top5": (
            top3_capture_at5_count == actual_top3_count if actual_top3_count else None
        ),
        "actual_top3_model_ranks": sorted(
            (rank if rank is not None else len(picks) + 1) for rank in actual_top3_ranks
        ),
        "top3_mean_model_rank": top3_mean_model_rank,
        "top3_worst_model_rank": top3_worst_model_rank,
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
        "competitive_cutoff": competitive_cutoff,
        "competitive_field_size": len(competitive_set) if competitive_cutoff is not None else None,
        "competitive_hits_at5": competitive_hits_at5 if competitive_cutoff is not None else None,
        "competitive_recall_at5": competitive_recall_at5,
        "competitive_precision_at5": competitive_precision_at5,
        "ndcg_at5": ndcg_at5,
        # cumulative KPIs
        #
        # ⚠️ 2026-08-03：`gold` 由「頭三揀全部上名」(hits == 3) 改成
        # **「實際前三全部落喺模型頭四揀之內」**。Kelvin 要追嘅係捕捉率 ——
        # 三隻上名馬有冇一隻走漏，而唔係頭三格有幾整齊。
        #
        # 新定義係舊定義嘅**超集**（hits == 3 ⟹ 三隻都喺頭三揀 ⟹ 喺頭四揀），
        # 所以任何一場舊 Gold 一定仍然係 Gold，數字只會升唔會跌。
        # 舊定義保留成 `gold_strict`，因為之前所有紀錄都係用佢量嘅，
        # 要同歷史對得上就要有得攞返。
        #
        # 分母陷阱：`top3_all_within_top4` 喺冇賽果（`actual_top3_count == 0`）
        # 嗰陣係 None 而唔係 False。呢度 `bool()` 落去會靜靜當 Miss，
        # 所以 `summarize_races` 要同其他 competitiveness 指標一樣只計有值嘅場次。
        "gold": bool(top3_all_within_top4_flag),
        "gold_strict": hits == 3,
        "good_positional": len(picks) >= 2 and picks[0] in actual_set and picks[1] in actual_set,
        "pass": hits >= 2,
        "any1": hits >= 1,
        # Compatibility aliases for archived HKJC/AU research scripts. New AU
        # reports must use ``pass`` and must not surface these retired labels.
        "good_any2": hits >= 2,
        "pass_any1": hits >= 1,
        "champion": bool(picks) and picks[0] in winners,
        "winner_in_top3": any(horse in winners for horse in top3_picks),
        "winner_in_top5": any(horse in winners for horse in picks[:5]),
        "order_issue": order_issue,
        # winner-rank quality
        "winner_rank": winner_rank,
        "reciprocal_rank": (1.0 / winner_rank) if winner_rank else 0.0,
        # exclusive reflector label
        "exclusive_label": exclusive_label(hits, top2_hits,
                                           gold=top3_all_within_top4_flag),
    }


def summarize_races(race_rows: Sequence[Mapping[str, Any]]) -> dict:
    """Aggregate per-race dicts from `race_metrics` into counts and rates."""
    races = len(race_rows)
    denominator = max(1, races)
    counts = {
        "gold": sum(bool(row["gold"]) for row in race_rows),
        "gold_strict": sum(bool(row.get("gold_strict")) for row in race_rows),
        "good_positional": sum(bool(row["good_positional"]) for row in race_rows),
        "pass": sum(bool(row["pass"]) for row in race_rows),
        "any1": sum(bool(row["any1"]) for row in race_rows),
        "good_any2": sum(bool(row["good_any2"]) for row in race_rows),
        "pass_any1": sum(bool(row["pass_any1"]) for row in race_rows),
        "champion": sum(bool(row["champion"]) for row in race_rows),
        "winner_in_top3": sum(bool(row["winner_in_top3"]) for row in race_rows),
        "winner_in_top5": sum(bool(row.get("winner_in_top5")) for row in race_rows),
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
            "top3_all_within_top4": _flag("top3_all_within_top4"),
            "top3_all_within_top5": _flag("top3_all_within_top5"),
            "mean_top3_capture_at4": _mean("top3_capture_at4"),
            "mean_top3_capture_at5": _mean("top3_capture_at5"),
            "mean_top3_model_rank": _mean("top3_mean_model_rank"),
            "mean_top3_worst_model_rank": _mean("top3_worst_model_rank"),
            "mean_competitive_recall_at5": _mean("competitive_recall_at5"),
            "mean_competitive_precision_at5": _mean("competitive_precision_at5"),
            "mean_ndcg_at5": _mean("ndcg_at5"),
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

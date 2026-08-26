#!/usr/bin/env python3
"""Isolate Sportsbet winner-margin semantics on the canonical AU evaluator.

This is a shadow-only experiment.  It replaces Performance Quality with a
field-relative score rebuilt from exactly the same Sportsbet history twice:

* absolute: every displayed margin is treated as a beaten-margin magnitude;
* neutral: a run with finish_pos == 1 has beaten margin forced to zero.

All other leaves, weights, gains and wet overlay stay unchanged.  The script
also writes two equivalent leaf datasets so the matrix refitter can be run on
the corrected distribution without touching production code.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path
from statistics import mean, pstdev

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
sys.path.insert(0, str(SCRIPTS))

from au_eval import baseline_report, compare, default_scorer, load_races, verdict_dict  # noqa: E402
from au_racing_engine.engine_core import clip_score  # noqa: E402

RECENCY = (1.0, 0.8, 0.6, 0.4)
CLASS_CREDIT = 4.0
REFERENCE_PRIZE = 50000.0


def identity(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def neutral_raw(digest: dict) -> float:
    qualities = []
    for run in (digest.get("runs") or [])[: len(RECENCY)]:
        margin = float(run.get("margin") or 0.0)
        if int(run.get("finish_pos") or 0) == 1:
            margin = 0.0
        prize = float(run.get("prize") or 0.0)
        quality = -min(20.0, abs(margin))
        if prize > 0:
            quality += CLASS_CREDIT * math.log10(prize / REFERENCE_PRIZE)
        qualities.append(quality)
    weights = RECENCY[: len(qualities)]
    return sum(q * w for q, w in zip(qualities, weights)) / sum(weights)


def attach_scores(races: list[dict], sidecar_path: Path) -> dict:
    document = json.loads(sidecar_path.read_text(encoding="utf-8"))
    quality = {tuple(rec["key"]): rec["digest"] for rec in document["records"]}
    counts = Counter()
    for race in races:
        meta = race.get("metadata") or {}
        date = str(race.get("date") or meta.get("date") or "")
        track = identity(meta.get("track"))
        race_number = int(meta.get("race_number") or 0)
        matched = []
        for row in race["rows"]:
            key = (date, track, race_number, identity(row.get("horse_name") or row.get("name")))
            digest = quality.get(key)
            if not digest or int(digest.get("run_count") or 0) < 2:
                continue
            absolute = float(digest["raw"])
            neutral = neutral_raw(digest)
            matched.append((row, absolute, neutral))
            counts["runner_matched"] += 1
            winner_runs = sum(
                1 for run in digest.get("runs") or []
                if int(run.get("finish_pos") or 0) == 1
                and abs(float(run.get("margin") or 0.0)) > 0
            )
            counts["winner_runs_neutralised"] += winner_runs
        if len(matched) < 3:
            counts["race_field_gate_failed"] += 1
            continue
        abs_values = [row[1] for row in matched]
        neutral_values = [row[2] for row in matched]
        abs_sd = pstdev(abs_values)
        neutral_sd = pstdev(neutral_values)
        if abs_sd <= 0 or neutral_sd <= 0:
            counts["race_field_gate_failed"] += 1
            continue
        counts["race_field_gate_passed"] += 1
        abs_mean, neutral_mean = mean(abs_values), mean(neutral_values)
        for row, absolute, neutral in matched:
            row["_pq_absolute"] = clip_score(60.0 + 20.0 * (absolute - abs_mean) / abs_sd)
            row["_pq_neutral"] = clip_score(60.0 + 20.0 * (neutral - neutral_mean) / neutral_sd)
            if abs(row["_pq_neutral"] - row["_pq_absolute"]) > 1e-12:
                counts["runner_score_changed"] += 1
    return {**document.get("extraction", {}), **counts}


def pq_scorer(key: str):
    def score(row: dict) -> float:
        replacement = row.get(key)
        if replacement is None:
            return default_scorer(row)
        original = row["features"].get("performance_quality_score", 60.0)
        row["features"]["performance_quality_score"] = replacement
        try:
            return default_scorer(row)
        finally:
            row["features"]["performance_quality_score"] = original
    return score


def rank_changes(races: list[dict], base_scorer, candidate_scorer) -> dict:
    counts = Counter()
    for race in races:
        before = sorted(range(len(race["rows"])), key=lambda i: -base_scorer(race["rows"][i]))
        after = sorted(range(len(race["rows"])), key=lambda i: -candidate_scorer(race["rows"][i]))
        if before != after:
            counts["races_any_rank_change"] += 1
        if before[:4] != after[:4]:
            counts["races_top4_order_change"] += 1
        if set(before[:4]) != set(after[:4]):
            counts["races_top4_membership_change"] += 1
    return dict(counts)


def serialisable_dataset(races: list[dict], score_key: str) -> dict:
    output = []
    scorer = pq_scorer(score_key)
    for race in races:
        copied = {key: copy.deepcopy(value) for key, value in race.items() if key != "rows"}
        copied_rows = []
        for row in race["rows"]:
            new_row = copy.deepcopy(row)
            replacement = row.get(score_key)
            if replacement is not None:
                new_row["features"]["performance_quality_score"] = replacement
                if "feature_scores" in new_row:
                    new_row["feature_scores"]["performance_quality_score"] = replacement
            new_row["score"] = scorer(row)
            new_row["ability"] = new_row["score"]
            copied_rows.append(new_row)
        copied["rows"] = copied_rows
        output.append(copied)
    return {"races": output}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--sidecar", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    races = load_races(args.dataset)
    extraction = attach_scores(races, args.sidecar)
    absolute = pq_scorer("_pq_absolute")
    neutral = pq_scorer("_pq_neutral")
    live_vs_absolute = compare(
        races, default_scorer, absolute,
        label="live stored PQ vs same-cache absolute-margin PQ",
    )
    absolute_vs_neutral = compare(
        races, absolute, neutral,
        label="winner margin neutralised (same Sportsbet evidence)",
    )
    report = {
        "design": {
            "dataset": str(args.dataset),
            "sidecar": str(args.sidecar),
            "only_change": "finish_pos == 1 => beaten margin 0",
            "point_in_time": "historical run date < target meeting date",
            "sp_in_scoring": False,
        },
        "coverage": extraction,
        "replay_drift": verdict_dict(live_vs_absolute),
        "correctness_ablation": verdict_dict(absolute_vs_neutral),
        "rank_changes": rank_changes(races, absolute, neutral),
        "absolute_baseline": baseline_report(races, scorer=absolute),
        "neutral_candidate": baseline_report(races, scorer=neutral),
    }
    (args.out_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (args.out_dir / "absolute_leaves.json").write_text(
        json.dumps(serialisable_dataset(races, "_pq_absolute"), separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    (args.out_dir / "neutral_leaves.json").write_text(
        json.dumps(serialisable_dataset(races, "_pq_neutral"), separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "coverage": extraction,
        "replay_drift": verdict_dict(live_vs_absolute),
        "correctness_ablation": verdict_dict(absolute_vs_neutral),
        "rank_changes": report["rank_changes"],
        "outputs": str(args.out_dir),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Leakage-safe walk-forward audit for the AU draw/barrier matrix.

The live draw matrix may legitimately use every result known today.  A
historical evaluation may not: each archived race must only use draw results
strictly earlier than its own date.  This script rebuilds that signal by date,
replaces only ``pace_map_score`` and sends the candidate through ``au_eval``.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR / "racing_engine"))

from au_eval import (  # noqa: E402
    compare,
    default_scorer,
    load_races,
    verdict_dict,
)
from io_utils import write_json_atomic, write_text_atomic  # noqa: E402
from matrix_mapper import map_features_to_matrix_scores  # noqa: E402
from scoring import MATRIX_WEIGHTS, PACE_MICRO_WEIGHTS  # noqa: E402


BUCKETS = ("inside", "middle", "outside", "wide")


def _integer(value):
    match = re.search(r"\d+", str(value or ""))
    return int(match.group()) if match else None


def _name(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _track(value):
    return re.sub(r"\s+", " ", str(value or "").strip()).title()


def barrier_bucket(barrier):
    if barrier <= 4:
        return "inside"
    if barrier <= 8:
        return "middle"
    if barrier <= 12:
        return "outside"
    return "wide"


def field_bucket(field_size):
    if field_size <= 8:
        return "field_1_8"
    if field_size <= 12:
        return "field_9_12"
    return "field_13_plus"


class RollingDrawStats:
    def __init__(self):
        self.global_stats = defaultdict(Counter)
        self.track_stats = defaultdict(Counter)
        self.distance_stats = defaultdict(Counter)
        self.seen = set()
        self.races = 0

    @staticmethod
    def _add(counter, bucket, position):
        counter[(bucket, "n")] += 1
        counter[(bucket, "win")] += position == 1
        counter[(bucket, "place")] += position <= 3

    def add_race(self, date, track, race_number, distance, runners):
        clean = []
        for row in runners:
            barrier = _integer(row.get("barrier"))
            position = _integer(row.get("position"))
            horse = _name(row.get("horse"))
            if not barrier or barrier <= 0 or not position or not horse:
                continue
            key = (date, _track(track), int(race_number), horse)
            if key in self.seen:
                continue
            clean.append((key, barrier, position))
        if not clean:
            return
        size = len(clean)
        f_bucket = field_bucket(size)
        trk = _track(track)
        dist = str(int(distance or 0))
        for key, barrier, position in clean:
            self.seen.add(key)
            bucket = barrier_bucket(barrier)
            self._add(self.global_stats[f_bucket], bucket, position)
            self._add(self.track_stats[trk], bucket, position)
            self._add(self.distance_stats[(trk, dist)], bucket, position)
        self.races += 1

    @staticmethod
    def _cell(counter, bucket):
        n = int(counter[(bucket, "n")])
        return {
            "n": n,
            "win_rate": counter[(bucket, "win")] / n if n else 0.0,
            "place_rate": counter[(bucket, "place")] / n if n else 0.0,
        }

    def modifier(self, track, distance, field_size, barrier):
        bucket = barrier_bucket(barrier)
        trk = _track(track)
        dist = str(int(distance or 0))
        source = "none"
        cell = self._cell(self.distance_stats[(trk, dist)], bucket)
        if cell["n"] >= 10:
            source = "track_distance"
        else:
            cell = self._cell(self.track_stats[trk], bucket)
            if cell["n"] >= 30:
                source = "track"
            else:
                cell = self._cell(self.global_stats[field_bucket(field_size)], bucket)
                source = "global" if cell["n"] else "none"
        if not cell["n"]:
            return 0.0, source, cell

        expected = 1.0 / max(1, field_size)
        weights = PACE_MICRO_WEIGHTS
        raw = (
            (cell["win_rate"] - expected)
            * 100.0
            * float(weights.get("modifier_multiplier", 1.0))
        )
        shrink_k = float(weights.get("shrinkage_k", 25.0))
        raw *= cell["n"] / (cell["n"] + shrink_k)
        modifier = max(
            float(weights.get("modifier_cap_min", -6.0)),
            min(float(weights.get("modifier_cap_max", 6.0)), raw),
        )
        return modifier, source, cell


def load_result_races(paths):
    grouped = defaultdict(list)
    for path in paths:
        with path.open(encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                date = str(row.get("Date") or "").strip()
                track = _track(row.get("Track"))
                race = _integer(row.get("Race"))
                distance = _integer(row.get("Distance"))
                if not date or not track or race is None:
                    continue
                grouped[(date, track, race, distance or 0)].append({
                    "horse": row.get("Horse"),
                    "barrier": row.get("Barrier"),
                    "position": row.get("Pos"),
                })
    return sorted((key, rows) for key, rows in grouped.items())


def score_with_walkforward_draw(row):
    features = dict(row["features"])
    features["pace_map_score"] = row["_walkforward_pace_map_score"]
    matrices = map_features_to_matrix_scores(features)
    return sum(
        matrices.get(key, 60.0) * weight
        for key, weight in MATRIX_WEIGHTS.items()
    ) + float(row["wet"] or 0.0)


def score_without_draw(row):
    features = dict(row["features"])
    features["pace_map_score"] = 60.0
    matrices = map_features_to_matrix_scores(features)
    return sum(
        matrices.get(key, 60.0) * weight
        for key, weight in MATRIX_WEIGHTS.items()
    ) + float(row["wet"] or 0.0)


def attach_walkforward_scores(races, result_races):
    stats = RollingDrawStats()
    source_counts = Counter()
    sample_sizes = []
    result_index = 0
    dates = sorted({str(race.get("date") or "") for race in races})
    for date in dates:
        while result_index < len(result_races) and result_races[result_index][0][0] < date:
            (rdate, track, race_no, distance), rows = result_races[result_index]
            stats.add_race(rdate, track, race_no, distance, rows)
            result_index += 1

        todays_races = [race for race in races if str(race.get("date") or "") == date]
        for race in todays_races:
            metadata = race.get("metadata") or {}
            track = metadata.get("track") or ""
            distance = int(metadata.get("distance") or 0)
            field_size = int(metadata.get("field_size") or len(race["rows"]))
            for row in race["rows"]:
                barrier = _integer((row.get("raw_pre_race") or {}).get("barrier"))
                if not barrier:
                    modifier, source, cell = 0.0, "missing_barrier", {"n": 0}
                else:
                    modifier, source, cell = stats.modifier(
                        track, distance, field_size, barrier,
                    )
                row["_walkforward_pace_map_score"] = 60.0 + modifier
                source_counts[source] += 1
                sample_sizes.append(int(cell.get("n", 0)))

        # Add today's labelled results only after every race on the date was scored.
        for race in todays_races:
            metadata = race.get("metadata") or {}
            runners = [{
                "horse": row.get("horse_name"),
                "barrier": (row.get("raw_pre_race") or {}).get("barrier"),
                "position": row.get("pos"),
            } for row in race["rows"]]
            stats.add_race(
                date,
                metadata.get("track") or "",
                int(metadata.get("race_number") or 0),
                int(metadata.get("distance") or 0),
                runners,
            )
    return {
        "source_counts": dict(source_counts),
        "mean_cell_sample": (
            sum(sample_sizes) / len(sample_sizes) if sample_sizes else 0.0
        ),
        "historical_races_consumed": stats.races,
        "unique_historical_runners": len(stats.seen),
    }


def render_markdown(report):
    wf = report["walkforward_verdict"]
    neutral = report["neutral_draw_verdict"]
    value = report["draw_value_verdict"]
    lo, hi = wf["top_hold_ci"]
    nlo, nhi = neutral["top_hold_ci"]
    vlo, vhi = value["top_hold_ci"]
    coverage = report["coverage"]
    lines = [
        "# AU Draw / Barrier Walk-forward Audit",
        "",
        "Each race is scored from draw outcomes strictly earlier than its date. "
        "Same-day results are added only after all races for that date are scored.",
        "",
        f"- Historical races/runners consumed: {coverage['historical_races_consumed']} / "
        f"{coverage['unique_historical_runners']}",
        f"- Lookup sources: {coverage['source_counts']}",
        f"- Mean matched cell sample: {coverage['mean_cell_sample']:.1f}",
        "",
        "| Candidate | Dev Top5 AUC Δ | Terminal Δ | 95% CI | Ship |",
        "|---|---:|---:|---:|:---:|",
        f"| point-in-time draw | {wf['top_dev']:+.4f} | {wf['top_hold']:+.4f} | "
        f"[{lo:+.4f}, {hi:+.4f}] | {'YES' if wf['ship'] else 'NO'} |",
        f"| neutral draw | {neutral['top_dev']:+.4f} | {neutral['top_hold']:+.4f} | "
        f"[{nlo:+.4f}, {nhi:+.4f}] | {'YES' if neutral['ship'] else 'NO'} |",
        f"| **point-in-time draw vs neutral** | {value['top_dev']:+.4f} | "
        f"{value['top_hold']:+.4f} | [{vlo:+.4f}, {vhi:+.4f}] | "
        f"{'YES' if value['ship'] else 'NO'} |",
    ]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-json", type=Path, required=True)
    parser.add_argument("--results-csv", type=Path, action="append", required=True)
    parser.add_argument(
        "--output-json", type=Path,
        default=Path("/private/tmp/au_draw_walkforward_audit.json"),
    )
    parser.add_argument(
        "--output-md", type=Path,
        default=Path("/private/tmp/au_draw_walkforward_audit.md"),
    )
    parser.add_argument("--holdout-fraction", type=float, default=0.15)
    args = parser.parse_args()

    races = load_races(args.dataset_json)
    coverage = attach_walkforward_scores(races, load_result_races(args.results_csv))
    walkforward = compare(
        races, default_scorer, score_with_walkforward_draw,
        label="point-in-time draw matrix", holdout=args.holdout_fraction,
    )
    neutral = compare(
        races, default_scorer, score_without_draw,
        label="neutral draw", holdout=args.holdout_fraction,
    )
    draw_value = compare(
        races, score_without_draw, score_with_walkforward_draw,
        label="point-in-time draw vs neutral", holdout=args.holdout_fraction,
    )
    report = {
        "design": {
            "dataset": str(args.dataset_json),
            "results_csv": [str(path) for path in args.results_csv],
            "same_day_results_visible": False,
            "future_results_visible": False,
        },
        "coverage": coverage,
        "walkforward_verdict": verdict_dict(walkforward),
        "neutral_draw_verdict": verdict_dict(neutral),
        "draw_value_verdict": verdict_dict(draw_value),
    }
    write_json_atomic(args.output_json, report)
    write_text_atomic(args.output_md, render_markdown(report))
    print(walkforward)
    print()
    print(neutral)
    print()
    print(draw_value)
    print(f"\nJSON: {args.output_json}\nMarkdown: {args.output_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

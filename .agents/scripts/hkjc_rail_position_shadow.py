#!/usr/bin/env python3
"""Audit HKJC venue/rail/draw/position effects without changing live scores.

Actual first-call position is deliberately labelled diagnostic-only: it is an
outcome used to learn gate-to-position conversion, never a pre-race feature.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

from build_rail_draw_dataset import OUT


SHRINK_RUNNERS = 60.0
MIN_STABLE_RUNNERS = 100
MIN_STABLE_RACES = 20


def _integer(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def draw_group(draw: Any) -> str:
    value = _integer(draw)
    if value <= 0:
        return "unknown"
    if value <= 4:
        return "inner_1_4"
    if value <= 8:
        return "middle_5_8"
    return "outer_9_plus"


def distance_band(distance: Any) -> str:
    value = _integer(distance)
    if value <= 0:
        return "unknown"
    if value <= 1200:
        return "sprint_1000_1200"
    if value <= 1650:
        return "middle_1400_1650"
    return "route_1800_plus"


def field_size_band(field_size: Any) -> str:
    value = _integer(field_size)
    if value <= 0:
        return "unknown"
    if value <= 10:
        return "small_10_or_less"
    if value <= 12:
        return "medium_11_12"
    return "large_13_plus"


def going_group(going: Any) -> str:
    text = str(going or "").strip().replace(" ", "")
    if not text:
        return "unknown"
    if "濕慢" in text or "大爛" in text:
        return "wet_slow"
    if "黏" in text or "軟" in text or "濕" in text:
        return "yielding_wet"
    if "快" in text:
        return "firm_fast"
    if "好" in text:
        return "good"
    return text


def read_rows(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _race_id(row: dict[str, Any]) -> str:
    return f"{row.get('Date')}|{row.get('Venue')}|{row.get('RaceNo')}"


def _aggregate(
    rows: list[dict[str, Any]],
    key_fn: Callable[[dict[str, Any]], tuple[str, ...]],
) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        buckets[key_fn(row)].append(row)
    output = []
    for key, members in sorted(buckets.items()):
        n = len(members)
        places = sum(_integer(row.get("Place")) for row in members)
        expected = sum(
            min(3, _integer(row.get("FieldSize"))) / max(1, _integer(row.get("FieldSize")))
            for row in members
        )
        races = len({_race_id(row) for row in members})
        raw_excess = (places - expected) / n if n else 0.0
        output.append(
            {
                "key": list(key),
                "runners": n,
                "races": races,
                "place_rate": places / n if n else 0.0,
                "expected_place_rate": expected / n if n else 0.0,
                "raw_excess": raw_excess,
                "shrunk_excess": (places - expected) / (n + SHRINK_RUNNERS),
                "stable": n >= MIN_STABLE_RUNNERS and races >= MIN_STABLE_RACES,
            }
        )
    return output


def analyse(rows: list[dict[str, Any]]) -> dict[str, Any]:
    complete = [
        row for row in rows
        if row.get("Date") and row.get("Venue") and row.get("Track")
        and row.get("Distance") and row.get("Rail")
    ]
    venue = _aggregate(complete, lambda row: (str(row.get("Venue")),))
    draw = _aggregate(
        complete,
        lambda row: (str(row.get("Venue")), draw_group(row.get("Draw"))),
    )
    rail_draw = _aggregate(
        [row for row in complete if str(row.get("Track")) == "Turf"],
        lambda row: (
            str(row.get("Venue")),
            str(row.get("Rail")),
            distance_band(row.get("Distance")),
            draw_group(row.get("Draw")),
        ),
    )
    rail_distance_going_draw = _aggregate(
        [row for row in complete if str(row.get("Track")) == "Turf" and going_group(row.get("Going")) != "unknown"],
        lambda row: (
            str(row.get("Venue")),
            str(row.get("Rail")),
            distance_band(row.get("Distance")),
            going_group(row.get("Going")),
            draw_group(row.get("Draw")),
        ),
    )
    rail_distance_field_draw = _aggregate(
        [row for row in complete if str(row.get("Track")) == "Turf"],
        lambda row: (
            str(row.get("Venue")),
            str(row.get("Rail")),
            distance_band(row.get("Distance")),
            field_size_band(row.get("FieldSize")),
            draw_group(row.get("Draw")),
        ),
    )
    early_position = _aggregate(
        [row for row in complete if str(row.get("EarlyGroup")) not in ("", "unknown")],
        lambda row: (
            str(row.get("Venue")),
            str(row.get("Rail")),
            distance_band(row.get("Distance")),
            str(row.get("EarlyGroup")),
        ),
    )

    draw_by_key = {(item["key"][0], item["key"][1]): item for item in draw}
    draw_deltas = {}
    for group in ("inner_1_4", "middle_5_8", "outer_9_plus"):
        st = draw_by_key.get(("沙田", group))
        hv = draw_by_key.get(("跑馬地", group))
        if st and hv:
            draw_deltas[group] = hv["shrunk_excess"] - st["shrunk_excess"]

    return {
        "contract": {
            "mode": "shadow_only",
            "live_score_changed": False,
            "actual_first_call_usage": "diagnostic_only",
        },
        "coverage": {
            "rows": len(rows),
            "complete_rows": len(complete),
            "complete_rate": len(complete) / len(rows) if rows else 0.0,
            "meetings": len({(row.get("Date"), row.get("Venue")) for row in complete}),
            "races": len({_race_id(row) for row in complete}),
        },
        "venue": venue,
        "venue_draw": draw,
        "rail_distance_draw": rail_draw,
        "rail_distance_going_draw": rail_distance_going_draw,
        "rail_distance_field_draw": rail_distance_field_draw,
        "rail_distance_early_position": early_position,
        "venue_draw_shrunk_delta_hv_minus_st": draw_deltas,
        "formula_decision": {
            "status": "KEEP_SHARED_7D_WITH_VENUE_COMPONENTS",
            "reason": (
                "Outcome-only rail data can validate venue-specific position components, "
                "but cannot justify two independent 7D formulas. A full split requires "
                "paired point-in-time model replay and materially larger per-venue cohorts."
            ),
        },
    }


def _pct(value: Any) -> str:
    return f"{100 * float(value):.1f}%"


def render_markdown(report: dict[str, Any]) -> str:
    coverage = report["coverage"]
    lines = [
        "# HKJC Rail / Position Shadow Audit",
        "",
        f"- Mode: `{report['contract']['mode']}`; live score changed: `false`",
        f"- Coverage: {coverage['complete_rows']}/{coverage['rows']} runners "
        f"({_pct(coverage['complete_rate'])}), {coverage['meetings']} meetings, {coverage['races']} races",
        "- Actual first-call position is post-race diagnostic evidence only.",
        "",
        "## Venue draw cohorts",
        "",
        "| Venue | Draw group | Runners | Races | Place | Expected | Shrunk excess | Stable |",
        "|---|---|---:|---:|---:|---:|---:|:---:|",
    ]
    for item in report["venue_draw"]:
        venue, group = item["key"]
        lines.append(
            f"| {venue} | {group} | {item['runners']} | {item['races']} | "
            f"{_pct(item['place_rate'])} | {_pct(item['expected_place_rate'])} | "
            f"{_pct(item['shrunk_excess'])} | {'Y' if item['stable'] else 'N'} |"
        )
    lines.extend([
        "",
        "## Venue-formula decision",
        "",
        f"**{report['formula_decision']['status']}** — {report['formula_decision']['reason']}",
        "",
        "Rail × distance cells are available in the JSON output; unstable cells must not be promoted.",
    ])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=OUT)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--markdown-out", type=Path)
    args = parser.parse_args()

    rows = read_rows(args.dataset)
    report = analyse(rows)
    markdown = render_markdown(report)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.markdown_out:
        args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_out.write_text(markdown, encoding="utf-8")
    if not args.json_out and not args.markdown_out:
        print(markdown, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Build a strict HKJC Top-2 0/1/2-hit baseline manifest.

This is a read-only Step-1 diagnostic.  It preserves the original model ranks,
uses dead-heat-safe official positions, and refuses to compress rank gaps caused
by withdrawals or missing results.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SHARED_RACING = ROOT / ".agents" / "skills" / "shared_racing"
sys.path.insert(0, str(SHARED_RACING))
from eval_metrics import exclusive_label  # noqa: E402


DEFAULT_ARCHIVE = (
    ROOT
    / ".agents"
    / "skills"
    / "hkjc_racing"
    / "hkjc_reflector"
    / "artifacts"
    / "hkjc_ranking_dataset.csv"
)
DEFAULT_HK_ROOT = Path(
    "/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/"
    "我的雲端硬碟/Antigravity Shared/Antigravity/"
    "Wong Choi Horse Race Analysis/HK_Racing"
)
DEFAULT_EXTERNAL = Path(
    "/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/"
    "我的雲端硬碟/Antigravity Shared/Antigravity/2026-07-15_HappyValley"
)


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def parse_position(value: Any) -> int:
    text = str(value or "").upper().replace("DH", "").strip()
    return as_int(text)


def result_positions(results_file: Path) -> dict[int, dict[int, int]]:
    payload = json.loads(results_file.read_text(encoding="utf-8"))
    races: dict[int, dict[int, int]] = {}
    for race_key, race_payload in payload.items():
        race_number = as_int(race_key)
        positions: dict[int, int] = {}
        for row in race_payload.get("results", []):
            horse_number = as_int(row.get("horse_no"))
            finish = parse_position(row.get("pos"))
            if horse_number > 0 and finish > 0:
                positions[horse_number] = finish
        if race_number > 0 and positions:
            races[race_number] = positions
    return races


def analyse_race(
    *,
    dataset: str,
    meeting: str,
    date: str,
    race_number: int,
    horses: list[dict[str, Any]],
    positions: dict[int, int],
    source: str,
) -> dict[str, Any]:
    issues: list[str] = []
    by_rank: defaultdict[int, list[dict[str, Any]]] = defaultdict(list)
    by_number = {as_int(row.get("number")): row for row in horses if as_int(row.get("number")) > 0}
    for horse in horses:
        rank = as_int(horse.get("rank"))
        if rank > 0:
            by_rank[rank].append(horse)

    picks: list[dict[str, Any]] = []
    for rank in (1, 2, 3):
        candidates = by_rank.get(rank, [])
        if len(candidates) != 1:
            issues.append(f"rank_{rank}_count={len(candidates)}")
            continue
        horse = candidates[0]
        number = as_int(horse.get("number"))
        if number not in positions:
            issues.append(f"rank_{rank}_missing_numeric_finish=#{number}")
        picks.append(
            {
                "rank": rank,
                "number": number,
                "name": str(horse.get("name") or ""),
                "score": round(as_float(horse.get("score")), 4),
                "finish": positions.get(number),
            }
        )

    actual_top3 = [
        {
            "finish": finish,
            "number": number,
            "name": str((by_number.get(number) or {}).get("name") or ""),
            "model_rank": as_int((by_number.get(number) or {}).get("rank"), 999),
        }
        for number, finish in sorted(positions.items(), key=lambda item: (item[1], item[0]))
        if finish <= 3
    ]
    if len(actual_top3) < 3:
        issues.append(f"actual_top3_count={len(actual_top3)}")

    valid = not issues
    pick_numbers = [row["number"] for row in picks]
    actual_set = {row["number"] for row in actual_top3}
    top2_hits = sum(number in actual_set for number in pick_numbers[:2]) if valid else None
    top3_hits = sum(number in actual_set for number in pick_numbers[:3]) if valid else None
    label = exclusive_label(top3_hits, top2_hits) if valid else "INVALID"
    third_pick_hit = bool(valid and pick_numbers[2] in actual_set)
    winners = sorted(number for number, finish in positions.items() if finish == 1)
    winner_model_ranks = sorted(
        as_int((by_number.get(number) or {}).get("rank"), 999) for number in winners
    )
    top3_finish_counts = Counter(row["finish"] for row in actual_top3)
    dead_heat_top3 = any(count > 1 for count in top3_finish_counts.values())

    return {
        "dataset": dataset,
        "meeting": meeting,
        "date": date,
        "race_number": race_number,
        "source": source,
        "valid": valid,
        "issues": issues,
        "field_finishers": len(positions),
        "model_horses": len(horses),
        "dead_heat_top3": dead_heat_top3,
        "top2_hits": top2_hits,
        "top3_hits": top3_hits,
        "reflector_label": label,
        "third_pick_hit": third_pick_hit,
        "third_pick_only_hit": bool(valid and top2_hits == 0 and third_pick_hit),
        "winner_in_top2": bool(valid and any(rank <= 2 for rank in winner_model_ranks)),
        "winner_model_ranks": winner_model_ranks,
        "picks": picks,
        "actual_top3": actual_top3,
    }


def load_archive(path: Path) -> tuple[list[dict[str, Any]], set[str]]:
    grouped: defaultdict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            meeting = str(row.get("meeting_name") or Path(str(row.get("meeting") or "")).name)
            date = str(row.get("date") or meeting[:10])
            race_number = as_int(row.get("race_number"))
            number = as_int(row.get("horse_number"))
            if not meeting or race_number <= 0 or number <= 0:
                continue
            grouped[(meeting, date, race_number)].append(
                {
                    "number": number,
                    "name": str(row.get("horse_name") or ""),
                    "rank": as_int(row.get("current_live_rank")),
                    "score": as_float(
                        row.get("current_live_rank_score"),
                        as_float(row.get("current_live_ability")),
                    ),
                    "finish": parse_position(row.get("finish_pos")),
                }
            )

    records = []
    for (meeting, date, race_number), horses in sorted(grouped.items()):
        positions = {
            row["number"]: row["finish"] for row in horses if as_int(row.get("finish")) > 0
        }
        records.append(
            analyse_race(
                dataset="archive",
                meeting=meeting,
                date=date,
                race_number=race_number,
                horses=horses,
                positions=positions,
                source=str(path),
            )
        )
    return records, {meeting for meeting, _date, _race in grouped}


def load_logic_race(logic_path: Path) -> list[dict[str, Any]]:
    payload = json.loads(logic_path.read_text(encoding="utf-8"))
    horses = []
    for horse_key, raw in (payload.get("horses") or {}).items():
        auto = raw.get("python_auto") if isinstance(raw.get("python_auto"), dict) else {}
        if not auto:
            continue
        horses.append(
            {
                "number": as_int(horse_key),
                "name": str(raw.get("horse_name") or ""),
                "rank": as_int(auto.get("rank")),
                "score": as_float(auto.get("rank_score"), as_float(auto.get("ability_score"))),
            }
        )
    return horses


def load_meeting(
    meeting_dir: Path,
    results_file: Path,
    dataset: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    positions_by_race = result_positions(results_file)
    logic_by_race = {
        as_int(path.stem.split("_")[1]): path
        for path in meeting_dir.glob("Race_*_Logic.json")
        if as_int(path.stem.split("_")[1]) > 0
    }
    gaps: list[dict[str, Any]] = []
    for race_number in sorted(set(logic_by_race) - set(positions_by_race)):
        gaps.append({"meeting": meeting_dir.name, "race": race_number, "reason": "logic_without_results"})
    for race_number in sorted(set(positions_by_race) - set(logic_by_race)):
        gaps.append({"meeting": meeting_dir.name, "race": race_number, "reason": "results_without_logic"})

    records = []
    for race_number in sorted(set(logic_by_race) & set(positions_by_race)):
        logic_path = logic_by_race[race_number]
        records.append(
            analyse_race(
                dataset=dataset,
                meeting=meeting_dir.name,
                date=meeting_dir.name[:10],
                race_number=race_number,
                horses=load_logic_race(logic_path),
                positions=positions_by_race[race_number],
                source=f"{logic_path} | {results_file}",
            )
        )
    return records, gaps


def load_independent(root: Path, archive_meetings: set[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    for meeting_dir in sorted(root.iterdir()):
        if not meeting_dir.is_dir():
            continue
        date = meeting_dir.name[:10]
        if not ("2026-05-25" <= date <= "2026-07-14") or meeting_dir.name in archive_meetings:
            continue
        logic_paths = list(meeting_dir.glob("Race_*_Logic.json"))
        result_paths = sorted(meeting_dir.glob("*全日賽果.json"))
        if not logic_paths or not result_paths:
            gaps.append(
                {
                    "meeting": meeting_dir.name,
                    "race": None,
                    "reason": "missing_logic_or_local_results",
                }
            )
            continue
        meeting_records, meeting_gaps = load_meeting(
            meeting_dir, result_paths[0], "independent_recent"
        )
        records.extend(meeting_records)
        gaps.extend(meeting_gaps)
    return records, gaps


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [row for row in records if row["valid"]]
    invalid = [row for row in records if not row["valid"]]
    top2 = Counter(str(row["top2_hits"]) for row in valid)
    labels = Counter(row["reflector_label"] for row in valid)
    winner_rank = Counter()
    for row in valid:
        ranks = row["winner_model_ranks"]
        if any(rank == 1 for rank in ranks):
            winner_rank["rank1"] += 1
        elif any(rank == 2 for rank in ranks):
            winner_rank["rank2"] += 1
        elif any(rank == 3 for rank in ranks):
            winner_rank["rank3"] += 1
        else:
            winner_rank["outside_top3"] += 1
    one_hit_patterns = Counter()
    for row in valid:
        if row["top2_hits"] != 1:
            continue
        actual_set = {horse["number"] for horse in row["actual_top3"]}
        hit_bits = [int(pick["number"] in actual_set) for pick in row["picks"][:3]]
        one_hit_patterns[
            f"rank1_{hit_bits[0]}_rank2_{hit_bits[1]}_rank3_{hit_bits[2]}"
        ] += 1
    return {
        "meetings": len({row["meeting"] for row in records}),
        "races_seen": len(records),
        "valid_races": len(valid),
        "invalid_races": len(invalid),
        "top2_hit_distribution": dict(sorted(top2.items())),
        "reflector_label_distribution": dict(sorted(labels.items())),
        "third_pick_hit_races": sum(row["third_pick_hit"] for row in valid),
        "third_pick_only_hit_races": sum(row["third_pick_only_hit"] for row in valid),
        "top2_third_pick_bridge": {
            f"top2_{top2_hits}_third_{int(third_hit)}": sum(
                row["top2_hits"] == top2_hits and row["third_pick_hit"] == third_hit
                for row in valid
            )
            for top2_hits in (0, 1, 2)
            for third_hit in (False, True)
        },
        "one_hit_pick_patterns": dict(sorted(one_hit_patterns.items())),
        "winner_model_rank": dict(winner_rank),
        "winner_top2_races": sum(row["winner_in_top2"] for row in valid),
        "dead_heat_top3_races": sum(row["dead_heat_top3"] for row in valid),
        "invalid_details": [
            {
                "meeting": row["meeting"],
                "race": row["race_number"],
                "issues": row["issues"],
            }
            for row in invalid
        ],
    }


def csv_value(value: Any) -> Any:
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return value


def write_outputs(records: list[dict[str, Any]], gaps: list[dict[str, Any]], output_prefix: Path) -> None:
    output_prefix.parent.mkdir(parents=True, exist_ok=True)
    csv_path = output_prefix.with_suffix(".csv")
    json_path = output_prefix.with_suffix(".json")
    report_path = output_prefix.with_name(output_prefix.name + "_report").with_suffix(".md")

    fieldnames = list(records[0]) if records else []
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in records:
            writer.writerow({key: csv_value(value) for key, value in row.items()})

    datasets = {
        dataset: summarize([row for row in records if row["dataset"] == dataset])
        for dataset in sorted({row["dataset"] for row in records})
    }
    payload = {
        "definition": {
            "primary": "number of original model Top-2 picks finishing in official position <= 3",
            "comparison": "canonical exclusive Reflector label",
            "dead_heat_safe": True,
            "rank_gap_compression": False,
            "market_free": True,
        },
        "coverage": summarize(records),
        "datasets": datasets,
        "source_gaps": gaps,
        "records": records,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    overall = payload["coverage"]
    lines = [
        "# HKJC Wong Choi Step 1 — 0／1 Hit Baseline Manifest",
        "",
        "## Definition Lock",
        "",
        "- Primary: original model Top 2 finishing in official Top 3: 0／1／2 hit.",
        "- Comparison: canonical Reflector exclusive label.",
        "- Dead heats are position-safe (`finish <= 3`); original rank gaps are never compressed.",
        "- No scoring, re-ranking, odds, going, draw, or rank-4-to-rank-7 tie-break is used.",
        "",
        "## Coverage",
        "",
        f"- Meetings: {overall['meetings']}",
        f"- Races seen: {overall['races_seen']}",
        f"- Valid races: {overall['valid_races']}",
        f"- Invalid races: {overall['invalid_races']}",
        f"- Source gaps: {len(gaps)}",
        "",
        "## Top 2 Baseline",
        "",
    ]
    for hit_count in ("0", "1", "2"):
        count = overall["top2_hit_distribution"].get(hit_count, 0)
        rate = count / overall["valid_races"] * 100 if overall["valid_races"] else 0.0
        lines.append(f"- {hit_count} hit: {count} ({rate:.1f}%)")
    lines.extend(
        [
            f"- Third pick finished Top 3: {overall['third_pick_hit_races']}",
            f"- Third pick was the only model Top-3 hit while Top 2 had 0: {overall['third_pick_only_hit_races']}",
            f"- Winner contained in model Top 2: {overall['winner_top2_races']}/{overall['valid_races']}",
            "",
            "## Top 2 / Third-Pick Bridge",
            "",
            f"- Top 2 = 0 hit, third pick hit: {overall['top2_third_pick_bridge']['top2_0_third_1']}",
            f"- Top 2 = 0 hit, no model Top-3 hit: {overall['top2_third_pick_bridge']['top2_0_third_0']}",
            f"- Top 2 = 1 hit, third pick also hit: {overall['top2_third_pick_bridge']['top2_1_third_1']}",
            f"- Top 2 = 1 hit, third pick missed: {overall['top2_third_pick_bridge']['top2_1_third_0']}",
            f"- Top 2 = 2 hit, third pick also hit (Gold): {overall['top2_third_pick_bridge']['top2_2_third_1']}",
            f"- Top 2 = 2 hit, third pick missed: {overall['top2_third_pick_bridge']['top2_2_third_0']}",
            "",
            "## One-Hit Position Split",
            "",
            f"- Rank 1 hit; rank 2 and rank 3 missed: {overall['one_hit_pick_patterns'].get('rank1_1_rank2_0_rank3_0', 0)}",
            f"- Rank 1 and rank 3 hit; rank 2 missed (direct rank-3 promotion opportunity): {overall['one_hit_pick_patterns'].get('rank1_1_rank2_0_rank3_1', 0)}",
            f"- Rank 1 missed; rank 2 and rank 3 hit (rank-2-to-rank-3 swap cannot improve hit count): {overall['one_hit_pick_patterns'].get('rank1_0_rank2_1_rank3_1', 0)}",
            f"- Rank 1 and rank 3 missed; rank 2 hit: {overall['one_hit_pick_patterns'].get('rank1_0_rank2_1_rank3_0', 0)}",
            "",
            "## Dataset Split",
            "",
        ]
    )
    for name, summary in datasets.items():
        lines.append(
            f"- `{name}`: {summary['meetings']} meetings / {summary['valid_races']} valid races; "
            f"Top2 hits {summary['top2_hit_distribution']}"
        )
    lines.extend(["", "## Data Gaps", ""])
    if not gaps and not overall["invalid_details"]:
        lines.append("- None.")
    for gap in gaps:
        lines.append(f"- {gap['meeting']} R{gap.get('race') or '-'}: {gap['reason']}")
    for row in overall["invalid_details"]:
        lines.append(f"- {row['meeting']} R{row['race']}: {', '.join(row['issues'])}")
    lines.extend(
        [
            "",
            "## Step 1 Status",
            "",
            "Baseline only. No causal conclusion or production model change is authorised at this step.",
        ]
    )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"csv": str(csv_path), "json": str(json_path), "report": str(report_path), **overall}, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--hk-root", type=Path, default=DEFAULT_HK_ROOT)
    parser.add_argument("--external", type=Path, default=DEFAULT_EXTERNAL)
    parser.add_argument(
        "--output-prefix",
        type=Path,
        default=ROOT / "scratch" / "hkjc_zero_one_hit_manifest",
    )
    args = parser.parse_args()

    archive_records, archive_meetings = load_archive(args.archive)
    recent_records, gaps = load_independent(args.hk_root, archive_meetings)
    external_results = sorted(args.external.glob("*全日賽果.json"))
    if external_results:
        external_records, external_gaps = load_meeting(
            args.external, external_results[0], "external_2026_07_15"
        )
        gaps.extend(external_gaps)
    else:
        external_records = []
        gaps.append(
            {"meeting": args.external.name, "race": None, "reason": "missing_external_results"}
        )

    records = sorted(
        archive_records + recent_records + external_records,
        key=lambda row: (row["date"], row["meeting"], row["race_number"]),
    )
    write_outputs(records, gaps, args.output_prefix)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

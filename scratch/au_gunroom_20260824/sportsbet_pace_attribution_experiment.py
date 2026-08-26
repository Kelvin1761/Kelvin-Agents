#!/usr/bin/env python3
"""Sportsbet-only PacePerf attribution shadow test.

Sportsbet's L600 delta is race-level context, not an individual runner split.
The live leaf averages every historical context in which the horse appeared.
This pre-declared candidate keeps trial rows unchanged, but only lets a formal
run contribute its race context when the horse finished within 3.0 lengths.

The 3L cutoff is fixed before evaluation; this script has no parameter sweep.
It changes only ``pace_figure_score`` and never reads market/SP fields.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
SHARED = ROOT / ".agents/skills/shared_racing/scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SHARED))
sys.path.insert(0, str(ROOT))

import au_eval  # noqa: E402
from au_archive_calibrator import (  # noqa: E402
    detect_meeting_date,
    detect_meeting_track,
    normalize_track_name,
)
from au_racing_engine.scoring import clip_score  # noqa: E402
from corpus_paths import meeting_dirs  # noqa: E402
from wongchoi_paths import AU_RACING  # noqa: E402


COMPETITIVE_MARGIN_L = 3.0
HORSE_HEADER = re.compile(r"^\[(\d+)\]\s+(.+?)\s+\((\d+)\)\s*$", re.M)
RUN_DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
L600 = re.compile(r"\bL600 Delta:\s*([-+]?\d+(?:\.\d+)?)", re.I)
MARGIN = re.compile(r"\bmargin:([-+]?\d+(?:\.\d+)?)L?\b", re.I)
SOURCE = "sportsbet_race_context"


def meeting_index() -> dict[tuple[str, str], list[Path]]:
    output: dict[tuple[str, str], list[Path]] = defaultdict(list)
    for directory in meeting_dirs(AU_RACING):
        logic = next(directory.glob("Race_*_Logic.json"), None)
        if logic is None:
            continue
        try:
            sample = json.loads(logic.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        date = detect_meeting_date(directory)
        track = detect_meeting_track(directory, sample)
        if date and track:
            output[(date, normalize_track_name(track))].append(directory)
    return output


def find_formguide(
    index: dict[tuple[str, str], list[Path]],
    *,
    date: str,
    track: str,
    race_number: int,
) -> Path | None:
    candidates = index.get((date, normalize_track_name(track)), [])
    matches = []
    for directory in candidates:
        matches.extend(directory.glob(f"*Race {race_number} Formguide.md"))
    matches = sorted({path for path in matches if path.is_file()})
    return matches[-1] if matches else None


def parse_l600_runs(path: Path, target_date: str) -> dict[int, list[dict]]:
    text = path.read_text(encoding="utf-8")
    headers = list(HORSE_HEADER.finditer(text))
    output: dict[int, list[dict]] = {}
    for index, header in enumerate(headers):
        body = text[
            header.end():
            headers[index + 1].start() if index + 1 < len(headers) else len(text)
        ]
        rows = []
        for line in body.splitlines():
            if f"Source: {SOURCE}" not in line:
                continue
            date_match = RUN_DATE.search(line)
            l600_match = L600.search(line)
            if not date_match or not l600_match or date_match.group(1) >= target_date:
                continue
            margin_match = MARGIN.search(line)
            rows.append(
                {
                    "date": date_match.group(1),
                    "l600": float(l600_match.group(1)),
                    "margin": float(margin_match.group(1)) if margin_match else None,
                    "trial": "**(TRIAL)**" in line,
                }
            )
        output[int(header.group(1))] = rows
    return output


def aggregate(rows: list[dict], *, attributed: bool) -> float | None:
    kept = []
    for row in rows:
        if not attributed:
            kept.append(float(row["l600"]))
            continue
        # Trial handling is deliberately unchanged.  The previous PacePerf
        # experiment already tested removing trials and rejected it; this test
        # isolates only whether formal-race context was demonstrated.
        if row["trial"]:
            kept.append(float(row["l600"]))
            continue
        margin = row.get("margin")
        if margin is None or abs(float(margin)) <= COMPETITIVE_MARGIN_L:
            kept.append(float(row["l600"]))
    return sum(kept) / len(kept) if kept else None


def source_for(row: dict) -> str:
    aggregates = (row.get("raw_pre_race") or {}).get("pf_aggregates") or {}
    return str(aggregates.get("source") or "")


def original_value(row: dict) -> float | None:
    aggregates = (row.get("raw_pre_race") or {}).get("pf_aggregates") or {}
    value = aggregates.get("l600_delta_avg")
    return float(value) if value is not None else None


def pace_score(values: list[float | None], value: float | None) -> float:
    present = [float(item) for item in values if item is not None]
    if value is None or len(present) < 3:
        return 60.0
    mean = sum(present) / len(present)
    stdev = math.sqrt(sum((item - mean) ** 2 for item in present) / len(present))
    if stdev <= 0:
        return 60.0
    return clip_score(60.0 - ((float(value) - mean) / stdev) * 20.0)


def annotate_race(race: dict, runs: dict[int, list[dict]] | None) -> dict:
    rows = race["rows"]
    original_values = [original_value(row) for row in rows]
    candidate_values = list(original_values)
    audit = {"sportsbet_rows": 0, "parsed_rows": 0, "drift": 0, "removed_runs": 0}

    for index, row in enumerate(rows):
        row["_candidate_features"] = dict(row["features"])
        if source_for(row) != SOURCE:
            continue
        audit["sportsbet_rows"] += 1
        horse_number = int(row.get("horse_number", row.get("n", 0)) or 0)
        horse_runs = (runs or {}).get(horse_number, [])
        if not horse_runs:
            continue
        audit["parsed_rows"] += 1
        replay = aggregate(horse_runs, attributed=False)
        stored = original_values[index]
        if replay is None or stored is None or abs(replay - stored) > 0.011:
            audit["drift"] += 1
            continue
        candidate = aggregate(horse_runs, attributed=True)
        candidate_values[index] = candidate
        audit["removed_runs"] += sum(
            1 for item in horse_runs
            if not item["trial"]
            and item.get("margin") is not None
            and abs(float(item["margin"])) > COMPETITIVE_MARGIN_L
        )

    for index, row in enumerate(rows):
        if source_for(row) != SOURCE:
            continue
        if candidate_values[index] == original_values[index]:
            continue
        row["_candidate_features"]["pace_figure_score"] = pace_score(
            candidate_values, candidate_values[index]
        )
    return audit


def base_scorer(row: dict) -> float:
    return float(au_eval.default_scorer(row))


def candidate_scorer(row: dict) -> float:
    copy = {**row, "features": row.get("_candidate_features", row["features"])}
    return float(au_eval.default_scorer(copy))


def metric_deltas(races: list[dict], indices: list[int]) -> dict:
    subset = [races[index] for index in indices]
    base = au_eval._counts(subset, base_scorer)
    candidate = au_eval._counts(subset, candidate_scorer)
    return {
        key: round(candidate[key] - base[key], 4)
        for key in candidate
        if key in base
    }


def field_bucket_deltas(races: list[dict], indices: list[int]) -> dict:
    subset = [races[index] for index in indices]
    base = au_eval._counts_by_field(subset, base_scorer)
    candidate = au_eval._counts_by_field(subset, candidate_scorer)
    output = {}
    for bucket, candidate_row in candidate.items():
        base_row = base.get(bucket) or {}
        output[bucket] = {
            key: round(value - base_row.get(key, value), 4)
            for key, value in candidate_row.items()
            if key != "races"
        }
        output[bucket]["races"] = candidate_row.get("races", 0)
    return output


def annotate_dataset(races: list[dict], index: dict) -> dict:
    total = defaultdict(int)
    for race in races:
        metadata = race.get("metadata") or {}
        has_sportsbet = any(source_for(row) == SOURCE for row in race["rows"])
        runs = None
        if has_sportsbet:
            path = find_formguide(
                index,
                date=str(race.get("date") or metadata.get("date") or ""),
                track=str(metadata.get("track") or ""),
                race_number=int(metadata.get("race_number") or race.get("race") or 0),
            )
            if path:
                runs = parse_l600_runs(path, str(race.get("date") or metadata.get("date")))
                total["formguides"] += 1
            else:
                total["missing_formguides"] += 1
        audit = annotate_race(race, runs)
        for key, value in audit.items():
            total[key] += value
    return dict(total)


def randwick_r1(directory: Path) -> dict:
    logic = json.loads((directory / "Race_1_Logic.json").read_text(encoding="utf-8"))
    formguide = next(directory.glob("*Race 1 Formguide.md"))
    parsed = parse_l600_runs(formguide, "2026-08-22")
    rows = []
    for number, horse in (logic.get("horses") or {}).items():
        auto = horse.get("python_auto") or {}
        features = dict(auto.get("feature_scores") or {})
        aggregates = ((horse.get("_data") or {}).get("pf_metrics") or {}).get("pf_aggregates") or {}
        rows.append(
            {
                "horse_number": int(number),
                "horse_name": horse.get("horse_name"),
                "features": features,
                "wet": float(auto.get("wet_form_feature") or 0.0),
                "raw_pre_race": {"pf_aggregates": aggregates},
            }
        )
    race = {"date": "2026-08-22", "metadata": {"track": "Randwick", "race_number": 1}, "rows": rows}
    audit = annotate_race(race, parsed)
    base = sorted(rows, key=base_scorer, reverse=True)
    candidate = sorted(rows, key=candidate_scorer, reverse=True)
    attribution = {}
    for row in rows:
        horse_runs = parsed.get(int(row["horse_number"]), [])
        original_pf = aggregate(horse_runs, attributed=False)
        candidate_pf = aggregate(horse_runs, attributed=True)
        attribution[row["horse_name"]] = {
            "original_l600_avg": round(original_pf, 4) if original_pf is not None else None,
            "attributed_l600_avg": round(candidate_pf, 4) if candidate_pf is not None else None,
            "pf_runs": len(horse_runs),
            "kept_runs": sum(
                1 for item in horse_runs
                if item["trial"]
                or item.get("margin") is None
                or abs(float(item["margin"])) <= COMPETITIVE_MARGIN_L
            ),
        }
    return {
        "audit": audit,
        "pace_attribution": attribution,
        "original_top5": [
            [rank, row["horse_name"], round(base_scorer(row), 4), round(row["features"].get("pace_figure_score", 60), 2)]
            for rank, row in enumerate(base[:5], 1)
        ],
        "candidate_top5": [
            [rank, row["horse_name"], round(candidate_scorer(row), 4), round(row["_candidate_features"].get("pace_figure_score", 60), 2)]
            for rank, row in enumerate(candidate[:5], 1)
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--randwick-dir", type=Path)
    args = parser.parse_args()

    races = au_eval.load_races(args.dataset)
    index = meeting_index()
    audit = annotate_dataset(races, index)
    dev, holdout = au_eval.date_partitions(races)
    changed = sum(
        1 for race in races for row in race["rows"]
        if abs(candidate_scorer(row) - base_scorer(row)) > 1e-9
    )
    print(f"races={len(races)} dev={len(dev)} holdout={len(holdout)}")
    print("alignment_audit=" + json.dumps(audit, ensure_ascii=False, sort_keys=True))
    print(f"changed_runners={changed}")
    if audit.get("drift"):
        raise SystemExit("stored Sportsbet aggregate does not replay from Formguide")

    print("\ncontract comparison (single pre-declared candidate):")
    verdict = au_eval.compare(
        races,
        base_scorer,
        candidate_scorer,
        label="sportsbet_competitive_run_pace_attribution_3L",
    )
    print(verdict)
    print("all_metric_deltas=" + json.dumps(metric_deltas(races, list(range(len(races)))), ensure_ascii=False))
    print("dev_metric_deltas=" + json.dumps(metric_deltas(races, dev), ensure_ascii=False))
    print("holdout_metric_deltas=" + json.dumps(metric_deltas(races, holdout), ensure_ascii=False))
    print("holdout_field_buckets=" + json.dumps(field_bucket_deltas(races, holdout), ensure_ascii=False, sort_keys=True))

    if args.randwick_dir:
        print("\nRandwick R1 frozen pre-race snapshot:")
        print(json.dumps(randwick_r1(args.randwick_dir), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

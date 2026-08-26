#!/usr/bin/env python3
"""Research-only: exact Sportsbet race class and PacePerf reliability A/B.

The live Sportsbet parser already reads every historical run's ``header.cls``
but ``write_meeting`` drops it before the Formguide/Facts layer.  This harness
recovers the point-in-time class labels from cached target-race pages and tests
three fixed candidates against the current engine-leaf dump:

* class_form: add a small field-relative exact-class signal to form_score;
* class_pf: shrink only positive PF deviations when they came from weaker
  historical race classes;
* both: the two independent changes together.

No odds, target result, or run on/after the target date enters a feature.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUTO_SCRIPTS = (
    ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts"
)
AU_RACING = ROOT / ".agents" / "skills" / "au_racing"
sys.path.insert(0, str(AUTO_SCRIPTS))
sys.path.insert(0, str(AU_RACING))

from au_eval import (  # noqa: E402
    _auc_indices,
    _pairs,
    compare,
    date_partitions,
    default_scorer,
    load_races,
    verdict_dict,
)
from au_racing_engine import matrix_mapper  # noqa: E402
from au_racing_engine.scoring import MATRIX_WEIGHTS, clip_score  # noqa: E402
from claw_sportsbet_form import (  # noqa: E402
    BASE,
    parse_race,
    parse_runner_blocks,
    run_date,
)


FORM_CLASS_Z_SCALE = 5.0
PF_CLASS_RELIABILITY_SLOPE = 0.25
DECAY = (1.0, 0.8, 0.6, 0.4)


def identity(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())


def cache_path(cache_dir: Path, meeting_id: str, race_id: str) -> Path:
    url = f"{BASE}/{meeting_id}/{race_id}/"
    return cache_dir / f"{hashlib.sha1(url.encode()).hexdigest()}.html"


def class_level(label: object) -> float | None:
    """Ordered class-strength index from the exact Sportsbet label.

    The scale is deliberately simple and fixed before evaluation.  Benchmark
    labels retain their published rating; class-number races sit below BM64;
    black type and open races sit above handicaps.  The experiment only uses
    field-relative z-scores, so the absolute origin is immaterial.
    """
    text = re.sub(r"\s+", " ", str(label or "").upper()).strip()
    if not text or "BARRIER TRIAL" in text or "JUMP OUT" in text or "-BT" in text:
        return None
    if re.search(r"\b(?:GROUP\s*1|G1)\b", text):
        return 100.0
    if re.search(r"\b(?:GROUP\s*2|G2)\b", text):
        return 92.0
    if re.search(r"\b(?:GROUP\s*3|G3)\b", text):
        return 86.0
    if re.search(r"\b(?:LISTED|LR)\b", text):
        return 82.0
    bm = re.search(r"\bBM\s*(\d{2,3})\b", text)
    if bm:
        return float(bm.group(1))
    class_match = re.search(r"\b(?:CLASS|CL|C)\s*([1-6])\b", text)
    if class_match:
        return 60.0 + 2.0 * int(class_match.group(1))
    if "OPEN" in text:
        return 78.0
    if "HCP" in text or "HANDICAP" in text:
        return 72.0
    if "MAIDEN" in text or re.search(r"\bMDN\b", text):
        return 56.0
    return None


def weighted_level(runs: list[dict], target_date: str) -> tuple[float | None, list[str]]:
    values: list[tuple[float, str]] = []
    for run in runs:
        if run.get("is_trial"):
            continue
        date = run_date(run)
        if not date or date >= target_date:
            continue
        label = str((run.get("header") or {}).get("cls") or "").strip()
        level = class_level(label)
        if level is not None:
            values.append((level, label))
        if len(values) >= 4:
            break
    if not values:
        return None, []
    weights = DECAY[: len(values)]
    return (
        sum(value * weight for (value, _), weight in zip(values, weights)) / sum(weights),
        [label for _, label in values],
    )


def extract_levels(
    index_path: Path,
    cache_dir: Path,
    target_dates: set[str],
) -> tuple[dict[tuple[str, str, int, str], dict], dict]:
    meetings = json.loads(index_path.read_text(encoding="utf-8"))
    output: dict[tuple[str, str, int, str], dict] = {}
    counts = Counter()
    for meeting in meetings.values():
        target_date = str(meeting.get("date") or "")
        if target_date not in target_dates:
            continue
        counts["meetings_considered"] += 1
        meeting_id = str(meeting.get("meetingId") or "")
        for race_id in meeting.get("races") or []:
            path = cache_path(cache_dir, meeting_id, str(race_id))
            if not path.exists():
                counts["race_cache_missing"] += 1
                continue
            try:
                html = path.read_text(encoding="utf-8")
                parsed = parse_race(html)
                blocks = parse_runner_blocks(html)
            except Exception:  # noqa: BLE001 - research audit counts and continues
                counts["race_parse_error"] += 1
                continue
            race_number = int(parsed["meta"].get("race_number") or 0)
            track = identity(parsed["meta"].get("venue") or meeting.get("slug"))
            if not race_number or not track:
                counts["race_identity_missing"] += 1
                continue
            counts["race_pages"] += 1
            for block in blocks:
                level, labels = weighted_level(block.get("runs", []), target_date)
                if level is None:
                    continue
                key = (target_date, track, race_number, identity(block.get("name")))
                output[key] = {"level": level, "labels": labels}
                counts["runner_with_class"] += 1
                counts["class_rows"] += len(labels)
    return output, dict(counts)


def attach(races: list[dict], extracted: dict) -> dict:
    counts = Counter()
    for race in races:
        date = str(race.get("date") or "")
        meeting = str(race.get("meeting") or "")
        track = identity(re.sub(r"^\d{4}-\d{2}-\d{2}\s+", "", meeting).split(" Race ", 1)[0])
        race_number = int(race.get("race") or 0)
        matched = []
        for row in race["rows"]:
            key = (date, track, race_number, identity(row.get("name")))
            info = extracted.get(key)
            if info:
                row["_exact_class_level"] = float(info["level"])
                row["_exact_class_labels"] = list(info["labels"])
                matched.append(row)
                counts["runner_matched"] += 1
        if len(matched) < 3:
            counts["race_insufficient_class"] += 1
            continue
        levels = [row["_exact_class_level"] for row in matched]
        mean = sum(levels) / len(levels)
        stdev = math.sqrt(sum((value - mean) ** 2 for value in levels) / len(levels))
        if stdev <= 0:
            counts["race_no_class_spread"] += 1
            continue
        for row in matched:
            row["_exact_class_z"] = (row["_exact_class_level"] - mean) / stdev
        counts["race_usable"] += 1
    return dict(counts)


def scorer(mode: str):
    if mode not in {"class_form", "class_pf", "both"}:
        raise ValueError(mode)

    def score(row: dict) -> float:
        features = dict(row["features"])
        z_value = row.get("_exact_class_z")
        if z_value is not None and mode in {"class_form", "both"}:
            features["form_score"] = clip_score(
                float(features.get("form_score", 60.0)) + FORM_CLASS_Z_SCALE * float(z_value)
            )
        if z_value is not None and mode in {"class_pf", "both"}:
            pace = float(features.get("pace_figure_score", 60.0))
            if pace > 60.0 and float(z_value) < 0.0:
                reliability = max(0.5, 1.0 + PF_CLASS_RELIABILITY_SLOPE * float(z_value))
                features["pace_figure_score"] = 60.0 + reliability * (pace - 60.0)
        matrices = matrix_mapper.map_features_to_matrix_scores(features)
        return (
            sum(matrices.get(key, 60.0) * weight for key, weight in MATRIX_WEIGHTS.items())
            + float(row.get("wet") or 0.0)
        )

    return score


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument(
        "--index",
        type=Path,
        default=AU_RACING / "data" / "sb_archive_meeting_ids.json",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=AU_RACING / ".sportsbet_cache",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    races = load_races(args.dataset)
    target_dates = {str(race.get("date") or "") for race in races}
    extracted, extraction = extract_levels(args.index, args.cache_dir, target_dates)
    attachment = attach(races, extracted)

    # The index ends on 2026-08-21.  Later unmatched races would merely dilute
    # the candidate with zeros, so evaluation uses the point-in-time-covered
    # window and keeps every whole date inside it.
    covered_races = [
        race for race in races
        if str(race.get("date") or "") <= "2026-08-21"
        and sum(row.get("_exact_class_z") is not None for row in race["rows"]) >= 3
    ]
    dev_indices, _holdout_indices = date_partitions(covered_races)
    baseline_pairs = _pairs(covered_races, default_scorer, True)
    development = []
    for mode in ("class_form", "class_pf", "both"):
        candidate_pairs = _pairs(covered_races, scorer(mode), True)
        development.append({
            "mode": mode,
            "development_top5_auc_delta": (
                _auc_indices(candidate_pairs, dev_indices)
                - _auc_indices(baseline_pairs, dev_indices)
            ),
        })
    chosen = max(development, key=lambda item: item["development_top5_auc_delta"])
    verdict = None
    if chosen["development_top5_auc_delta"] > 0:
        verdict = verdict_dict(compare(
            covered_races,
            default_scorer,
            scorer(chosen["mode"]),
            label=f"exact class candidate: {chosen['mode']}",
        ))

    report = {
        "design": {
            "dataset": str(args.dataset),
            "point_in_time": "historical run date < target meeting date",
            "odds_used": False,
            "fixed_candidates": {
                "class_form": f"form_score += {FORM_CLASS_Z_SCALE} * field-relative class z",
                "class_pf": (
                    "positive PF deviation reliability = max(0.5, "
                    f"1 + {PF_CLASS_RELIABILITY_SLOPE} * negative class z)"
                ),
                "both": "class_form + class_pf",
            },
        },
        "extraction": extraction,
        "attachment": attachment,
        "covered_races": len(covered_races),
        "development": development,
        "chosen": chosen,
        "holdout_verdict": verdict,
    }
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

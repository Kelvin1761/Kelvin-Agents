#!/usr/bin/env python3
"""Evaluate Sportsbet complete-form Performance Quality on the canonical gate.

The historical run is point-in-time safe only when its date is strictly before
the target meeting.  SP/result never enters candidate scoring.  Candidate
strength is selected on development dates; terminal dates are opened once by
``au_eval.compare``.
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
from statistics import mean, pstdev

SCRIPT_DIR = Path(__file__).resolve().parent
AUTO_DIR = SCRIPT_DIR.parent
AU_RACING = AUTO_DIR.parent
ENGINE_DIR = SCRIPT_DIR / "au_racing_engine"
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(ENGINE_DIR.parent))
sys.path.insert(0, str(AU_RACING))

from au_racing_engine import matrix_mapper  # noqa: E402
from au_eval import (  # noqa: E402
    _auc_indices,
    _pairs,
    compare,
    date_partitions,
    default_scorer,
    load_races,
    verdict_dict,
)
from claw_sportsbet_form import BASE, parse_race, parse_runner_blocks, run_date  # noqa: E402
from au_racing_engine.engine_core import (  # noqa: E402
    _performance_quality_digest,
    clip_score,
)
from au_racing_engine.scoring import MATRIX_WEIGHTS  # noqa: E402


def _identity(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def _cache_path(cache_dir: Path, meeting_id: str, race_id: str) -> Path:
    url = f"{BASE}/{meeting_id}/{race_id}/"
    return cache_dir / f"{hashlib.sha1(url.encode()).hexdigest()}.html"


def _entry(run: dict) -> dict:
    return {
        "date": run_date(run),
        "finish_pos": int(run["pos"]) if run.get("pos") else None,
        "margin": float(run["margin"]) if run.get("margin") else None,
        "margin_source": "header" if run.get("margin") else "",
        "prize": float(re.sub(r"[^\d.]", "", run.get("prize") or "") or 0),
        "starters": int(run["field"]) if run.get("field") else None,
        "distance": int((run.get("header") or {}).get("dist") or 0) or None,
        "is_trial": bool(run.get("is_trial")),
    }


def extract_quality(
    index_path: Path,
    cache_dir: Path,
    target_dates: set[str],
) -> tuple[dict[tuple[str, str, int, str], dict], dict]:
    meetings = json.loads(index_path.read_text(encoding="utf-8"))
    output = {}
    counts = Counter()
    for meeting_index, meeting in enumerate(meetings.values(), 1):
        target_date = str(meeting.get("date") or "")
        if target_date not in target_dates:
            continue
        counts["meetings_considered"] += 1
        meeting_id = str(meeting.get("meetingId") or "")
        for race_id in meeting.get("races") or []:
            path = _cache_path(cache_dir, meeting_id, str(race_id))
            if not path.exists():
                counts["race_cache_missing"] += 1
                continue
            try:
                html = path.read_text(encoding="utf-8")
                parsed = parse_race(html)
                blocks = parse_runner_blocks(html)
            except Exception:  # noqa: BLE001 - count and continue this research audit
                counts["race_parse_error"] += 1
                continue
            race_number = int(parsed["meta"].get("race_number") or 0)
            track = _identity(parsed["meta"].get("venue") or meeting.get("slug"))
            if not race_number or not track:
                counts["race_identity_missing"] += 1
                continue
            counts["race_pages"] += 1
            for block in blocks:
                entries = [
                    _entry(run) for run in block.get("runs", [])
                    if run_date(run) and run_date(run) < target_date
                    and not run.get("is_trial")
                ]
                digest = _performance_quality_digest(
                    entries,
                    meeting_date=target_date,
                )
                if not digest:
                    counts["runner_no_complete_digest"] += 1
                    continue
                key = (
                    target_date,
                    track,
                    race_number,
                    _identity(block.get("name")),
                )
                output[key] = digest
                counts["runner_digest"] += 1
        if meeting_index % 20 == 0:
            print(
                f"Sportsbet quality extraction: {meeting_index}/{len(meetings)} meetings",
                flush=True,
            )
    return output, dict(counts)


def load_quality_cache(path: Path) -> tuple[dict, dict] | None:
    if not path.exists():
        return None
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        quality = {
            tuple(record["key"]): record["digest"]
            for record in document.get("records", [])
        }
        return quality, document.get("extraction", {})
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None


def save_quality_cache(path: Path, quality: dict, extraction: dict) -> None:
    document = {
        "extraction": extraction,
        "records": [
            {"key": list(key), "digest": digest}
            for key, digest in quality.items()
        ],
    }
    path.write_text(
        json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def attach_candidate(races: list[dict], quality: dict) -> dict:
    counts = Counter()
    for race in races:
        meta = race.get("metadata") or {}
        date = str(race.get("date") or meta.get("date") or "")
        track = _identity(meta.get("track"))
        race_number = int(meta.get("race_number") or 0)
        values = []
        for row in race["rows"]:
            key = (date, track, race_number, _identity(row.get("horse_name")))
            digest = quality.get(key)
            row["_sb_performance_quality"] = digest
            if digest and digest.get("run_count", 0) >= 2:
                values.append(float(digest["raw"]))
        if len(values) < 3 or pstdev(values) <= 0:
            counts["race_field_gate_failed"] += 1
            continue
        field_mean, field_stdev = mean(values), pstdev(values)
        counts["race_field_gate_passed"] += 1
        for row in race["rows"]:
            digest = row.get("_sb_performance_quality")
            if not digest or digest.get("run_count", 0) < 2:
                continue
            raw = float(digest["raw"])
            row["_sb_performance_quality_score"] = clip_score(
                60.0 + 20.0 * (raw - field_mean) / field_stdev
            )
            counts["runner_score"] += 1
            state = (row.get("feature_evidence_state") or {}).get(
                "performance_quality_score"
            )
            if state in {"missing", "fallback"}:
                counts["runner_fillable"] += 1
    return dict(counts)


def candidate_scorer(alpha: float):
    def score(row: dict) -> float:
        features = dict(row["features"])
        current = float(features.get("performance_quality_score", 60.0))
        sportsbet = row.get("_sb_performance_quality_score")
        state = (row.get("feature_evidence_state") or {}).get(
            "performance_quality_score"
        )
        if sportsbet is not None and state in {"missing", "fallback"}:
            features["performance_quality_score"] = (
                current + float(alpha) * (float(sportsbet) - current)
            )
        matrices = matrix_mapper.map_features_to_matrix_scores(features)
        return (
            sum(matrices.get(key, 60.0) * weight
                for key, weight in MATRIX_WEIGHTS.items())
            + float(row.get("wet") or 0.0)
        )
    return score


def _rank_lookup(race: dict, scorer) -> dict[int, int]:
    ranked = sorted(
        race["rows"],
        key=lambda row: (-scorer(row), int(row["horse_number"])),
    )
    return {
        int(row["horse_number"]): rank for rank, row in enumerate(ranked, 1)
    }


def directional_changes(races: list[dict], scorer) -> dict:
    base_cold = cand_cold = base_fav = cand_fav = 0
    fav_improved = fav_worsened = cold_improved = cold_worsened = 0
    for race in races:
        rows = race["rows"]
        base_rank = _rank_lookup(race, default_scorer)
        cand_rank = _rank_lookup(race, scorer)
        last = max(int(row["pos"]) for row in rows)
        prices = [float(row["result_sp_label"]) for row in rows
                  if row.get("result_sp_label") is not None]
        favourite = min(prices) if prices else None
        for row in rows:
            number = int(row["horse_number"])
            sp = row.get("result_sp_label")
            actual = int(row["pos"])
            if sp is not None and float(sp) >= 21 and actual == last:
                base_cold += base_rank[number] <= 3
                cand_cold += cand_rank[number] <= 3
                cold_improved += cand_rank[number] > base_rank[number]
                cold_worsened += cand_rank[number] < base_rank[number]
            if (favourite is not None and sp is not None
                    and float(sp) == favourite and actual <= 3):
                base_fav += base_rank[number] >= 5
                cand_fav += cand_rank[number] >= 5
                fav_improved += cand_rank[number] < base_rank[number]
                fav_worsened += cand_rank[number] > base_rank[number]
    return {
        "cold_last_model_top3_before": base_cold,
        "cold_last_model_top3_after": cand_cold,
        "cold_last_rank_improved": cold_improved,
        "cold_last_rank_worsened": cold_worsened,
        "favourite_top3_model_low_before": base_fav,
        "favourite_top3_model_low_after": cand_fav,
        "favourite_rank_improved": fav_improved,
        "favourite_rank_worsened": fav_worsened,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument(
        "--index", type=Path,
        default=AU_RACING / "data" / "sb_archive_meeting_ids.json",
    )
    parser.add_argument(
        "--cache-dir", type=Path,
        default=AU_RACING / ".sportsbet_cache",
    )
    parser.add_argument(
        "--alphas", default="0.25,0.5,0.75,1.0",
        help="Development-only shrink candidates.",
    )
    parser.add_argument(
        "--output", type=Path,
        default=Path("/private/tmp/au_sportsbet_performance_quality_candidate.json"),
    )
    parser.add_argument(
        "--quality-cache", type=Path,
        default=Path("/private/tmp/au_sportsbet_performance_quality_sidecar.json"),
    )
    args = parser.parse_args()
    races = load_races(args.dataset)
    target_dates = {str(race.get("date") or "") for race in races}
    cached = load_quality_cache(args.quality_cache)
    if cached:
        quality, extraction = cached
        print(f"Loaded {len(quality)} cached Sportsbet quality records", flush=True)
    else:
        quality, extraction = extract_quality(args.index, args.cache_dir, target_dates)
        save_quality_cache(args.quality_cache, quality, extraction)
    attachment = attach_candidate(races, quality)
    dev_indices, _terminal_indices = date_partitions(races)
    base_pairs = _pairs(races, default_scorer, True)
    search = []
    for alpha in [float(value) for value in args.alphas.split(",") if value.strip()]:
        scorer = candidate_scorer(alpha)
        pairs = _pairs(races, scorer, True)
        delta = _auc_indices(pairs, dev_indices) - _auc_indices(base_pairs, dev_indices)
        search.append({"alpha": alpha, "development_top5_auc_delta": delta})
    # Terminal labels remain unopened during selection.
    chosen = max(search, key=lambda row: (row["development_top5_auc_delta"], -row["alpha"]))
    scorer = candidate_scorer(chosen["alpha"])
    verdict = compare(
        races,
        default_scorer,
        scorer,
        label=f"Sportsbet complete-form Performance Quality ×{chosen['alpha']:g}",
    )
    # Selection is already locked above.  These are post-selection sensitivity
    # reports, never used to change ``chosen_alpha``.
    sensitivity = []
    for row in search:
        alpha = row["alpha"]
        tested = compare(
            races,
            default_scorer,
            candidate_scorer(alpha),
            label=f"sensitivity alpha={alpha:g}",
        )
        sensitivity.append({
            "alpha": alpha,
            "verdict": verdict_dict(tested),
            "directional_failures": directional_changes(
                races, candidate_scorer(alpha)
            ),
        })
    report = {
        "design": {
            "point_in_time": "historical run date < target meeting date",
            "selection": "alpha selected by development top-5 AUC only",
            "terminal": "opened once by canonical paired whole-race bootstrap",
            "sp_in_scoring": False,
        },
        "extraction": extraction,
        "attachment": attachment,
        "development_search": search,
        "chosen_alpha": chosen["alpha"],
        "verdict": verdict_dict(verdict),
        "directional_failures": directional_changes(races, scorer),
        "post_selection_sensitivity": sensitivity,
    }
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if verdict.ship else 2


if __name__ == "__main__":
    raise SystemExit(main())

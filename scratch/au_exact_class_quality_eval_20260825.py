#!/usr/bin/env python3
"""Research-only exact Sportsbet class encodings for AU ranking.

This is a follow-up to EXP-20260825-02.  It deliberately tests three
*alternative* encodings rather than stacking them:

* ``average_class``: decay-weighted mean strength of the last four runs;
* ``proven_class``: class strength weighted by how competitively the horse ran;
* ``today_proof``: best recent performance at today's class or stronger.

Historical rows must pre-date the target race.  Today's race class is metadata
available on the racecard; no target result or odds enter any feature.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUTO_SCRIPTS = ROOT / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
AU_RACING = ROOT / ".agents/skills/au_racing"
sys.path.insert(0, str(AUTO_SCRIPTS))
sys.path.insert(0, str(AU_RACING))

from au_eval import (  # noqa: E402
    _auc_indices,
    _counts,
    _pairs,
    compare,
    date_partitions,
    default_scorer,
    load_races,
    verdict_dict,
)
from claw_sportsbet_form import BASE, parse_race, parse_runner_blocks, run_date  # noqa: E402


DECAY = (1.0, 0.8, 0.6, 0.4)
KS = (0.25, 0.5, 1.0, 1.5, 2.0, 3.0)
MIN_RUNNERS = 3


def identity(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())


def cache_path(cache_dir: Path, meeting_id: str, race_id: str) -> Path:
    url = f"{BASE}/{meeting_id}/{race_id}/"
    return cache_dir / f"{hashlib.sha1(url.encode()).hexdigest()}.html"


def class_level(label: object) -> float | None:
    """Conservative ordered strength for common Sportsbet class labels.

    Order matters: maiden handicaps are maidens, not generic handicaps.  This
    was reversed in EXP-20260825-02 and is the semantic reason for this retry.
    Absolute values do not enter the scorer directly; each feature is
    standardised within the target race.
    """
    text = re.sub(r"\s+", " ", str(label or "").upper()).strip()
    if not text or any(token in text for token in ("BARRIER TRIAL", "JUMP OUT", "-BT")):
        return None
    if re.search(r"\b(?:GROUP\s*1|G1)\b", text):
        return 100.0
    if re.search(r"\b(?:GROUP\s*2|G2)\b", text):
        return 92.0
    if re.search(r"\b(?:GROUP\s*3|G3)\b", text):
        return 86.0
    if re.search(r"\b(?:LISTED|LR)\b", text):
        return 82.0
    if "MAIDEN" in text or re.search(r"\bMDN\b", text):
        return 56.0
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
    return None


def finish_quality(run: dict) -> float | None:
    """0..1 field-relative finish quality, using only the historical result."""
    try:
        pos = int(run.get("pos") or 0)
        field = int(run.get("field") or 0)
    except (TypeError, ValueError):
        return None
    if pos <= 0 or field <= 1 or pos > field:
        return None
    return 1.0 - (pos - 1.0) / (field - 1.0)


def runner_signals(runs: list[dict], target_date: str, today_level: float | None) -> dict:
    recent = []
    labels = []
    for run in runs:
        if run.get("is_trial"):
            continue
        date = run_date(run)
        if not date or date >= target_date:
            continue
        label = str((run.get("header") or {}).get("cls") or "").strip()
        level = class_level(label)
        if level is None:
            continue
        recent.append((level, finish_quality(run)))
        labels.append(label)
        if len(recent) >= 4:
            break
    if not recent:
        return {"labels": []}

    weights = DECAY[: len(recent)]
    average = sum(level * weight for (level, _), weight in zip(recent, weights)) / sum(weights)

    # A high-class run is evidence only in proportion to the achieved finish.
    # Subtracting the maiden floor avoids granting a large intercept to every
    # runner; within-race z-scoring then measures only comparative support.
    proven_num = proven_den = 0.0
    for (level, quality), weight in zip(recent, weights):
        if quality is None:
            continue
        proven_num += weight * (level - 56.0) * quality
        proven_den += weight
    proven = proven_num / proven_den if proven_den else None

    today_proof = None
    if today_level is not None:
        eligible = [
            quality for level, quality in recent
            if quality is not None and level >= today_level
        ]
        if eligible:
            # Best recent result at this class-or-higher.  Missing means
            # unknown and stays neutral after attachment, not an automatic
            # penalty for lightly raced horses.
            today_proof = max(eligible)
    return {
        "average_class": average,
        "proven_class": proven,
        "today_proof": today_proof,
        "labels": labels,
    }


def extract(index_path: Path, cache_dir: Path, target_dates: set[str]) -> tuple[dict, dict]:
    meetings = json.loads(index_path.read_text(encoding="utf-8"))
    output = {}
    counts = Counter()
    label_counts = Counter()
    unmapped_counts = Counter()
    target_label_counts = Counter()
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
            target_label = str(parsed["meta"].get("race_class") or "").strip()
            target_level = class_level(target_label)
            if target_label:
                target_label_counts[target_label] += 1
            if target_level is not None:
                counts["target_class_mapped"] += 1
            if not race_number or not track:
                counts["race_identity_missing"] += 1
                continue
            counts["race_pages"] += 1
            for block in blocks:
                signals = runner_signals(block.get("runs", []), target_date, target_level)
                if not signals.get("labels"):
                    continue
                for label in signals["labels"]:
                    label_counts[label] += 1
                    if class_level(label) is None:
                        unmapped_counts[label] += 1
                key = "|".join((target_date, track, str(race_number), identity(block.get("name"))))
                output[key] = signals
                counts["runner_with_class"] += 1
                counts["class_rows"] += len(signals["labels"])
    audit = dict(counts)
    audit["top_labels"] = label_counts.most_common(40)
    audit["top_unmapped_labels"] = unmapped_counts.most_common(40)
    audit["top_target_labels"] = target_label_counts.most_common(30)
    return output, audit


def extract_case_page(path: Path, target_date: str) -> tuple[dict, dict]:
    """Extract one later meeting page for a locked-candidate case replay."""
    html = path.read_text(encoding="utf-8")
    parsed = parse_race(html)
    race_number = int(parsed["meta"].get("race_number") or 0)
    track = identity(parsed["meta"].get("venue"))
    target_label = str(parsed["meta"].get("race_class") or "").strip()
    target_level = class_level(target_label)
    output = {}
    for block in parse_runner_blocks(html):
        signals = runner_signals(block.get("runs", []), target_date, target_level)
        if not signals.get("labels"):
            continue
        key = "|".join((target_date, track, str(race_number), identity(block.get("name"))))
        output[key] = signals
    return output, {
        "path": str(path),
        "date": target_date,
        "track": track,
        "race": race_number,
        "target_label": target_label,
        "target_level": target_level,
        "runners": len(output),
    }


def _zs(values: list[float | None]) -> list[float | None]:
    have = [float(value) for value in values if value is not None]
    if len(have) < MIN_RUNNERS:
        return [None] * len(values)
    stdev = statistics.pstdev(have)
    if stdev <= 0:
        return [None] * len(values)
    mean = statistics.mean(have)
    return [None if value is None else (float(value) - mean) / stdev for value in values]


def attach(races: list[dict], extracted: dict) -> dict:
    counts = Counter()
    for race in races:
        date = str(race.get("date") or "")
        meeting = str(race.get("meeting") or "")
        track = identity(re.sub(r"^\d{4}-\d{2}-\d{2}\s+", "", meeting).split(" Race ", 1)[0])
        race_number = int(race.get("race") or 0)
        infos = []
        for row in race["rows"]:
            key = "|".join((date, track, str(race_number), identity(row.get("name"))))
            info = extracted.get(key)
            infos.append(info)
            if info:
                row["_class_labels"] = info.get("labels") or []
                counts["runner_matched"] += 1
        for feature in ("average_class", "proven_class", "today_proof"):
            z_values = _zs([info.get(feature) if info else None for info in infos])
            usable = 0
            for row, value in zip(race["rows"], z_values):
                if value is not None:
                    row[f"_{feature}_z"] = value
                    usable += 1
            if usable >= MIN_RUNNERS:
                counts[f"race_usable_{feature}"] += 1
    return dict(counts)


def candidate_scorer(feature: str, k: float):
    key = f"_{feature}_z"

    def score(row: dict) -> float:
        # A missing value is evidence-neutral.  k is in final-score points and
        # is chosen on development only.
        return default_scorer(row) + k * float(row.get(key) or 0.0)

    return score


def development_folds(races: list[dict], dev_indices: list[int], folds: int = 5) -> list[list[int]]:
    by_date = {}
    for index in dev_indices:
        by_date.setdefault(str(races[index].get("date") or ""), []).append(index)
    dates = sorted(by_date)
    result = []
    for fold_no in range(folds):
        lo = math.floor(len(dates) * fold_no / folds)
        hi = math.floor(len(dates) * (fold_no + 1) / folds)
        result.append([index for date in dates[lo:hi] for index in by_date[date]])
    return result


def delta_counts(races: list[dict], indices: list[int], scorer) -> dict:
    subset = [races[index] for index in indices]
    base = _counts(subset, default_scorer)
    cand = _counts(subset, scorer)
    return {key: cand[key] - base[key] for key in cand if key in base}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--index", type=Path, default=AU_RACING / "data/sb_archive_meeting_ids.json")
    parser.add_argument("--cache-dir", type=Path, default=AU_RACING / ".sportsbet_cache")
    parser.add_argument("--extract-cache", type=Path)
    parser.add_argument("--case-html", type=Path)
    parser.add_argument("--case-date")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    races = load_races(args.dataset)
    target_dates = {str(race.get("date") or "") for race in races}
    if args.extract_cache and args.extract_cache.exists():
        cached = json.loads(args.extract_cache.read_text(encoding="utf-8"))
        extracted, extraction = cached["runners"], cached["audit"]
    else:
        extracted, extraction = extract(args.index, args.cache_dir, target_dates)
        if args.extract_cache:
            args.extract_cache.write_text(
                json.dumps({"runners": extracted, "audit": extraction}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
    case_meta = None
    if args.case_html:
        if not args.case_date:
            parser.error("--case-html requires --case-date")
        case_extracted, case_meta = extract_case_page(args.case_html, args.case_date)
        extracted.update(case_extracted)
    attachment = attach(races, extracted)

    # The cache index currently ends 2026-08-21.  Keep whole dates and only
    # races where at least one candidate has genuine within-race variation.
    covered = [
        race for race in races
        if str(race.get("date") or "") <= "2026-08-21"
        and any(
            sum(f"_{feature}_z" in row for row in race["rows"]) >= MIN_RUNNERS
            for feature in ("average_class", "proven_class", "today_proof")
        )
    ]
    dev_indices, _holdout_indices = date_partitions(covered)
    folds = development_folds(covered, dev_indices)
    base_top = _pairs(covered, default_scorer, True)
    base_all = _pairs(covered, default_scorer, False)

    development = []
    for feature in ("average_class", "proven_class", "today_proof"):
        for k in KS:
            scorer = candidate_scorer(feature, k)
            cand_top = _pairs(covered, scorer, True)
            cand_all = _pairs(covered, scorer, False)
            top_delta = _auc_indices(cand_top, dev_indices) - _auc_indices(base_top, dev_indices)
            all_delta = _auc_indices(cand_all, dev_indices) - _auc_indices(base_all, dev_indices)
            fold_deltas = [
                _auc_indices(cand_top, fold) - _auc_indices(base_top, fold)
                for fold in folds if fold
            ]
            counts = delta_counts(covered, dev_indices, scorer)
            development.append({
                "feature": feature,
                "k": k,
                "top5_auc_delta": top_delta,
                "all_auc_delta": all_delta,
                "nonnegative_folds": sum(delta >= 0 for delta in fold_deltas),
                "fold_top5_auc_deltas": fold_deltas,
                "count_deltas": counts,
            })

    eligible = [
        item for item in development
        if item["top5_auc_delta"] > 0 and item["nonnegative_folds"] >= 4
    ]
    chosen = max(eligible, key=lambda item: item["top5_auc_delta"]) if eligible else None
    verdict = None
    if chosen:
        verdict = verdict_dict(compare(
            covered,
            default_scorer,
            candidate_scorer(chosen["feature"], chosen["k"]),
            label=f"exact class {chosen['feature']} k={chosen['k']}",
        ))

    case_replay = None
    if chosen and case_meta:
        case_race = next((
            race for race in races
            if str(race.get("date") or "") == case_meta["date"]
            and int(race.get("race") or 0) == case_meta["race"]
            and identity(race.get("meeting")) .find(case_meta["track"]) >= 0
        ), None)
        if case_race:
            cand = candidate_scorer(chosen["feature"], chosen["k"])
            base_order = sorted(case_race["rows"], key=default_scorer, reverse=True)
            cand_order = sorted(case_race["rows"], key=cand, reverse=True)
            base_rank = {id(row): rank for rank, row in enumerate(base_order, 1)}
            cand_rank = {id(row): rank for rank, row in enumerate(cand_order, 1)}
            case_replay = {
                **case_meta,
                "locked_feature": chosen["feature"],
                "locked_k": chosen["k"],
                "ranking": [{
                    "name": row.get("name"),
                    "actual_pos": row.get("pos"),
                    "baseline_rank": base_rank[id(row)],
                    "candidate_rank": cand_rank[id(row)],
                    "baseline_score": default_scorer(row),
                    "candidate_score": cand(row),
                    "feature_z": row.get(f"_{chosen['feature']}_z"),
                    "labels": row.get("_class_labels") or [],
                } for row in cand_order],
            }

    report = {
        "design": {
            "dataset": str(args.dataset),
            "point_in_time": "historical run date < target date; current race class is pre-race metadata",
            "odds_used": False,
            "actual_result_usage": "labels/evaluation only",
            "alternatives_not_stacked": ["average_class", "proven_class", "today_proof"],
            "k_grid_development_only": list(KS),
            "promotion_gate": "dev top5 AUC > 0; >=4/5 whole-date folds nonnegative; canonical holdout CI > 0",
        },
        "extraction": extraction,
        "attachment": attachment,
        "covered_races": len(covered),
        "development": development,
        "chosen_before_holdout": chosen,
        "holdout_verdict": verdict,
        "case_replay": case_replay,
    }
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

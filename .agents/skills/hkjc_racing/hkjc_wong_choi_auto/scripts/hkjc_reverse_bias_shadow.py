#!/usr/bin/env python3
"""Prospective intraday reverse-bias shadow for HKJC Wong Choi.

The shadow never edits Logic, ability scores, ranks, or the official Top 4.
For target race N it may only inspect completed races < N from the same
meeting and surface.  Official draw is a gate-position proxy; it is never
described as the lane actually travelled.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any


CONTRACT_VERSION = "HKJC_REVERSE_BIAS_SHADOW_V1"
MIN_PRIOR_SAME_SURFACE_RACES = 2
FULL_RELIABILITY_RACES = 4
REVERSE_THRESHOLD = 0.55
OUTER_DRAW_PERCENTILE = 2.0 / 3.0
MIN_ACTIVE_RACES_FOR_REVIEW = 80


def _int(value: Any) -> int | None:
    match = re.search(r"\d+", str(value or ""))
    return int(match.group()) if match else None


def _float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_hash(payload: dict) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temp, path)


def _surface_key(context: dict) -> str:
    venue = " ".join(
        str(context.get(key) or "")
        for key in ("venue", "course", "racecourse")
    ).upper()
    surface = " ".join(
        str(context.get(key) or "")
        for key in ("track", "surface", "track_type", "venue")
    ).upper()
    is_hv = "跑馬地" in venue or "HAPPY VALLEY" in venue or "HAPPYVALLEY" in venue
    is_awt = any(token in surface for token in ("AWT", "ALL WEATHER", "全天候", "泥地"))
    if is_hv:
        return "HV_TURF"
    return "ST_AWT" if is_awt else "ST_TURF"


def _race_number(path: Path) -> int:
    match = re.search(r"Race[_ ](\d+)", path.name, re.I)
    return int(match.group(1)) if match else 0


def load_logic(meeting_dir: Path) -> dict[int, dict]:
    output = {}
    for path in sorted(meeting_dir.glob("Race_*_Logic.json"), key=_race_number):
        race_no = _race_number(path)
        if race_no <= 0 or path.stat().st_size <= 10:
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        horses = payload.get("horses") if isinstance(payload, dict) else None
        if not isinstance(horses, dict) or not horses:
            continue
        output[race_no] = {
            "path": path,
            "sha256": _sha256(path),
            "surface": _surface_key(payload.get("race_analysis") or {}),
            "horses": horses,
        }
    return output


def load_results(path: Path) -> dict[int, dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("results payload must be an object keyed by race number")
    output = {}
    for race_no_text, race in payload.items():
        race_no = _int(race_no_text)
        rows = race.get("results") if isinstance(race, dict) else None
        if race_no and isinstance(rows, list):
            valid = [row for row in rows if isinstance(row, dict) and _int(row.get("pos"))]
            if len(valid) >= 4:
                output[race_no] = {**race, "results": valid}
    return output


def completed_prefix(results: dict[int, dict], logic: dict[int, dict]) -> list[int]:
    prefix = []
    for race_no in range(1, max(logic, default=0) + 1):
        if race_no not in results or race_no not in logic:
            break
        prefix.append(race_no)
    return prefix


def _top3_observations(race: dict) -> tuple[list[float], list[float]]:
    rows = race.get("results") if isinstance(race.get("results"), list) else []
    starters = [row for row in rows if _int(row.get("pos"))]
    field_size = len(starters)
    if field_size < 4:
        return [], []
    positions: list[float] = []
    draws: list[float] = []
    for row in starters:
        finish = _int(row.get("pos"))
        if finish is None or finish > 3:
            continue
        early = _int(row.get("running_positions"))
        draw = _int(row.get("draw"))
        if early is not None and 1 <= early <= field_size:
            positions.append((early - 1.0) / (field_size - 1.0))
        if draw is not None and 1 <= draw <= field_size:
            draws.append((draw - 1.0) / (field_size - 1.0))
    return positions, draws


def prior_bias(
    *,
    target_race: int,
    target_surface: str,
    prefix: list[int],
    results: dict[int, dict],
    logic: dict[int, dict],
) -> dict:
    positions: list[float] = []
    draws: list[float] = []
    used_races = []
    source_observations = []
    for race_no in prefix:
        if race_no >= target_race or logic[race_no]["surface"] != target_surface:
            continue
        race_positions, race_draws = _top3_observations(results[race_no])
        if len(race_positions) < 2 or len(race_draws) < 2:
            continue
        positions.extend(race_positions)
        draws.extend(race_draws)
        used_races.append(race_no)
        source_observations.append(
            {
                "race_number": race_no,
                "top3_early_position_percentiles": [
                    round(value, 6) for value in race_positions
                ],
                "top3_draw_percentiles": [round(value, 6) for value in race_draws],
            }
        )
    races = len(used_races)
    raw_position = sum(positions) / len(positions) if positions else 0.5
    raw_draw = sum(draws) / len(draws) if draws else 0.5
    reliability = min(races / float(FULL_RELIABILITY_RACES), 1.0)
    position = 0.5 + reliability * (raw_position - 0.5)
    draw = 0.5 + reliability * (raw_draw - 0.5)
    if races < MIN_PRIOR_SAME_SURFACE_RACES:
        status = "insufficient_evidence"
    elif position >= REVERSE_THRESHOLD and draw >= REVERSE_THRESHOLD:
        status = "reverse_bias"
    elif position >= REVERSE_THRESHOLD or draw >= REVERSE_THRESHOLD:
        status = "watch"
    else:
        status = "baseline"
    return {
        "status": status,
        "same_surface_races": races,
        "source_races": used_races,
        "source_observations": source_observations,
        "reliability": round(reliability, 4),
        "top3_early_position_raw": round(raw_position, 4),
        "top3_draw_raw": round(raw_draw, 4),
        "top3_early_position_shrunk": round(position, 4),
        "top3_draw_shrunk": round(draw, 4),
    }


def _ranked_horses(horses: dict) -> list[dict]:
    ranked = []
    for horse_no_text, horse in horses.items():
        if not isinstance(horse, dict):
            continue
        horse_no = _int(horse_no_text)
        auto = horse.get("python_auto") if isinstance(horse.get("python_auto"), dict) else {}
        ability = _float(auto.get("ability_score"))
        rank = _int(auto.get("rank"))
        if horse_no is None or ability is None:
            continue
        ranked.append(
            {
                "horse_number": horse_no,
                "horse_name": str(horse.get("horse_name") or "").strip(),
                "barrier": _int(horse.get("barrier") or horse.get("draw")),
                "ability_score": round(ability, 4),
                "stored_rank": rank,
            }
        )
    ranked.sort(
        key=lambda row: (
            row["stored_rank"] if row["stored_rank"] is not None else 10_000,
            -row["ability_score"],
            row["horse_number"],
        )
    )
    return ranked


def target_decision(race_no: int, item: dict, bias: dict) -> dict:
    ranked = _ranked_horses(item["horses"])
    baseline = [row["horse_number"] for row in ranked[:4]]
    field_size = max(len(ranked), 2)
    alternate = None
    for row in ranked[4:]:
        barrier = row["barrier"]
        if barrier is None:
            continue
        draw_pct = (barrier - 1.0) / (field_size - 1.0)
        if draw_pct >= OUTER_DRAW_PERCENTILE:
            alternate = {
                **row,
                "draw_percentile": round(draw_pct, 4),
                "reason": "最高排名而未入Top4之外檔情境馬；檔位只係proxy，唔代表實際走外疊",
            }
            break
    applied = bias["status"] == "reverse_bias" and alternate is not None
    shadow_top4 = list(baseline)
    if applied and len(shadow_top4) == 4:
        shadow_top4[-1] = int(alternate["horse_number"])
    return {
        "race_number": race_no,
        "surface": item["surface"],
        "logic_sha256": item["sha256"],
        "bias": bias,
        "baseline_top4": baseline,
        "shadow_top4": shadow_top4,
        "alternate": alternate,
        "candidate_applied": applied,
        "live_score_changed": False,
    }


def build_snapshot(meeting_dir: Path, results_path: Path) -> dict:
    logic = load_logic(meeting_dir)
    if not logic:
        raise ValueError(f"no scored Race_*_Logic.json in {meeting_dir}")
    results = load_results(results_path)
    prefix = completed_prefix(results, logic)
    targets = []
    for race_no in sorted(logic):
        if race_no in prefix:
            continue
        bias = prior_bias(
            target_race=race_no,
            target_surface=logic[race_no]["surface"],
            prefix=prefix,
            results=results,
            logic=logic,
        )
        if bias["same_surface_races"] < MIN_PRIOR_SAME_SURFACE_RACES:
            continue
        targets.append(target_decision(race_no, logic[race_no], bias))
    material = {
        "contract_version": CONTRACT_VERSION,
        "meeting": meeting_dir.name,
        "results_sha256": _sha256(results_path),
        "completed_prefix": prefix,
        "targets": targets,
        "contract": {
            "mode": "prospective_shadow_only",
            "live_score_changed": False,
            "target_results_used": False,
            "minimum_prior_same_surface_races": MIN_PRIOR_SAME_SURFACE_RACES,
            "full_reliability_races": FULL_RELIABILITY_RACES,
            "reverse_threshold": REVERSE_THRESHOLD,
            "outer_draw_percentile": round(OUTER_DRAW_PERCENTILE, 6),
            "draw_is_only_a_proxy_for_lane": True,
            "actual_lane_observed": False,
            "sanitized_source_observations_persisted": True,
            "market_used": False,
            "official_top4_unchanged": True,
        },
    }
    snapshot_id = _canonical_hash(material)
    return {
        **material,
        "schema_version": 1,
        "snapshot_id": snapshot_id,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }


def persist_snapshot(snapshot: dict, snapshot_dir: Path) -> tuple[Path | None, bool]:
    if not snapshot["targets"]:
        return None, False
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    completed = max(snapshot["completed_prefix"], default=0)
    path = snapshot_dir / f"reverse_bias_after_R{completed}_{snapshot['snapshot_id'][:12]}.json"
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing.get("snapshot_id") != snapshot["snapshot_id"]:
            raise RuntimeError(f"immutable snapshot collision: {path}")
        return path, False
    with path.open("x", encoding="utf-8") as handle:
        json.dump(snapshot, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return path, True


def _find_results(meeting_dir: Path) -> Path | None:
    candidates = sorted(
        [*meeting_dir.glob("*全日賽果.json"), *meeting_dir.glob("full_day_results.json")],
        key=lambda path: (path.stat().st_mtime, path.name),
        reverse=True,
    )
    return candidates[0] if candidates else None


def _metric(top4: list[int], actual: dict[int, int]) -> dict:
    top3 = {horse for horse, position in actual.items() if position <= 3}
    return {
        "gold": float(bool(top3) and top3.issubset(set(top4))),
        "top3_capture_at4": float(len(top3 & set(top4)) / len(top3)) if top3 else 0.0,
    }


def settle(meeting_dir: Path, results_path: Path, snapshot_dir: Path) -> dict:
    results = load_results(results_path)
    snapshots = []
    for path in sorted(snapshot_dir.glob("reverse_bias_after_R*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if payload.get("contract_version") != CONTRACT_VERSION:
            continue
        completed = max(payload.get("completed_prefix") or [0])
        for target in payload.get("targets") or []:
            race_no = _int(target.get("race_number"))
            if race_no and race_no > completed:
                snapshots.append((race_no, completed, payload, target, path))
    latest: dict[int, tuple] = {}
    for item in snapshots:
        race_no, completed, *_rest = item
        if race_no not in latest or completed > latest[race_no][1]:
            latest[race_no] = item
    records = []
    for race_no, (_rn, completed, payload, target, path) in sorted(latest.items()):
        if race_no not in results or not target.get("candidate_applied"):
            continue
        actual = {}
        for row in results[race_no]["results"]:
            horse = _int(row.get("horse_no"))
            position = _int(row.get("pos"))
            if horse and position:
                actual[horse] = position
        baseline = [int(value) for value in target.get("baseline_top4") or []]
        candidate = [int(value) for value in target.get("shadow_top4") or []]
        records.append(
            {
                "race_number": race_no,
                "snapshot_id": payload["snapshot_id"],
                "snapshot_file": path.name,
                "observed_after_race": completed,
                "baseline_top4": baseline,
                "candidate_top4": candidate,
                "actual_top3": sorted(
                    (horse for horse, position in actual.items() if position <= 3),
                    key=lambda horse: actual[horse],
                ),
                "baseline": _metric(baseline, actual),
                "candidate": _metric(candidate, actual),
            }
        )
    return {
        "meeting": meeting_dir.name,
        "results_sha256": _sha256(results_path),
        "active_records": records,
    }


def update_ledger(ledger_path: Path, meeting_report: dict) -> dict:
    if ledger_path.exists():
        try:
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            ledger = {}
    else:
        ledger = {}
    ledger.setdefault("schema_version", 1)
    ledger.setdefault("contract_version", CONTRACT_VERSION)
    ledger.setdefault("meetings", {})
    ledger["meetings"][meeting_report["meeting"]] = meeting_report
    records = [
        row
        for meeting in ledger["meetings"].values()
        for row in meeting.get("active_records") or []
    ]
    baseline_gold = sum(row["baseline"]["gold"] for row in records)
    candidate_gold = sum(row["candidate"]["gold"] for row in records)
    baseline_capture = sum(row["baseline"]["top3_capture_at4"] for row in records)
    candidate_capture = sum(row["candidate"]["top3_capture_at4"] for row in records)
    count = len(records)
    ledger["summary"] = {
        "active_races": count,
        "minimum_active_races_for_review": MIN_ACTIVE_RACES_FOR_REVIEW,
        "status": "ready_for_locked_review" if count >= MIN_ACTIVE_RACES_FOR_REVIEW else "collecting",
        "baseline_gold_rate": round(baseline_gold / count, 6) if count else None,
        "candidate_gold_rate": round(candidate_gold / count, 6) if count else None,
        "baseline_top3_capture_at4": round(baseline_capture / count, 6) if count else None,
        "candidate_top3_capture_at4": round(candidate_capture / count, 6) if count else None,
        "auto_promotion": False,
    }
    ledger["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    _atomic_json(ledger_path, ledger)
    return ledger


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("meeting_dir", type=Path)
    parser.add_argument("--results-file", type=Path)
    parser.add_argument("--snapshot-dir", type=Path)
    parser.add_argument("--settle", action="store_true")
    parser.add_argument("--ledger", type=Path)
    args = parser.parse_args()

    meeting_dir = args.meeting_dir.resolve()
    snapshot_dir = args.snapshot_dir or meeting_dir / "Prediction_Snapshots" / "Reverse_Bias"
    results_path = args.results_file or _find_results(meeting_dir)
    if results_path is None or not results_path.exists():
        print(json.dumps({"status": "no_results", "meeting": meeting_dir.name}, ensure_ascii=False))
        return 0

    if args.settle:
        report = settle(meeting_dir, results_path, snapshot_dir)
        payload: dict[str, Any] = {"status": "settled", **report}
        if args.ledger:
            ledger = update_ledger(args.ledger, report)
            payload["ledger"] = str(args.ledger)
            payload["summary"] = ledger["summary"]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    snapshot = build_snapshot(meeting_dir, results_path)
    path, created = persist_snapshot(snapshot, snapshot_dir)
    risk_targets = [
        target for target in snapshot["targets"] if target["bias"]["status"] == "reverse_bias"
    ]
    print(
        json.dumps(
            {
                "status": "snapshot_created" if created else ("snapshot_reused" if path else "insufficient_evidence"),
                "meeting": meeting_dir.name,
                "snapshot": str(path) if path else None,
                "snapshot_id": snapshot["snapshot_id"] if path else None,
                "completed_prefix": snapshot["completed_prefix"],
                "target_count": len(snapshot["targets"]),
                "reverse_bias_targets": [target["race_number"] for target in risk_targets],
                "candidate_applied_races": [
                    target["race_number"] for target in risk_targets if target["candidate_applied"]
                ],
                "live_score_changed": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

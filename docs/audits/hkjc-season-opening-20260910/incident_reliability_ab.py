"""Point-in-time A/B for latest-run medical-incident reliability shadows.

Fixed arms (declared before measurement):
  M   replace the latest L400 with the median of chronology-verified prior runs;
  R   neutralise only correlated negative L400/energy/finish-time trend labels;
  M+R combine both changes.

The script never writes meeting/archive data.  Its only output is --out JSON.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [
    str(ROOT / ".agents/skills/hkjc_racing/hkjc_reflector/scripts"),
    str(ROOT / ".agents/skills/shared_racing"),
]

import pit_backtest as pit
import rescore_backtest as bt
from eval_metrics import race_metrics
from hkjc_racing_engine.engine_core import RacingEngine
from model_evaluation_decision import build_evaluation_input, evaluate_candidate


SNAPSHOTS = {
    "2026-09-06_ShaTin": "20260906T112332+1000",
    "2026-09-09_HappyValley": "20260909T111642+1000",
}
ARMS = {
    "baseline": None,
    "M": "incident_reliability_m",
    "R": "incident_reliability_r",
    "M+R": "incident_reliability",
}
METRIC_KEYS = (
    "gold",
    "good_positional",
    "champion",
    "top3_capture_at5",
    "mean_top3_model_rank",
    "competitive_recall_at5",
    "ndcg_at5",
)


def _rankings(logic: dict) -> tuple[dict[str, list[int]], list[dict]]:
    horses = logic.get("horses", {})
    race_context = logic.get("race_analysis", {})
    scores = {arm: {} for arm in ARMS}
    affected = []
    for horse_no, horse in horses.items():
        number = int(horse_no)
        auto = horse["python_auto"]
        scores["baseline"][number] = float(auto["ability_score_raw"])
        engine = RacingEngine(horse, race_context)
        horse_detail = {
            "horse_no": number,
            "horse_name": horse.get("horse_name", ""),
            "baseline_rank": int(auto.get("rank", 0) or 0),
            "baseline_ability_raw": float(auto["ability_score_raw"]),
            "medical_flags": (horse.get("_data") or {}).get("medical_flags", ""),
            "arms": {},
        }
        any_applied = False
        for arm, profile in ARMS.items():
            if profile is None:
                continue
            shadow = engine.build_shadow_profile(profile, base_auto=auto)
            scores[arm][number] = float(shadow["ability_score_raw"])
            horse_detail["arms"][arm] = {
                "applied": bool(shadow["applied"]),
                "ability_raw": float(shadow["ability_score_raw"]),
                "ability_delta_display": float(shadow["ability_delta"]),
                "sectional_delta": float(shadow["sectional_delta"]),
                "adjustments": shadow["adjustments"],
                "l400_context": shadow["l400_context"],
            }
            any_applied = any_applied or bool(shadow["applied"])
        if any_applied:
            affected.append(horse_detail)
    orders = {
        arm: sorted(values, key=lambda number: (-values[number], number))
        for arm, values in scores.items()
    }
    for horse in affected:
        number = horse["horse_no"]
        for arm in ARMS:
            horse["arms"].setdefault(arm, {})["rank"] = orders[arm].index(number) + 1
    return orders, affected


def _metrics(order: list[int], actual: dict[int, int]) -> dict:
    top3 = {horse for horse, position in actual.items() if position <= 3}
    winners = {horse for horse, position in actual.items() if position == 1}
    result = race_metrics(
        order,
        top3,
        winner=next(iter(winners), None),
        actual_pos=actual,
        field_size=len(actual),
    )
    return {
        "gold": result["gold"],
        "good_positional": result["good_positional"],
        "champion": result["champion"],
        "top3_capture_at5": result["top3_capture_at5"],
        "mean_top3_model_rank": result["top3_mean_model_rank"],
        "competitive_recall_at5": result["competitive_recall_at5"],
        "ndcg_at5": result["ndcg_at5"],
    }


def _race_record(meeting: str, race_no: int, logic: dict, actual: dict[int, int]) -> tuple[dict, list[dict]]:
    orders, affected = _rankings(logic)
    record = {
        "meeting": meeting,
        "date": meeting[:10],
        "venue": "HappyValley" if "HappyValley" in meeting else "ShaTin",
        "race": race_no,
        "field": len(actual),
        "metrics": {arm: _metrics(order, actual) for arm, order in orders.items()},
        "orders": orders,
    }
    for horse in affected:
        horse["finish"] = actual.get(horse["horse_no"])
        horse["meeting"] = meeting
        horse["race"] = race_no
    return record, affected


def _mean(values: list[float | bool | None]) -> float | None:
    usable = [float(value) for value in values if value is not None]
    return float(np.mean(usable)) if usable else None


def _summary(races: list[dict]) -> dict:
    return {
        arm: {
            "races": len(races),
            **{
                key: None if (value := _mean([race["metrics"][arm][key] for race in races])) is None else round(value, 6)
                for key in METRIC_KEYS
            },
        }
        for arm in ARMS
    }


def _folds(races: list[dict], terminal_dates: set[str]) -> list[dict]:
    dev_dates = sorted({race["date"] for race in races if race["date"] not in terminal_dates})
    chunks = [list(chunk) for chunk in np.array_split(dev_dates, 5) if len(chunk)]
    rows = []
    for index, dates in enumerate(chunks, start=1):
        selected = [race for race in races if race["date"] in set(dates)]
        rows.append({
            "fold": index,
            "dates": [str(date) for date in dates],
            "affected_races": sum(bool(race.get("affected")) for race in selected),
            "summary": _summary(selected),
        })
    return rows


def _stage4(races: list[dict], arm: str) -> dict:
    built = build_evaluation_input(
        domain="hkjc",
        dates=[race["date"] for race in races],
        baseline_rows=[race["metrics"]["baseline"] for race in races],
        candidate_rows=[race["metrics"][arm] for race in races],
        leakage_audit_passed=False,
        holdout_fraction=0.15,
        ranking_metrics=("top3_capture_at5", "mean_top3_model_rank", "competitive_recall_at5", "ndcg_at5"),
    )
    return {
        "verdict": evaluate_candidate(built),
        "evidence": {
            "primary": {key: dataclasses.asdict(value) for key, value in built.primary.items()},
            "ranking": {key: dataclasses.asdict(value) for key, value in built.ranking.items()},
            "sample_hash": built.baseline_sample_hash,
        },
    }


def _report(races: list[dict], affected: list[dict], *, immutable: bool) -> dict:
    unique_dates = sorted({race["date"] for race in races})
    terminal_count = max(1, math.ceil(len(unique_dates) * 0.15))
    terminal_dates = set(unique_dates[-terminal_count:])
    affected_keys = {(row["meeting"], row["race"]) for row in affected}
    for race in races:
        race["affected"] = (race["meeting"], race["race"]) in affected_keys
    dev = [race for race in races if race["date"] not in terminal_dates]
    terminal = [race for race in races if race["date"] in terminal_dates]
    affected_races = len(affected_keys)
    effective_n = affected_races
    return {
        "races": len(races),
        "dates": unique_dates,
        "immutable_prediction_source": immutable,
        "terminal_dates": sorted(terminal_dates),
        "coverage": {
            "affected_horses": len(affected),
            "affected_races": affected_races,
            "affected_development_races": sum((meeting, race) in affected_keys for meeting, race in {(r['meeting'], r['race']) for r in dev}),
            "affected_terminal_races": sum((meeting, race) in affected_keys for meeting, race in {(r['meeting'], r['race']) for r in terminal}),
            "effective_n": effective_n,
            "binary_80pct_power_mde": None if not effective_n else round(2.80 / math.sqrt(effective_n), 4),
            "power_note": "MDE is the conservative paired-binary effect among races capable of changing; values above 1.0 are unattainable.",
        },
        "summary": {
            "all": _summary(races),
            "development": _summary(dev),
            "terminal": _summary(terminal),
            "ShaTin": _summary([race for race in races if race["venue"] == "ShaTin"]),
            "HappyValley": _summary([race for race in races if race["venue"] == "HappyValley"]),
        },
        "development_folds": _folds(races, terminal_dates),
        "stage4": {arm: _stage4(races, arm) for arm in ARMS if arm != "baseline"},
        "affected_horses": affected,
        "races_detail": races,
    }


def _load_opening(data_root: Path) -> tuple[list[dict], list[dict], list[dict]]:
    races, affected, manifest = [], [], []
    for meeting, snapshot in SNAPSHOTS.items():
        meeting_dir = data_root / meeting
        results = bt.load_results(bt.find_results_json(meeting_dir))
        snapshot_dir = meeting_dir / "Prediction_Snapshots" / snapshot
        for logic_path in sorted(snapshot_dir.glob("Race_*_Logic.json"), key=bt.race_num_from_path):
            race_no = bt.race_num_from_path(logic_path)
            logic = json.loads(logic_path.read_text(encoding="utf-8"))
            record, rows = _race_record(meeting, race_no, logic, results[race_no])
            races.append(record)
            affected.extend(rows)
            manifest.append({"path": str(logic_path), "sha256": hashlib.sha256(logic_path.read_bytes()).hexdigest()})
    return races, affected, manifest


def _load_archive(data_root: Path) -> tuple[list[dict], list[dict], list[dict], list[str]]:
    races, affected, manifest, errors = [], [], [], []
    all_rows = pit.load_all_rows()
    for meeting_dir in sorted(data_root.iterdir()):
        if not meeting_dir.is_dir() or not meeting_dir.name.startswith("2026-") or meeting_dir.name[:10] >= "2026-09-01":
            continue
        results_path = bt.find_results_json(meeting_dir)
        if not results_path or bt.meeting_is_legacy_schema(meeting_dir):
            continue
        results = bt.load_results(results_path)
        pit.inject_as_of(all_rows, meeting_dir.name[:10])
        for logic_path in sorted(meeting_dir.glob("Race_*_Logic.json"), key=bt.race_num_from_path):
            race_no = bt.race_num_from_path(logic_path)
            if race_no not in results:
                continue
            try:
                logic = json.loads(logic_path.read_text(encoding="utf-8"))
                bt.resolve_meeting_context(logic, meeting_dir)
                rescored = bt.rescore_logic(logic)
                record, rows = _race_record(meeting_dir.name, race_no, rescored, results[race_no])
            except Exception as exc:
                errors.append(f"{logic_path}: {exc}")
                continue
            races.append(record)
            affected.extend(rows)
            manifest.append({"path": str(logic_path), "sha256": hashlib.sha256(logic_path.read_bytes()).hexdigest()})
        print(meeting_dir.name, flush=True)
    return races, affected, manifest, errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    data_root = Path((ROOT / ".wongchoi_hk_data_root").read_text(encoding="utf-8").strip())
    opening_races, opening_affected, opening_manifest = _load_opening(data_root)
    archive_races, archive_affected, archive_manifest, errors = _load_archive(data_root)
    payload = {
        "experiment": "incident_reliability_M_R_M+R",
        "promotion_safe": False,
        "promotion_blockers": [
            "historical affected cases are concentrated on one date",
            "historical Logic files lack immutable pre-race snapshot provenance",
            "2026-09-06 and 2026-09-09 outcomes were already observed before this hypothesis test",
        ],
        "archive": _report(archive_races, archive_affected, immutable=False),
        "opening_observed_diagnostic": _report(opening_races, opening_affected, immutable=True),
        "errors": errors,
        "manifest": {"archive": archive_manifest, "opening": opening_manifest},
    }
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "archive_races": len(archive_races),
        "archive_affected": len(archive_affected),
        "opening_races": len(opening_races),
        "opening_affected": len(opening_affected),
        "errors": len(errors),
    }, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

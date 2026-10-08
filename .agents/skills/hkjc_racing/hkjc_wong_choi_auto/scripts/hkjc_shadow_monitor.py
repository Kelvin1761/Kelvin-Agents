#!/usr/bin/env python3
"""Settle frozen HKJC prospective shadows against official results.

Predictions are read only from the immutable pre-race snapshot.  Results are
joined afterwards and can never flow back into scoring.  Reruns upsert the same
meeting/race/profile key, making the ledger deterministic and restart-safe.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[5]
SHARED_RACING = PROJECT_ROOT / ".agents" / "skills" / "shared_racing"

if str(SHARED_RACING) not in sys.path:
    sys.path.insert(0, str(SHARED_RACING))

from eval_metrics import race_metrics  # noqa: E402


PROFILE_MINIMUMS = {
    "weight_refit_t02": 120,
    "race_shape_v3_hv": 80,
    "race_shape_v3_hv_t02": 80,
    "race_shape_v2_legacy_hv": 20,
    "race_shape_st_draw70": 80,
    "race_shape_legacy_unbounded": 80,
    "trainer_recency_st_early90": 80,
    "pre_race_draw_context_v2": 80,
    "pre_race_draw_context_v1_generic": 20,
}
METRICS = (
    "gold",
    "good",
    "champion",
    "top3_capture_at5",
    "competitive_recall_at5",
    "ndcg_at5",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _latest_snapshot(meeting_dir: Path) -> tuple[Path, dict[str, Any]]:
    manifests = sorted((meeting_dir / "Prediction_Snapshots").glob("*/manifest.json"))
    if not manifests:
        raise RuntimeError("immutable prediction snapshot missing")
    manifest_path = manifests[-1]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("immutable_prediction_snapshot") is not True:
        raise RuntimeError("prediction snapshot is not marked immutable")
    expected = {
        str(row.get("name")): str(row.get("sha256"))
        for row in manifest.get("files", [])
        if isinstance(row, dict)
    }
    for logic_path in sorted(manifest_path.parent.glob("Race_*_Logic.json")):
        if expected.get(logic_path.name) != _sha256(logic_path):
            raise RuntimeError(f"snapshot hash mismatch: {logic_path.name}")
    return manifest_path.parent, manifest


def _results_file(meeting_dir: Path) -> Path:
    files = sorted(meeting_dir.glob("*全日賽果.json"))
    if not files:
        raise RuntimeError("official results file missing")
    return files[-1]


def _load_results(path: Path) -> dict[str, dict[int, int]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    races: dict[str, dict[int, int]] = {}
    for race_no, race in payload.items():
        positions: dict[int, int] = {}
        for item in (race or {}).get("results", []):
            try:
                horse = int(item.get("horse_no"))
                position = int(item.get("pos"))
            except (TypeError, ValueError):
                continue
            if horse > 0 and position > 0:
                positions[horse] = position
        if sum(position <= 3 for position in positions.values()) >= 3:
            races[str(race_no)] = positions
    return races


def _ranking(verdict: dict[str, Any]) -> list[int]:
    ranked = []
    for item in verdict.get("ranking", []):
        try:
            ranked.append(int(item.get("horse_number")))
        except (TypeError, ValueError):
            continue
    return ranked


def _metrics(picks: list[int], actual_pos: dict[int, int]) -> dict[str, float]:
    actual_top3 = {horse for horse, position in actual_pos.items() if position <= 3}
    winner = next((horse for horse, position in actual_pos.items() if position == 1), None)
    canonical = race_metrics(
        picks,
        actual_top3,
        winner=winner,
        actual_pos=actual_pos,
        field_size=len(actual_pos),
    )
    return {
        "gold": float(actual_top3.issubset(set(picks[:4]))),
        "good": float(len(picks) >= 2 and picks[0] in actual_top3 and picks[1] in actual_top3),
        "champion": float(bool(picks) and picks[0] == winner),
        "top3_capture_at5": float(canonical.get("top3_capture_at5") or 0.0),
        "competitive_recall_at5": float(canonical.get("competitive_recall_at5") or 0.0),
        "ndcg_at5": float(canonical.get("ndcg_at5") or 0.0),
    }


def settle_meeting(meeting_dir: Path) -> list[dict[str, Any]]:
    snapshot_dir, manifest = _latest_snapshot(meeting_dir)
    result_path = _results_file(meeting_dir)
    results = _load_results(result_path)
    rows: list[dict[str, Any]] = []
    for logic_path in sorted(snapshot_dir.glob("Race_*_Logic.json")):
        logic = json.loads(logic_path.read_text(encoding="utf-8"))
        race_context = logic.get("race_analysis") or {}
        race_no = str(race_context.get("race_number") or "")
        actual_pos = results.get(race_no)
        if not actual_pos:
            continue
        mainline = _ranking(logic.get("python_auto_verdict") or {})
        if not mainline:
            continue
        baseline_metrics = _metrics(mainline, actual_pos)
        for profile, verdict in (logic.get("python_auto_shadow_verdicts") or {}).items():
            if profile not in PROFILE_MINIMUMS:
                continue
            candidate = _ranking(verdict or {})
            if not candidate:
                continue
            candidate_metrics = _metrics(candidate, actual_pos)
            active = any(bool(item.get("applied")) for item in (verdict or {}).get("ranking", []))
            rows.append(
                {
                    "key": f"{meeting_dir.name}::{race_no}::{profile}",
                    "meeting": meeting_dir.name,
                    "race_number": int(race_no),
                    "venue": str(race_context.get("venue") or race_context.get("course") or ""),
                    "track": str(race_context.get("track") or race_context.get("surface") or ""),
                    "profile": profile,
                    "profile_applied": active,
                    "snapshot": snapshot_dir.name,
                    "snapshot_created_at": manifest.get("created_at"),
                    "snapshot_signature": manifest.get("signature"),
                    "results_file": result_path.name,
                    "mainline_picks": mainline,
                    "candidate_picks": candidate,
                    "actual_positions": {str(key): value for key, value in actual_pos.items()},
                    "baseline": baseline_metrics,
                    "candidate": candidate_metrics,
                    "delta": {
                        metric: round(candidate_metrics[metric] - baseline_metrics[metric], 8)
                        for metric in METRICS
                    },
                }
            )
    return rows


def _mean(rows: list[dict[str, Any]], section: str, metric: str) -> float:
    return sum(float(row[section][metric]) for row in rows) / len(rows) if rows else 0.0


def _is_happy_valley(row: dict[str, Any]) -> bool:
    text = f"{row.get('venue', '')} {row.get('meeting', '')}"
    return any(token in text for token in ("HV", "HappyValley", "Happy Valley", "跑馬地"))


def _is_sha_tin_turf(row: dict[str, Any]) -> bool:
    text = f"{row.get('venue', '')} {row.get('meeting', '')}"
    track = str(row.get("track", "")).upper()
    is_st = any(token in text for token in ("ST", "ShaTin", "Sha Tin", "沙田"))
    is_awt = any(token in track for token in ("AWT", "ALL WEATHER", "全天候", "泥地"))
    return is_st and bool(track.strip()) and not is_awt


def _is_sha_tin_awt(row: dict[str, Any]) -> bool:
    text = f"{row.get('venue', '')} {row.get('meeting', '')}"
    track = str(row.get("track", "")).upper()
    is_st = any(token in text for token in ("ST", "ShaTin", "Sha Tin", "沙田"))
    return is_st and any(token in track for token in ("AWT", "ALL WEATHER", "全天候", "泥地"))


def _metric_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "races": len(rows),
        "metrics": {
            metric: {
                "baseline": round(_mean(rows, "baseline", metric), 8),
                "candidate": round(_mean(rows, "candidate", metric), 8),
                "delta": round(
                    _mean(rows, "candidate", metric) - _mean(rows, "baseline", metric),
                    8,
                ),
            }
            for metric in METRICS
        },
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for profile, minimum in PROFILE_MINIMUMS.items():
        profile_rows = [row for row in rows if row.get("profile") == profile]
        active_rows = [row for row in profile_rows if row.get("profile_applied")]
        if profile in {"race_shape_v3_hv", "race_shape_v3_hv_t02", "race_shape_v2_legacy_hv"}:
            active_rows = [row for row in active_rows if _is_happy_valley(row)]
        elif profile in {"race_shape_st_draw70", "trainer_recency_st_early90"}:
            active_rows = [row for row in active_rows if _is_sha_tin_turf(row)]
        metrics = {}
        for metric in METRICS:
            baseline = _mean(active_rows, "baseline", metric)
            candidate = _mean(active_rows, "candidate", metric)
            metrics[metric] = {
                "baseline": round(baseline, 8),
                "candidate": round(candidate, 8),
                "delta": round(candidate - baseline, 8),
            }
        rollback_gate = None
        if profile in {
            "race_shape_legacy_unbounded",
        }:
            gold_net = sum(float(row["delta"]["gold"]) for row in active_rows)
            good_net = sum(float(row["delta"]["good"]) for row in active_rows)
            trigger = (
                len(active_rows) >= minimum
                and gold_net >= 2.0
                and good_net >= 0.0
            ) or (
                len(active_rows) >= minimum
                and good_net >= 2.0
                and gold_net >= 0.0
            )
            rollback_gate = {
                "status": "recommend_rollback" if trigger else "retain_experimental_live",
                "gold_net_races_legacy_minus_live": round(gold_net, 4),
                "good_net_races_legacy_minus_live": round(good_net, 4),
                "rule": "at least 80 active races; legacy gains >=2 Gold or Good with the other primary nonnegative",
                "automatic_activation": False,
            }
        summary[profile] = {
            "races": len(profile_rows),
            "active_races": len(active_rows),
            "minimum_active_races": minimum,
            "status": "ready_for_locked_review" if len(active_rows) >= minimum else "collecting",
            "metrics": metrics,
            "promotion_blocked": True,
            "promotion_rule": "Stage-4 v2 review plus paired race bootstrap; never auto-promote",
            "decision_role": (
                "rollback_comparator"
                if profile == "race_shape_v2_legacy_hv"
                else "sha_tin_forward_candidate" if profile == "race_shape_st_draw70"
                else "whole_field_robustness_rollback_comparator"
                if profile == "race_shape_legacy_unbounded"
                else "sha_tin_early_season_trainer_candidate"
                if profile == "trainer_recency_st_early90"
                else "all_turf_pre_race_draw_candidate"
                if profile == "pre_race_draw_context_v2"
                else "rail_draw_v1_rollback_comparator"
                if profile == "pre_race_draw_context_v1_generic"
                else "candidate"
            ),
            "cohorts": {
                "sha_tin_turf": _metric_summary([row for row in active_rows if _is_sha_tin_turf(row)]),
                "sha_tin_awt": _metric_summary([row for row in active_rows if _is_sha_tin_awt(row)]),
                "happy_valley": _metric_summary([row for row in active_rows if _is_happy_valley(row)]),
            },
            "rollback_gate": rollback_gate,
        }
    return summary


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            temporary = Path(handle.name)
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def update_ledger(meeting_dir: Path, ledger_path: Path) -> dict[str, Any]:
    new_rows = settle_meeting(meeting_dir)
    if ledger_path.exists():
        payload = json.loads(ledger_path.read_text(encoding="utf-8"))
    else:
        payload = {"schema_version": 1, "rows": []}
    indexed = {
        str(row.get("key")): row
        for row in payload.get("rows", [])
        if isinstance(row, dict) and row.get("key")
    }
    for row in new_rows:
        indexed[row["key"]] = row
    rows = [indexed[key] for key in sorted(indexed)]
    output = {
        "schema_version": 2,
        "contract": "HKJC_20260929_HV_V3_LIVE_ROLLBACK_AND_WEIGHT_SHADOW",
        "rows": rows,
        "summary": summarize(rows),
    }
    _atomic_write(ledger_path, output)
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("meeting_dir")
    parser.add_argument("--ledger", required=True)
    args = parser.parse_args()
    payload = update_ledger(Path(args.meeting_dir).resolve(), Path(args.ledger).resolve())
    print(json.dumps(payload["summary"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
HK_REFLECTOR_DIR = ROOT / ".agents" / "skills" / "hkjc_racing" / "hkjc_reflector" / "scripts"
AU_REFLECTOR_SCRIPT = ROOT / ".agents" / "scripts" / "reflector_auto_stats.py"
OBSERVABILITY_VERSION = "WONG_CHOI_OBSERVABILITY_V1"
DEFAULT_SCORING_PROFILE = "baseline"


def compute_file_hash(path: Path | str | None) -> str | None:
    if not path:
        return None
    resolved = Path(path)
    if not resolved.exists() or not resolved.is_file():
        return None
    digest = hashlib.sha256()
    with resolved.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def start_run(
    meeting_dir: Path | str,
    platform: str,
    *,
    scoring_profile: str = DEFAULT_SCORING_PROFILE,
    run_id: str | None = None,
    pipeline_version: str = OBSERVABILITY_VERSION,
    metadata: dict[str, Any] | None = None,
) -> str:
    target_dir = Path(meeting_dir).resolve()
    resolved_run_id = run_id or _generate_run_id(platform, target_dir, scoring_profile)
    record = _base_record(
        target_dir,
        platform,
        resolved_run_id,
        event_type="run_started",
        scoring_profile=scoring_profile,
        race_no=None,
        pipeline_version=pipeline_version,
    )
    if metadata:
        record["metadata"] = metadata
    _append_record(target_dir, record)
    return resolved_run_id


def log_race(
    meeting_dir: Path | str,
    platform: str,
    run_id: str,
    *,
    race_no: int | None = None,
    event_type: str = "race_processed",
    scoring_profile: str = DEFAULT_SCORING_PROFILE,
    validation_flags: list[str] | None = None,
    stage: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    target_dir = Path(meeting_dir).resolve()
    record = _base_record(
        target_dir,
        platform,
        run_id,
        event_type=event_type,
        scoring_profile=scoring_profile,
        race_no=race_no,
    )
    if validation_flags:
        record["validation_flags"] = sorted(set(validation_flags))
    if stage:
        record["stage"] = stage
    if payload:
        record.update(payload)
    return _append_record(target_dir, record)


def log_horse_score(
    meeting_dir: Path | str,
    platform: str,
    run_id: str,
    *,
    race_no: int,
    horse_no: str | int,
    horse_name: str,
    python_auto: dict[str, Any],
    facts_path: Path | str | None,
    logic_path: Path | str | None,
    scoring_profile: str = DEFAULT_SCORING_PROFILE,
    validation_flags: list[str] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    target_dir = Path(meeting_dir).resolve()
    derived_flags = list(validation_flags or [])
    derived_flags.extend(build_validation_flags(python_auto, facts_path=facts_path, logic_path=logic_path))
    record = _base_record(
        target_dir,
        platform,
        run_id,
        event_type="horse_scored",
        scoring_profile=scoring_profile,
        race_no=race_no,
    )
    record.update(
        {
            "horse_no": str(horse_no),
            "horse_name": horse_name,
            "facts_path": str(Path(facts_path).resolve()) if facts_path else None,
            "logic_path": str(Path(logic_path).resolve()) if logic_path else None,
            "facts_hash": compute_file_hash(facts_path),
            "logic_hash": compute_file_hash(logic_path),
            "engine_version": python_auto.get("version"),
            "ability_score": python_auto.get("ability_score"),
            "rank_score": python_auto.get("rank_score", python_auto.get("ability_score")),
            "rank": python_auto.get("rank"),
            "grade": python_auto.get("grade"),
            "feature_scores": python_auto.get("feature_scores", {}),
            "matrix_scores": python_auto.get("matrix_scores", {}),
            "matrix_reasoning": python_auto.get("matrix_reasoning", {}),
            "risk_flags": python_auto.get("risk_flags", []),
            "reason_codes": python_auto.get("reason_codes", []),
            "score_provenance": python_auto.get("score_provenance", {}),
            "validation_flags": sorted(set(flag for flag in derived_flags if flag)),
        }
    )
    if extra:
        record.update(extra)
    return _append_record(target_dir, record)


def log_validation(
    meeting_dir: Path | str,
    platform: str,
    run_id: str,
    *,
    message: str,
    race_no: int | None = None,
    horse_no: str | int | None = None,
    code: str | None = None,
    scoring_profile: str = DEFAULT_SCORING_PROFILE,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    target_dir = Path(meeting_dir).resolve()
    record = _base_record(
        target_dir,
        platform,
        run_id,
        event_type="validation_warning",
        scoring_profile=scoring_profile,
        race_no=race_no,
    )
    record["message"] = message
    if code:
        record["code"] = code
    if horse_no is not None:
        record["horse_no"] = str(horse_no)
    if details:
        record["details"] = details
    return _append_record(target_dir, record)


def finalize_run(
    meeting_dir: Path | str,
    platform: str,
    run_id: str,
    *,
    status: str,
    scoring_profile: str = DEFAULT_SCORING_PROFILE,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    stage_payload = {"status": status}
    if payload:
        stage_payload.update(payload)
    return log_race(
        meeting_dir,
        platform,
        run_id,
        event_type="stage_completed",
        stage="run_finalized",
        scoring_profile=scoring_profile,
        payload=stage_payload,
    )


def attach_results_and_evaluate(
    meeting_dir: Path | str,
    platform: str,
    *,
    run_id: str | None = None,
    scoring_profile: str = DEFAULT_SCORING_PROFILE,
) -> dict[str, Any] | None:
    target_dir = Path(meeting_dir).resolve()
    log_path = target_dir / "racing_run_log.jsonl"
    if not log_path.exists():
        return None

    events = load_events(log_path, run_id=run_id)
    if not events:
        return None

    resolved_run_id = run_id or events[-1]["run_id"]
    results_file, report = _load_results_report(target_dir, platform)
    if not results_file:
        log_validation(
            target_dir,
            platform,
            resolved_run_id,
            message="Results file not found; evaluation skipped.",
            code="RESULTS_NOT_FOUND",
            scoring_profile=scoring_profile,
        )
        return None

    if not report or "summary" not in report:
        log_validation(
            target_dir,
            platform,
            resolved_run_id,
            message="Reflector stats report is unavailable; evaluation skipped.",
            code="EVALUATION_UNAVAILABLE",
            scoring_profile=scoring_profile,
            details={"results_file": str(results_file)},
        )
        return None

    log_race(
        target_dir,
        platform,
        resolved_run_id,
        event_type="results_joined",
        scoring_profile=scoring_profile,
        payload={"results_file": str(results_file.resolve())},
    )

    summary = report["summary"]
    evaluation = {
        "run_id": resolved_run_id,
        "platform": platform,
        "meeting_dir": str(target_dir),
        "generated_at": _timestamp(),
        "scoring_profile": scoring_profile,
        "results_file": str(results_file.resolve()),
        "kpis": {
            "gold": dict(summary.get("position_hit_rates", {}).get("gold_standard", {})),
            "good": dict(summary.get("position_hit_rates", {}).get("good_result", {})),
            "pass": dict(summary.get("position_hit_rates", {}).get("min_threshold", {})),
            "top1_hit": dict(summary.get("champion_hit_rates", {}).get("top1_champion", {})),
            "top3_contains_winner": dict(summary.get("champion_hit_rates", {}).get("top3_has_champ", {})),
            "pick34_overtake_12": dict(summary.get("ranking_order", {}).get("pick34_beat_12", {})),
        },
        "event_counts": dict(Counter(event.get("event_type") for event in events)),
        "race_count": len({event.get("race_no") for event in events if event.get("race_no") is not None}),
        "horse_scored_count": sum(1 for event in events if event.get("event_type") == "horse_scored"),
        "races": report.get("races", []),
        "false_positives": summary.get("false_positives", []),
        "false_negatives": summary.get("false_negatives", []),
    }
    output_path = target_dir / "evaluation_summary.json"
    _atomic_write_json(output_path, evaluation)

    log_race(
        target_dir,
        platform,
        resolved_run_id,
        event_type="evaluation_completed",
        scoring_profile=scoring_profile,
        payload={
            "evaluation_summary_path": str(output_path.resolve()),
            "results_file": str(results_file.resolve()),
            "gold_rate": evaluation["kpis"]["gold"].get("rate"),
            "good_rate": evaluation["kpis"]["good"].get("rate"),
            "pass_rate": evaluation["kpis"]["pass"].get("rate"),
        },
    )
    return evaluation


def load_events(log_path: Path | str, *, run_id: str | None = None) -> list[dict[str, Any]]:
    resolved = Path(log_path)
    if not resolved.exists():
        return []
    records: list[dict[str, Any]] = []
    with resolved.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if run_id and record.get("run_id") != run_id:
                continue
            records.append(record)
    return records


def build_validation_flags(
    python_auto: dict[str, Any],
    *,
    facts_path: Path | str | None = None,
    logic_path: Path | str | None = None,
) -> list[str]:
    flags: list[str] = []
    if not facts_path or not Path(facts_path).exists():
        flags.append("missing_facts_file")
    if not logic_path or not Path(logic_path).exists():
        flags.append("missing_logic_file")
    if not python_auto.get("feature_scores"):
        flags.append("missing_feature_scores")
    if not python_auto.get("matrix_scores"):
        flags.append("missing_matrix_scores")
    if not python_auto.get("matrix_reasoning"):
        flags.append("missing_matrix_reasoning")
    if not python_auto.get("score_provenance"):
        flags.append("missing_score_provenance")
    if python_auto.get("rank") in (None, ""):
        flags.append("missing_rank")
    if not python_auto.get("grade"):
        flags.append("missing_grade")
    if _has_out_of_range_scores(python_auto.get("feature_scores", {})):
        flags.append("feature_score_out_of_range")
    if _has_out_of_range_scores(python_auto.get("matrix_scores", {})):
        flags.append("matrix_score_out_of_range")
    return sorted(set(flags))


def _load_results_report(meeting_dir: Path, platform: str) -> tuple[Path | None, dict[str, Any] | None]:
    if platform.upper() == "HKJC":
        results_file = _find_hkjc_results_file(meeting_dir)
        if not results_file:
            return None, None
        module = _load_module("hkjc_reflector_auto_stats", HK_REFLECTOR_DIR / "reflector_auto_stats.py")
        return results_file, module.run_stats(str(meeting_dir), str(results_file))

    results_file = _find_au_results_file(meeting_dir)
    if not results_file:
        return None, None
    module = _load_module("shared_reflector_auto_stats", AU_REFLECTOR_SCRIPT)
    return results_file, module.run_stats(str(meeting_dir), str(results_file))


def _find_hkjc_results_file(meeting_dir: Path) -> Path | None:
    module = _load_module("hkjc_results_db_observability", HK_REFLECTOR_DIR / "hkjc_results_db.py")
    return module.find_meeting_results_file(meeting_dir, module.get_season_results_roots())


def _find_au_results_file(meeting_dir: Path) -> Path | None:
    md_results = sorted(meeting_dir.glob("Race_Results_Reflector.md"))
    if md_results:
        return md_results[0]
    json_results = sorted(meeting_dir.glob("Race_Results_*.json"))
    return json_results[0] if json_results else None


def _append_record(meeting_dir: Path, record: dict[str, Any]) -> dict[str, Any]:
    log_path = meeting_dir / "racing_run_log.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def _base_record(
    meeting_dir: Path,
    platform: str,
    run_id: str,
    *,
    event_type: str,
    scoring_profile: str,
    race_no: int | None,
    pipeline_version: str | None = None,
) -> dict[str, Any]:
    record = {
        "timestamp": _timestamp(),
        "event_type": event_type,
        "run_id": run_id,
        "platform": platform,
        "meeting_dir": str(meeting_dir),
        "race_no": race_no,
        "scoring_profile": scoring_profile,
    }
    if pipeline_version:
        record["pipeline_version"] = pipeline_version
    return record


def _generate_run_id(platform: str, meeting_dir: Path, scoring_profile: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", meeting_dir.name).strip("-") or "meeting"
    profile_slug = re.sub(r"[^A-Za-z0-9._-]+", "-", scoring_profile).strip("-") or DEFAULT_SCORING_PROFILE
    return f"{stamp}_{platform.upper()}_{slug}_{profile_slug}"


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    temp_path = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp_path, path)


def _has_out_of_range_scores(scores: dict[str, Any]) -> bool:
    for value in scores.values():
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            continue
        if numeric < 0 or numeric > 100:
            return True
    return False


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

#!/usr/bin/env python3
"""Unattended-safe scheduler around the canonical NBA Wong Choi orchestrator.

This file owns scheduling, idempotency, immutable snapshots, post-game review,
health and deployment.  It deliberately does not implement prediction logic.
"""
from __future__ import annotations

import argparse
import csv
import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[3]
NBA_SKILL = HERE.parent
ORCHESTRATOR = NBA_SKILL / "nba_orchestrator.py"
REVIEW_ARCHIVE = (
    NBA_SKILL / "nba_reflector" / "scripts" / "nba_daily_review_archive.py"
)
LOG_DIR = HERE / "logs"
STATE_DIR = HERE / "state"
NOTIFICATION_STATE = STATE_DIR / "telegram_notifications.json"
SYDNEY = ZoneInfo("Australia/Sydney")
TEMPORARY_FAILURE = 75

sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(NBA_SKILL))
from nba_schedule import canonical_game_tag, load_espn_events, load_espn_schedule  # noqa: E402
from nba_season import classify_nba_season  # noqa: E402
from wongchoi_paths import NBA_ANALYSIS  # noqa: E402

HOOK_DIR = (
    PROJECT_ROOT
    / ".agents"
    / "skills"
    / "shared_racing"
    / "post_success_hooks"
    / "scripts"
)
SHARED_DIR = PROJECT_ROOT / ".agents" / "skills" / "shared_racing" / "scripts"
sys.path.insert(0, str(HOOK_DIR))
sys.path.insert(0, str(SHARED_DIR))
from cloudflare_deploy_hook import run_post_success_cloudflare_deploy  # noqa: E402
from racing_telegram import send_message  # noqa: E402

DASHBOARD_BACKEND = PROJECT_ROOT / "Horse_Racing_Dashboard" / "backend"
sys.path.insert(0, str(DASHBOARD_BACKEND))
from services.multisport_exporter import export_nba_snapshot  # noqa: E402

SHARED_WC_DIR = PROJECT_ROOT / ".agents" / "skills"
sys.path.insert(0, str(SHARED_WC_DIR))
from shared_wong_choi.schedule_policy import (  # noqa: E402
    FreshnessRole,
    nba_pregame_role,
)

CLAW_SPORTSBET = (
    NBA_SKILL / "nba_data_extractor" / "scripts" / "claw_sportsbet_odds.py"
)


class TemporaryFailure(RuntimeError):
    """A retryable source/deploy/results failure."""


class RunLog:
    def __init__(self, mode: str, target_date: str) -> None:
        now = datetime.now(SYDNEY)
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        self.path = LOG_DIR / f"run-{now:%Y%m%d-%H%M%S}-{mode}.json"
        self.payload: dict[str, Any] = {
            "task_name": "nba-wong-choi-daily",
            "mode": mode,
            "target_date": target_date,
            "timezone": "Australia/Sydney",
            "started_at": now.isoformat(),
            "completed_at": None,
            "status": "running",
            "steps": [],
            "errors": [],
            "warnings": [],
        }
        self.write()

    def step(self, name: str, status: str, **detail: Any) -> None:
        self.payload["steps"].append(
            {"step": name, "status": status, "at": datetime.now(SYDNEY).isoformat(), **detail}
        )
        self.write()

    def finish(self, status: str, **detail: Any) -> None:
        self.payload.update(detail)
        self.payload["status"] = status
        self.payload["completed_at"] = datetime.now(SYDNEY).isoformat()
        self.write()

    def write(self) -> None:
        temp = self.path.with_suffix(".tmp")
        temp.write_text(
            json.dumps(self.payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temp.replace(self.path)


def now_sydney() -> datetime:
    return datetime.now(SYDNEY)


def pregame_target(now: datetime) -> date:
    """Evening runs warm tomorrow; midnight/morning runs cover today."""
    return now.date() + timedelta(days=1) if now.timetz().replace(tzinfo=None) >= time(12) else now.date()


def live_dir(target_date: str) -> Path:
    return PROJECT_ROOT / f"{target_date} NBA Analysis"


def archived_dirs(target_date: str) -> list[Path]:
    if not NBA_ANALYSIS.is_dir():
        return []
    return sorted(NBA_ANALYSIS.glob(f"{target_date} NBA Analysis*"))


def _run(command: list[str], *, timeout: int = 3600) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        timeout=timeout,
        env=os.environ.copy(),
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temp.replace(path)


def notify_once(key: str, message: str, *, audience: str = "primary") -> dict[str, Any]:
    """Send one Telegram notification once; failed sends remain retryable."""
    state = _read_json(NOTIFICATION_STATE, {})
    if not isinstance(state, dict):
        state = {}
    if key in state:
        return {"ok": True, "status": "duplicate_skipped", "key": key}

    result = send_message(message, audience=audience)
    if isinstance(result, dict) and result.get("ok") and result.get("status") == "sent":
        state[key] = {
            "audience": audience,
            "sent_at": datetime.now(SYDNEY).isoformat(),
            "status": result.get("status") or "sent",
        }
        _write_json(NOTIFICATION_STATE, state)
    return result if isinstance(result, dict) else {"ok": False, "status": "invalid_result"}


def _pct(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "N/A"
    if abs(number) > 1:
        number /= 100
    return f"{number:.1%}"


def _odds(value: Any) -> str:
    try:
        return f"@{float(value):.2f}"
    except (TypeError, ValueError):
        return "@N/A"


def nba_betting_message(target_date: str, snapshot: dict[str, Any]) -> str:
    """Render a Telegram card from the validated Dashboard NBA contract only."""
    status = str(snapshot.get("validation_status") or "unavailable")
    warnings = [str(value) for value in snapshot.get("warnings") or []]
    recommendations = [
        row
        for row in snapshot.get("recommendations") or []
        if isinstance(row, dict)
        and row.get("decision") == "BET"
        and row.get("validation_status") == "valid"
    ]
    safe_no_bet = (
        not recommendations
        and status == "blocked"
        and bool(warnings)
        and set(warnings) <= {"no_validated_nba_combos"}
    )
    if status != "valid" and not safe_no_bet:
        raise ValueError(f"telegram_betting_card_blocked:{status}:{','.join(warnings)}")
    if status == "valid" and not recommendations:
        raise ValueError("telegram_betting_card_blocked:valid:no_valid_bet_rows")

    if safe_no_bet:
        return (
            f"🏀 NBA 旺財投注卡｜{target_date}\n"
            "⛔ 今日 NO BET\n"
            "原因：正式分析未有通過全部驗證嘅 NBA 組合。\n"
            "紀律：唔為咗有飛而降低門檻。"
        )

    bankers = [row for row in recommendations if row.get("category") == "banker"]
    combos = [row for row in recommendations if row.get("bet_type") == "combo"]
    lines = [f"🏀 NBA 旺財投注卡｜{target_date}", "✅ 只列已驗證 BET"]
    for row in bankers:
        metrics = row.get("metrics") or {}
        lines.extend(
            [
                "",
                f"🛡️ Banker｜{row.get('event_name') or 'NBA'}",
                f"{row.get('selection') or 'N/A'} {_odds(row.get('odds'))}",
                (
                    f"模型命中率 {_pct(metrics.get('model_probability'))}｜"
                    f"Edge {_pct(metrics.get('edge'))}｜EV {_pct(metrics.get('expected_value'))}"
                ),
            ]
        )
    for row in combos:
        metrics = row.get("metrics") or {}
        lines.extend(
            [
                "",
                f"🎰 SGM｜{row.get('event_name') or 'NBA'}｜{_odds(row.get('odds'))}",
                f"{row.get('selection') or 'N/A'}",
            ]
        )
        for index, leg in enumerate(row.get("legs") or [], start=1):
            leg_metrics = leg.get("metrics") or {}
            lines.append(
                f"{index}. {leg.get('selection') or 'N/A'} {_odds(leg.get('odds'))} "
                f"(P {_pct(leg_metrics.get('model_probability'))}, "
                f"EV {_pct(leg_metrics.get('expected_value'))})"
            )
        lines.append(
            f"組合模型率 {_pct(metrics.get('model_probability'))}｜"
            f"平均 Edge {_pct(metrics.get('average_edge'))}｜Risk {row.get('risk') or 'N/A'}"
        )
    lines.extend(
        [
            "",
            "⚠️ 賠率以訊息發出時嘅已抽取快照為準；落注前要再核對。",
            "資金管理：只用預先設定注碼，模型唔保證盈利。",
        ]
    )
    return "\n".join(lines)


def postgame_message(target_date: str, archive: Path) -> str:
    """Render a results-backed performance summary from reflector artifacts."""
    snapshot_path = archive / f"Reflector_Training_Snapshot_{target_date}.csv"
    rows: list[dict[str, str]] = []
    if snapshot_path.is_file():
        with snapshot_path.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"postgame_training_snapshot_missing_or_empty:{snapshot_path}")
    settled = [row for row in rows if str(row.get("cleared") or "").strip() in {"0", "1"}]
    voids = [
        row for row in rows
        if "VOID" in str(row.get("status") or "").upper()
        or str(row.get("outcome") or "").lower() == "void"
    ]
    hits = sum(str(row.get("cleared") or "").strip() == "1" for row in settled)
    misses = len(settled) - hits

    proposal = _read_json(
        archive / f"Dashboard_Settlement_Proposal_{target_date}.json", {}
    )
    proposal_count = int(((proposal.get("summary") or {}).get("nba") or 0)) if isinstance(proposal, dict) else 0
    run_summary = _read_json(archive / f"Reflector_Run_Summary_{target_date}.json", {})
    ml_summary = run_summary.get("ml_summary") or {} if isinstance(run_summary, dict) else {}

    lines = [
        f"🏀 NBA 旺財賽後覆盤｜{target_date}",
        f"已核實 legs：{len(settled) + len(voids)}/{len(rows)}｜命中 {hits}｜失手 {misses}｜作廢 {len(voids)}",
        f"命中率：{_pct(hits / len(settled)) if settled else 'N/A'}",
        f"Dashboard 結算 proposal：{proposal_count}（只生成，未自動套用）",
    ]
    if isinstance(ml_summary, dict) and ml_summary.get("status") == "ok":
        baseline = ml_summary.get("baseline") or {}
        model = ml_summary.get("ml_model") or {}
        lines.append(
            f"歷史評估 Brier：baseline {baseline.get('brier', 'N/A')}｜ML {model.get('brier', 'N/A')}"
        )
    unresolved = len(rows) - len(settled) - len(voids)
    if unresolved:
        lines.append(f"未落實 legs：{unresolved}（不計入命中率）")
    lines.append("📌 呢份係賽果核實摘要，唔會用未完成結果補數。")
    return "\n".join(lines)


def sportsbet_tags(folder: Path, target_date: str) -> list[str]:
    tags: list[str] = []
    for path in sorted(folder.glob("Sportsbet_Odds_*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        explicit_dates = [
            value
            for value in (
                payload.get("target_analysis_date"),
                payload.get("event_local_date"),
            )
            if value
        ]
        if explicit_dates and all(value == target_date for value in explicit_dates):
            tags.append(canonical_game_tag(path.stem.removeprefix("Sportsbet_Odds_")))
    return sorted(set(tags))


def schedule_coverage_problems(schedule_tags: set[str], verified_tags: list[str]) -> list[str]:
    """Require a one-to-one official schedule/odds match before publication."""
    verified = set(verified_tags)
    problems = [f"missing_official_game:{tag}" for tag in sorted(schedule_tags - verified)]
    problems.extend(f"unexpected_game:{tag}" for tag in sorted(verified - schedule_tags))
    return problems


def validate_analysis(folder: Path, target_date: str, tags: list[str]) -> list[str]:
    problems: list[str] = []
    if not tags:
        return ["no_verified_sportsbet_games"]
    for tag in tags:
        required = (
            folder / f"Sportsbet_Odds_{tag}.json",
            folder / f"nba_game_data_{tag}.json",
            folder / f"Game_{tag}_Full_Analysis.md",
        )
        for path in required:
            if not path.is_file() or path.stat().st_size == 0:
                problems.append(f"missing_or_empty:{path.name}")
        report = folder / f"Game_{tag}_Full_Analysis.md"
        if report.is_file():
            text = report.read_text(encoding="utf-8", errors="replace")
            if "[FILL]" in text:
                problems.append(f"fill_residual:{report.name}")
            if len(text) < 2000:
                problems.append(f"report_too_small:{report.name}")
    for name in ("NBA_All_SGM_Report.txt", "NBA_Banker_Report.txt"):
        path = folder / name
        if not path.is_file() or path.stat().st_size == 0:
            problems.append(f"missing_or_empty:{name}")
    return sorted(set(problems))


def snapshot_manifest(snapshot: Path) -> dict[str, Any]:
    return _read_json(snapshot / "manifest.json", {}) if snapshot.is_dir() else {}


def latest_snapshot(folder: Path, *, role: FreshnessRole | None = None) -> Path | None:
    root = folder / "_prediction_snapshots"
    snapshots = sorted(path for path in root.glob("*") if (path / "manifest.json").is_file())
    if role is not None:
        snapshots = [
            path
            for path in snapshots
            if snapshot_manifest(path).get("snapshot_role") == role.value
        ]
    return snapshots[-1] if snapshots else None


def create_prediction_snapshot(
    folder: Path,
    target_date: str,
    tags: list[str],
    *,
    role: FreshnessRole = FreshnessRole.PRODUCTION,
    refreshable_tags: list[str] | None = None,
) -> Path:
    problems = validate_analysis(folder, target_date, tags)
    if problems:
        raise ValueError("analysis_not_snapshot_ready:" + ",".join(problems))

    root = folder / "_prediction_snapshots"
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(SYDNEY).strftime("%Y%m%d-%H%M%S-%f")
    temp = root / f".{stamp}.tmp"
    final = root / stamp
    temp.mkdir()

    names = ["NBA_All_SGM_Report.txt", "NBA_Banker_Report.txt", "_nba_session_state.md"]
    for tag in tags:
        names.extend(
            [
                f"Sportsbet_Odds_{tag}.json",
                f"nba_game_data_{tag}.json",
                f"Game_{tag}_Full_Analysis.md",
            ]
        )
    copied: dict[str, dict[str, Any]] = {}
    for name in names:
        source = folder / name
        if not source.is_file():
            continue
        destination = temp / name
        shutil.copy2(source, destination)
        copied[name] = {"sha256": _sha256(destination), "bytes": destination.stat().st_size}

    commit = _run(["git", "rev-parse", "HEAD"], timeout=30)
    manifest = {
        "schema_version": 1,
        "sport": "nba",
        "target_date": target_date,
        "created_at": datetime.now(SYDNEY).isoformat(),
        "model_commit": commit.stdout.strip() if commit.returncode == 0 else "unknown",
        "game_tags": sorted(tags),
        "season_context": classify_nba_season(target_date),
        "snapshot_role": role.value,
        "refreshable_game_tags": sorted(refreshable_tags or tags),
        "append_only": True,
        "files": copied,
    }
    (temp / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temp.replace(final)
    return final


def _deploy(source: str, folder: Path) -> str:
    if os.environ.get("WC_DISABLE_POST_SUCCESS_DEPLOY", "").strip().lower() in {
        "1", "true", "yes", "on"
    }:
        return "disabled"
    ok = run_post_success_cloudflare_deploy(
        source=source,
        target_dir=folder,
        allow_failure=True,
    )
    if not ok:
        raise TemporaryFailure("cloudflare_deploy_failed")
    return "ok"


def _game_artifacts(folder: Path, tag: str) -> tuple[Path, ...]:
    return (
        folder / f"Sportsbet_Odds_{tag}.json",
        folder / f"nba_game_data_{tag}.json",
        folder / f"Game_{tag}_Full_Analysis.md",
    )


def _artifact_hashes(folder: Path, tags: set[str]) -> dict[str, str]:
    return {
        path.name: _sha256(path)
        for tag in sorted(tags)
        for path in _game_artifacts(folder, tag)
        if path.is_file()
    }


def _restore_bytes(path: Path, content: bytes) -> None:
    temp = path.with_suffix(path.suffix + ".restore.tmp")
    temp.write_bytes(content)
    temp.replace(path)


def refresh_sportsbet_odds(
    folder: Path,
    target_date: str,
    *,
    protected_tags: set[str],
    log: RunLog,
) -> None:
    """Refresh odds while preserving every already-started game's exact bytes."""
    folder.mkdir(parents=True, exist_ok=True)
    existing = {
        path.name: path.read_bytes()
        for path in folder.glob("Sportsbet_Odds_*.json")
        if path.is_file()
    }
    result = _run(
        [
            sys.executable,
            str(CLAW_SPORTSBET),
            "--outdir",
            str(folder),
            "--date",
            target_date,
        ],
        timeout=1800,
    )
    log.step(
        "odds_refresh",
        "ok" if result.returncode == 0 else "failed",
        exit_code=result.returncode,
        protected_games=sorted(protected_tags),
        stdout_tail=result.stdout[-1200:],
        stderr_tail=result.stderr[-1200:],
    )
    if result.returncode != 0:
        for path in folder.glob("Sportsbet_Odds_*.json"):
            if path.name not in existing:
                path.unlink(missing_ok=True)
        for name, content in existing.items():
            _restore_bytes(folder / name, content)
        raise TemporaryFailure(f"sportsbet_refresh_exit_{result.returncode}")

    for tag in protected_tags:
        path = folder / f"Sportsbet_Odds_{tag}.json"
        previous = existing.get(path.name)
        if previous is None:
            path.unlink(missing_ok=True)
        else:
            _restore_bytes(path, previous)


def _run_orchestrator_refresh(
    target_date: str,
    folder: Path,
    *,
    refreshable_tags: set[str],
    schedule_tags: set[str],
    log: RunLog,
) -> None:
    commands: list[list[str]] = []
    base = [
        sys.executable,
        str(ORCHESTRATOR),
        "--date",
        target_date,
        "--auto",
        "--skip-cloudflare-deploy",
    ]
    if refreshable_tags == schedule_tags:
        commands.append(base)
    else:
        for tag in sorted(refreshable_tags):
            commands.append([*base, "--game", tag])

    for command in commands:
        result = _run(command)
        tag = command[-1] if "--game" in command else "all"
        log.step(
            "orchestrator",
            "ok" if result.returncode == 0 else "failed",
            game=tag,
            exit_code=result.returncode,
            stdout_tail=result.stdout[-2000:],
            stderr_tail=result.stderr[-2000:],
        )
        if result.returncode != 0:
            raise TemporaryFailure(f"orchestrator_exit_{result.returncode}:{tag}")


def run_pregame(
    target_date: str,
    log: RunLog,
    *,
    freshness_role: FreshnessRole = FreshnessRole.PRODUCTION,
    at: datetime | None = None,
    schedule_events: tuple[dict[str, datetime], bool] | None = None,
) -> str:
    now = at or now_sydney()
    season_context = classify_nba_season(target_date)
    if schedule_events is None:
        schedule_tags, reachable = load_espn_schedule(target_date)
        event_starts = {tag: now + timedelta(days=1) for tag in schedule_tags}
    else:
        event_starts, reachable = schedule_events
        schedule_tags = set(event_starts)
    log.step(
        "schedule",
        "ok" if reachable else "failed",
        games=len(schedule_tags),
        season_context=season_context,
        freshness_role=freshness_role.value,
    )
    if not reachable:
        raise TemporaryFailure("ESPN schedule source unavailable")
    if not schedule_tags:
        log.step("pregame", "dormant", reason="no_nba_games")
        return "dormant"
    if season_context["season_phase"] == "OFF_SEASON":
        raise TemporaryFailure("official_games_found_during_configured_off_season")

    folder = live_dir(target_date)
    refreshable_tags = (
        set(schedule_tags)
        if freshness_role is FreshnessRole.WARMUP
        else {
            tag
            for tag, starts_at in event_starts.items()
            if starts_at.tzinfo is not None and starts_at > now
        }
    )
    if not refreshable_tags:
        log.step(
            "pregame",
            "dormant",
            reason="all_games_started",
            freshness_role=freshness_role.value,
        )
        return "dormant"

    snapshot = latest_snapshot(folder, role=freshness_role)
    no_material_change = False
    if snapshot:
        tags = sportsbet_tags(folder, target_date)
        coverage = schedule_coverage_problems(schedule_tags, tags)
        if coverage:
            raise TemporaryFailure("schedule_coverage_failed:" + ",".join(coverage))
        log.step(
            "analysis",
            "already_snapshotted",
            snapshot=str(snapshot),
            freshness_role=freshness_role.value,
        )
    else:
        protected_tags = schedule_tags - refreshable_tags
        protected_before = _artifact_hashes(folder, protected_tags)
        material_before = _artifact_hashes(folder, refreshable_tags)
        if freshness_role is not FreshnessRole.WARMUP:
            refresh_sportsbet_odds(
                folder,
                target_date,
                protected_tags=protected_tags,
                log=log,
            )
        _run_orchestrator_refresh(
            target_date,
            folder,
            refreshable_tags=refreshable_tags,
            schedule_tags=schedule_tags,
            log=log,
        )
        protected_after = _artifact_hashes(folder, protected_tags)
        if protected_after != protected_before:
            raise TemporaryFailure("started_game_artifact_changed_during_refresh")
        tags = sportsbet_tags(folder, target_date)
        problems = schedule_coverage_problems(schedule_tags, tags)
        problems.extend(validate_analysis(folder, target_date, tags))
        if problems:
            raise TemporaryFailure("analysis_gate_failed:" + ",".join(problems))
        material_after = _artifact_hashes(folder, refreshable_tags)
        no_material_change = (
            freshness_role is FreshnessRole.FINAL_REFRESH
            and bool(material_before)
            and material_after == material_before
        )
        if no_material_change:
            snapshot = latest_snapshot(folder, role=FreshnessRole.PRODUCTION) or latest_snapshot(folder)
            if snapshot is None:
                raise TemporaryFailure("final_refresh_has_no_prior_snapshot")
            log.step(
                "prediction_snapshot",
                "skipped_no_material_change",
                snapshot=str(snapshot),
                refreshable_games=sorted(refreshable_tags),
            )
        else:
            snapshot = create_prediction_snapshot(
                folder,
                target_date,
                tags,
                role=freshness_role,
                refreshable_tags=sorted(refreshable_tags),
            )
            log.step(
                "prediction_snapshot",
                "ok",
                snapshot=str(snapshot),
                games=len(tags),
                freshness_role=freshness_role.value,
                refreshable_games=sorted(refreshable_tags),
            )

    if freshness_role is FreshnessRole.WARMUP:
        log.step("dashboard", "warmup_skipped")
        notify_once(
            f"pregame-warmup:{target_date}:{snapshot.name}",
            (
                f"🟡 NBA Wong Choi {target_date} warm-up完成\n"
                f"已驗證賽事：{len(schedule_tags)}\n"
                f"Prediction snapshot：{snapshot.name}\n"
                "00:30 production refresh前唔發投注Dashboard或content投注卡。"
            ),
            audience="primary",
        )
        return "warmup_complete"

    if no_material_change:
        log.step("dashboard", "refresh_skipped_no_material_change")
        return "complete"

    is_preseason = season_context["automation_mode"] == "shadow"
    deploy = (
        "shadow_skipped"
        if is_preseason
        else _deploy("NBA Wong Choi scheduled pregame", folder)
    )
    log.step("dashboard", deploy)
    tags = sportsbet_tags(folder, target_date)
    operational = notify_once(
        f"pregame-ops:{target_date}:{snapshot.name}",
        (
            f"✅ NBA Wong Choi {target_date} 分析完成\n"
            f"已驗證賽事：{len(tags)}\n"
            f"階段：{season_context['season_phase']}\n"
            f"Prediction snapshot：{snapshot.name}\nDashboard：{deploy}"
        ),
        audience="primary",
    )
    log.step("telegram_operational", str(operational.get("status") or "unknown"))

    if is_preseason:
        shadow_notice = notify_once(
            f"pregame-preseason-shadow:{target_date}:{snapshot.name}",
            (
                f"🧪 NBA Wong Choi preseason shadow｜{target_date}\n"
                "分析同 snapshot 已完成，但 preseason 強制 NO BET；"
                "唔會發布 Dashboard 投注建議或 content 投注卡。"
            ),
            audience="primary",
        )
        log.step(
            "telegram_betting_card",
            "preseason_shadow",
            notify_status=shadow_notice.get("status"),
        )
        return "shadow_complete"

    exported = export_nba_snapshot(PROJECT_ROOT, target_date=target_date)
    try:
        card = nba_betting_message(target_date, exported)
    except ValueError as exc:
        blocked = notify_once(
            f"pregame-card-blocked:{target_date}:{snapshot.name}",
            (
                f"⚠️ NBA Wong Choi {target_date} 投注卡已攔截\n"
                f"原因：{exc}\n分析已保存，但唔會發送投注建議。"
            ),
            audience="primary",
        )
        log.step(
            "telegram_betting_card",
            "blocked",
            reason=str(exc),
            notify_status=blocked.get("status"),
        )
    else:
        card_result = notify_once(
            f"pregame-card:{target_date}:{snapshot.name}",
            card,
            audience="content",
        )
        log.step(
            "telegram_betting_card",
            str(card_result.get("status") or "unknown"),
            validation_status=exported.get("validation_status"),
            recommendations=len(exported.get("recommendations") or []),
        )
    return "complete"


def _last_json_line(output: str) -> dict[str, Any] | None:
    for line in reversed(output.splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def run_postgame(target_date: str, log: RunLog) -> str:
    folder = live_dir(target_date)
    if not folder.is_dir():
        if archived_dirs(target_date):
            log.step("postgame", "already_archived")
            return "already_archived"
        log.step("postgame", "dormant", reason="no_live_analysis")
        return "dormant"

    if latest_snapshot(folder) is None:
        raise TemporaryFailure("live_analysis_has_no_prediction_snapshot")
    result = _run([sys.executable, str(REVIEW_ARCHIVE), "--date", target_date], timeout=3600)
    summary = _last_json_line(result.stdout) or {}
    status = str(summary.get("status") or "unknown")
    log.step(
        "reflector_archive",
        "ok" if result.returncode == 0 else "failed",
        exit_code=result.returncode,
        result=status,
        detail=summary,
        stderr_tail=result.stderr[-2000:],
    )
    if result.returncode != 0:
        raise TemporaryFailure(f"postgame_exit_{result.returncode}")
    if status == "archive_skipped":
        raise TemporaryFailure(str(summary.get("message") or "results_not_ready"))
    if status != "archived":
        return status

    archive = Path(str(summary.get("archive_path") or ""))
    deploy_target = archive if archive.is_dir() else folder
    deploy = _deploy("NBA Wong Choi scheduled postgame", deploy_target)
    log.step("dashboard", deploy)
    operational = notify_once(
        f"postgame-ops:{target_date}",
        f"✅ NBA Wong Choi {target_date} 覆盤完成並已歸檔\nDashboard：{deploy}",
        audience="primary",
    )
    log.step("telegram_operational", str(operational.get("status") or "unknown"))
    if archive.is_dir():
        try:
            performance_message = postgame_message(target_date, archive)
        except ValueError as exc:
            warning = notify_once(
                f"postgame-performance-blocked:{target_date}",
                f"⚠️ NBA Wong Choi {target_date} 賽後摘要已攔截\n{exc}",
                audience="primary",
            )
            log.step(
                "telegram_performance",
                "blocked",
                reason=str(exc),
                notify_status=warning.get("status"),
            )
        else:
            performance = notify_once(
                f"postgame-performance:{target_date}",
                performance_message,
                audience="content",
            )
            log.step("telegram_performance", str(performance.get("status") or "unknown"))
    else:
        log.step("telegram_performance", "skipped", reason="archive_path_unavailable")
    return "archived"


def health_payload(target_date: str) -> tuple[dict[str, Any], int]:
    schedule_tags, reachable = load_espn_schedule(target_date)
    season_context = classify_nba_season(target_date)
    payload: dict[str, Any] = {
        "target_date": target_date,
        "schedule_reachable": reachable,
        "scheduled_games": len(schedule_tags),
        "season_context": season_context,
        "live_dir": str(live_dir(target_date)),
        "archive_root": str(NBA_ANALYSIS),
    }
    if not reachable:
        payload["status"] = "degraded"
        payload["reason"] = "schedule_unavailable"
        return payload, TEMPORARY_FAILURE
    if not schedule_tags:
        payload["status"] = "dormant"
        payload["reason"] = "no_nba_games"
        return payload, 0
    folder = live_dir(target_date)
    if archived_dirs(target_date):
        payload["status"] = "archived"
        return payload, 0
    snapshot = latest_snapshot(folder)
    payload["snapshot"] = str(snapshot) if snapshot else None
    payload["status"] = "ok" if snapshot else "missing_prediction"
    return payload, 0 if snapshot else 1


def run_startup(log: RunLog) -> str:
    now = now_sydney()
    today = now.date()
    yesterday = (today - timedelta(days=1)).isoformat()
    if live_dir(yesterday).is_dir():
        try:
            run_postgame(yesterday, log)
        except TemporaryFailure as exc:
            log.payload["warnings"].append(f"startup postgame: {exc}")
            notify_once(
                f"startup-postgame-failure:{yesterday}:{exc}",
                f"⚠️ NBA Wong Choi startup 未能完成 {yesterday} 覆盤\n{exc}",
                audience="primary",
            )
    target = pregame_target(now).isoformat()
    return run_pregame(
        target,
        log,
        freshness_role=nba_pregame_role(now),
        at=now,
        schedule_events=load_espn_events(target),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="NBA Wong Choi daily automation")
    parser.add_argument("--mode", choices=("pregame", "postgame", "health", "startup"), required=True)
    parser.add_argument("--date", help="Override target Australia/Sydney date (YYYY-MM-DD)")
    parser.add_argument(
        "--freshness-role",
        choices=("auto", "warmup", "production", "final_refresh"),
        default="auto",
        help="Pregame snapshot role; auto derives it from the Sydney run time.",
    )
    args = parser.parse_args()

    now = now_sydney()
    if args.date:
        target_date = datetime.strptime(args.date, "%Y-%m-%d").date().isoformat()
    elif args.mode == "pregame":
        target_date = pregame_target(now).isoformat()
    else:
        target_date = now.date().isoformat()

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = STATE_DIR / "nba_daily_schedule.lock"
    with lock_path.open("a", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(json.dumps({"status": "skipped_locked", "mode": args.mode, "target_date": target_date}))
            return 0

        log = RunLog(args.mode, target_date)
        try:
            if args.mode == "pregame":
                role = (
                    nba_pregame_role(now)
                    if args.freshness_role == "auto"
                    else FreshnessRole(args.freshness_role)
                )
                status = run_pregame(
                    target_date,
                    log,
                    freshness_role=role,
                    at=now,
                    schedule_events=load_espn_events(target_date),
                )
            elif args.mode == "postgame":
                status = run_postgame(target_date, log)
            elif args.mode == "startup":
                status = run_startup(log)
            else:
                health, code = health_payload(target_date)
                health_detail = {key: value for key, value in health.items() if key != "status"}
                log.step("health", health["status"], **health_detail)
                if code != 0:
                    telegram = notify_once(
                        f"health:{target_date}:{health['status']}",
                        (
                            f"⚠️ NBA Wong Choi health 異常｜{target_date}\n"
                            f"狀態：{health['status']}\n"
                            f"原因：{health.get('reason') or 'missing prediction snapshot'}"
                        ),
                        audience="primary",
                    )
                    log.step("telegram_health", str(telegram.get("status") or "unknown"))
                log.finish(health["status"], health=health)
                print(json.dumps(health, ensure_ascii=False, sort_keys=True))
                return code
            log.finish(status)
            print(json.dumps({"status": status, "mode": args.mode, "target_date": target_date}))
            return 0
        except TemporaryFailure as exc:
            message = str(exc)
            log.payload["errors"].append(message)
            log.finish("temporary_failure")
            notify_once(
                f"failure:{args.mode}:{target_date}:{message}",
                f"⚠️ NBA Wong Choi {args.mode} 暫時失敗｜{target_date}\n{message}",
                audience="primary",
            )
            print(json.dumps({"status": "temporary_failure", "error": message, "target_date": target_date}))
            return TEMPORARY_FAILURE
        except Exception as exc:  # keep a durable run log before launchd retries
            message = f"{type(exc).__name__}: {exc}"
            log.payload["errors"].append(message)
            log.finish("failed")
            notify_once(
                f"failure:{args.mode}:{target_date}:{message}",
                f"❌ NBA Wong Choi {args.mode} 失敗｜{target_date}\n{message}",
                audience="primary",
            )
            print(json.dumps({"status": "failed", "error": message, "target_date": target_date}))
            return 1


if __name__ == "__main__":
    raise SystemExit(main())

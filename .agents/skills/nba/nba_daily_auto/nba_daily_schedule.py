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
from nba_research_evidence import (  # noqa: E402
    build_feature_projection,
    build_recommendation_projection,
    freeze_settlement_artifacts,
)
import nba_market_ledger as market_ledger  # noqa: E402
import nba_combo_roi  # noqa: E402
import nba_reliability  # noqa: E402
import nba_no_prediction as no_prediction  # noqa: E402

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
from shared_wong_choi.contracts import Domain  # noqa: E402
from shared_wong_choi.domain_evidence import (  # noqa: E402
    record_prediction_decision_if_configured,
    record_settlement_for_event,
)
from shared_wong_choi.evidence import DecisionState  # noqa: E402

CLAW_SPORTSBET = (
    NBA_SKILL / "nba_data_extractor" / "scripts" / "claw_sportsbet_odds.py"
)


class TemporaryFailure(RuntimeError):
    """A retryable source/deploy/results failure."""


class PlayerMarketsWaiting(TemporaryFailure):
    """Verified source waiting, distinct from a broken extraction or analysis."""

    reason = "player_markets_not_open"
    step = "player_markets"
    notification_key = "waiting-player-markets"
    title = "等待球員盤口"
    source_note = "Sportsbet 未開球員盤口；下次排程會重新抓取。"

    def __init__(self, games: list[str]) -> None:
        self.games = sorted(set(games))
        super().__init__(self.reason + ":" + ",".join(self.games))


class GameMarketsWaiting(PlayerMarketsWaiting):
    reason = "sportsbet_game_data_missing"
    step = "game_markets"
    notification_key = "waiting-game-markets"
    title = "等待賽事盤口資料"
    source_note = "Sportsbet 賽事資料未齊；下次排程會重新抓取。"


def _waiting_market_games(result: subprocess.CompletedProcess[str], status: str, reason: str) -> list[str]:
    if result.returncode != TEMPORARY_FAILURE:
        return []
    prefix = "NBA_PIPELINE_RESULT: "
    for line in reversed(result.stdout.splitlines()):
        if not line.startswith(prefix):
            continue
        try:
            payload = json.loads(line[len(prefix):])
        except ValueError:
            return []
        if not isinstance(payload, dict):
            return []
        games = payload.get("waiting_games")
        if (
            payload.get("status") == status
            and payload.get("reason") == reason
            and isinstance(games, list)
            and games
            and all(isinstance(tag, str) and tag for tag in games)
        ):
            return sorted(set(games))
        return []
    return []


class AnalysisGamesBlocked(TemporaryFailure):
    """Some games failed the per-game firewall; the others are publishable.

    Before 2026-10-14 one blocked game made the orchestrator exit 1 and the
    scheduler froze nothing at all, so postgame had no prediction to review
    (2026-10-10/11/12: ``live_analysis_has_no_prediction_snapshot``).
    """

    def __init__(self, blocked: list[str], passed: list[str]) -> None:
        self.blocked = sorted(set(blocked))
        self.passed = sorted(set(passed))
        super().__init__("games_blocked:" + ",".join(self.blocked))


def blocked_games_result(result: subprocess.CompletedProcess[str]) -> dict[str, Any] | None:
    """Parse the orchestrator's ``games_blocked`` outcome (exit 1 only)."""
    if result.returncode != 1:
        return None
    prefix = "NBA_PIPELINE_RESULT: "
    for line in reversed(result.stdout.splitlines()):
        if not line.startswith(prefix):
            continue
        try:
            payload = json.loads(line[len(prefix):])
        except ValueError:
            return None
        if not isinstance(payload, dict) or payload.get("status") != "games_blocked":
            return None
        blocked = payload.get("blocked_games")
        passed = payload.get("passed_games")
        if not (
            isinstance(blocked, list)
            and blocked
            and isinstance(passed, list)
            and all(isinstance(tag, str) and tag for tag in [*blocked, *passed])
        ):
            return None
        return {
            "blocked": sorted(set(blocked)),
            "passed": sorted(set(passed)),
            "sgm_ok": payload.get("sgm_ok") is True,
        }
    return None


def waiting_player_games(result: subprocess.CompletedProcess[str]) -> list[str]:
    return _waiting_market_games(result, "waiting_player_markets", "player_markets_not_open")


def waiting_game_markets(result: subprocess.CompletedProcess[str]) -> list[str]:
    return _waiting_market_games(result, "waiting_game_markets", "sportsbet_game_data_missing")


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
    # ⚠️ 一定要 encoding="utf-8", errors="replace"。`text=True` 係嚴格 UTF-8，
    # 而 launchd 底下 locale 可能係 POSIX（會退去 ASCII）。2026-09-09 實測：
    # 一個 shell 錯誤訊息入面嘅孤立 0xef 就令 HKJC prerace 同 Tennis card
    # 兩個 run 死喺 UnicodeDecodeError，而個訊息連係邊條命令都冇講。
    # subprocess 輸出係俾人睇嘅 log，永遠唔應該有能力令 run 死。
    return subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        encoding="utf-8",
        errors="replace",
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


def _no_banker_diagnostics(snapshot: dict[str, Any]) -> str:
    latest = snapshot.get("latest_analysis") or {}
    coverage = latest.get("coverage") or {}
    games = latest.get("games") or []
    recent = edge = 0
    found = False
    for game in games:
        counts = ((game.get("diagnostics") or {}).get("banker_funnel") or {}).get("fallback", {}).get("remaining", {})
        if counts:
            found = True
            recent += counts.get("recent_hits", 0)
            edge += counts.get("nonnegative_edge", 0)
    summary = f"分析：{coverage.get('analysed_games', 0)}/{coverage.get('scheduled_games', 0)} 場；正式穩膽 0。"
    if found:
        summary += f"\n穩膽 fallback 漏斗：近期命中率合格 {recent} 腿 → 同時非負 edge {edge} 腿；之後仍需波幅／陣容／合法組合／實價 EV 檢查。"
    else:
        summary += "\n原因：正式分析未有通過全部驗證嘅 NBA 組合；逐關診斷未齊，唔將原因一律歸咎門檻。"
    return summary


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
            "正式策略：只保留穩膽；真實 SGM 價 ≥2.0，保留 EV 驗證。\n"
            + _no_banker_diagnostics(snapshot)
            + "\n" + nba_reliability.selection_message(snapshot.get("selection_health") or {})
            + "\n零出手亦需檢查機率、門檻及市場價；唔等於已證明模型有盈利優勢。"
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


def snapshot_is_partial(snapshot: Path) -> bool:
    return snapshot_manifest(snapshot).get("completeness") == "partial"


def latest_snapshot(
    folder: Path,
    *,
    role: FreshnessRole | None = None,
    include_partial: bool | None = None,
) -> Path | None:
    """Latest snapshot; role lookups (pregame idempotency) skip partial ones.

    A partial snapshot freezes the games that passed while others were
    blocked.  It is a real prediction for postgame/health, but it must not
    tell the next pregame run "already snapshotted": the blocked games still
    need their retry.
    """
    root = folder / "_prediction_snapshots"
    snapshots = sorted(path for path in root.glob("*") if (path / "manifest.json").is_file())
    if include_partial is None:
        include_partial = role is None
    if not include_partial:
        snapshots = [path for path in snapshots if not snapshot_is_partial(path)]
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
    event_starts: dict[str, datetime] | None = None,
    blocked_tags: list[str] | None = None,
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

    names = ["NBA_All_SGM_Report.txt", "NBA_Banker_Report.txt", "_nba_session_state.md",
             "NBA_Opportunity_Sources.json"]
    for tag in tags:
        names.extend(
            [
                f"Sportsbet_Odds_{tag}.json",
                f"nba_game_data_{tag}.json",
                f"Game_{tag}_Full_Analysis.md",
                # Optional market-evaluation sidecar; absent files are skipped.
                f"Game_{tag}_Full_Analysis.md{market_ledger.SIDECAR_SUFFIX}",
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

    cutoff = datetime.now(SYDNEY)
    research_status: dict[str, str] = {"status": "blocked"}
    try:
        if event_starts is None:
            raise ValueError("NBA official schedule unavailable for research")
        projection = build_feature_projection(
            folder=folder,
            source_folder=temp,
            event_id=target_date,
            game_tags=tags,
            source_cutoff_at=cutoff,
            event_starts=event_starts,
        )
    except ValueError as exc:
        research_status["reason"] = str(exc)
    else:
        name = f"NBA_Feature_Evidence_{target_date}.json"
        destination = temp / name
        destination.write_bytes(projection)
        copied[name] = {"sha256": _sha256(destination), "bytes": len(projection)}
        research_status = {"status": "feature_verified", "monitoring_status": "pending"}
        try:
            recommendations = build_recommendation_projection(
                source_folder=temp, event_id=target_date, game_tags=tags,
                source_cutoff_at=cutoff,
            )
        except ValueError as exc:
            research_status["monitoring_status"] = "blocked"
            research_status["reason"] = str(exc)
        else:
            name = f"NBA_Recommendation_Evidence_{target_date}.json"
            destination = temp / name
            destination.write_bytes(recommendations)
            copied[name] = {"sha256": _sha256(destination), "bytes": len(recommendations)}
            research_status = {"status": "pregame_verified", "monitoring_status": "settlement_pending"}

    commit = _run(["git", "rev-parse", "HEAD"], timeout=30)
    manifest = {
        "schema_version": 1,
        "sport": "nba",
        "domain": "nba",
        "event_id": target_date,
        "target_date": target_date,
        "created_at": cutoff.isoformat(),
        "model_commit": commit.stdout.strip() if commit.returncode == 0 else "unknown",
        "game_tags": sorted(tags),
        "season_context": classify_nba_season(target_date),
        "snapshot_role": role.value,
        "refreshable_game_tags": sorted(refreshable_tags or tags),
        "completeness": "partial" if blocked_tags else "complete",
        # Aggregate SGM/Banker reports are copied as written and may still
        # mention a blocked game; consumers must filter by game_tags.
        "blocked_game_tags": sorted(blocked_tags or []),
        "append_only": True,
        "files": [{"name": name, **copied[name]} for name in sorted(copied)],
        "research_evidence": research_status,
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


def _market_ledger(log: Any, action: str, call) -> None:
    """Run one forward market-ledger write; it can never fail or alter a run."""
    try:
        detail = call()
    except market_ledger.LedgerIsolationError as exc:
        log.step("market_ledger", "skipped", action=action, reason=str(exc))
    except Exception as exc:  # noqa: BLE001
        log.step("market_ledger", "failed", action=action, error=f"{type(exc).__name__}: {exc}")
    else:
        log.step("market_ledger", "ok", action=action, detail=detail)


def _record_no_prediction_ledger(
    written_off: "no_prediction.NoPredictionScope", target_date: str, log: Any
) -> None:
    """Re-assert the ledger exclusion (idempotent) so evaluation never counts it."""
    if not written_off.marked:
        return

    def call() -> dict[str, Any]:
        summary = written_off.summary()
        appended = market_ledger.record_no_prediction(
            target_date,
            game_tags=None if written_off.whole_date else sorted(written_off.game_tags),
            reason=str(summary.get("reason") or ""),
            marked_by=str(summary.get("marked_by") or ""),
            marked_at=str(summary.get("marked_at") or ""),
        )
        return {"status": "no_prediction_excluded", "appended": appended, **summary}

    _market_ledger(log, "no_prediction", call)


def _settle_market_ledger(archive: Path, target_date: str, log: Any) -> None:
    def call() -> dict[str, Any]:
        root = market_ledger.ledger_root()
        results = market_ledger.results_brief_for(archive, target_date)
        if not results.is_file():
            return {"status": "results_brief_missing", "path": results.name}
        settled = market_ledger.settle(target_date, results, root=root)
        report = market_ledger.evaluate(root=root)
        market_ledger.write_evaluation(report, root=root)
        return {**settled, "verdict_status": report.get("verdict_status")}

    _market_ledger(log, "settle", call)


def refresh_sportsbet_odds(
    folder: Path,
    target_date: str,
    *,
    protected_tags: set[str],
    log: RunLog,
    event_starts: dict[str, datetime] | None = None,
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
    # Every successful scrape is a price observation, even when the analysis
    # later waits; this is what makes "earliest" and "close" observable.
    _market_ledger(
        log,
        "record_prices",
        lambda: market_ledger.record_prices(
            folder, target_date, event_starts=event_starts, context="odds_refresh"
        ),
    )


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

    blocked: set[str] = set()
    passed: set[str] = set()
    for command in commands:
        result = _run(command)
        tag = command[-1] if "--game" in command else "all"
        game_markets = waiting_game_markets(result)
        waiting_games = game_markets or waiting_player_games(result)
        outcome = None if waiting_games else blocked_games_result(result)
        partial_ok = bool(outcome and outcome["sgm_ok"])
        log.step(
            "orchestrator",
            "waiting" if waiting_games
            else "ok" if result.returncode == 0
            else "games_blocked" if partial_ok
            else "failed",
            game=tag,
            exit_code=result.returncode,
            blocked_games=outcome["blocked"] if outcome else None,
            stdout_tail=result.stdout[-2000:],
            stderr_tail=result.stderr[-2000:],
        )
        if game_markets:
            raise GameMarketsWaiting(game_markets)
        if waiting_games:
            raise PlayerMarketsWaiting(waiting_games)
        if outcome and partial_ok:
            # Keep going: in per-game mode the other games still need their run.
            blocked.update(outcome["blocked"])
            passed.update(outcome["passed"])
            continue
        if result.returncode != 0:
            raise TemporaryFailure(f"orchestrator_exit_{result.returncode}:{tag}")
        if tag != "all":
            passed.add(tag)
    # Single-game runs each write an aggregate for their own scope. Rebuild the
    # union once, after all refreshable games finish, without touching started games.
    if len(commands) > 1 and passed - blocked:
        compile_result = _run([
            sys.executable, str(ORCHESTRATOR), "--date", target_date,
            "--compile-only", "--games", *sorted(passed - blocked),
            "--skip-cloudflare-deploy",
        ])
        log.step("compile_refreshed_games", "ok" if compile_result.returncode == 0 else "failed",
                 game_tags=sorted(passed - blocked), exit_code=compile_result.returncode)
        if compile_result.returncode != 0:
            raise TemporaryFailure(f"compile_refreshed_games_exit_{compile_result.returncode}")
    if blocked:
        raise AnalysisGamesBlocked(sorted(blocked), sorted(passed - blocked))


def _freeze_partial_snapshot(
    folder: Path,
    target_date: str,
    blocked: AnalysisGamesBlocked,
    *,
    schedule_tags: set[str],
    refreshable_tags: set[str],
    freshness_role: FreshnessRole,
    event_starts: dict[str, datetime] | None,
    log: Any,
) -> Path | None:
    """Freeze the games that passed; return None when nothing can be frozen."""
    blocked_tags = set(blocked.blocked)
    tags = [tag for tag in sportsbet_tags(folder, target_date) if tag not in blocked_tags]
    problems = schedule_coverage_problems(schedule_tags - blocked_tags, tags)
    problems.extend(validate_analysis(folder, target_date, tags))
    if problems:
        log.step(
            "prediction_snapshot",
            "partial_blocked",
            problems=problems,
            blocked_games=sorted(blocked_tags),
        )
        return None
    current = _artifact_hashes(folder, set(tags))
    previous = latest_snapshot(folder, role=freshness_role, include_partial=True)
    if previous is not None and snapshot_is_partial(previous):
        manifest = snapshot_manifest(previous)
        frozen = {
            entry.get("name"): entry.get("sha256") for entry in manifest.get("files") or []
        }
        if (
            sorted(manifest.get("game_tags") or []) == sorted(tags)
            and sorted(manifest.get("blocked_game_tags") or []) == sorted(blocked_tags)
            and all(frozen.get(name) == sha for name, sha in current.items())
        ):
            log.step(
                "prediction_snapshot",
                "partial_unchanged",
                snapshot=str(previous),
                blocked_games=sorted(blocked_tags),
            )
            return previous
    snapshot = create_prediction_snapshot(
        folder,
        target_date,
        tags,
        role=freshness_role,
        refreshable_tags=sorted(refreshable_tags - blocked_tags),
        event_starts=event_starts,
        blocked_tags=sorted(blocked_tags),
    )
    log.step(
        "prediction_snapshot",
        "partial",
        snapshot=str(snapshot),
        games=len(tags),
        blocked_games=sorted(blocked_tags),
        freshness_role=freshness_role.value,
    )
    _market_ledger(
        log,
        "record_snapshot",
        lambda: market_ledger.record_snapshot(
            snapshot, target_date, event_starts=event_starts
        ),
    )
    return snapshot


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
    written_off = no_prediction.scope(folder)
    if written_off.whole_date:
        # A written-off date must never grow a post-hoc snapshot.
        log.step("pregame", "no_prediction", **written_off.summary())
        return "no_prediction"
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
        # Every incomplete attempt needs a fresh source read, including warmup.
        # A cached moneyline-only file must not hide newly opened player markets.
        refresh_sportsbet_odds(
            folder,
            target_date,
            protected_tags=protected_tags,
            log=log,
            event_starts=event_starts if schedule_events is not None else None,
        )
        try:
            _run_orchestrator_refresh(
                target_date,
                folder,
                refreshable_tags=refreshable_tags,
                schedule_tags=schedule_tags,
                log=log,
            )
        except AnalysisGamesBlocked as blocked:
            if _artifact_hashes(folder, protected_tags) != protected_before:
                raise TemporaryFailure("started_game_artifact_changed_during_refresh")
            partial = _freeze_partial_snapshot(
                folder,
                target_date,
                blocked,
                schedule_tags=schedule_tags,
                refreshable_tags=refreshable_tags,
                freshness_role=freshness_role,
                event_starts=event_starts if schedule_events is not None else None,
                log=log,
            )
            # Still a failure: no dashboard, no card, and the next run retries
            # the blocked games.  The message is stable so Telegram dedupes it.
            raise TemporaryFailure(
                f"games_blocked:{','.join(blocked.blocked)}"
                + (":partial_snapshot_frozen" if partial else ":nothing_frozen")
            ) from blocked
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
                event_starts=event_starts if schedule_events is not None else None,
            )
            log.step(
                "prediction_snapshot",
                "ok",
                snapshot=str(snapshot),
                games=len(tags),
                freshness_role=freshness_role.value,
                refreshable_games=sorted(refreshable_tags),
            )

    recorded_snapshot = snapshot
    _market_ledger(
        log,
        "record_snapshot",
        lambda: market_ledger.record_snapshot(
            recorded_snapshot,
            target_date,
            event_starts=event_starts if schedule_events is not None else None,
        ),
    )
    if freshness_role is not FreshnessRole.WARMUP:
        # Sportsbet's own price for each published combo (ledger only).
        _market_ledger(
            log,
            "record_sgm_prices",
            lambda: market_ledger.record_sgm_prices(
                recorded_snapshot,
                target_date,
                event_starts=event_starts if schedule_events is not None else None,
            ),
        )

    decision_state = (
        DecisionState.SHADOW
        if freshness_role is FreshnessRole.WARMUP
        or season_context["automation_mode"] == "shadow"
        else DecisionState.RECOMMEND
    )
    try:
        evidence = record_prediction_decision_if_configured(
            domain=Domain.NBA,
            event_id=target_date,
            snapshot=snapshot,
            evidence_root=Path(
                os.environ.get(
                    "WONGCHOI_CONTROL_STATE_ROOT",
                    Path.home() / "WongChoiData" / "WongChoiControl",
                )
            )
            / "evidence",
            decision_state=decision_state,
        )
    except Exception as exc:  # noqa: BLE001
        evidence = {
            "status": "failed",
            "error": f"{type(exc).__name__}: {exc}",
        }
        log.payload["warnings"].append(
            f"prediction evidence not recorded: {type(exc).__name__}: {exc}"
        )
    log.step(
        "prediction_evidence",
        str(evidence.get("status") or "unknown"),
        prediction_id=evidence.get("prediction_id"),
        decision_state=decision_state.value,
    )

    if freshness_role is FreshnessRole.WARMUP:
        log.step("dashboard", "warmup_skipped")
        notify_once(
            f"pregame-warmup:{target_date}:{snapshot.name}",
            (
                f"🟡 NBA Wong Choi {target_date} warm-up完成\n"
                f"已驗證賽事：{len(schedule_tags)}\n"
                f"Prediction snapshot：{snapshot.name}\n"
                "21:00 production refresh前唔發投注Dashboard或content投注卡。"
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
        exported["selection_health"] = nba_reliability.selection_health(target_date)
    except Exception as exc:
        exported["selection_health"] = {"status": "insufficient_data"}
        log.step("selection_health", "failed", error=f"{type(exc).__name__}: {exc}")
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


def _record_settlement_evidence(archive: Path, target_date: str, log: RunLog) -> None:
    try:
        artifacts = freeze_settlement_artifacts(folder=archive, event_id=target_date)
    except ValueError as exc:
        # Missing research provenance cannot undo a completed ordinary archive.
        settlement = {"status": "blocked", "reason": str(exc)}
    except OSError as exc:
        log.step("settlement_evidence", "failed", error=f"{type(exc).__name__}: {exc}")
        raise TemporaryFailure("settlement_capture_failed") from exc
    else:
        try:
            settlement = record_settlement_for_event(
                domain=Domain.NBA,
                event_id=target_date,
                evidence_root=Path(
                    os.environ.get(
                        "WONGCHOI_CONTROL_STATE_ROOT",
                        Path.home() / "WongChoiData" / "WongChoiControl",
                    )
                ) / "evidence",
                summary={"archive_status": "archived", "archive_path": str(archive)},
                artifacts=artifacts,
            )
        except Exception as exc:  # noqa: BLE001
            log.step("settlement_evidence", "failed", error=f"{type(exc).__name__}: {exc}")
            raise TemporaryFailure("settlement_evidence_failed") from exc
    log.step(
        "settlement_evidence",
        str(settlement.get("status") or "unknown"),
        settlement_id=settlement.get("settlement_id"),
        reason=settlement.get("reason"),
    )


def _combo_roi_text(target_date: str, log: RunLog) -> str:
    """Daily + cumulative combo ROI by type; never blocks the postgame summary."""
    try:
        reports = nba_combo_roi.write_reports(target_date, market_ledger.ledger_root())
        log.step("combo_roi", "ok", combos=reports["daily"]["total"]["combos"],
                 settled=reports["daily"]["total"]["settled"])
        return "\n".join(nba_combo_roi.message_lines(reports))
    except Exception as exc:  # noqa: BLE001 — a reporting add-on must not fail postgame
        log.step("combo_roi", "failed", error=f"{type(exc).__name__}: {exc}")
        return "📊 組合 ROI：今次計算失敗（已記錄），唔影響上面賽果摘要。"


def _reliability_text(target_date: str, log: RunLog) -> str:
    """Rolling calibration of the live probability; never blocks the postgame summary."""
    try:
        report = nba_reliability.build(target_date, market_ledger.ledger_root())
        nba_reliability.write(report, market_ledger.ledger_root())
        log.step("reliability", report["status"], settled=report["overall"]["n"])
        return "\n".join(nba_reliability.message_lines(report))
    except Exception as exc:  # noqa: BLE001 — monitoring add-on must not fail postgame
        log.step("reliability", "failed", error=f"{type(exc).__name__}: {exc}")
        return "📐 機率校準：今次計算失敗（已記錄），唔影響上面賽果摘要。"


def run_postgame(target_date: str, log: RunLog) -> str:
    folder = live_dir(target_date)
    if not folder.is_dir():
        archives = archived_dirs(target_date)
        if archives:
            if len(archives) == 1:
                written_off = no_prediction.scope(archives[0])
                if no_prediction.covers_date(archives[0]):
                    log.step("settlement_evidence", "skipped", reason="no_prediction")
                    _record_no_prediction_ledger(written_off, target_date, log)
                else:
                    _record_settlement_evidence(archives[0], target_date, log)
                    _record_no_prediction_ledger(written_off, target_date, log)
                    _settle_market_ledger(archives[0], target_date, log)
            else:
                log.step("settlement_evidence", "blocked", reason="ambiguous_archive_paths")
            log.step("postgame", "already_archived")
            return "already_archived"
        log.step("postgame", "dormant", reason="no_live_analysis")
        return "dormant"

    written_off = no_prediction.scope(folder)
    date_written_off = no_prediction.covers_date(folder)
    if latest_snapshot(folder) is None:
        # Pregame creates the directory before odds discovery. A failed first
        # extraction can leave it empty; there is no prediction to review.
        # Keep the guard for partial analyses and lost snapshots.
        if not any(folder.iterdir()):
            log.step("postgame", "dormant", reason="no_prediction_artifacts")
            return "dormant"
        if not date_written_off:
            raise TemporaryFailure("live_analysis_has_no_prediction_snapshot")
        # Explicitly written off (mark-no-prediction): archive results only.
        log.step("prediction_snapshot", "no_prediction", **written_off.summary())
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
    if date_written_off:
        log.step("settlement_evidence", "skipped", reason="no_prediction")
        _record_no_prediction_ledger(written_off, target_date, log)
    else:
        _record_settlement_evidence(archive, target_date, log)
        _record_no_prediction_ledger(written_off, target_date, log)
        _settle_market_ledger(archive if archive.is_dir() else folder, target_date, log)
    deploy_target = archive if archive.is_dir() else folder
    deploy = _deploy("NBA Wong Choi scheduled postgame", deploy_target)
    log.step("dashboard", deploy)
    operational_text = f"✅ NBA Wong Choi {target_date} 覆盤完成並已歸檔\nDashboard：{deploy}"
    if date_written_off:
        operational_text = (
            f"✅ NBA Wong Choi {target_date} 已歸檔（no_prediction：冇 prediction snapshot，"
            f"只存賽果，唔計表現）\n原因：{written_off.summary().get('reason')}\nDashboard：{deploy}"
        )
    operational = notify_once(
        f"postgame-ops:{target_date}",
        operational_text,
        audience="primary",
    )
    log.step("telegram_operational", str(operational.get("status") or "unknown"))
    if date_written_off:
        log.step("telegram_performance", "skipped", reason="no_prediction")
    elif archive.is_dir():
        try:
            performance_message = postgame_message(target_date, archive)
            performance_message += "\n\n" + _combo_roi_text(target_date, log)
            performance_message += "\n\n" + _reliability_text(target_date, log)
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
    written_off = no_prediction.scope(folder)
    if written_off.marked:
        payload["no_prediction"] = written_off.summary()
    if snapshot is None and no_prediction.covers_date(folder):
        payload["status"] = "no_prediction"
        payload["reason"] = "marked_no_prediction:" + str(written_off.summary().get("reason"))
        return payload, 0
    if snapshot and snapshot_is_partial(snapshot):
        blocked = snapshot_manifest(snapshot).get("blocked_game_tags") or []
        if written_off.covers(blocked):
            payload["status"] = "ok"
            payload["reason"] = "blocked_games_marked_no_prediction:" + ",".join(blocked)
            return payload, 0
        payload["status"] = "partial_prediction"
        payload["reason"] = "blocked_games:" + ",".join(blocked)
        return payload, 1
    payload["status"] = "ok" if snapshot else "missing_prediction"
    return payload, 0 if snapshot else 1


def mark_no_prediction(
    target_date: str,
    *,
    reason: str,
    marked_by: str,
    game_tags: list[str] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Write off a date (or games) as no_prediction; never creates a snapshot.

    Writes ``_no_prediction.json`` in the date folder (live, or the single
    archive copy) and the matching market-ledger exclusion row(s).
    """
    folder = live_dir(target_date)
    if not folder.is_dir():
        archives = archived_dirs(target_date)
        if len(archives) != 1:
            raise no_prediction.NoPredictionError(
                "analysis_folder_missing" if not archives else "ambiguous_archive_paths"
            )
        folder = archives[0]
    commit = _run(["git", "rev-parse", "HEAD"], timeout=30)
    result = no_prediction.mark(
        folder,
        target_date,
        reason=reason,
        marked_by=marked_by,
        now=now or now_sydney(),
        game_tags=[canonical_game_tag(tag) for tag in game_tags or []],
        model_commit=commit.stdout.strip() if commit.returncode == 0 else "unknown",
    )
    written_off = no_prediction.scope(folder)
    summary = written_off.summary()
    try:
        appended = market_ledger.record_no_prediction(
            target_date,
            game_tags=None if written_off.whole_date else sorted(written_off.game_tags),
            reason=str(summary.get("reason") or ""),
            marked_by=str(summary.get("marked_by") or ""),
            marked_at=str(summary.get("marked_at") or ""),
        )
    except market_ledger.LedgerIsolationError as exc:
        result["market_ledger"] = {"status": "skipped", "reason": str(exc)}
    else:
        result["market_ledger"] = {"status": "ok", "appended": appended}
    result["folder"] = str(folder)
    return result


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
    parser.add_argument(
        "--mode",
        choices=("pregame", "postgame", "health", "startup", "mark-no-prediction"),
        required=True,
    )
    parser.add_argument("--date", help="Override target Australia/Sydney date (YYYY-MM-DD)")
    parser.add_argument("--reason", help="mark-no-prediction: why this date/game has no prediction")
    parser.add_argument("--by", dest="marked_by", help="mark-no-prediction: who decided (e.g. Kelvin)")
    parser.add_argument(
        "--game",
        action="append",
        default=[],
        help="mark-no-prediction: limit to one game tag (repeatable); omit for the whole date",
    )
    parser.add_argument(
        "--freshness-role",
        choices=("auto", "warmup", "production", "final_refresh"),
        default="auto",
        help="Pregame snapshot role; auto derives it from the Sydney run time.",
    )
    args = parser.parse_args()
    if args.mode == "mark-no-prediction" and not (args.date and args.reason and args.marked_by):
        parser.error("--mode mark-no-prediction requires --date, --reason and --by")

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
            return 0 if args.mode != "mark-no-prediction" else TEMPORARY_FAILURE

        if args.mode == "mark-no-prediction":
            # A manual audit action: no RunLog/Telegram, the marker is the record.
            try:
                result = mark_no_prediction(
                    target_date,
                    reason=args.reason,
                    marked_by=args.marked_by,
                    game_tags=args.game,
                )
            except no_prediction.NoPredictionError as exc:
                print(json.dumps({"status": "refused", "error": str(exc), "target_date": target_date},
                                 ensure_ascii=False))
                return 1
            print(json.dumps({**result, "target_date": target_date}, ensure_ascii=False, sort_keys=True))
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
        except PlayerMarketsWaiting as exc:
            log.step(exc.step, "waiting", games=exc.games)
            log.finish("partial", reason=exc.reason, waiting_games=exc.games)
            notify_once(
                f"{exc.notification_key}:{target_date}",
                (
                    f"⏳ NBA Wong Choi {exc.title}｜{target_date}\n"
                    f"賽事：{', '.join(exc.games)}\n"
                    f"{exc.source_note}\n"
                    "完整分析同 prediction snapshot 尚未完成。"
                ),
                audience="primary",
            )
            print(json.dumps({
                "status": "partial",
                "reason": exc.reason,
                "waiting_games": exc.games,
                "target_date": target_date,
            }))
            return TEMPORARY_FAILURE
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

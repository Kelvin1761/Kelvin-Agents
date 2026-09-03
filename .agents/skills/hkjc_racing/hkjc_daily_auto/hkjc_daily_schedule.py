#!/usr/bin/env python3
"""HKJC Wong Choi unattended orchestration.

This module only coordinates the existing production pipeline.  It never owns
scoring logic and never merges a model candidate.  The modes are designed
for launchd/cron:

* ``watch``: dormant off-season poll for the next materialized racecard.
* ``prerace``: run extraction -> Facts -> Logic -> scoring -> data-health -> deploy.
* ``postrace``: extract results and run the unified reflector once results exist.
* ``recovery``: retry only meetings whose required sources were temporarily unavailable.
* ``weekly``: send the current performance/review state and create a non-draft
  PR only when an external candidate gate explicitly says ``passed``.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore


HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[3]
SHARED_RACING = PROJECT_ROOT / ".agents" / "skills" / "shared_racing" / "scripts"
SHARED_WC = PROJECT_ROOT / ".agents" / "skills"
for item in (PROJECT_ROOT, SHARED_RACING, SHARED_WC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from racing_telegram import send_message  # noqa: E402
from shared_wong_choi.contracts import Domain  # noqa: E402
from shared_wong_choi.domain_evidence import (  # noqa: E402
    record_prediction_decision_if_configured,
    record_settlement_for_event,
)
from shared_wong_choi.evidence import DecisionState  # noqa: E402
from wongchoi_paths import HK_RACING, HK_RACING_MIRROR, is_materialized_file  # noqa: E402


TIMEZONE = "Australia/Sydney"
DISCOVERY_URL = "https://racing.hkjc.com/zh-hk/local/information/racecard"
HKJC_ORCHESTRATOR = (
    PROJECT_ROOT
    / ".agents/skills/hkjc_racing/hkjc_wong_choi/scripts/hkjc_orchestrator.py"
)
REFLECTOR = (
    PROJECT_ROOT
    / ".agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_reflector_orchestrator.py"
)
DASHBOARD_DEPLOY = PROJECT_ROOT / "deploy.sh"
WEIGHT_REVIEW = (
    PROJECT_ROOT
    / ".agents/skills/hkjc_racing/hkjc_reflector/scripts/review_auto_weighting.py"
)
STATE_DIR = HERE / "state"
LOG_DIR = HERE / "logs"
DEFAULT_STATE = STATE_DIR / "hkjc_daily_state.json"
DEFAULT_CANDIDATE_GATE = STATE_DIR / "HKJC_Candidate_Gate.json"
DEFAULT_FORWARD_START = date(2026, 9, 6)

EXIT_OK = 0
EXIT_TEMPORARY = 75
EXIT_FAILED = 1

_CONTROL_OUTCOME: dict[str, object] = {}


def set_control_outcome(status: str, **detail: object) -> None:
    """Record one machine-readable scheduler outcome for the shared adapter."""
    _CONTROL_OUTCOME.clear()
    _CONTROL_OUTCOME.update({"status": status, **detail})


def emit_control_outcome(args: argparse.Namespace, code: int) -> int:
    if not args.control_json:
        return code
    if not _CONTROL_OUTCOME:
        fallback = "succeeded" if code == EXIT_OK else (
            "partial" if code == EXIT_TEMPORARY else "failed"
        )
        set_control_outcome(fallback)
    print(
        json.dumps(
            {
                **_CONTROL_OUTCOME,
                "mode": args.mode,
                "exit_code": code,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return code


def now_local() -> datetime:
    if ZoneInfo is not None:
        return datetime.now(ZoneInfo(TIMEZONE))
    return datetime.now().astimezone()


def stamp() -> str:
    return now_local().isoformat(timespec="seconds")


def log(message: str) -> None:
    log_dir = Path(os.environ.get("WC_HKJC_SCHED_LOG_DIR") or LOG_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)
    line = f"[{stamp()}] {message}"
    print(line, flush=True)
    with (log_dir / "hkjc_daily_schedule.log").open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            temp_path = Path(handle.name)
        os.replace(temp_path, path)
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()


def load_state(path: Path) -> dict:
    if not is_materialized_file(path):
        return {"schema_version": 1, "meetings": {}, "notifications": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {"schema_version": 1, "meetings": {}, "notifications": {}}
    payload.setdefault("schema_version", 1)
    payload.setdefault("meetings", {})
    payload.setdefault("notifications", {})
    return payload


def save_state(path: Path, state: dict) -> None:
    state["updated_at"] = stamp()
    _atomic_json(path, state)


def fetch_text(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read().decode("utf-8", errors="replace")


def discover_meetings(page_text: str, *, today: date | None = None) -> list[dict]:
    """Return unique current/future ST/HV meeting links in chronological order."""
    today = today or now_local().date()
    decoded = html.unescape(page_text).replace("&amp;", "&")
    pattern = re.compile(
        r"racedate=(20\d{2})/(\d{2})/(\d{2})&Racecourse=(ST|HV)", re.I
    )
    found: dict[tuple[date, str], dict] = {}
    for match in pattern.finditer(decoded):
        meeting_date = date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        if meeting_date < today:
            continue
        course = match.group(4).upper()
        venue = "ShaTin" if course == "ST" else "HappyValley"
        url = (
            "https://racing.hkjc.com/zh-hk/local/information/racecard"
            f"?racedate={meeting_date:%Y/%m/%d}&Racecourse={course}&RaceNo=1"
        )
        found[(meeting_date, course)] = {
            "date": meeting_date.isoformat(),
            "course": course,
            "venue": venue,
            "url": url,
        }
    return [found[key] for key in sorted(found)]


def discover_next_meeting(
    *,
    today: date | None = None,
    fetcher: Callable[[str], str] = fetch_text,
) -> dict | None:
    meetings = discover_meetings(fetcher(DISCOVERY_URL), today=today)
    return meetings[0] if meetings else None


def meeting_dir_for(meeting: dict, *, create: bool = False) -> Path:
    prefix = f"{meeting['date']}_{meeting['venue']}"
    try:
        matches = sorted(
            path for path in HK_RACING.glob(f"{prefix}*") if path.is_dir()
        )
    except OSError as exc:
        raise RuntimeError(
            f"HKJC data root unavailable: {HK_RACING}. "
            "Make the Google Drive HK_Racing folder available offline and grant "
            "the background Python process file access."
        ) from exc
    if len(matches) > 1:
        raise RuntimeError(
            f"meeting folder ambiguity for {prefix}: "
            + ", ".join(path.name for path in matches)
        )
    if matches:
        return matches[0]
    path = HK_RACING / prefix
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def meeting_date_from_dir(path: Path) -> date | None:
    match = re.match(r"(20\d{2}-\d{2}-\d{2})", path.name)
    if not match:
        return None
    try:
        return date.fromisoformat(match.group(1))
    except ValueError:
        return None


def results_url(meeting_date: date) -> str:
    return (
        "https://racing.hkjc.com/racing/information/Chinese/Racing/"
        f"LocalResults.aspx?RaceDate={meeting_date:%Y/%m/%d}&RaceNo=1"
    )


def run_cmd(cmd: list[str], *, timeout: int = 7200,
            env_overlay: dict | None = None) -> tuple[int, str]:
    log("$ " + " ".join(str(part) for part in cmd))
    env = os.environ.copy()
    env.update(env_overlay or {})
    existing = env.get("PYTHONPATH", "")
    if str(PROJECT_ROOT) not in existing.split(os.pathsep):
        env["PYTHONPATH"] = (
            f"{PROJECT_ROOT}{os.pathsep}{existing}" if existing else str(PROJECT_ROOT)
        )
    try:
        completed = subprocess.run(
            [str(part) for part in cmd],
            cwd=PROJECT_ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return 124, f"TIMEOUT after {timeout}s"
    output = (completed.stdout or "").strip()
    if output:
        for line in output.splitlines()[-20:]:
            log("   | " + line)
    return completed.returncode, output


def notify(message: str, *, audience: str = "primary") -> bool:
    try:
        result = send_message(message, audience=audience)
        if not result.get("ok"):
            log(f"Telegram warning: {result}")
        return bool(result.get("ok"))
    except Exception as exc:  # noqa: BLE001
        log(f"Telegram warning: {type(exc).__name__}: {exc}")
        return False


def mirror_meeting(meeting_dir: Path) -> dict:
    """Best-effort copy from the local HK primary to the familiar Drive folder."""
    if HK_RACING_MIRROR is None or HK_RACING_MIRROR == HK_RACING:
        return {"status": "not_configured", "copied": 0, "failed": 0}
    copied = 0
    failures: list[str] = []
    try:
        relative = meeting_dir.resolve().relative_to(HK_RACING.resolve())
    except ValueError:
        return {"status": "outside_primary", "copied": 0, "failed": 1}
    destination_root = HK_RACING_MIRROR / relative
    for source in sorted(path for path in meeting_dir.rglob("*") if path.is_file()):
        target = destination_root / source.relative_to(meeting_dir)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied += 1
        except OSError as exc:
            failures.append(f"{source.name}: {type(exc).__name__}")
            if len(failures) >= 8:
                break
    status = "ok" if not failures else ("partial" if copied else "unavailable")
    if failures:
        log("HKJC Drive mirror warning: " + ", ".join(failures))
    return {"status": status, "copied": copied, "failed": len(failures)}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


SNAPSHOT_PATTERNS = (
    "* Facts.md",
    "* 排位表.md",
    "* 晨操.md",
    "* 晨操.json",
    "Race_*_Logic.json",
    "Race_*_Auto_Analysis.md",
    "Race_*_Auto_Scoring.csv",
    "HKJC_Auto_Scoring.csv",
    "Data_Health.json",
    "Data_Health.md",
)


def create_prediction_snapshot(meeting_dir: Path, *, at: datetime | None = None) -> Path:
    """Create an immutable pre-race snapshot; identical reruns reuse the last one."""
    files = sorted({
        path
        for pattern in SNAPSHOT_PATTERNS
        for path in meeting_dir.glob(pattern)
        if path.is_file() and is_materialized_file(path)
    })
    if not files:
        raise RuntimeError(f"no pre-race artifacts to snapshot in {meeting_dir}")
    manifest_files = [
        {"name": path.name, "size": path.stat().st_size, "sha256": _sha256(path)}
        for path in files
    ]
    signature = hashlib.sha256(
        json.dumps(manifest_files, sort_keys=True).encode("utf-8")
    ).hexdigest()
    root = meeting_dir / "Prediction_Snapshots"
    existing = sorted(root.glob("*/manifest.json")) if root.exists() else []
    if existing:
        try:
            last = json.loads(existing[-1].read_text(encoding="utf-8"))
            if last.get("signature") == signature:
                return existing[-1].parent
        except (OSError, UnicodeError, json.JSONDecodeError):
            pass

    at = at or now_local()
    destination = root / at.strftime("%Y%m%dT%H%M%S%z")
    if destination.exists():
        raise RuntimeError(f"snapshot destination already exists: {destination}")
    destination.mkdir(parents=True)
    for source in files:
        shutil.copy2(source, destination / source.name)
    manifest = {
        "schema_version": 1,
        "platform": "hkjc",
        "meeting": meeting_dir.name,
        "created_at": at.isoformat(timespec="seconds"),
        "signature": signature,
        "files": manifest_files,
        "immutable_prediction_snapshot": True,
    }
    _atomic_json(destination / "manifest.json", manifest)
    return destination


def health_status(meeting_dir: Path) -> str:
    path = meeting_dir / "Data_Health.json"
    if not is_materialized_file(path):
        return "❌ Data health report missing"
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
        summary = report["summary"]
    except (KeyError, OSError, UnicodeError, json.JSONDecodeError):
        return "❌ Data health report invalid"
    coverage = summary.get("average_coverage_pct")
    coverage_text = "—" if coverage is None else f"{float(coverage):.1f}%"
    return (
        f"{report.get('status', 'unknown').upper()}｜{summary.get('races', 0)}場／"
        f"{summary.get('horses', 0)}匹｜{summary.get('errors', 0)} errors／"
        f"{summary.get('warnings', 0)} warnings｜coverage {coverage_text}"
    )


def run_watch(state: dict, state_path: Path, *, meeting: dict | None = None) -> int:
    try:
        meeting = meeting or discover_next_meeting()
    except Exception as exc:  # noqa: BLE001
        log(f"HKJC racecard poll temporary failure: {exc}")
        set_control_outcome("partial", reason="racecard_discovery_failed")
        return EXIT_TEMPORARY
    if meeting is None:
        log("HKJC dormant: official site has no future racecard yet")
        set_control_outcome("dormant", reason="no_future_racecard")
        return EXIT_OK
    key = f"{meeting['date']}|{meeting['venue']}"
    if state["notifications"].get("racecard_available") != key:
        notify(
            "🏇 HKJC 新賽季／下一賽日 racecard 已可用\n"
            f"{meeting['date']} {meeting['venue']}\n"
            "automation 會開始 pre-race extraction、scoring、data-health 同 snapshot。"
        )
        state["notifications"]["racecard_available"] = key
        save_state(state_path, state)
    set_control_outcome("succeeded", meeting=key)
    return EXIT_OK


DASHBOARD_DIR = PROJECT_ROOT / "Horse_Racing_Dashboard"
DASHBOARD_GENERATOR = DASHBOARD_DIR / "generate_static.py"
DASHBOARD_FETCH_LIVE = DASHBOARD_DIR / "scripts" / "fetch_live_snapshot.py"
DASHBOARD_LIVE_URL = os.environ.get(
    "WC_DASHBOARD_LIVE_SNAPSHOT_URL",
    "https://wongchoi-dashboard.pages.dev/dashboard-data.json",
)


def build_dashboard_snapshot(*meeting_dirs: Path) -> Path | None:
    """Live projection + this meeting -> a snapshot for `deploy.sh` to publish.

    Without it `deploy.sh` falls through to its "no scheduler snapshot" branch,
    which downloads the live projection and republishes it **unchanged**. AU
    passes `WC_DASHBOARD_BASE_SNAPSHOT` (au_daily_schedule); HKJC never did, so
    every prerace run reported a successful deploy while no HKJC meeting
    analysed after 2026-07-12 ever reached the board.

    Returns None on failure: the caller then deploys as before, which is no
    worse than the old behaviour and never publishes a half-built snapshot.
    """
    dirs = [Path(d) for d in meeting_dirs if d]
    if not dirs:
        return None
    work = dirs[-1] / "Dashboard_Snapshot"
    work.mkdir(parents=True, exist_ok=True)
    live = work / "live-dashboard-data.json"
    code, output = run_cmd(
        [sys.executable, str(DASHBOARD_FETCH_LIVE),
         "--url", DASHBOARD_LIVE_URL, "--output", str(live)],
        timeout=600,
    )
    if code != 0 or not live.exists():
        log(f"dashboard: 攞唔到 live snapshot（rc={code}）；交返 deploy.sh 自己處理")
        return None
    # Chain the merges: each meeting is folded into the result of the previous
    # one. Re-fetching live per meeting would silently keep only the last.
    base = live
    merged = None
    for index, meeting_dir in enumerate(dirs):
        merged = work / f"dashboard-data-{index}.json"
        code, output = run_cmd(
            [sys.executable, str(DASHBOARD_GENERATOR),
             "--base-snapshot", str(base),
             "--meeting-dir", str(meeting_dir),
             "--output-json", str(merged),
             "--output-html", str(work / f"dashboard-{index}.html")],
            timeout=1800,
        )
        if code != 0 or not merged.exists():
            log(f"dashboard: 合併 {meeting_dir.name} 失敗（rc={code}）：{output[-300:]}")
            return None
        base = merged
    return merged


def readiness_digest(meeting_dir: Path) -> str:
    """One compact line per fact from `Extraction_Readiness.json`.

    The failure notice used to paste `output[-1200:]` -- 1,200 characters of raw
    extractor stdout. Telegram clipped it, and what survived was the middle of a
    per-race checklist with the header gone, so the one thing a reader needs
    ("what is missing, and will it fix itself") was the part that got cut.
    Returns "" when the file is absent or unreadable: a missing digest must not
    stop the notice going out.
    """
    try:
        data = json.loads((meeting_dir / "Extraction_Readiness.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    expected = data.get("expected_races") or 0
    lines = [
        f"排位表 {data.get('racecards_ready', 0)}/{expected}"
        f" · 賽績 {data.get('formguides_ready', 0)}/{expected}"
        f" · 晨操 {data.get('trackwork_ready', 0)}/{expected}"
        f" · PDF {'✅' if data.get('starter_pdf_ready') else '❌'}"
    ]
    missing = []
    for race in data.get("races") or []:
        if not race.get("racecard_ok"):
            missing.append(f"R{race.get('race')}排位")
        if not race.get("formguide_ok"):
            missing.append(f"R{race.get('race')}賽績")
    if missing:
        shown = "、".join(missing[:8])
        more = f" 等 {len(missing)} 項" if len(missing) > 8 else ""
        lines.append(f"未齊：{shown}{more}")
    return "\n".join(lines)


def run_prerace(
    state: dict,
    state_path: Path,
    *,
    meeting: dict | None = None,
    force: bool = False,
) -> int:
    try:
        meeting = meeting or discover_next_meeting()
    except Exception as exc:  # noqa: BLE001
        notify(f"⚠️ HKJC pre-race discovery 暫時失敗：{exc}")
        set_control_outcome("partial", reason="racecard_discovery_failed")
        return EXIT_TEMPORARY
    if meeting is None:
        log("HKJC pre-race dormant: no racecard")
        set_control_outcome("dormant", reason="no_future_racecard")
        return EXIT_OK
    meeting_date = date.fromisoformat(meeting["date"])
    today = now_local().date()
    lead_days = max(0, int(os.environ.get("WC_HKJC_ANALYSIS_LEAD_DAYS", "2")))
    if meeting_date < today or ((meeting_date - today).days > lead_days and not force):
        log(f"HKJC pre-race not due: {meeting['date']} (lead={lead_days})")
        set_control_outcome("dormant", reason="meeting_not_due", meeting=meeting["date"])
        return EXIT_OK
    if force:
        log(f"HKJC manual force requested for {meeting['date']} {meeting['venue']}")

    meeting_dir = meeting_dir_for(meeting, create=True)
    code, output = run_cmd(
        [
            sys.executable,
            str(HKJC_ORCHESTRATOR),
            meeting["url"],
            "--auto",
            "--validate-engine",
            "--skip-cloudflare-deploy",
        ]
    )
    if code != 0:
        key = f"{meeting['date']}|{meeting['venue']}"
        record = state["meetings"].setdefault(key, {})
        streak = int(record.get("failure_streak") or 0) + 1
        temporary = code in (EXIT_TEMPORARY, 124)
        record.update(
            {
                "meeting_dir": str(meeting_dir),
                "last_prerace_attempt": stamp(),
                "last_prerace_exit": code,
                "failure_streak": streak,
                "recovery_pending": temporary,
                "last_failure_excerpt": output[-1200:],
            }
        )
        save_state(state_path, state)
        # First failure is actionable; later retries stay quiet except for
        # periodic reminders so an unpublished formguide cannot flood Telegram.
        if not temporary or streak == 1 or streak % 6 == 0:
            status = "資料未齊，30 分鐘後自動重試" if temporary else "需要人工檢查"
            digest = readiness_digest(meeting_dir)
            parts = [
                f"{'⏳' if temporary else '❌'} HKJC 未完成｜"
                f"{meeting['date']} {meeting['venue']}",
                f"exit={code}｜第{streak}次｜{status}",
            ]
            if digest:
                parts.append(digest)
            if not temporary:
                # A genuine failure still needs the extractor's own words, but
                # 300 characters of tail is enough to name the exception.
                parts.append(output[-300:].strip())
            elif not digest:
                parts.append(output[-300:].strip())
            notify("\n".join(parts))
        if temporary:
            set_control_outcome("partial", reason="prerace_source_incomplete", meeting=key)
            return EXIT_TEMPORARY
        set_control_outcome("failed", reason="prerace_pipeline_failed", meeting=key)
        return EXIT_FAILED
    try:
        snapshot = create_prediction_snapshot(meeting_dir)
    except Exception as exc:  # noqa: BLE001
        notify(f"❌ HKJC scoring 完成但 prediction snapshot 失敗：{exc}")
        set_control_outcome("failed", reason="prediction_snapshot_failed")
        return EXIT_FAILED
    try:
        evidence = record_prediction_decision_if_configured(
            domain=Domain.HKJC,
            event_id=f"{meeting['date']}|{meeting['venue']}",
            snapshot=snapshot,
            evidence_root=Path(
                os.environ.get(
                    "WONGCHOI_CONTROL_STATE_ROOT",
                    Path.home() / "WongChoiData" / "WongChoiControl",
                )
            )
            / "evidence",
            decision_state=DecisionState.RECOMMEND,
        )
    except Exception as exc:  # noqa: BLE001
        notify(f"❌ HKJC prediction evidence 寫入失敗，Dashboard 已攔截：{exc}")
        set_control_outcome("failed", reason="prediction_evidence_failed")
        return EXIT_FAILED
    snapshot_for_deploy = build_dashboard_snapshot(meeting_dir)
    deploy_env = ({"WC_DASHBOARD_BASE_SNAPSHOT": str(snapshot_for_deploy)}
                  if snapshot_for_deploy else None)
    deploy_code, deploy_output = run_cmd([str(DASHBOARD_DEPLOY)], timeout=1800,
                                         env_overlay=deploy_env)
    if deploy_code != 0:
        notify(f"⏳ HKJC evidence 已保存但 Dashboard deploy 失敗：{deploy_output[-1200:]}")
        set_control_outcome("partial", reason="dashboard_deploy_failed")
        return EXIT_TEMPORARY
    mirror = mirror_meeting(meeting_dir)

    key = f"{meeting['date']}|{meeting['venue']}"
    record = state["meetings"].setdefault(key, {})
    previous_snapshot = record.get("latest_snapshot")
    recovered = bool(record.get("failure_streak"))
    record.update(
        {
            "meeting_dir": str(meeting_dir),
            "last_prerace_success": stamp(),
            "latest_snapshot": str(snapshot),
            "latest_evidence": evidence,
            "last_mirror": mirror,
            "last_prerace_exit": 0,
            "failure_streak": 0,
            "recovery_pending": False,
            "last_failure_excerpt": "",
        }
    )
    save_state(state_path, state)
    if previous_snapshot != str(snapshot) or recovered:
        notify(
            f"✅ HKJC analysis {'自動恢復並' if recovered else ''}完成｜"
            f"{meeting['date']} {meeting['venue']}\n"
            f"{health_status(meeting_dir)}\n"
            f"Prediction snapshot：{snapshot.name}\nDashboard 已按 health gate 結果處理。"
            f"\nDrive mirror：{mirror['status']}（{mirror['copied']} files）",
            audience="content",
        )
    else:
        log(f"HKJC unchanged rerun: reuse snapshot {snapshot.name}; Telegram skipped")
    set_control_outcome(
        "succeeded",
        meeting=key,
        snapshot=str(snapshot),
        evidence=evidence,
        recovered=recovered,
    )
    return EXIT_OK


def _meeting_from_state_key(key: str) -> dict | None:
    try:
        date_text, venue = key.split("|", 1)
        date.fromisoformat(date_text)
    except (ValueError, TypeError):
        return None
    if venue not in {"ShaTin", "HappyValley"}:
        return None
    course = "ST" if venue == "ShaTin" else "HV"
    return {
        "date": date_text,
        "venue": venue,
        "course": course,
        "url": (
            "https://racing.hkjc.com/zh-hk/local/information/racecard"
            f"?racedate={date_text.replace('-', '/')}&Racecourse={course}&RaceNo=1"
        ),
    }


def run_recovery(state: dict, state_path: Path) -> int:
    """Retry only a due meeting previously classified as temporary/incomplete."""
    today = now_local().date()
    pending: list[tuple[str, dict]] = []
    changed = False
    for key, record in state.get("meetings", {}).items():
        if not isinstance(record, dict) or not record.get("recovery_pending"):
            continue
        meeting = _meeting_from_state_key(key)
        if meeting is None or date.fromisoformat(meeting["date"]) < today:
            record["recovery_pending"] = False
            changed = True
            continue
        pending.append((key, meeting))
    if changed:
        save_state(state_path, state)
    if not pending:
        log("HKJC recovery dormant: no pending temporary failure")
        set_control_outcome("dormant", reason="no_pending_recovery")
        return EXIT_OK
    key, meeting = sorted(pending, key=lambda item: item[0])[0]
    log(f"HKJC self-recovery retry: {key}")
    return run_prerace(state, state_path, meeting=meeting)


def pending_postrace_meetings(*, today: date | None = None) -> list[Path]:
    today = today or now_local().date()
    pending = []
    if not HK_RACING.exists():
        return pending
    try:
        paths = list(HK_RACING.iterdir())
    except OSError as exc:
        raise RuntimeError(
            f"HKJC data root unavailable for post-race scan: {HK_RACING}"
        ) from exc
    for path in paths:
        meeting_date = meeting_date_from_dir(path) if path.is_dir() else None
        if meeting_date is None or meeting_date >= today:
            continue
        if not list(path.glob("Race_*_Logic.json")):
            continue
        if is_materialized_file(path / "HKJC_Reflection_Report.md"):
            continue
        pending.append(path)
    return sorted(pending, key=lambda path: path.name)


def venue_from_meeting_dir(path: Path) -> str:
    for venue in ("ShaTin", "HappyValley"):
        if venue in path.name:
            return venue
    raise ValueError(f"cannot infer HKJC venue from meeting folder: {path.name}")


def refresh_dashboard_after_results(
    state: dict,
    state_path: Path,
    *,
    meeting_dirs: list[Path],
) -> bool:
    """Re-publish after settlement. It does NOT take the meeting off the board.

    The docstring used to claim reflected meetings disappear here. They must
    not: a settled card stays visible until the next one is analysed (Kelvin,
    2026-09-04), and that removal happens in the pre-race merge instead, where
    `collect_incremental_au_data` drops superseded HKJC meetings.

    What this step is for is the other half: re-merging the settled meeting so
    its reflected result replaces the pre-race card in place. Passing no
    snapshot made `deploy.sh` republish the live projection unchanged, so the
    board kept showing the pre-race state until the next meeting pushed it off.
    """
    # Merge each settled meeting again so its reflected result reaches the
    # board. Without a snapshot `deploy.sh` republishes the live projection
    # unchanged, so the card kept showing its pre-race state for ever.
    snapshot_for_deploy = build_dashboard_snapshot(*meeting_dirs)
    deploy_env = ({"WC_DASHBOARD_BASE_SNAPSHOT": str(snapshot_for_deploy)}
                  if snapshot_for_deploy else None)
    code, output = run_cmd([str(DASHBOARD_DEPLOY)], timeout=1800,
                           env_overlay=deploy_env)
    if code != 0:
        state["pending_dashboard_refresh"] = {
            "meeting_dirs": [str(path) for path in meeting_dirs],
            "failed_at": stamp(),
            "exit": code,
            "error_excerpt": output[-1200:],
        }
        save_state(state_path, state)
        log(f"HKJC post-race dashboard refresh pending: exit={code}")
        return False
    state.pop("pending_dashboard_refresh", None)
    state["last_postrace_dashboard_refresh"] = stamp()
    save_state(state_path, state)
    return True


def run_postrace(state: dict, state_path: Path) -> int:
    pending = pending_postrace_meetings()
    retry_payload = state.get("pending_dashboard_refresh") or {}
    retry_dirs = [Path(path) for path in retry_payload.get("meeting_dirs", [])]
    if not pending and not retry_dirs:
        log("HKJC post-race: no pending analyzed meeting")
        set_control_outcome("dormant", reason="no_pending_postrace")
        return EXIT_OK
    overall = EXIT_OK
    completed: list[Path] = []
    for meeting_dir in pending:
        meeting_date = meeting_date_from_dir(meeting_dir)
        if meeting_date is None:
            continue
        code, output = run_cmd(
            [
                sys.executable,
                str(REFLECTOR),
                str(meeting_dir),
                "--results-url",
                results_url(meeting_date),
                "--json",
            ]
        )
        key = meeting_dir.name
        if code != 0:
            # Results not published yet is expected on the first morning poll.
            log(f"post-race pending {key}: exit={code}")
            overall = max(overall, EXIT_TEMPORARY)
            continue
        report = meeting_dir / "HKJC_Reflection_Report.md"
        try:
            settlement = record_settlement_for_event(
                domain=Domain.HKJC,
                event_id=f"{meeting_date.isoformat()}|{venue_from_meeting_dir(meeting_dir)}",
                evidence_root=Path(
                    os.environ.get(
                        "WONGCHOI_CONTROL_STATE_ROOT",
                        Path.home() / "WongChoiData" / "WongChoiControl",
                    )
                )
                / "evidence",
                summary={"meeting": key, "reflector_exit": code},
                artifacts=[report],
            )
        except Exception as exc:  # noqa: BLE001
            log(f"settlement evidence pending {key}: {type(exc).__name__}: {exc}")
            overall = max(overall, EXIT_TEMPORARY)
            continue
        state["meetings"].setdefault(key, {}).update(
            {
                "last_reflector_success": stamp(),
                "report": str(report),
                "settlement_evidence": settlement,
            }
        )
        mirror = mirror_meeting(meeting_dir)
        state["meetings"][key]["last_mirror"] = mirror
        save_state(state_path, state)
        completed.append(meeting_dir)

    dashboard_targets = sorted({*retry_dirs, *completed}, key=lambda path: str(path))
    if dashboard_targets:
        refreshed = refresh_dashboard_after_results(
            state, state_path, meeting_dirs=dashboard_targets
        )
        if not refreshed:
            notify(
                "⚠️ HKJC 覆盤已完成，但 dashboard 更新失敗；"
                "排程會自動重試。\n"
                + "、".join(path.name for path in dashboard_targets)
            )
            set_control_outcome("partial", reason="dashboard_refresh_pending")
            return max(overall, EXIT_TEMPORARY)
        for meeting_dir in completed:
            notify(
                f"🏁 HKJC 覆盤完成｜{meeting_dir.name}\n"
                "正式賽果已對齊 pre-race prediction，forward corpus／Matrix review 已更新；"
                "已由 Wong Choi dashboard 移除已完成賽日。"
            )
    if overall == EXIT_TEMPORARY:
        set_control_outcome("partial", reason="results_pending")
    else:
        set_control_outcome(
            "succeeded",
            meetings=[path.name for path in completed],
        )
    return overall


def run_startup(state: dict, state_path: Path) -> int:
    """Catch up pre-race and post-race work once after macOS user login."""
    log("HKJC startup catch-up begins")
    prerace = run_prerace(state, state_path)
    prerace_status = str(_CONTROL_OUTCOME.get("status") or "")
    postrace = run_postrace(state, state_path)
    postrace_status = str(_CONTROL_OUTCOME.get("status") or "")
    results = (prerace, postrace)
    if EXIT_FAILED in results:
        set_control_outcome("failed", reason="startup_subrun_failed")
        return EXIT_FAILED
    if EXIT_TEMPORARY in results:
        set_control_outcome("partial", reason="startup_subrun_partial")
        return EXIT_TEMPORARY
    if "succeeded" in {prerace_status, postrace_status}:
        set_control_outcome("succeeded", reason="startup_catchup_complete")
    else:
        set_control_outcome("dormant", reason="startup_nothing_due")
    return EXIT_OK


def _parse_forward_start() -> date:
    raw = os.environ.get("WC_HKJC_FORWARD_START", DEFAULT_FORWARD_START.isoformat())
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return DEFAULT_FORWARD_START


def forward_meeting_count(*, start: date | None = None) -> int:
    start = start or _parse_forward_start()
    try:
        paths = list(HK_RACING.iterdir()) if HK_RACING.exists() else []
    except OSError:
        return 0
    return sum(
        1
        for path in paths
        if path.is_dir()
        and (meeting_date := meeting_date_from_dir(path)) is not None
        and meeting_date >= start
        and is_materialized_file(path / "HKJC_Reflection_Report.md")
    )


def _review_summary(payload: dict) -> str:
    coverage = payload.get("coverage") or {}
    models = payload.get("model_summary") or {}
    current = models.get("current_live") or models.get("published_mainline") or {}
    races = coverage.get("valid_races") or coverage.get("races") or current.get("races") or 0
    if not races:
        return "reference corpus 未 materialize／今次無可評估 races"
    fields = (
        ("gold", "Gold"),
        ("good", "Good"),
        ("min_threshold", "Pass"),
        ("champion", "Champion"),
        ("top3_has_champion", "Winner@3"),
    )
    metrics = "｜".join(f"{label} {current[key]}" for key, label in fields if key in current)
    return f"historical/reference {races} races" + (f"｜{metrics}" if metrics else "")


def process_candidate_gate(path: Path) -> tuple[str, str | None]:
    """Create a PR for an externally passed gate.  Never merge or deploy it."""
    if not is_materialized_file(path):
        return "none", None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("status") != "passed":
        return str(payload.get("status") or "not_passed"), None
    if payload.get("pr_url"):
        return "existing", str(payload["pr_url"])
    required = ("branch", "title", "body_file", "performance_summary")
    missing = [key for key in required if not payload.get(key)]
    if missing:
        raise ValueError("candidate gate missing: " + ", ".join(missing))
    body_file = Path(payload["body_file"])
    if not is_materialized_file(body_file):
        raise ValueError(f"candidate PR body is not materialized: {body_file}")
    code, output = run_cmd(
        [
            "gh",
            "pr",
            "create",
            "--base",
            "main",
            "--head",
            str(payload["branch"]),
            "--title",
            str(payload["title"]),
            "--body-file",
            str(body_file),
        ],
        timeout=120,
    )
    if code != 0:
        raise RuntimeError(f"gh pr create failed: {output[-1000:]}")
    url_match = re.search(r"https://github\.com/\S+/pull/\d+", output)
    if not url_match:
        raise RuntimeError("gh pr create succeeded but no PR URL was returned")
    payload["pr_url"] = url_match.group(0)
    payload["pr_created_at"] = stamp()
    payload["merge_requires_user_approval"] = True
    _atomic_json(path, payload)
    return "created", payload["pr_url"]


def run_weekly(state: dict, state_path: Path, candidate_gate: Path) -> int:
    code, output = run_cmd([sys.executable, str(WEIGHT_REVIEW), "--json"])
    if code != 0:
        notify(f"⚠️ HKJC weekly review 失敗｜exit={code}\n{output[-1000:]}")
        return EXIT_FAILED
    try:
        review = json.loads(output)
    except json.JSONDecodeError:
        notify("⚠️ HKJC weekly review JSON 無法解析，請人手檢查 log。")
        return EXIT_FAILED
    count = forward_meeting_count()
    forward_status = (
        "已達正式 forward diagnosis 門檻"
        if count >= 8
        else f"繼續觀察（距離 8 meetings 門檻尚欠 {8 - count}）"
    )
    gate_status, pr_url = process_candidate_gate(candidate_gate)
    gate_text = {
        "none": "冇候選 gate",
        "existing": "候選 PR 已存在",
        "created": "候選 non-draft PR 已建立，等待你批准",
    }.get(gate_status, f"候選 gate={gate_status}")
    message = (
        "📊 HKJC 每週模型 review\n"
        f"Forward：{count} meetings（由 {_parse_forward_start().isoformat()} 起）— {forward_status}\n"
        f"Reference：{_review_summary(review)}\n"
        f"Candidate：{gate_text}"
    )
    if is_materialized_file(candidate_gate):
        try:
            gate_payload = json.loads(candidate_gate.read_text(encoding="utf-8"))
            performance = str(gate_payload.get("performance_summary") or "").strip()
            recommendation = str(gate_payload.get("recommendation") or "").strip()
            if performance:
                message += f"\nCandidate performance：{performance}"
            if recommendation:
                message += f"\n建議：{recommendation}"
            elif gate_status in {"created", "existing"}:
                message += "\n建議：批准前先查看 paired metrics、cohort regression 同 rollback。"
        except (OSError, UnicodeError, json.JSONDecodeError):
            pass
    if pr_url:
        message += f"\n{pr_url}"
    notify(message)
    state["last_weekly_review"] = stamp()
    save_state(state_path, state)
    return EXIT_OK


def previous_calendar_month(today: date) -> tuple[date, date]:
    first_this_month = today.replace(day=1)
    last_previous_month = first_this_month - timedelta(days=1)
    return last_previous_month.replace(day=1), last_previous_month


def monthly_review_prompt(period_start: date, period_end: date) -> str:
    return (
        "請用約15分鐘，為 AU Wong Choi 同 HKJC Wong Choi 做月度整體 review，"
        f"評估期間只限 {period_start.isoformat()} 至 {period_end.isoformat()}。\n"
        "先凍結正式 pre-race prediction snapshots，再對齊官方賽果；嚴禁用賽後資料"
        "重建當時預測。請：\n"
        "1. 分開列 AU/HKJC 場數、有效樣本、Gold/Good/Pass、Top1 win/place、"
        "Top2 place coverage、Top4 coverage，同上月及既有 reference baseline 比較；"
        "沿用現有 canonical metric 定義，唔好重新解釋。\n"
        "2. 分析高賠率 Top2 包尾、熱門馬排模型底部但勝出/上名，按場地、途程、"
        "going、班次、檔位、步速、分差及 data coverage 分 cohort。\n"
        "3. 檢查每個 Matrix 維度、維度 crossover、draw score、資料缺失/neutral fallback，"
        "指出係真訊號、資料問題定細樣本。\n"
        "4. 檢查 racecard/formguide/results/horse identity/track-turf-distance alignment、"
        "placeholder、Top4 drift、排程漏跑、自動修復、Telegram、mirror 同 deploy。\n"
        "5. 只提出有 forward/holdout 證據、無 cohort regression 嘅 Matrix/ML candidate；"
        "唔好為 micro-adjustment 犧牲 Top2，亦唔好自動改 model。\n"
        "最後輸出：今月結論、可信度、要保持嘅地方、最多3個優先改善項、"
        "所需實驗、rollback gate，以及 Keep / Observe / Prepare PR 建議；任何 PR 都等我批准。"
    )


def run_monthly_review_reminder(state: dict, state_path: Path) -> int:
    period_start, period_end = previous_calendar_month(now_local().date())
    period_key = f"{period_start.isoformat()}|{period_end.isoformat()}"
    if state.get("last_monthly_review_reminder") == period_key:
        log(f"Wong Choi monthly review reminder already sent: {period_key}")
        return EXIT_OK
    message = (
        "🗓️ AU + HKJC Wong Choi 月度 review（約15分鐘）\n"
        f"期間：{period_start.isoformat()} 至 {period_end.isoformat()}\n\n"
        "請將以下 prompt 貼返入 Codex：\n\n"
        + monthly_review_prompt(period_start, period_end)
    )
    if not notify(message):
        return EXIT_FAILED
    state["last_monthly_review_reminder"] = period_key
    save_state(state_path, state)
    return EXIT_OK


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="HKJC Wong Choi daily automation")
    parser.add_argument(
        "--mode",
        choices=(
            "watch",
            "prerace",
            "recovery",
            "postrace",
            "startup",
            "weekly",
            "monthly",
        ),
        required=True,
    )
    parser.add_argument("--state-file", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--candidate-gate", type=Path, default=DEFAULT_CANDIDATE_GATE)
    parser.add_argument("--meeting-url", help="Optional explicit HKJC racecard URL")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Run an available future meeting even outside the normal lead-day window",
    )
    parser.add_argument(
        "--control-json",
        action="store_true",
        help="Emit one final machine-readable control-plane outcome.",
    )
    return parser.parse_args(argv)


def _meeting_from_url(url: str) -> dict:
    match = re.search(
        r"racedate=(20\d{2})/(\d{2})/(\d{2}).*?Racecourse=(ST|HV)", url, re.I
    )
    if not match:
        raise ValueError("meeting URL must contain racedate and Racecourse=ST/HV")
    meeting_date = date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    course = match.group(4).upper()
    return {
        "date": meeting_date.isoformat(),
        "course": course,
        "venue": "ShaTin" if course == "ST" else "HappyValley",
        "url": url,
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    _CONTROL_OUTCOME.clear()
    args.state_file.parent.mkdir(parents=True, exist_ok=True)
    lock_path = args.state_file.with_suffix(".lock")
    with lock_path.open("a", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            log("HKJC scheduler already running; skip overlapping invocation")
            set_control_outcome("blocked", reason="scheduler_locked")
            return emit_control_outcome(args, EXIT_OK)
        state = load_state(args.state_file)
        meeting = _meeting_from_url(args.meeting_url) if args.meeting_url else None
        try:
            if args.mode == "watch":
                code = run_watch(state, args.state_file, meeting=meeting)
            elif args.mode == "prerace":
                code = run_prerace(
                    state, args.state_file, meeting=meeting, force=args.force
                )
            elif args.mode == "recovery":
                code = run_recovery(state, args.state_file)
            elif args.mode == "postrace":
                code = run_postrace(state, args.state_file)
            elif args.mode == "startup":
                code = run_startup(state, args.state_file)
            elif args.mode == "monthly":
                code = run_monthly_review_reminder(state, args.state_file)
            else:
                code = run_weekly(state, args.state_file, args.candidate_gate)
        except Exception as exc:  # noqa: BLE001
            log(f"HKJC {args.mode} failed: {type(exc).__name__}: {exc}")
            notify(f"❌ HKJC {args.mode} automation failed：{type(exc).__name__}: {exc}")
            set_control_outcome("failed", reason=f"{type(exc).__name__}: {exc}")
            code = EXIT_FAILED
        return emit_control_outcome(args, code)


if __name__ == "__main__":
    raise SystemExit(main())

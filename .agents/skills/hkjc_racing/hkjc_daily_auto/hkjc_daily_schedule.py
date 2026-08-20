#!/usr/bin/env python3
"""HKJC Wong Choi unattended orchestration.

This module only coordinates the existing production pipeline.  It never owns
scoring logic and never merges a model candidate.  The four modes are designed
for launchd/cron:

* ``watch``: dormant off-season poll for the next materialized racecard.
* ``prerace``: run extraction -> Facts -> Logic -> scoring -> data-health -> deploy.
* ``postrace``: extract results and run the unified reflector once results exist.
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
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore


HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[3]
SHARED_RACING = PROJECT_ROOT / ".agents" / "skills" / "shared_racing" / "scripts"
for item in (PROJECT_ROOT, SHARED_RACING):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from racing_telegram import send_message  # noqa: E402
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


def run_cmd(cmd: list[str], *, timeout: int = 7200) -> tuple[int, str]:
    log("$ " + " ".join(str(part) for part in cmd))
    env = os.environ.copy()
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


def notify(message: str) -> None:
    try:
        result = send_message(message)
        if not result.get("ok"):
            log(f"Telegram warning: {result}")
    except Exception as exc:  # noqa: BLE001
        log(f"Telegram warning: {type(exc).__name__}: {exc}")


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
        return EXIT_TEMPORARY
    if meeting is None:
        log("HKJC dormant: official site has no future racecard yet")
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
    return EXIT_OK


def run_prerace(state: dict, state_path: Path, *, meeting: dict | None = None) -> int:
    try:
        meeting = meeting or discover_next_meeting()
    except Exception as exc:  # noqa: BLE001
        notify(f"⚠️ HKJC pre-race discovery 暫時失敗：{exc}")
        return EXIT_TEMPORARY
    if meeting is None:
        log("HKJC pre-race dormant: no racecard")
        return EXIT_OK
    meeting_date = date.fromisoformat(meeting["date"])
    today = now_local().date()
    lead_days = max(0, int(os.environ.get("WC_HKJC_ANALYSIS_LEAD_DAYS", "2")))
    if meeting_date < today or (meeting_date - today).days > lead_days:
        log(f"HKJC pre-race not due: {meeting['date']} (lead={lead_days})")
        return EXIT_OK

    meeting_dir = meeting_dir_for(meeting, create=True)
    code, output = run_cmd(
        [
            sys.executable,
            str(HKJC_ORCHESTRATOR),
            meeting["url"],
            "--auto",
            "--validate-engine",
        ]
    )
    if code != 0:
        notify(
            f"❌ HKJC automation 失敗｜{meeting['date']} {meeting['venue']}\n"
            f"exit={code}\n{output[-1200:]}"
        )
        return EXIT_TEMPORARY if code in (75, 124) else EXIT_FAILED
    try:
        snapshot = create_prediction_snapshot(meeting_dir)
    except Exception as exc:  # noqa: BLE001
        notify(f"❌ HKJC scoring 完成但 prediction snapshot 失敗：{exc}")
        return EXIT_FAILED
    mirror = mirror_meeting(meeting_dir)

    key = f"{meeting['date']}|{meeting['venue']}"
    state["meetings"].setdefault(key, {}).update(
        {
            "meeting_dir": str(meeting_dir),
            "last_prerace_success": stamp(),
            "latest_snapshot": str(snapshot),
            "last_mirror": mirror,
        }
    )
    save_state(state_path, state)
    notify(
        f"✅ HKJC analysis 完成｜{meeting['date']} {meeting['venue']}\n"
        f"{health_status(meeting_dir)}\n"
        f"Prediction snapshot：{snapshot.name}\nDashboard 已按 health gate 結果處理。"
        f"\nDrive mirror：{mirror['status']}（{mirror['copied']} files）"
    )
    return EXIT_OK


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


def run_postrace(state: dict, state_path: Path) -> int:
    pending = pending_postrace_meetings()
    if not pending:
        log("HKJC post-race: no pending analyzed meeting")
        return EXIT_OK
    overall = EXIT_OK
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
        state["meetings"].setdefault(key, {}).update(
            {"last_reflector_success": stamp(), "report": str(meeting_dir / "HKJC_Reflection_Report.md")}
        )
        mirror = mirror_meeting(meeting_dir)
        state["meetings"][key]["last_mirror"] = mirror
        save_state(state_path, state)
        notify(
            f"🏁 HKJC 覆盤完成｜{meeting_dir.name}\n"
            "正式賽果已對齊 pre-race prediction，forward corpus／Matrix review 已更新。"
        )
    return overall


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


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="HKJC Wong Choi daily automation")
    parser.add_argument("--mode", choices=("watch", "prerace", "postrace", "weekly"), required=True)
    parser.add_argument("--state-file", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--candidate-gate", type=Path, default=DEFAULT_CANDIDATE_GATE)
    parser.add_argument("--meeting-url", help="Optional explicit HKJC racecard URL")
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
    args.state_file.parent.mkdir(parents=True, exist_ok=True)
    lock_path = args.state_file.with_suffix(".lock")
    with lock_path.open("a", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            log("HKJC scheduler already running; skip overlapping invocation")
            return EXIT_OK
        state = load_state(args.state_file)
        meeting = _meeting_from_url(args.meeting_url) if args.meeting_url else None
        try:
            if args.mode == "watch":
                return run_watch(state, args.state_file, meeting=meeting)
            if args.mode == "prerace":
                return run_prerace(state, args.state_file, meeting=meeting)
            if args.mode == "postrace":
                return run_postrace(state, args.state_file)
            return run_weekly(state, args.state_file, args.candidate_gate)
        except Exception as exc:  # noqa: BLE001
            log(f"HKJC {args.mode} failed: {type(exc).__name__}: {exc}")
            notify(f"❌ HKJC {args.mode} automation failed：{type(exc).__name__}: {exc}")
            return EXIT_FAILED


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python < 3.9 fallback
    ZoneInfo = None

PROJECT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from tennis_wc.pipeline_readiness import analysis_retry_reasons, book_fixture_count


# Engine runs from local disk; analysis/archive folders stay on Google Drive
# so Kelvin keeps reading reports where he always has. Falls back to the
# repo parent when the override is unset or the Drive mount is unavailable.
def _usable_output_root(candidate: str | None) -> Path | None:
    """Can we actually WRITE there, not merely stat it.

    `is_dir()` is not a permission check. Under launchd the launcher's own
    probe -- reading one specific file in the Drive root -- fails on TCC and
    prints "Drive output root unreadable" every single run, 19 times so far,
    while `is_dir()` succeeds and the reports land on Drive anyway. So the log
    carried a warning that contradicted what the run then did, and nobody could
    act on it because it was not true.

    The same mistake in the other direction is already recorded on the AU side:
    a directory you can stat is not a directory you can read.
    """
    if not candidate:
        return None
    root = Path(candidate)
    probe = root / ".tennis_output_probe"
    try:
        probe.touch()
        probe.unlink()
    except OSError:
        return None
    return root


_OUTPUT_ROOT_OVERRIDE = os.environ.get("TENNIS_ANALYSIS_OUTPUT_ROOT")
ANTIGRAVITY_DIR = _usable_output_root(_OUTPUT_ROOT_OVERRIDE) or PROJECT_DIR.parent
ARCHIVE_DIR = ANTIGRAVITY_DIR / "Archieve Tennis Analysis"
# Overridable so the test suite cannot append to the log the live scheduler
# reads. It had been doing exactly that -- 866,594 lines and 28MB, with
# "Live network preflight passed" and "Notify skipped" entries from pytest
# interleaved with the real run history. A record that tests write into is not
# a record you can diagnose from.
LOG_DIR = Path(os.environ.get("TENNIS_LOG_DIR") or (PROJECT_DIR / "data" / "logs"))
PYTHON = PROJECT_DIR / ".venv" / "bin" / "python"
DASHBOARD_SETTLEMENT = (
    PROJECT_DIR.parent / "Horse_Racing_Dashboard" / "settle_dashboard_bets.py"
)
TIMEZONE = "Australia/Sydney"
# Nothing bounded this log before, and both passes are now scheduled daily. 8MB
# per generation and five generations keeps well over the two days the 0.2 exit
# test needs -- 29 days of real entries occupied 1,075 lines -- while the head
# and tail caps stop one card's JSON from being 99.88% of the file.
MAX_LOG_BYTES = 8 * 1024 * 1024
LOG_BACKUPS = 5
CAPTURED_HEAD_LINES = 40
CAPTURED_TAIL_LINES = 40


class TemporaryDataUnavailable(RuntimeError):
    """The scheduled run needs live data and should be retried later."""


class AnalysisBoardMissing(RuntimeError):
    """The board we price from is absent on a day it cannot legitimately be.

    Distinct from TemporaryDataUnavailable on purpose. "The book is not open
    yet" and "we can no longer see the book" were the same exception and the
    same log line until 2026-08-11, and the pipeline spent three days dark
    without anything looking wrong.
    """


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Daily Tennis Wong Choi scheduler runner.")
    parser.add_argument("--today", help="Override today's date in YYYY-MM-DD for testing.")
    parser.add_argument("--skip-analysis", action="store_true", help="Skip tomorrow run-daily.")
    parser.add_argument("--skip-review", action="store_true", help="Skip yesterday review/archive.")
    parser.add_argument("--no-archive", action="store_true", help="Review yesterday but do not move the folder.")
    parser.add_argument(
        "--source", default="manual",
        help="Who started this run: 'launchd' from the scheduled jobs, "
             "'manual' otherwise. Logged so the two-day exit test can tell a "
             "SCHEDULED success from someone running it by hand -- which is "
             "exactly the distinction that was missing when the morning pass "
             "stopped being run manually and nobody noticed for three days.",
    )
    parser.add_argument(
        "--notify-self-test",
        action="store_true",
        help="Verify the Telegram wiring WITHOUT sending a message (getMe) and exit.",
    )
    parser.add_argument(
        "--refresh-today",
        action="store_true",
        help="Same-day mode: run run-daily for TODAY only (no review, no archive). "
             "This is the pass that produces the betting card, and it is scheduled "
             "at 09:00 Sydney by com.antigravity.tennis-wong-choi.card. The 18:00 "
             "job asks Sportsbet for tomorrow, whose book is not open -- its "
             "listing returns two bytes -- so it settles, reviews and warms "
             "fixtures instead. 09:00 is also the price the backtest measured: "
             "earliest_odds=True reads each selection's first snapshot, which for "
             "almost every date is this run.",
    )
    args = parser.parse_args(argv)

    if args.notify_self_test:
        print(json.dumps(notify_self_test(), ensure_ascii=False, indent=2))
        return 0

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    for capture in ("launchd.card.stdout.log", "launchd.card.stderr.log",
                    "launchd.daily.stdout.log", "launchd.daily.stderr.log"):
        trim_launchd_capture(LOG_DIR / capture)
    headroom = disk_headroom()
    if not headroom["ok"]:
        # Loud and early. On 2026-08-11 the volume filled to zero bytes free; a
        # run that cannot write produces an absent card, which is what every
        # other failure produces too.
        log(f"DISK HEADROOM TOO LOW: {headroom['detail']} -- refusing to start. "
            f"A run that cannot write looks exactly like a run that found "
            f"nothing.")
        return 75
    lock_path = LOG_DIR / "tennis_daily_schedule.lock"
    with lock_path.open("w") as lock_file:
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            log("Another Tennis Wong Choi daily run is already active; exiting.")
            return 0

        log(f"Reports will be written under {ANTIGRAVITY_DIR}"
            + ("" if _OUTPUT_ROOT_OVERRIDE and str(ANTIGRAVITY_DIR) == _OUTPUT_ROOT_OVERRIDE
               else f" (requested {_OUTPUT_ROOT_OVERRIDE or 'nothing'}; not writable "
                    "from this context)"))

        today = date.fromisoformat(args.today) if args.today else local_today()
        yesterday = today - timedelta(days=1)
        tomorrow = today + timedelta(days=1)

        if args.refresh_today:
            log(f"Starting SAME-DAY refresh for {today} "
                f"(no review, no archive). run_source={args.source} mode=card")
            try:
                ensure_live_network()
                run_cli("init-db")
                analyse_next_day(today.isoformat(), today=today.isoformat())
            except subprocess.CalledProcessError as exc:
                log(f"Command failed with exit code {exc.returncode}: {' '.join(exc.cmd)}")
                return exc.returncode or 1
            except AnalysisBoardMissing as exc:
                log(f"BOARD MISSING: {exc}")
                notify_board_missing(str(exc))
                return 70
            except TemporaryDataUnavailable as exc:
                log(f"TEMPORARY DATA FAILURE: {exc}")
                return 75
            except Exception as exc:  # noqa: BLE001
                log(f"Same-day refresh failed: {exc}")
                return 1
            log("Same-day refresh complete.")
            return 0

        log(f"Starting scheduled workflow. today={today} review={yesterday} "
            f"analysis={tomorrow} run_source={args.source} mode=daily")

        try:
            ensure_live_network()
            run_cli("init-db")
            if not args.skip_review:
                review_payload = review_previous_day(yesterday.isoformat())
                sync_dashboard_settlements(yesterday.isoformat())
                if not args.no_archive:
                    archive_previous_day(yesterday.isoformat(), review_payload)
            if not args.skip_analysis:
                analyse_next_day(tomorrow.isoformat(), today=today.isoformat())
            # Sunday: emit the weekly validation review into today's folder.
            # weekday() == 6 is Sunday; guard so a bad review never fails the run.
            if today.weekday() == 6:
                try:
                    run_cli("weekly-review", "--date", today.isoformat())
                    log("Weekly review written.")
                except Exception as exc:  # noqa: BLE001
                    log(f"Weekly review skipped: {exc}")
        except subprocess.CalledProcessError as exc:
            log(f"Command failed with exit code {exc.returncode}: {' '.join(exc.cmd)}")
            return exc.returncode or 1
        except AnalysisBoardMissing as exc:
            log(f"BOARD MISSING: {exc}")
            notify_board_missing(str(exc))
            return 70
        except TemporaryDataUnavailable as exc:
            log(f"TEMPORARY DATA FAILURE: {exc}")
            return 75
        except Exception as exc:
            log(f"Workflow failed: {exc}")
            return 1

        log("Scheduled workflow complete.")
        return 0


def local_today() -> date:
    if ZoneInfo is not None:
        return datetime.now(ZoneInfo(TIMEZONE)).date()
    return datetime.now().date()


# The AU side already has a Telegram channel configured here; the tennis
# pipeline had no way to tell anyone anything, which is the other half of why
# three dark days went unnoticed. Same file, same chat, no new secrets.
NOTIFY_ENV_PATH = Path.home() / ".wongchoi_notify.env"


def _notify_env_values(path: Path | None = None) -> dict[str, str]:
    """Read the shared notification file without exporting secrets."""
    source = path or NOTIFY_ENV_PATH
    try:
        text = source.read_text()
    except OSError:
        return {}
    values: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, sep, value = line.partition("=")
        if sep:
            values[key.strip()] = value.strip().strip("'\"")
    return values


def notify_credentials(path: Path | None = None) -> tuple[str, str] | None:
    """(token, primary_chat_id) from the shared notify env file, or None."""
    values = _notify_env_values(path)
    token = values.get("WC_NOTIFY_TELEGRAM_TOKEN")
    chat = values.get("WC_NOTIFY_TELEGRAM_CHAT")
    return (token, chat) if token and chat else None


def notify_targets(path: Path | None = None, *, audience: str = "primary") -> list[str]:
    """Resolve the operational or content audience, preserving stable order.

    Operational health/failure messages stay with the primary owner. Betting
    content also goes to WC_NOTIFY_TELEGRAM_EXTRA (Heison in production).
    Extras may be comma- or semicolon-separated; duplicates are removed so a
    copied chat ID cannot cause the same betting card to arrive twice.
    """
    values = _notify_env_values(path)
    primary = values.get("WC_NOTIFY_TELEGRAM_CHAT")
    if not primary:
        return []
    targets = [primary]
    if audience == "content":
        raw = values.get("WC_NOTIFY_TELEGRAM_EXTRA", "")
        targets.extend(item.strip() for item in re.split(r"[,;]", raw) if item.strip())
    return list(dict.fromkeys(targets))


def _telegram_chunks(text: str, *, limit: int = 3800) -> list[str]:
    """Split long cards on line boundaries below Telegram's 4096-char cap."""
    chunks: list[str] = []
    current = ""
    for line in text.splitlines():
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
        while len(line) > limit:
            chunks.append(line[:limit])
            line = line[limit:]
        current = line
    if current:
        chunks.append(current)
    return chunks or [""]


def notify(
    text: str,
    *,
    path: Path | None = None,
    audience: str = "primary",
) -> bool:
    """Best effort to every target. One failed chat never blocks the others."""
    credentials = notify_credentials(path)
    if not credentials:
        log("Notify skipped: no Telegram credentials in "
            f"{path or NOTIFY_ENV_PATH}")
        return False
    token, _primary = credentials
    targets = notify_targets(path, audience=audience)
    sent = 0
    attempted = 0
    import urllib.parse
    import urllib.request

    for chat in targets:
        target_ok = True
        for chunk in _telegram_chunks(text):
            attempted += 1
            try:
                body = urllib.parse.urlencode({"chat_id": chat, "text": chunk}).encode()
                request = urllib.request.Request(
                    f"https://api.telegram.org/bot{token}/sendMessage", data=body
                )
                with urllib.request.urlopen(request, timeout=15) as response:
                    target_ok = target_ok and 200 <= response.status < 300
            except Exception as exc:  # noqa: BLE001 - never let this fail a run
                target_ok = False
                log(f"Notify failed for one {audience} recipient: {exc}")
                break
        sent += int(target_ok)
    ok = bool(targets) and sent == len(targets)
    log(
        f"Notify {audience}: {sent}/{len(targets)} recipients succeeded "
        f"across {attempted} request(s)."
    )
    return ok


def notify_self_test(path: Path | None = None) -> dict:
    """Prove the notification path works WITHOUT sending anything to anybody.

    `getMe` is a read-only Telegram call: it confirms the token is valid and
    names the bot, and it puts no message in anyone's chat. That makes the
    wiring verifiable at any time, including from a test run, without deciding
    on Kelvin's behalf that his phone should buzz.
    """
    credentials = notify_credentials(path)
    if not credentials:
        return {"ok": False, "reason": "no credentials",
                "path": str(path or NOTIFY_ENV_PATH)}
    token, chat = credentials
    targets = notify_targets(path, audience="content")
    result: dict = {
        "chat_id_present": bool(chat),
        "configured_content_recipients": len(targets),
    }
    try:
        import json as _json
        import urllib.parse
        import urllib.request

        with urllib.request.urlopen(
            f"https://api.telegram.org/bot{token}/getMe", timeout=15
        ) as response:
            body = _json.loads(response.read().decode())
        result["ok"] = bool(body.get("ok"))
        result["bot"] = ((body.get("result") or {}).get("username"))
        reachable = 0
        for target in targets:
            request = urllib.request.Request(
                f"https://api.telegram.org/bot{token}/getChat?"
                + urllib.parse.urlencode({"chat_id": target})
            )
            try:
                with urllib.request.urlopen(request, timeout=15) as response:
                    chat_body = _json.loads(response.read().decode())
                reachable += int(bool(chat_body.get("ok")))
            except Exception:  # noqa: BLE001 - count only; do not leak IDs/names
                pass
        result["reachable_content_recipients"] = reachable
        result["ok"] = result["ok"] and reachable == len(targets)
    except Exception as exc:  # noqa: BLE001
        result["ok"] = False
        result["reason"] = str(exc)
    return result


def daily_bet_message(
    match_date: str, report_path: str | Path | None, *, early: bool = False
) -> str:
    """Render the official report's formal recommendations for Telegram.

    The report is the source of truth. This deliberately ignores watchlists,
    research-only signals and match-winner model-edge rows, so a reference row
    can never be promoted into a "what to bet" push by accident.

    ``early`` renders the evening pass over tomorrow's board. That board is
    genuinely half-open -- measured 2026-08-16, the 18:00 run priced 12 of the
    next day's matches against 47-56 on the day itself, and rescanning at 21:18
    moved that to 13 -- so the framing has to say so. It is sent anyway because
    matches starting in the Sydney small hours are otherwise never pushed at
    all: the 09:24 card covers a Sydney-dated day whose first nine hours have
    already happened.
    """
    if not report_path:
        raise ValueError("run-daily returned no report_path")
    report = Path(report_path)
    text = report.read_text(encoding="utf-8")
    start_marker = "## 🎯 今日落注建議"
    start = text.find(start_marker)
    if start < 0:
        raise ValueError(f"formal recommendation section missing in {report}")
    section = text[start:].splitlines()
    body: list[str] = []
    for line in section[1:]:
        if line.startswith("## "):
            break
        body.append(line.rstrip())

    if early:
        result = [
            f"🎾 Tennis Wong Choi｜{match_date} 早報（前一晚）",
            "🌙 呢張係俾凌晨開波嗰批 —— 佢哋喺明早 09:00 張卡出之前就已經開咗波，唔會再推第二次。",
            "⚠️ 盤口未開齊，明早會有完整一張；呢張淨係補返夜晚嗰段。",
        ]
    else:
        result = [f"🎾 Tennis Wong Choi｜{match_date}", "🎯 今日落注建議"]
    conclusion_seen = False
    in_pick = False
    for line in body:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("⚠️") or (not conclusion_seen and stripped.startswith("·")):
            result.append(stripped)
        elif stripped.startswith("今日結論："):
            conclusion_seen = True
            result.append(stripped)
        elif stripped.startswith("（") and conclusion_seen and not in_pick:
            result.append(stripped)
        elif stripped.startswith("### 注 "):
            in_pick = True
            result.extend(["", stripped.removeprefix("### ")])
        elif in_pick and stripped.startswith(("- 選擇：", "- 腳 ", "- 開賽：", "- 賠率：", "- 合併賠率：", "- 校準命中概率：", "- 公式可信度：")):
            result.append("• " + stripped.removeprefix("- "))

    if not conclusion_seen:
        raise ValueError(f"formal recommendation conclusion missing in {report}")
    if in_pick:
        result.extend(["", "只跟以上正式推薦；觀察板、研究訊號同 Match-winner 參考單唔落。"])
        if early:
            result.append("盤口仲會郁，落注前格返價；明早完整一張會覆蓋白天嗰批。")
    elif early:
        result.extend(["", "明日凌晨場暫時無正式推薦；明早 09:00 有完整一張。"])
    else:
        result.extend(["", "今日無正式推薦，唔好用觀察板或研究訊號代替落注。"])
    return "\n".join(result)


def notify_daily_bets(match_date: str, payload: dict, *, early: bool = False) -> bool:
    """Send the completed card to Kelvin + Heison.

    ``early`` is the evening pass over the next Sydney day; see
    :func:`daily_bet_message` for why a half-open board is still worth sending.
    """
    label = "早報投注訊息" if early else "投注訊息"
    try:
        message = daily_bet_message(match_date, payload.get("report_path"), early=early)
    except Exception as exc:  # noqa: BLE001 - reporting must not break analysis
        log(f"Betting-card notification skipped: {exc}")
        notify(
            f"🎾 Tennis Wong Choi {label}未能整理\n"
            f"日期：{match_date}\n原因：{exc}",
            audience="primary",
        )
        return False
    return notify(message, audience="content")


def _intish_or_zero(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def daily_health_line(match_date: str, payload: dict) -> str:
    """One line a person can read, every day, including days with no bet.

    An empty card is a legitimate output. That is exactly why it hid a broken
    pipeline for two months once, and three dark days again in August: nothing
    errored, nothing printed, and "no bet today" and "no pipeline today" looked
    identical from the outside. A number that is always emitted cannot be
    confused with a number that stopped being emitted.
    """
    coverage = payload.get("odds_coverage") or {}
    readiness = payload.get("readiness") or {}
    trackers = (payload.get("tracker_sync") or {}).get("clv") or {}
    deploy = payload.get("cloudflare_deploy") or {}
    props = _prop_counts(match_date)
    fixtures = coverage.get("fixtures")
    priced = coverage.get("priced_matches")
    # The gate divides by the BOOK, not by the calendar, so the health line has
    # to show the book -- otherwise "賽事 176 · 有價 57" reads as 32% to a person
    # while the gate is reading 65%, and the two disagreeing silently is exactly
    # how 2026-08-24 spent three passes blocked on a number nobody could see.
    book = book_fixture_count(coverage)
    fixtures_cell = (
        f"賽事 {fixtures}" if book == _intish_or_zero(fixtures)
        else f"賽事 {fixtures} (盤面 {book})"
    )
    return (
        f"🎾 {match_date} · {readiness.get('severity') or readiness.get('status') or '?'}"
        f" ({readiness.get('horizon') or '?'})\n"
        f"{fixtures_cell} · 有價 {priced} · 已分析 {payload.get('matches_analysed')}\n"
        f"prop {props['props']} · value {props['value']} · "
        f"未結算 {props['pending_older']} (三日前)\n"
        f"CLV 同步 {trackers.get('synced', 0)} (prop {trackers.get('props_synced', 0)}, "
        f"無標識 {trackers.get('props_without_feed_identity', 0)}) · "
        f"已計 {trackers.get('clv_updated', 0)}\n"
        f"Dashboard {deploy.get('status') or 'unknown'}"
    )


def _prop_counts(match_date: str) -> dict:
    """Counts straight from the tracker; a health line that guesses is no use."""
    try:
        import sqlite3

        database = os.environ.get("DATABASE_URL", "")
        path = database.split("sqlite:///", 1)[-1] if "sqlite" in database else str(
            PROJECT_DIR / "tennis_wc.db"
        )
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        row = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(is_value),0) FROM prop_tracker "
            "WHERE match_date = ?", (match_date,)
        ).fetchone()
        older = conn.execute(
            "SELECT COUNT(*) FROM prop_tracker WHERE result_status='PENDING' "
            "AND is_value=1 AND match_date <= date(?, '-3 day')", (match_date,)
        ).fetchone()
        conn.close()
        return {"props": row[0], "value": row[1], "pending_older": older[0]}
    except Exception as exc:  # noqa: BLE001 - a health line must not fail the run
        log(f"Health counts unavailable: {exc}")
        return {"props": "?", "value": "?", "pending_older": "?"}


def notify_board_missing(detail: str) -> bool:
    return notify(
        "🎾 Tennis Wong Choi — 出唔到咭\n"
        f"{detail}\n"
        "同一句訊息以前代表「盤未開」,而家淨係代表「本應開咗但見唔到」。"
    )


PERFORMANCE_FAMILY_LABELS = {
    "player_aces": "球員 Ace",
    "player_double_faults": "球員雙錯",
    "player_total_games": "球員總局數",
    "player_win_a_set": "贏一盤",
    "first_set_winner": "首盤勝方",
    "player_game_handicap": "球員讓局",
    "player_set_handicap": "球員讓盤",
    "player_exact_set_score": "盤數波膽",
}


def daily_performance_snapshot(match_date: str) -> dict:
    """One read-only, auditable performance view for the Telegram review.

    Paper recommendations and bets recorded in the manual live ledger are
    deliberately separate.  Treating every generated recommendation as money
    actually staked was the main reason old summaries looked more certain than
    the account evidence justified.
    """
    from tennis_wc.database.db import get_connection
    from tennis_wc.props.settlement import (
        model_vs_market_scorecard,
        prop_roi_report,
    )
    from tennis_wc.props.strategy import recommendation_gate

    next_date = (date.fromisoformat(match_date) + timedelta(days=1)).isoformat()
    recent_14_start = (
        date.fromisoformat(match_date) - timedelta(days=13)
    ).isoformat()
    with get_connection() as conn:
        paper = prop_roi_report(conn, as_of_date=next_date)
        day = prop_roi_report(
            conn, as_of_date=next_date, since_date=match_date
        )
        recent_14 = prop_roi_report(
            conn, as_of_date=next_date, since_date=recent_14_start
        )
        scorecard = model_vs_market_scorecard(conn, as_of_date=next_date)
        gate = recommendation_gate(scorecard, paper)
        live_rows = conn.execute(
            """
            SELECT p.result_status, p.market_key, p.profit_loss_units,
                   b.stake_units, b.odds_taken
            FROM prop_live_bets b
            JOIN prop_tracker p ON p.id = b.prop_id
            WHERE p.match_date <= ?
              AND p.result_status IN ('WON', 'LOST', 'VOID')
            ORDER BY p.match_date, p.id
            """,
            (match_date,),
        ).fetchall()
        pending_value_older = conn.execute(
            """
            SELECT COUNT(*) FROM prop_tracker
            WHERE result_status = 'PENDING' AND is_value = 1
              AND match_date <= date(?, '-3 day')
            """,
            (match_date,),
        ).fetchone()[0]

    settled_live = [row for row in live_rows if row["result_status"] != "VOID"]
    live_staked = sum(float(row["stake_units"] or 0.0) for row in settled_live)
    live_pnl = sum(
        float(row["stake_units"] or 0.0) * (float(row["odds_taken"]) - 1.0)
        if row["result_status"] == "WON"
        else -float(row["stake_units"] or 0.0)
        for row in settled_live
    )
    return {
        "paper": {
            "daily": day.get("formal_player_prop_profile") or {},
            "recent_14": recent_14.get("formal_player_prop_profile") or {},
            "overall": paper.get("formal_player_prop_profile") or {},
            "families": paper.get("by_family_formal_profile") or {},
        },
        "live": {
            "settled": len(settled_live),
            "wins": sum(row["result_status"] == "WON" for row in settled_live),
            "pnl": round(live_pnl, 3),
            "roi": round(live_pnl / live_staked, 4) if live_staked else None,
        },
        "scorecard": scorecard,
        "gate": gate,
        "pending_value_older": int(pending_value_older),
    }


def _performance_pct(value) -> str:
    return "—" if value is None else f"{float(value):+.1%}"


def _performance_units(value) -> str:
    return f"{float(value or 0):+.3f}u"


def daily_performance_message(match_date: str, snapshot: dict) -> str:
    paper = snapshot.get("paper") or {}
    daily = paper.get("daily") or {}
    recent_14 = paper.get("recent_14") or {}
    overall = paper.get("overall") or {}
    live = snapshot.get("live") or {}
    scorecard = snapshot.get("scorecard") or {}
    gate = snapshot.get("gate") or {}
    model = (scorecard.get("model") or {}).get("brier")
    market = (scorecard.get("market") or {}).get("brier")
    enabled = gate.get("enabled_families") or []

    lines = [
        f"📊 Tennis Wong Choi｜{match_date} 每日績效",
        "口徑：正式 player-prop 推薦；紙上盤同已登記實盤分開。",
        (
            f"當日 {daily.get('settled', 0)} 注｜"
            f"{daily.get('wins', 0)} 中｜{_performance_units(daily.get('pnl'))}｜"
            f"ROI {_performance_pct(daily.get('roi'))}"
        ),
        (
            f"近14日 {recent_14.get('settled', 0)} 注｜"
            f"{recent_14.get('wins', 0)} 中｜{_performance_units(recent_14.get('pnl'))}｜"
            f"ROI {_performance_pct(recent_14.get('roi'))}"
        ),
        (
            f"紙上盤累計 {overall.get('settled', 0)} 注｜"
            f"{_performance_units(overall.get('pnl'))}｜"
            f"ROI {_performance_pct(overall.get('roi'))}"
        ),
        (
            f"實盤 {live.get('settled', 0)} 注｜{_performance_units(live.get('pnl'))}｜"
            f"ROI {_performance_pct(live.get('roi'))}"
        ),
        "",
        "逐市場（正式紙上盤）：",
    ]
    families = paper.get("families") or {}
    for family, label in PERFORMANCE_FAMILY_LABELS.items():
        stats = families.get(family) or {}
        lines.append(
            f"• {label}: {stats.get('settled', 0)} 注｜"
            f"{_performance_units(stats.get('pnl'))}｜ROI {_performance_pct(stats.get('roi'))}｜"
            f"近 {stats.get('short_term_settled', stats.get('recent_settled', 0)) or 0} 注 "
            f"{_performance_pct(stats.get('short_term_roi', stats.get('recent_roi')))}"
        )
    if model is not None and market is not None:
        comparison = "Model 較佳" if float(model) < float(market) else "Market 較佳"
        lines.extend([
            "",
            f"概率校準：Model {float(model):.4f}｜Market {float(market):.4f}｜{comparison}",
        ])
    lines.append(
        "策略閘：" + ("、".join(enabled) if enabled else "RESEARCH_ONLY（暫停正式下注）")
    )
    lines.append(f"三日前 value 未結算 {snapshot.get('pending_value_older', 0)} 筆")
    lines.append("ROI 係歷史樣本結果，唔保證之後為正；只會用未來 OOS 數據升級市場。")
    return "\n".join(lines)


def notify_daily_performance(match_date: str) -> bool:
    try:
        snapshot = daily_performance_snapshot(match_date)
        message = daily_performance_message(match_date, snapshot)
    except Exception as exc:  # noqa: BLE001 - review must still complete
        log(f"Daily-performance notification skipped: {exc}")
        return False
    return notify(message, audience="content")


def ensure_live_network() -> None:
    """Fail before creating misleading reports when the task has no network."""
    payload = run_cli_json("network-check")
    diagnosis = str(payload.get("diagnosis") or "unknown")
    if diagnosis != "network_ready":
        raise TemporaryDataUnavailable(
            f"live network preflight failed ({diagnosis}); rerun the scheduled "
            "script with host network access"
        )
    log("Live network preflight passed.")


def review_previous_day(match_date: str) -> dict:
    top_up_lowtier_corpus(match_date)
    log(f"Reviewing previous day: {match_date}")
    payload = run_cli_json("review-date", "--date", match_date)
    report_path = payload.get("review_report_path")
    qa_path = payload.get("settlement_qa_report_path")
    log(f"Review written. summary={report_path or 'none'} qa={qa_path or 'none'}")
    if os.environ.get("TENNIS_NOTIFY_PERFORMANCE") == "1":
        notify_daily_performance(match_date)
    return payload


def sync_dashboard_settlements(match_date: str) -> bool:
    """Apply native results to confirmed dashboard bets, best effort.

    This runs after the domain review has settled its own trackers.  The
    exporter only proposes results backed by those native tables, and the
    Cloudflare endpoint matches by immutable recommendation ID while retaining
    Kelvin's actual odds and stake.  A dashboard/network failure must not erase
    an otherwise successful review or stop tomorrow's card.
    """
    if not DASHBOARD_SETTLEMENT.is_file():
        log(f"Dashboard settlement skipped: missing {DASHBOARD_SETTLEMENT}")
        return False
    command = [
        str(PYTHON), str(DASHBOARD_SETTLEMENT),
        "--date", match_date, "--apply",
    ]
    try:
        result = subprocess.run(
            command,
            cwd=str(PROJECT_DIR.parent),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=90,
        )
    except Exception as exc:  # noqa: BLE001 - dashboard sync is downstream
        log(f"WARNING: dashboard auto-settlement failed: {exc}")
        return False
    output = (result.stdout or "").strip()
    if output:
        log(f"Dashboard settlement: {output[-1200:]}")
    if result.returncode:
        log(f"WARNING: dashboard auto-settlement exit {result.returncode}")
        return False
    return True


def top_up_lowtier_corpus(match_date: str) -> None:
    """Add yesterday's lower-tier results to the corpus Elo is built from.

    The Sackmann/TennisMyLife files carry no ITF, so without this daily top-up
    the ITF half of the board never accumulates a rating -- and ITF is ~85% of
    what we price.
    """
    try:
        payload = run_cli_json("build-lowtier-corpus", "--start", match_date)
        log(f"Lower-tier corpus: {payload.get('matches')} matches, "
            f"{payload.get('players_created')} new players")
    except Exception as exc:  # a feed hiccup must not stop the day's analysis
        log(f"WARNING: lower-tier corpus top-up failed: {exc}")


def analyse_next_day(match_date: str, *, today: str | None = None) -> None:
    """Price a date. How an empty board is read depends on WHICH date.

    Sportsbet does not open tomorrow's book in the evening -- its own listing
    returns HTTP 200 and two bytes -- so the 18:00 warm pass finding nothing is
    the ordinary state of the world. The 09:00 pass finding nothing never is.
    Until 2026-08-11 both raised the same TEMPORARY DATA FAILURE, and the
    pipeline ran three days dark while every evening looked normal.
    """
    from tennis_wc.pipeline_readiness import (
        HORIZON_NEXT_DAY, SEVERITY_ERROR, SEVERITY_EXPECTED_EMPTY,
        SEVERITY_RETRY, analysis_readiness, horizon_for,
    )

    horizon = horizon_for(match_date, today or local_today().isoformat())
    log(f"Running analysis for {match_date} (horizon={horizon})")
    payload = run_cli_json("run-daily", "--date", match_date)
    matches = intish(payload.get("matches_analysed"))
    source_errors = payload.get("source_errors") or []
    log(
        "Analysis complete. "
        f"matches={payload.get('matches_analysed')} "
        f"valid={payload.get('valid_feature_snapshots')} "
        f"dir={payload.get('analysis_dir')}"
    )

    # A zero-match run caused by upstream data sources failing is NOT a normal
    # "no bets today" outcome - it means the pipeline never saw any matches.
    # Make it loud so it is not silently mistaken for a quiet betting day.
    if matches == 0 and source_errors:
        sources = ", ".join(str(err.get("source", "?")) for err in source_errors)
        log(f"WARNING: 0 matches analysed because data sources failed: {sources}. Details: {compact_json(source_errors)}")

    # run-daily owns tracker sync and post-success dashboard deployment.  Keep
    # this wrapper scheduling-only so manual and scheduled analysis behave the
    # same and a scheduled run cannot sync or deploy twice.
    tracker_sync = payload.get("tracker_sync") or {}
    deploy = payload.get("cloudflare_deploy") or {}
    log(
        "Pipeline-owned post-run steps complete. "
        f"trackers={compact_json(tracker_sync)} "
        f"dashboard={compact_json(deploy)}"
    )

    # The database had no retention of any kind and reached 2.6GB, at which
    # point `disk_headroom` -- which wants two database-widths -- started
    # refusing to run recovery on a volume with 3.7GB free. Growth is the bug,
    # so this runs every day rather than being cleaned up by hand when it next
    # becomes an outage. No VACUUM here on purpose: rebuilding the file needs
    # room for a second copy, and the blanked pages are reused in place.
    try:
        pruned = run_cli_json("prune-raw-responses", "--keep-days", "7")
        if pruned.get("rows"):
            log(
                f"Pruned {pruned['rows']} superseded API payloads "
                f"({pruned['bytes_freed'] / 1024 ** 2:.0f}MB reclaimed in-file)."
            )
    except Exception as exc:  # noqa: BLE001 - housekeeping must not lose the day
        log(f"Retention step skipped: {exc}")

    readiness = analysis_readiness(payload, horizon=horizon)
    observed = "; ".join(readiness["observed"]) or "none"

    # Emitted on EVERY outcome, before any raise, so a quiet day and a dead
    # pipeline stop looking the same from the outside.
    line = daily_health_line(match_date, payload)
    log("HEALTH " + line.replace("\n", " | "))
    coverage = payload.get("odds_coverage") or {}
    log("HEALTH_JSON " + json.dumps({
        "date": match_date,
        "horizon": horizon,
        "severity": readiness["severity"],
        "fixtures": coverage.get("fixtures"),
        "priced": coverage.get("priced_matches"),
        "analysed": payload.get("matches_analysed"),
        "deploy": deploy.get("status"),
    }, ensure_ascii=False))
    # The push is OPT-IN. The line is always written to the log, but deciding
    # that Kelvin's phone should buzz every morning is his call, not this
    # script's. Set TENNIS_NOTIFY_HEALTH=1 in the launcher to turn it on.
    if horizon != HORIZON_NEXT_DAY and os.environ.get("TENNIS_NOTIFY_HEALTH") == "1":
        notify(line)
    if readiness["severity"] == SEVERITY_EXPECTED_EMPTY:
        # Not a failure. The warm pass exists to discover fixtures; the prices
        # arrive on the morning pass, which is where the card comes from.
        log(f"Book not open for {match_date} yet, as expected on a "
            f"{HORIZON_NEXT_DAY} pass ({observed}). Fixtures warmed; the card "
            "comes from the 09:00 same-day pass.")
        return
    if readiness["severity"] == SEVERITY_ERROR:
        raise AnalysisBoardMissing(
            f"analysis for {match_date} is BROKEN, not merely early: {observed}"
        )
    if readiness["severity"] == SEVERITY_RETRY:
        raise TemporaryDataUnavailable(
            f"analysis for {match_date} is incomplete: {observed}"
        )
    # Failed/retry cards have already raised above rather than masquerading as
    # "no bet" advice, so anything reaching here is a completed pass.
    #
    # The evening pass used to be barred from sending outright, on the grounds
    # that tomorrow's board is half-open. It is -- 12 priced next-day matches
    # against 47-56 same-day, measured 2026-08-16 -- but the bar had a cost
    # nobody had counted: `match_date` is the Sydney calendar date, so matches
    # in the small hours are over before the 09:24 card exists. 35.9% of the
    # matches on a card had already started when it was pushed. A half-open
    # board that says it is half-open beats no card at all for that cohort.
    #
    # Separate switch from TENNIS_NOTIFY_BETS on purpose: the evening card can
    # be turned off without touching the morning one, and vice versa.
    if horizon == HORIZON_NEXT_DAY:
        if os.environ.get("TENNIS_NOTIFY_EARLY_BETS") == "1":
            notify_daily_bets(match_date, payload, early=True)
    elif os.environ.get("TENNIS_NOTIFY_BETS") == "1":
        notify_daily_bets(match_date, payload)


def archive_previous_day(match_date: str, review_payload: dict) -> None:
    source = ANTIGRAVITY_DIR / f"{match_date} Tennis Analysis"
    destination = ARCHIVE_DIR / source.name

    if not source.exists():
        if destination.exists():
            log(f"Archive already contains {destination.name}; no live folder to move.")
            return
        log(f"No analysis folder found for {match_date}; archive skipped.")
        return

    if not can_archive(review_payload):
        log(f"Review did not confirm result extraction for {match_date}; archive skipped.")
        return

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    final_destination = destination
    if final_destination.exists():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        final_destination = ARCHIVE_DIR / f"{source.name} rerun {stamp}"

    shutil.move(str(source), str(final_destination))
    log(f"Archived {source.name} -> {final_destination}")


def can_archive(payload: dict) -> bool:
    if not payload.get("review_report_path") or not payload.get("settlement_qa_report_path"):
        return False

    settlement = payload.get("settlement") or {}
    tracker = settlement.get("tracker_settlement") or {}
    combo = settlement.get("combo_settlement") or {}
    result_health = ((settlement.get("auto_refresh") or {}).get("results") or {})
    tml = result_health.get("tennismylife") or {}
    resolver = result_health.get("resolver") or {}

    extracted = any(
        intish(value) > 0
        for value in (
            result_health.get("imported"),
            result_health.get("winners_seen"),
            result_health.get("lookup_winners_seen"),
            tml.get("results_imported"),
            tml.get("rows_seen"),
            tml.get("lookup_rows_seen"),
            resolver.get("event_result_imported"),
            resolver.get("provider_rows_imported"),
            resolver.get("local_history_imported"),
            settlement.get("settled"),
            tracker.get("settled"),
            combo.get("settled"),
        )
    )
    pending = sum(
        intish(value)
        for value in (
            settlement.get("pending_without_result"),
            tracker.get("pending_without_result"),
            combo.get("pending_without_result"),
        )
    )
    return extracted or pending == 0


def run_cli_json(*args: str) -> dict:
    output = run_cli(*args)
    payload = last_top_level_json(output)
    if isinstance(payload, dict):
        return payload
    raise RuntimeError(f"Expected JSON object from {' '.join(args)}, got: {output[-500:]}")


def last_top_level_json(output: str) -> object:
    decoder = json.JSONDecoder()
    parsed: list[object] = []
    for match in re.finditer(r"(?m)^\{", output):
        try:
            payload, _ = decoder.raw_decode(output[match.start() :])
        except json.JSONDecodeError:
            continue
        parsed.append(payload)
    if parsed:
        return parsed[-1]
    return json.loads(output)


def run_cli(*args: str) -> str:
    python = PYTHON if PYTHON.exists() else Path(sys.executable)
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    cmd = [str(python), "-m", "tennis_wc.cli", *args]
    log(f"$ {' '.join(cmd)}")
    completed = subprocess.run(
        cmd,
        cwd=PROJECT_DIR,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    output = completed.stdout.strip()
    if output:
        log(summarise_captured_output(output))
    completed.check_returncode()
    return output


def summarise_captured_output(output: str) -> str:
    """Keep a subprocess's head and tail, and SAY how much was left out.

    The CLI prints the whole card as pretty JSON and this wrote all of it. On
    2026-08-11 the log was 869,771 lines of which 1,075 carried a timestamp:
    99.88% of the file was one payload shape repeated 76,477 times, and
    `verify_scheduled_runs.py` -- the tool the 0.2 exit test is read from --
    reads the file whole.

    Truncating silently would be worse than the size, so the elision states its
    own line count. The full payload is not lost either: the card is written to
    the analysis output root, which is where it is meant to be read.
    """
    lines = output.splitlines()
    if len(lines) <= CAPTURED_HEAD_LINES + CAPTURED_TAIL_LINES:
        return output
    elided = len(lines) - CAPTURED_HEAD_LINES - CAPTURED_TAIL_LINES
    return "\n".join(
        lines[:CAPTURED_HEAD_LINES]
        + [f"... {elided} lines elided by the scheduler "
           f"(kept first {CAPTURED_HEAD_LINES} and last {CAPTURED_TAIL_LINES}; "
           f"the full card is written to the analysis output root) ..."]
        + lines[-CAPTURED_TAIL_LINES:]
    )


def compact_json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def intish(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def rotate_log_if_needed(path: Path) -> bool:
    """Bound the log, keeping enough history for the two-day exit test.

    Nothing rotated it before -- no RotatingFileHandler, no newsyslog entry --
    and now that both passes are scheduled it grows every day unattended.
    Rotation keeps LOG_BACKUPS generations, and `verify_scheduled_runs.py` reads
    the rotated files too, so a rotation cannot quietly erase the evidence the
    exit test is judged on.
    """
    try:
        if path.stat().st_size < MAX_LOG_BYTES:
            return False
    except OSError:
        return False
    oldest = path.with_suffix(path.suffix + f".{LOG_BACKUPS}")
    if oldest.exists():
        oldest.unlink()
    for index in range(LOG_BACKUPS - 1, 0, -1):
        source = path.with_suffix(path.suffix + f".{index}")
        if source.exists():
            source.rename(path.with_suffix(path.suffix + f".{index + 1}"))
    path.rename(path.with_suffix(path.suffix + ".1"))
    return True


def disk_headroom(db_path: Path | None = None) -> dict:
    """Is there room to finish a run? Settlement rewrites pages and needs a journal.

    Two database-widths, with a 2GB floor. Not a guess pulled from nowhere: the
    database is 2.5GB and both the repair and the A/B harness clone it, so the
    working set is multiples of it, and on 2026-08-11 the volume reached zero
    bytes free with three such copies alive at once.
    """
    import shutil

    database = db_path or (PROJECT_DIR / "tennis_wc.db")
    try:
        db_bytes = database.stat().st_size
    except OSError:
        db_bytes = 0
    required = max(int(db_bytes * 2.0), 2 * 1024 ** 3)
    free = shutil.disk_usage(PROJECT_DIR).free
    return {
        "ok": free >= required,
        "free_bytes": free,
        "required_bytes": required,
        "detail": f"{free / 1024 ** 3:.1f}GB free, {required / 1024 ** 3:.1f}GB "
                  f"required for a {db_bytes / 1024 ** 3:.1f}GB database",
    }


def trim_launchd_capture(path: Path) -> bool:
    """Bound launchd's own stdout/stderr copy, which nothing else can.

    `StandardOutPath` is a second copy of every line `log()` already prints, and
    launchd never rotates it -- rotation would need a newsyslog.d entry, which
    needs root. It cannot simply be dropped either: a failure BEFORE python
    starts (a missing venv, an unreadable launcher) appears only there, and that
    silence is the failure mode this whole phase exists to remove.

    So it is trimmed in place to its last MAX_LOG_BYTES, keeping the tail, which
    is where a fresh failure is. Trimmed rather than renamed on purpose: launchd
    holds the descriptor open for the current run, and a rename would send this
    run's output to the file nobody looks at.
    """
    try:
        size = path.stat().st_size
    except OSError:
        return False
    if size < MAX_LOG_BYTES:
        return False
    try:
        with path.open("r+b") as handle:
            handle.seek(size - MAX_LOG_BYTES // 2)
            tail = handle.read()
            handle.seek(0)
            handle.write(b"... earlier lines trimmed by the scheduler; launchd "
                         b"does not rotate this file ...\n")
            handle.write(tail)
            handle.truncate()
    except OSError:
        return False
    return True


def log(message: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    line = f"[{timestamp}] {message}"
    print(line, flush=True)
    path = LOG_DIR / "tennis_daily_schedule.log"
    rotate_log_if_needed(path)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


if __name__ == "__main__":
    raise SystemExit(main())

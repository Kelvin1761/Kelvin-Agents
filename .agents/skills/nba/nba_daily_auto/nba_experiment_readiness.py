#!/usr/bin/env python3
"""Is there enough data to read each frozen NBA experiment yet? Read-only.

Wraps the existing forward tools (their own frozen rules decide verdicts) and reports,
per experiment, how far it is from its next checkpoint and whether that checkpoint is
due. The scheduler sends a Monday progress digest and a one-off alert the first time a
checkpoint becomes due. Never changes a probability, pick or protocol.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import nba_market_ledger as ledger
import nba_ms_forward as ms
import nba_season_rate_v4_forward as v4
import nba_early_season_guard_monitor as guard
import nba_availability_outcomes as availability

MS_TESTS = (("MS1", ms.CONFIG_PATH), ("MS2", ms.CONFIG_V2_PATH), ("MS2 REB+3PM", ms.CONFIG_V2_REB3PM_PATH),
            ("MS3", ms.CONFIG_V3_PATH))
GUARD_REVIEW_DATE = "2026-11-15"      # EXP-20261026-06 §6
GUARD_MIN_GAMES = 15
# Practical "enough for a first look" floors (not verdict rules; see EXP-20261026-09).
AVAILABILITY_MIN_PER_STATUS = 30
TIMING_MIN_DAYS = 10
TIMING_EPOCH = "2026-10-27"


def _ms_items(root: Path, until: str) -> list[dict]:
    items = []
    for name, path in MS_TESTS:
        config, sha = ms.load_config(path)
        legs, counts = ms.collect(root, config["epoch"], until, config)
        report = ms.analyse(legs, counts, sha, config.get("protocol_id", "EXP-20261025-12"))
        look = report.get("look")
        events, dates = report["events"], report["dates"]
        next_events = next((n for n in (ms.HARM_CHECK_EVENTS, ms.PRIMARY_EVENTS, ms.FINAL_EVENTS) if events < n), None)
        items.append({
            "name": name, "protocol": report["protocol"], "status": report["status"],
            "progress": f"{events} 場／{dates} 日" + (f"（下一個檢查點 {next_events} 場）" if next_events else ""),
            "checkpoint": look if look else (report["status"] if report["status"] in ("REJECT_HARM", "INVALID_DATA") else None),
        })
    return items


def _v4_item(root: Path, until: str) -> dict:
    legs, slate_days = v4.collect(root, v4.EPOCH, until)
    report = v4.analyse(legs, slate_days, until)
    return {"name": "S_v4 vs S_v2", "protocol": report["protocol"], "status": report["status"],
            "progress": f"{report['events']} 場有上季比賽嘅腿",
            "checkpoint": "final" if report.get("analysis_due") else None}


def _guard_item(root: Path, until: str) -> dict:
    rows = guard.legs(root, "2026-10-27", until, "bet")
    games = len({(r["day"], r["game"]) for r in rows if r["guard"] != "none"})
    due = until >= GUARD_REVIEW_DATE and games >= GUARD_MIN_GAMES
    return {"name": "季初穩膽保護", "protocol": "EXP-20261026-06", "status": "DUE" if due else "ACCUMULATING",
            "progress": f"被擋嘅穩膽類腿 {games} 場（要 ≥{GUARD_MIN_GAMES} 場，且 ≥{GUARD_REVIEW_DATE}）",
            "checkpoint": "review" if due else None}


def _availability_item(root: Path, until: str, analysis_roots: list[Path]) -> dict:
    rows = availability.outcomes(root, analysis_roots, "2026-10-27", until)
    counts = defaultdict(int)
    for r in rows:
        counts[r.get("official_status") or "-"] += 1
    q, p = counts.get("Questionable", 0), counts.get("Probable", 0)
    due = q >= AVAILABILITY_MIN_PER_STATUS and p >= AVAILABILITY_MIN_PER_STATUS
    return {"name": "Questionable／Probable 上場率", "protocol": "EXP-20261026-02", "status": "DUE" if due else "ACCUMULATING",
            "progress": f"Questionable {q}、Probable {p}（各要 ≥{AVAILABILITY_MIN_PER_STATUS}）",
            "checkpoint": "first_look" if due else None}


def _timing_item(root: Path, until: str) -> dict:
    days = 0
    for day in ledger._iter_dates(TIMING_EPOCH, until, root):
        roles = {r.get("snapshot_role") for r in ledger.read_rows(root, day) if r.get("row_type") == "model_obs"}
        days += {"production", "final_refresh"} <= roles
    due = days >= TIMING_MIN_DAYS
    return {"name": "最佳落注時間研究", "protocol": "（未開）", "status": "DUE" if due else "ACCUMULATING",
            "progress": f"有 21:00 同朝早快照嘅日子 {days} 日（要 ≥{TIMING_MIN_DAYS}）",
            "checkpoint": "first_look" if due else None}


def build(until: str, root: Path | None = None, analysis_roots: list[Path] | None = None) -> dict:
    root = root or ledger.ledger_root()
    if analysis_roots is None:
        from wongchoi_paths import NBA_ANALYSIS
        analysis_roots = [availability.PROJECT_ROOT, NBA_ANALYSIS]
    items = []
    for build_item in (lambda: _ms_items(root, until), lambda: [_v4_item(root, until)],
                       lambda: [_guard_item(root, until)],
                       lambda: [_availability_item(root, until, analysis_roots)],
                       lambda: [_timing_item(root, until)]):
        try:
            items.extend(build_item())
        except Exception as exc:  # one broken tool must not hide the others
            items.append({"name": "error", "status": "ERROR", "progress": f"{type(exc).__name__}: {exc}",
                          "checkpoint": None, "protocol": "-"})
    return {"until": until, "items": items}


# A data-guard trip or a failed harm check is a problem to look at, not a checkpoint to read.
WARNINGS = {"INVALID_DATA": "⚠️ {name}（{protocol}）數據守則觸發：唔可以判斷，要先查數據管線",
            "REJECT_HARM": "⛔ {name}（{protocol}）傷害檢查不合格：候選明顯差過現役 C"}


def due_alerts(report: dict) -> list[tuple[str, str]]:
    """(dedup key, line) for each checkpoint that is due; the scheduler sends each once."""
    out = []
    for item in report["items"]:
        checkpoint = item.get("checkpoint")
        if not checkpoint:
            continue
        head = WARNINGS.get(checkpoint, "🔔 {name}（{protocol}）可以開始判斷：{checkpoint}").format(
            name=item["name"], protocol=item["protocol"], checkpoint=checkpoint)
        out.append((f"{item['protocol']}:{item['name']}:{checkpoint}",
                    f"{head}｜狀態 {item['status']}｜{item['progress']}"))
    return out


def progress_lines(report: dict) -> list[str]:
    lines = [f"🧪 NBA 實驗準備進度｜截至 {report['until']}"]
    for item in report["items"]:
        mark = "🔔" if item.get("checkpoint") else "⏳"
        lines.append(f"{mark} {item['name']}：{item['status']}｜{item['progress']}")
    lines.append("只係數據準備度；判決要按各自協議，唔好因為中途數字行動。")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--until", required=True)
    parser.add_argument("--root", type=Path, default=None)
    args = parser.parse_args(argv)
    report = build(args.until, args.root)
    print("\n".join(progress_lines(report)))
    print(json.dumps(due_alerts(report), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())

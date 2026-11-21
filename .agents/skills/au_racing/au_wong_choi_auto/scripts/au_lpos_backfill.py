#!/usr/bin/env python3
"""EXP-20261120-87：Lpos 歷史回填測試 —— 進度、完整度、回填完成先判一次並凍結。

特徵、分數、判決同 EXP-20261116-20 forward 一模一樣（直接 import `au_lpos_forward`），只係母體換成
08-05 → 11-05 嘅歷史場次（手機頁由 `au_mobile_sectionals.py fetch --backfill` 每晚回填）。

**未完成唔睇賽果**：status 只寫抓咗幾多版、完整度、覆蓋率。完成條件（預先登記）：範圍內每個有分析嘅賽日都有
`_events.json` 而且全部場次抓齊，或者連續 3 晚冇進度（剩低嘅抓唔到）。

    python3 au_lpos_backfill.py --output work/au-lpos-backfill-status.json [--notify]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import au_lpos_forward as fwd  # noqa: E402
import au_mobile_sectionals as ams  # noqa: E402

EXPERIMENT_ID = "EXP-20261120-87"
IDLE_NIGHTS_TO_CLOSE = 3
MILESTONES = (25, 50, 75)


def completeness(root: Path) -> dict:
    """→ {target, fetched, days_total, days_listed, days_complete, missing_days}。只計有分析嘅賽日。"""
    out = {"target": 0, "fetched": 0, "days_total": 0, "days_listed": 0, "days_complete": 0, "missing_days": []}
    for day in ams.backfill_days():
        wanted = ams.analysed_races(day, root)
        if not wanted:
            continue
        out["days_total"] += 1
        out["target"] += len(wanted)
        folder = ams.store_dir(root) / day
        listed = folder / "_events.json"
        if not listed.exists():
            out["missing_days"].append(day)
            continue
        out["days_listed"] += 1
        events = json.loads(listed.read_text(encoding="utf-8"))
        have = sum((folder / f"{ev['event_id']}.json.gz").exists() for ev in events)
        out["fetched"] += have
        if have == len(events):
            out["days_complete"] += 1
        else:
            out["missing_days"].append(day)
    return out


def collect(root: Path):
    """歷史母體：forward 同一個 collect，限 BACKFILL 範圍；頁面有 ≥ 賽日往績行嘅場剔走（登記要求）。"""
    races, skipped = fwd.collect(root, start=ams.BACKFILL_FROM, mobile_root=root)
    races = [r for r in races if r["date"] <= ams.BACKFILL_TO]
    keep = [r for r in races if not r.get("mobile_post_race_rows")]
    skipped["post_race_rows"] = len(races) - len(keep)
    return keep, skipped


def _push(text: str) -> None:
    try:
        sys.path.insert(0, str(SCRIPT_DIR.parents[1] / "au_daily_auto"))
        import au_notify
        au_notify.push(text, title="🏇 AU 段速回填", audience="primary")
    except Exception as exc:  # noqa: BLE001 — 通知失敗唔可以令 job 死
        print(f"notify failed: {type(exc).__name__}: {exc}", file=sys.stderr)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-root", default=None)
    ap.add_argument("--output", required=True)
    ap.add_argument("--notify", action="store_true", help="排程用：里程碑同完成推 primary Telegram")
    args = ap.parse_args(argv)
    root = Path(args.data_root) if args.data_root else ams.data_root()
    out_path = Path(args.output)
    prev = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else {}
    if prev.get("evaluation"):
        print(f"{EXPERIMENT_ID} 已判（凍結）：{prev['evaluation']['verdict']}")
        return 0
    comp = completeness(root)
    today = datetime.now().date().isoformat()
    idle = int(prev.get("idle_nights") or 0)
    if prev.get("checked_on") != today:
        idle = idle + 1 if comp["fetched"] <= int(prev.get("races_collected") or 0) else 0
    complete = comp["days_total"] > 0 and comp["days_complete"] == comp["days_total"]
    close = complete or (comp["fetched"] > 0 and idle >= IDLE_NIGHTS_TO_CLOSE)
    pct = round(100.0 * comp["fetched"] / comp["target"], 1) if comp["target"] else 0.0
    status = {"experiment": EXPERIMENT_ID, "range": [ams.BACKFILL_FROM, ams.BACKFILL_TO],
              "races_collected": comp["fetched"], "target_races": comp["target"], "pct": pct,
              "completeness": comp, "idle_nights": idle, "checked_on": today,
              "milestones_notified": prev.get("milestones_notified") or [],
              "outcomes_visible": close, "state": "evaluated" if close else "collecting",
              "generated_at": datetime.now(timezone.utc).isoformat()}
    if close:
        races, skipped = collect(root)
        status.update(eligible_races=len(races), skipped=skipped, coverage=fwd.coverage(races),
                      closed_because="complete" if complete else f"{idle} 晚冇進度")
        status["evaluation"] = fwd.evaluate(races)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(status, ensure_ascii=False, indent=1), encoding="utf-8")
    if args.notify:
        for m in MILESTONES:
            if pct >= m and m not in status["milestones_notified"] and not close:
                _push(f"段速回填（{EXPERIMENT_ID}）進度 {pct:.0f}%：已抓 {comp['fetched']}/{comp['target']} 場，"
                      f"{comp['days_complete']}/{comp['days_total']} 日齊。未睇賽果。")
                status["milestones_notified"].append(m)
        out_path.write_text(json.dumps(status, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in status.items() if k not in ("evaluation", "completeness")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

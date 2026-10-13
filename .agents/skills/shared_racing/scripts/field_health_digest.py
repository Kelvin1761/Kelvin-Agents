#!/usr/bin/env python3
"""每週 Telegram 摘要：邊啲欄位變差 + 上週失手分佈。

讀兩份 ledger（都喺資料根）：
    <平台>_Field_Health.jsonl   ← field_health.py --record
    <平台>_Miss_Autopsy.jsonl   ← miss_autopsy.py --write

出一段短文字。發送由 caller 負責（AU：au_healthcheck；HKJC：run_weekly）。
呢度唔 import 任何 Telegram 嘢，所以測試唔會誤發。

Usage
-----
    python field_health_digest.py --platform au            # 印出嚟
    python field_health_digest.py --platform au --week 2026-W41
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import field_health as fh  # noqa: E402

MISS_LEDGERS = {"au": "AU_Miss_Autopsy.jsonl", "hkjc": "HKJC_Miss_Autopsy.jsonl"}
MAX_FIELDS = 5
TOP_RULES = 3
BUCKETS = ("input_anomaly", "crowded", "model_wrong")
BUCKET_SHORT = {"input_anomaly": "輸入", "crowded": "擠迫", "model_wrong": "模型"}


def _read_jsonl(path: Path) -> list[dict]:
    return fh.read_ledger(path)


def miss_summary(rows: list[dict], week: str) -> dict:
    """目標週同之前 4 週嘅失手分佈（只計 kind == race）。"""
    races = [r for r in rows if r.get("kind") == "race"]
    scored = {r["week"]: 0 for r in rows if r.get("kind") == "summary" and r.get("week")}
    for r in rows:
        if r.get("kind") == "summary" and r.get("week"):
            scored[r["week"]] += int(r.get("scored_races") or 0)
    this_week = [r for r in races if r.get("week") == week]
    earlier_weeks = sorted({r["week"] for r in races if r.get("week") and r["week"] < week})[-fh.BASELINE_WEEKS:]
    earlier = [r for r in races if r.get("week") in earlier_weeks]
    from miss_autopsy import CROWD_RULES
    rules = Counter(rule for r in this_week if r.get("bucket") == "input_anomaly"
                    for rule in r.get("rules") or [] if rule not in CROWD_RULES)

    def share(items):
        counts = Counter(r.get("bucket") for r in items)
        total = sum(counts.values())
        return {b: (counts.get(b, 0), counts.get(b, 0) / total if total else 0.0) for b in BUCKETS}

    return {
        "week": week,
        "scored": scored.get(week, 0),
        "misses": len(this_week),
        "now": share(this_week),
        "before": share(earlier),
        "before_weeks": len(earlier_weeks),
        "top_rules": rules.most_common(TOP_RULES),
    }


def build(platform: str, root: Path, week: str | None = None, today: dt.date | None = None) -> str:
    field_rows = _read_jsonl(fh.ledger_path(platform, root))
    target, findings = fh.trend(field_rows, week, today)
    lines = [f"🩺 {platform.upper()} 欄位健康週報 {target or ''}".rstrip()]

    if not target:
        lines.append("欄位：未有紀錄（未跑過 field_health.py --record）")
    elif not findings:
        lines.append("欄位：✅ 冇欄位變差")
    else:
        lines.append(f"欄位：{len(findings)} 項要留意")
        for f in findings[:MAX_FIELDS]:
            since = f.get("since")
            tail = f"（{since} 起）" if since and since != f["week"] else ""
            lines.append(f"  {fh.STATUS_ICONS.get(f['status'], '•')} "
                         f"{fh.SOURCE_LABELS.get(f['source'], f['source'])} {f['field']}：{f['detail']}{tail}")
        if len(findings) > MAX_FIELDS:
            lines.append(f"  …另外 {len(findings) - MAX_FIELDS} 項")

    miss_rows = _read_jsonl(Path(root) / MISS_LEDGERS[platform])
    if target and miss_rows:
        s = miss_summary(miss_rows, target)
        if s["misses"]:
            now = "　".join(f"{BUCKET_SHORT[b]} {s['now'][b][0]}（{s['now'][b][1]:.0%}）" for b in BUCKETS)
            lines.append(f"失手體檢：{s['scored']} 場入面 {s['misses']} 場唔係 Gold／Good")
            lines.append(f"  {now}")
            if s["before_weeks"]:
                before = "　".join(f"{BUCKET_SHORT[b]} {s['before'][b][1]:.0%}" for b in BUCKETS)
                lines.append(f"  前 {s['before_weeks']} 週：{before}")
            if s["top_rules"]:
                from miss_autopsy import TRIGGER_LABELS
                rules = "、".join(f"{TRIGGER_LABELS.get(rule, rule)} ×{n}" for rule, n in s["top_rules"])
                lines.append(f"  輸入問題主要係：{rules}")
        else:
            lines.append("失手體檢：呢週未有紀錄")
    lines.append("（只做診斷：唔准用失手體檢嚟調權重）")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--platform", required=True, choices=sorted(MISS_LEDGERS))
    parser.add_argument("--week")
    parser.add_argument("--root", type=Path, help="覆寫資料根（測試用）")
    args = parser.parse_args(argv)
    root = args.root or fh.dc.resolve_root(args.platform)
    if root is None:
        print("搵唔到資料根目錄（wongchoi_paths）", file=sys.stderr)
        return 2
    print(build(args.platform, Path(root), args.week))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

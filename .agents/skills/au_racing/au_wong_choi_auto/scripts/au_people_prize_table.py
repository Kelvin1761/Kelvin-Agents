#!/usr/bin/env python3
"""建騎練總獎金表（EXP-20261122-03 T3，實驗性上線 2026-11-22）。排程每晚分析下一日之前跑。

讀 `AU_Sportsbet_People_Snapshots.jsonl`（每次抓個人頁都 append 一份，含 captured_at），
每份快照計 log10(過去 12 個月總獎金 + 1)（`people_overlays.log_total_prize`），
輸出 `<資料根>/AU_People_Prize.json`：{"people": {"jockey|名": [[快照日期 UTC, 值], ...]}}（日期升序；同日留最後一份）。
引擎只用**早過賽日**嘅最後一份（`people_overlays.prize_raw`）—— 同研究一樣，冇前視。

    python3 au_people_prize_table.py [--data-root DIR] [--output PATH]
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from au_racing_engine.people_overlays import (PRIZE_BETA_JOCKEY, PRIZE_BETA_TRAINER,  # noqa: E402
                                              default_prize_table_path, log_total_prize, norm)


def build(snapshots: Path, cache: Path) -> dict:
    names = {}
    try:
        names = {k: v.get("name") for k, v in json.loads(cache.read_text(encoding="utf-8")).items()}
    except (OSError, ValueError):
        pass
    by = defaultdict(dict)
    with snapshots.open(encoding="utf-8") as fh:
        for line in fh:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            cs = row.get("contextual_stats")
            if isinstance(cs, str):
                try:
                    cs = ast.literal_eval(cs)
                except (ValueError, SyntaxError):
                    continue
            value = log_total_prize((cs or {}).get("Prize Money"))
            name = norm(names.get(row.get("key")) or row.get("name"))
            kind = str(row.get("kind") or "").lower()
            if value is None or not name or kind not in ("jockey", "trainer"):
                continue
            by[f"{kind}|{name}"][str(row.get("captured_at") or "")[:10]] = round(value, 6)
    return {k: sorted([d, v] for d, v in days.items() if d) for k, days in by.items()}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-root", default=None)
    ap.add_argument("--output", default=None)
    args = ap.parse_args(argv)
    root = Path(args.data_root) if args.data_root else default_prize_table_path().parent
    table = build(root / "AU_Sportsbet_People_Snapshots.jsonl", root / "AU_Sportsbet_People_Cache.json")
    out = Path(args.output) if args.output else default_prize_table_path()
    payload = {"experiment": "EXP-20261122-03", "built_at": datetime.now(timezone.utc).isoformat(),
               "beta_jockey": PRIZE_BETA_JOCKEY, "beta_trainer": PRIZE_BETA_TRAINER, "people": table}
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(out)
    print(json.dumps({"people": len(table), "output": str(out)}, ensure_ascii=False))


if __name__ == "__main__":
    main()

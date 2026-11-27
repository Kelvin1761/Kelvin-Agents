#!/usr/bin/env python3
"""S2 Sportsbet 全程速度事件表（EXP-20261127-02）：語料所有 Formguide 往績 → 去重嘅場級事件（頭馬時間 + 每匹輸距換算時間）。

引擎（`au_racing_engine/sb_full_time.py`）每個賽日只用嗰日之前嘅事件建情境標準，所以表幾時建都唔會前視。
每晚分析之前重建（同速度參考表同一個 step）；失敗沿用舊表。

    python3 au_sb_full_time_table.py --data-root <AU_Racing>
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR.parents[2] / "shared_racing" / "scripts"))

from au_racing_engine import sb_full_time as S2  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-root", required=True)
    ap.add_argument("--output", default=None)
    args = ap.parse_args(argv)
    from corpus_paths import meeting_dirs  # noqa: PLC0415
    root = Path(args.data_root)
    sources = []
    for meeting in meeting_dirs(root):
        m = re.search(r"(\d{4}-\d{2}-\d{2})", meeting.name)
        if m:
            sources.append((m[1], meeting))
    events, audit = S2.build_events(sources)
    out = Path(args.output) if args.output else root / S2.EVENTS_NAME
    tmp = out.with_suffix(".tmp")
    tmp.write_bytes(gzip.compress(json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(),
                                              "audit": audit, "events": events}, ensure_ascii=False).encode("utf-8")))
    os.replace(tmp, out)
    print(f"S2 全程速度事件表：{len(events)} 場（{audit}）→ {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""WinningTime 速度分參考表（EXP-20261124-40）：所有 Formguide 往績行 → 去重嘅場級頭馬時間。

引擎（`au_racing_engine/winning_time_speed.py`）每個賽日只用嗰日之前嘅行計標準，所以表幾時建都唔會前視。
每晚喺分析之前重建（同練馬師剩餘表現表同一個 step）；失敗就沿用舊表。

    python3 au_speed_reference_table.py --data-root <AU_Racing>
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from au_racing_engine import winning_time_speed as W  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-root", required=True)
    ap.add_argument("--output", default=None)
    args = ap.parse_args(argv)
    root = Path(args.data_root)
    rows, conflicts = W.collect_reference(root)
    out = Path(args.output) if args.output else root / W.REFERENCE_NAME
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(), "conflicts": conflicts,
                               "rows": rows}, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, out)
    print(f"速度參考表：{len(rows)} 場（衝突剔走 {conflicts}）→ {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

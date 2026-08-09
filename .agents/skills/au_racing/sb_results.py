#!/usr/bin/env python3
"""由 Sportsbet cache 生成覆盤用嘅 `Race_Results_Reflector.md`。

點解需要：`unified_reflector_core.py` 攞 AU 賽果係 shell out 去
`claw_racenet_results.py` —— **Racenet，已經全封**。所以覆盤而家攞唔到賽果。

點解唔重寫嗰個 extractor：唔使。reflector 嘅 `find_existing_results_file()`
會**先**喺 meeting 目錄搵 `Race_Results_Reflector.md`，搵到就唔會 call 任何
extractor、亦唔需要 results URL。所以最乾淨嘅做法係直接生成嗰個檔 ——
Racenet 那條路就永遠唔會行到。

賽果由邊嚟：Sportsbet 賽事頁本身。每匹馬嘅往績第一行就係嗰場嘅賽果
（`Finished 3/11 0.42L`）—— 呢個正正係 `write_meeting` 為咗防洩漏而丟走嘅行。
**做標準答案啱，做評分輸入唔啱**，同 `au_source_compare` 同一個道理。

全程讀 cache，零網絡請求。

用法：
    python3 sb_results.py --meeting "2026-08-01 Flemington Race 1-9"
    python3 sb_results.py --meeting-dir "<路徑>"      # 寫落嗰個目錄
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from claw_sportsbet_form import (BASE, SportsbetFormFetcher,  # noqa: E402
                                parse_race, parse_runner_blocks, run_date)


def collect(meeting_key, ids):
    """→ {race_no: [(pos, num, name, margin, sp)]}，全部由 cache 讀。"""
    meta = ids.get(meeting_key)
    if not meta:
        return None, f"對應表冇 `{meeting_key}`"
    f = SportsbetFormFetcher(delay=0.0, verbose=False)
    out, missing = {}, 0
    for rid in meta["races"]:
        url = f"{BASE}/{meta['meetingId']}/{rid}/"
        if not f._cache_path(url).exists():
            missing += 1
            continue
        html = f.get(url)
        pr = parse_race(html)
        rno = pr["meta"].get("race_number")
        if rno is None:
            continue
        num_by_name = {(v.get("name") or "").lower(): k
                       for k, v in pr["overview"].items()}
        rows = []
        for blk in parse_runner_blocks(html):
            for run in blk.get("runs", []):
                h = run.get("header") or {}
                if run_date(run) != meta["date"] or str(h.get("race")) != str(rno):
                    continue
                try:
                    pos = int(run["pos"])
                except (TypeError, ValueError, KeyError):
                    continue
                rows.append((pos, num_by_name.get(blk["name"].lower()), blk["name"],
                             run.get("margin"), run.get("sp")))
                break
        if rows:
            out[rno] = sorted(rows)
    return (out, f"{missing} 場唔喺 cache" if missing else None)


def render(venue, date, races):
    lines = [f"# {venue} Race Results — {date}", ""]
    ORD = {1: "1st", 2: "2nd", 3: "3rd"}
    for rno in sorted(races):
        lines.append(f"## Race {rno}")
        for pos, num, name, mgn, sp in races[rno]:
            label = ORD.get(pos, f"{pos}th")
            bits = [f"{label}:", f"#{num}" if num else "#?", name]
            if pos > 1 and mgn:
                bits.append(f"({mgn}L)")
            if sp:
                bits.append(f"SP${sp}")
            lines.append(" ".join(bits))
        lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="由 cache 生成覆盤賽果檔")
    ap.add_argument("--meeting", help="對應表嘅 key，例如「2026-08-01 Flemington Race 1-9」")
    ap.add_argument("--meeting-dir", help="寫落邊個目錄（預設用 --meeting 推）")
    ap.add_argument("--top", type=int, default=6, help="每場寫頭幾名")
    args = ap.parse_args()

    from sb_backfill_archive import load_meeting_ids

    ids = load_meeting_ids()
    key = args.meeting
    if not key and args.meeting_dir:
        key = Path(args.meeting_dir).name
    if not key:
        print("❌ 要 --meeting 或 --meeting-dir")
        return 1

    races, warn = collect(key, ids)
    if races is None:
        print(f"❌ {warn}")
        return 1
    if not races:
        print("❌ cache 冇任何賽果 —— 呢個場次未抽過，或者仲未跑")
        return 1
    for rno in races:
        races[rno] = races[rno][:args.top]

    meta = ids[key]
    venue = meta["slug"].replace("_", " ").title()
    dest = Path(args.meeting_dir or key) / "Race_Results_Reflector.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(render(venue, meta["date"], races), encoding="utf-8")
    print(f"✅ {len(races)} 場賽果 → {dest}")
    if warn:
        print(f"   ⚠️ {warn}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

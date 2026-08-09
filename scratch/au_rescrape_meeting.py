#!/usr/bin/env python3
"""安全重抽一個 meeting 嘅 Racecard + Formguide（為咗攞新加嘅 ` starters:`）。

Racenet 係機率性 403（~50-60%），慢速冇幫助、只有重試先穿。所以：

  * 全部抽入 **staging**，Drive 上嘅現有檔案全程唔會被半成品覆蓋
  * 每輪之後只**合併**成功而且通過驗證嘅場次
  * 驗證 = Formguide 有 `starters:` **而且** run line 數量唔少過現有檔案
    （防止一個殘缺回應洗走完整資料）
  * 最多 N 輪，缺幾多報幾多，唔會靜靜當成功

用法：
    python3 scratch/au_rescrape_meeting.py "<meeting_dir>" --slug flemington-20260801 --races 9
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRAPER = (Path(__file__).resolve().parents[1]
           / ".agents/skills/au_racing/claw_racenet_scraper.py")
RUN_LINE = re.compile(r"^[A-Za-z].* R\d+ \d{4}-\d{2}-\d{2} \d+m cond:")
HORSE = re.compile(r"^\[(\d+)\]\s+(.+?)\s*\(")


def per_horse_runs(path: Path) -> dict[str, int]:
    """{馬名: 該馬嘅 run line 數}。用逐匹馬比較而唔係總數 —— 一個 meeting
    喺賽前會有退出馬，總 run line 跌係正常，唔可以當成殘缺回應。"""
    counts: dict[str, int] = {}
    current = None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return counts
    for line in text.splitlines():
        stripped = line.strip()
        h = HORSE.match(stripped)
        if h:
            current = h.group(2).strip()
            counts.setdefault(current, 0)
        elif current and RUN_LINE.match(stripped):
            counts[current] += 1
    return counts


def has_starters(path: Path) -> bool:
    try:
        return "starters:" in path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("meeting_dir")
    ap.add_argument("--slug", required=True)
    ap.add_argument("--venue", required=True)
    ap.add_argument("--date", required=True)
    ap.add_argument("--races", type=int, required=True)
    ap.add_argument("--rounds", type=int, default=4)
    args = ap.parse_args()

    dest = Path(args.meeting_dir)
    if not dest.is_dir():
        sys.exit(f"meeting dir not found: {dest}")
    mm_dd = args.date[5:]
    pending = set(range(1, args.races + 1))
    merged = []

    for rnd in range(1, args.rounds + 1):
        if not pending:
            break
        print(f"\n─── round {rnd}  仲差 {sorted(pending)}", flush=True)
        staging = Path(tempfile.mkdtemp(prefix="au_rescrape_"))
        try:
            subprocess.run(
                [sys.executable, str(SCRAPER), "--date", args.date,
                 "--venue", args.venue, "--slug", args.slug,
                 "--races", str(args.races)],
                cwd=staging, check=False, capture_output=True, text=True, timeout=1800,
            )
            out_dir = staging / f"{args.date} {args.venue} Race 1-{args.races}"
            for race in sorted(pending):
                fg = out_dir / f"{mm_dd} Race {race} Formguide.md"
                rc = out_dir / f"{mm_dd} Race {race} Racecard.md"
                if not fg.exists() or not rc.exists():
                    continue
                if not has_starters(fg):
                    print(f"   R{race}: 抽到但冇 starters: —— 唔合併")
                    continue
                old = dest / f"{mm_dd} Race {race} Formguide.md"
                new_counts, old_counts = per_horse_runs(fg), per_horse_runs(old)
                if not new_counts:
                    print(f"   R{race}: 新檔冇馬匹區塊 —— 唔合併")
                    continue
                shared = set(new_counts) & set(old_counts)
                shrunk = [h for h in shared if new_counts[h] < old_counts[h]]
                if old_counts and not shared:
                    print(f"   R{race}: 新舊檔冇一匹馬對得上 —— 唔合併")
                    continue
                if shrunk:
                    print(f"   R{race}: {len(shrunk)} 匹馬嘅賽績變少（例 {shrunk[0]}）"
                          f" —— 疑似殘缺回應，唔合併")
                    continue
                scratched = sorted(set(old_counts) - set(new_counts))
                note = f"，退出 {len(scratched)} 匹（{', '.join(scratched[:3])}）" if scratched else ""
                shutil.copy2(fg, dest / fg.name)
                shutil.copy2(rc, dest / rc.name)
                merged.append(race)
                pending.discard(race)
                print(f"   R{race}: ✓ 合併（{len(old_counts)} → {len(new_counts)} 匹{note}）")
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    print(f"\n合併 {len(merged)} / {args.races} 場：{sorted(merged)}")
    if pending:
        print(f"⚠️ 仲差 {sorted(pending)} —— 呢幾場保持舊版本（冇馬群大細），"
              f"其餘修正照樣生效。")
    return 0 if not pending else 1


if __name__ == "__main__":
    sys.exit(main())

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
    python3 sb_results.py --meeting "2026-08-01 Flemington Race 1-9"  # 寫落 AU archive 同名目錄
    python3 sb_results.py --meeting-dir "<路徑>"                      # 寫落嗰個目錄
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


def ordinal(pos: int) -> str:
    """1st / 2nd / 3rd / 4th ... 11th / 21st / 22nd / 23rd.

    Used to render every finisher, not just the first six, so the teens
    exception and the 21st/22nd/23rd cases actually come up now.
    """
    if 11 <= (pos % 100) <= 13:
        return f"{pos}th"
    return f"{pos}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(pos % 10, 'th') }"


def render(venue, date, races):
    lines = [f"# {venue} Race Results — {date}", ""]
    for rno in sorted(races):
        lines.append(f"## Race {rno}")
        for pos, num, name, mgn, sp in races[rno]:
            label = ordinal(pos)
            bits = [f"{label}:", f"#{num}" if num else "#?", name]
            if pos > 1 and mgn:
                bits.append(f"({mgn}L)")
            if sp:
                bits.append(f"SP${sp}")
            lines.append(" ".join(bits))
        lines.append("")
    return "\n".join(lines)


def resolve_dest_dir(key, meeting_dir_arg):
    """→ (目錄, 錯誤訊息)。`--meeting-dir` 話事；冇就喺 AU archive 搵返 `key`。

    以前呢度係 `Path(meeting_dir or key)` —— 淨係俾 `--meeting` 嘅時候，個
    relative key 會喺 **CWD** 開一個新目錄出嚟，然後 ✅ 咁報成功；但 reflector
    永遠喺 archive 度搵賽果，自然搵唔到。寧願大聲失敗，都唔好寫落一個冇人會
    讀嘅位。
    """
    if meeting_dir_arg:
        return Path(meeting_dir_arg).expanduser(), None

    from sb_backfill_archive import archive_meetings

    for path, _date, _track in archive_meetings():
        if path.name == key:
            return path, None
    return None, (f"AU archive 搵唔到 meeting 目錄 `{key}`；"
                  "如果個目錄唔喺 archive，請用 --meeting-dir 指明")


def main():
    ap = argparse.ArgumentParser(description="由 cache 生成覆盤賽果檔")
    ap.add_argument("--meeting", help="對應表嘅 key，例如「2026-08-01 Flemington Race 1-9」")
    ap.add_argument("--meeting-dir", help="寫落邊個目錄（預設用 --meeting 推）")
    ap.add_argument(
        "--top",
        type=int,
        default=0,
        help="每場最多寫幾名（0 = 全部，預設）",
    )
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
    # 預設寫齊全副出馬名單。以前呢度硬截頭 6 名 —— cache 本身有齊每匹馬
    # （每個 runner 自己嗰條 form line 就係佢喺呢場嘅名次），所以嗰個 cap 係
    # 淨蝕：2026-08-30 四個場次 270 行只寫低 174 行，丟失 35.6%。
    #
    # 兩個下游因此壞咗：
    #   1. 任何用呢個檔嘅 SP 計 ROI 都有生存者偏差 —— 跑第 7 名之後嘅首選冇
    #      SP，會被靜靜咁剔出分母。實測同一批注：截住計 +3.7%，寫齊計 -19.8%。
    #   2. `form_score` 讀唔到嘅名次會當「未上名 → 中性 60」，等於將真嘅差績
    #      洗白成冇資料。
    if args.top > 0:
        for rno in races:
            races[rno] = races[rno][:args.top]

    meta = ids[key]
    venue = meta["slug"].replace("_", " ").title()
    dest_dir, err = resolve_dest_dir(key, args.meeting_dir)
    if dest_dir is None:
        print(f"❌ {err}")
        return 1
    dest = dest_dir / "Race_Results_Reflector.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(render(venue, meta["date"], races), encoding="utf-8")
    print(f"✅ {len(races)} 場賽果 → {dest}")
    if warn:
        print(f"   ⚠️ {warn}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

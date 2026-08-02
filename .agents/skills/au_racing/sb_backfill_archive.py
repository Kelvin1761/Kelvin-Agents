#!/usr/bin/env python3
"""用 Sportsbet 重抽歷史馬場 —— 補返 Racenet 從來冇畀過嘅欄位。

點解值得重抽：archive 而家 480/713 場**完全冇**段速實速數據，賽績線 88.5% 冇對手線。
Sportsbet 同一批場次有 ~92–96%。同一引擎同一權重，九場 Flemington 換咗數據源之後
Miss 由 3 場變 0 場、前三精準 41% → 67%。

⚠️ 發現途徑（呢個係關鍵）：sportsbetform **首頁 403**，所以歷史 meetingId 唔可以
   靠索引頁攞。但 **puntcdn 嘅 PDF 完全通**（實測 200、1.4MB），而檔名本身就編碼晒：

       //puntcdn.com/form-guides-sportsbet/20260801_flemington_446234.pdf
                                            ^日期     ^馬場      ^meetingId

   而且 puntcdn 係另一個 host，唔受 sportsbetform 嘅 rate limit 影響。

⚠️ Rate limit 係真嘅、而且突然：約十個急促請求之後，一個啱啱通到嘅頁面就開始 403。
   所以呢個腳本：
     * 預設每個請求隔 12 秒（比日常抓取保守）
     * 撞到拒絕就指數退避
     * **每次抓到就落 cache** —— 中斷之後重跑會由斷點續，唔會重打
     * `--max-meetings` 限制單次跑幾多個馬場，方便分批做

用法：
    # 睇下邊啲 archive 場次搵到對應嘅 Sportsbet meetingId（唔會抓賽事頁）
    python3 sb_backfill_archive.py --plan

    # 分批重抽（建議一次三兩個馬場，跑完再跑）
    python3 sb_backfill_archive.py --run --max-meetings 2 --out-root /tmp/sb_archive
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from claw_sportsbet_form import (  # noqa: E402
    BASE, SportsbetFormFetcher, parse_race, parse_runner_blocks, write_meeting)

PDF_BASE = "https://puntcdn.com/form-guides-sportsbet"
# archive 目錄名 → Sportsbet 檔名用嘅 slug
TRACK_SLUG = {
    "rosehill gardens": "rosehill_gardens", "flemington": "flemington",
    "randwick": "randwick", "caulfield": "caulfield", "doomben": "doomben",
    "eagle farm": "eagle_farm", "moonee valley": "moonee_valley",
    "sandown lakeside": "sandown_lakeside", "sandown hillside": "sandown_hillside",
    "geelong": "geelong", "ballarat": "ballarat", "warwick farm": "warwick_farm",
    "sunshine coast": "sunshine_coast", "newcastle": "newcastle",
    "morphettville": "morphettville", "belmont": "belmont",
}


def archive_meetings():
    from wongchoi_paths import AU_RACING

    root = Path(AU_RACING)
    roots = [root] + ([root / "Archive"] if (root / "Archive").exists() else [])
    out, seen = [], set()
    for r in roots:
        try:
            entries = sorted(p for p in r.iterdir() if p.is_dir())
        except OSError:
            continue
        for p in entries:
            m = re.match(r"(\d{4})-(\d{2})-(\d{2})\s+(.+?)\s+Race", p.name)
            if not m or p.name in seen:
                continue
            seen.add(p.name)
            out.append((p, f"{m.group(1)}{m.group(2)}{m.group(3)}",
                        m.group(4).strip().lower()))
    return out


def find_meeting_id(fetcher, yyyymmdd, track_name):
    """由 puntcdn PDF 檔名反查 meetingId。

    冇索引可以查，所以用**已知格式 + HEAD 探測**：檔名係
    `{date}_{track_slug}_{meetingId}.pdf`，而 meetingId 我哋唔知 —— 所以呢個函數
    只可以喺已知 ID 時做驗證。真正嘅 ID 發現要行 sportsbet.com.au 嘅
    NextEvents API（當日）或者由用戶提供。歷史場次冇公開索引係已知限制。
    """
    slug = TRACK_SLUG.get(track_name)
    if not slug:
        return None, f"未知馬場 slug：{track_name}"
    return None, (f"需要 meetingId —— puntcdn 檔名格式 "
                  f"{yyyymmdd}_{slug}_<meetingId>.pdf，但冇公開索引可以反查。"
                  f"當日場次用 NextEvents API；歷史場次要人手提供 ID。")


def backfill(mapping, out_root, delay=12.0, max_meetings=3, verbose=True):
    """`mapping` = [(meeting_dir, date_str, venue, meeting_id, [race_ids])]。"""
    f = SportsbetFormFetcher(delay=delay, verbose=verbose)
    done = 0
    for meeting_dir, date_str, venue, mid, race_ids in mapping[:max_meetings]:
        out = Path(out_root) / meeting_dir.name
        races = []
        for rid in race_ids:
            html = f.get(f"{BASE}/{mid}/{rid}/")
            if not html:
                print(f"   ⚠️ {meeting_dir.name} race {rid} 攞唔到，跳過")
                continue
            pr = parse_race(html)
            races.append((pr["meta"].get("race_number", len(races) + 1), pr,
                          parse_runner_blocks(html)))
        if races:
            write_meeting(races, out, date_str, venue, verbose=verbose)
            done += 1
            print(f"   ✅ {meeting_dir.name}: {len(races)} 場 → {out}")
    return done


def main():
    ap = argparse.ArgumentParser(description="用 Sportsbet 重抽歷史馬場")
    ap.add_argument("--plan", action="store_true", help="只列 archive 場次同 slug 對應")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--out-root", default="/tmp/sb_archive")
    ap.add_argument("--delay", type=float, default=12.0)
    ap.add_argument("--max-meetings", type=int, default=3)
    ap.add_argument("--mapping", help="JSON: [[dir, date, venue, meetingId, [raceIds]]]")
    args = ap.parse_args()

    if args.plan or not args.run:
        ms = archive_meetings()
        known = [m for m in ms if m[2] in TRACK_SLUG]
        print(f"archive 有 {len(ms)} 個場次，其中 {len(known)} 個馬場 slug 已知\n")
        print(f"{'目錄':46}{'日期':>10}  puntcdn 檔名（缺 meetingId）")
        for p, d, t in known[:15]:
            print(f"{p.name[:44]:46}{d:>10}  {d}_{TRACK_SLUG[t]}_<id>.pdf")
        miss = sorted({t for _, _, t in ms if t not in TRACK_SLUG})
        if miss:
            print(f"\n未有 slug 對應（要加入 TRACK_SLUG）：{miss}")
        print("\n⚠️ 歷史 meetingId 冇公開索引可以反查 —— sportsbetform 首頁 403。"
              "\n   當日場次可以行 NextEvents API；歷史場次要人手提供 ID，"
              "\n   再用 --mapping 餵入。呢個係已知限制，唔係未寫。")
        return 0

    if not args.mapping:
        print("❌ --run 要 --mapping（見 --plan 嘅說明）")
        return 1
    import json
    raw = json.loads(Path(args.mapping).read_text())
    mapping = [(Path(d), dt, v, mid, rids) for d, dt, v, mid, rids in raw]
    n = backfill(mapping, args.out_root, args.delay, args.max_meetings)
    print(f"完成 {n} 個馬場")
    return 0


if __name__ == "__main__":
    sys.exit(main())

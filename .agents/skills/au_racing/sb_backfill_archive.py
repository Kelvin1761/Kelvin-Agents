#!/usr/bin/env python3
"""用 Sportsbet 重抽歷史馬場。

點解值得重抽：archive 而家 480/713 場**完全冇**段速實速數據，賽績線 88.5% 冇對手線。
Sportsbet 同一批場次寫得到，而且帶埋馬群大細、起步定位同 600m 段速。

⚠️ **唔好引用舊嗰個「Miss 3→0、前三精準 41%→67%」。** 嗰個係賽後洩漏量出嚟嘅
   （見 `6c02caa`）。濾走洩漏之後，同頭馬有關嘅優勢完全消失。重抽嘅理由係
   **覆蓋率**，唔係已證實嘅準確度提升 —— 幅度要等呢次重抽做完先講得。

⚠️ 呢個腳本會**丟走**任何日期喺場次當日或之後嘅往績（`write_meeting` 做），
   因為歷史場次一定係事後抓，唔隔就會逐場食自己嘅賽果。每個馬場都會印
   `丟走賽後 N` —— 呢個數係 tripwire，長期見到 0 就要懷疑 filter 壞咗。

meetingId 由 `data/sb_archive_meeting_ids.json` 嚟（94 個場次 / 836 場，
2025-08-02 → 2026-08-01），已經由 `/{YYYY-MM-DD}/` 索引頁解晒 —— 見
`load_meeting_ids()`。

⚠️ Rate limit 係真嘅、而且突然：約十個急促請求之後，一個啱啱通到嘅頁面就開始 403。
   所以呢個腳本：
     * 預設每個請求隔 12 秒（比日常抓取保守）
     * 撞到拒絕就指數退避
     * **每次抓到就落 cache** —— 中斷之後重跑會由斷點續，唔會重打
     * 每個馬場抽完即刻寫檔；已經有 `Meeting_Summary.md` 嘅會跳過
     * `--max-meetings` 限制單次跑幾多個馬場，方便分批做

用法：
    python3 sb_backfill_archive.py --plan
    python3 sb_backfill_archive.py --run --max-meetings 2 --out-root /tmp/sb_archive
    python3 sb_backfill_archive.py --run --only Flemington --max-meetings 99
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


MEETING_IDS = Path(__file__).resolve().parent / "data" / "sb_archive_meeting_ids.json"


def load_meeting_ids(path=MEETING_IDS):
    """已解好嘅 {archive 目錄名: {date, slug, meetingId, races}}。

    ⚠️ 之前呢度寫住「歷史 meetingId 冇公開索引可以反查」。**嗰句係錯嘅。**
    網站首頁「Previous Form Guides」個日曆行 `/{YYYY-MM-DD}/`，嗰版列晒當日
    每個馬場嘅 puntcdn PDF（檔名帶 meetingId）同每一場嘅賽事連結。widget 寫住
    淨係準揀 14 日內，但個限制淨係喺 widget，直接開 URL 至少返到一年前。
    當初搵唔到，係因為只試過 API 同 sitemap，冇睇網站自己個日曆。

    索引版 curl_cffi 一樣 403（同首頁），所以發現行瀏覽器、抽取行 curl_cffi。
    parse 用 `claw_sportsbet_form.parse_date_index()`。
    """
    import json
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"❌ 讀唔到 meetingId 對應表 {path}：{exc}")
        return {}


def scored_meeting_index(root: str | Path) -> dict[str, Path]:
    """Index scored meeting folders below ``root``, including ``Archive/``.

    Research scripts used to assume every meeting was an immediate child of
    the AU root.  Once completed meetings were moved under ``Archive/``, that
    silently turned full-history audits into stale partial-history audits.
    Centralising the recursive lookup keeps every offline evaluator aligned.
    Duplicate folder names are refused because choosing one silently could mix
    two different snapshots of the same meeting.
    """
    root_path = Path(root).expanduser().resolve()
    indexed: dict[str, Path] = {}
    for scoring_path in sorted(root_path.rglob("Meeting_Auto_Scoring.csv")):
        meeting_dir = scoring_path.parent
        existing = indexed.get(meeting_dir.name)
        if existing is not None and existing != meeting_dir:
            raise RuntimeError(
                f"duplicate scored meeting folder {meeting_dir.name!r}: "
                f"{existing} and {meeting_dir}"
            )
        indexed[meeting_dir.name] = meeting_dir
    return indexed


def backfill(mapping, out_root, delay=12.0, max_meetings=3, verbose=True,
             cache_only=False):
    """`mapping` = [(dir_name, date_str, venue, meeting_id, [race_ids])]。

    每個馬場抽完即刻寫檔 + 更新馬匹索引，所以中途斷咗，已完成嗰啲唔會蝕。
    抓過嘅頁面全部落 cache，重跑係由斷點續，唔會重打。
    """
    import sb_horse_index

    f = SportsbetFormFetcher(delay=delay, verbose=False)
    done = skipped = missing_pages = 0
    for dir_name, date_str, venue, mid, race_ids in mapping[:max_meetings]:
        out = Path(out_root) / dir_name
        if (out / "Meeting_Summary.md").exists():
            skipped += 1
            continue
        races, blocks, missing = [], [], 0
        for rid in race_ids:
            url = f"{BASE}/{mid}/{rid}/"
            # ⚠️ cache-only：抽取階段行瀏覽器，呢度就唔應該再出網。冇咗呢個閘，
            # 一個抽漏咗嘅版就會用 `--delay 0` 去打一個啱啱擋過我哋嘅網站。
            if cache_only and not f._cache_path(url).exists():
                missing_pages += 1
                missing += 1
                continue
            html = f.get(url)
            if not html:
                missing += 1
                continue
            pr = parse_race(html)
            blk = parse_runner_blocks(html)
            # ⚠️ 場次一定要由頁面攞。raceId 唔跟場次遞增，用 enumerate 會洗牌。
            rno = pr["meta"].get("race_number")
            if rno is None:
                print(f"   ⚠️ {dir_name} {rid}：讀唔到場次號，跳過")
                continue
            races.append((rno, pr, blk))
            blocks += blk
        if not races:
            print(f"   ❌ {dir_name}：一場都攞唔到（可能撞 rate limit）")
            continue
        races.sort(key=lambda x: x[0])
        stats = write_meeting(races, out, date_str, venue, verbose=False)
        idx = sb_horse_index.update(blocks)
        done += 1
        flag = f"  ⚠️ 缺 {missing} 場" if missing else ""
        print(f"   ✅ {dir_name}: {len(races)} 場、往績 {stats['kept']} 條"
              f"（丟走賽後 {stats['dropped']}）、索引 {idx['index_size']:,} 匹{flag}",
              flush=True)
    if skipped:
        print(f"   ⏭️ 已經有嘅跳過 {skipped} 個")
    if missing_pages:
        print(f"   ⚠️ {missing_pages} 版唔喺 cache，cache-only 之下跳過（未抽到）")
    return done


def main():
    ap = argparse.ArgumentParser(description="用 Sportsbet 重抽歷史馬場")
    ap.add_argument("--plan", action="store_true", help="只列 archive 場次同已解 meetingId")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--out-root", default="/tmp/sb_archive")
    ap.add_argument("--delay", type=float, default=12.0)
    ap.add_argument("--max-meetings", type=int, default=3)
    ap.add_argument("--mapping", help="自訂 JSON；預設用 data/sb_archive_meeting_ids.json")
    ap.add_argument("--only", help="淨係做名入面含呢個字嘅場次（例如 Flemington）")
    ap.add_argument("--cache-only", action="store_true",
                    help="只讀 cache，一個網絡請求都唔出（抽取行瀏覽器嗰陣用）")
    args = ap.parse_args()

    ids = load_meeting_ids(args.mapping or MEETING_IDS)
    if not ids:
        return 1
    rows = sorted(ids.items(), key=lambda kv: kv[1]["date"])
    if args.only:
        rows = [r for r in rows if args.only.lower() in r[0].lower()]

    if args.plan or not args.run:
        races = sum(len(v["races"]) for _, v in rows)
        print(f"{len(rows)} 個場次 / {races} 場，"
              f"{rows[0][1]['date']} → {rows[-1][1]['date']}\n")
        print(f"{'目錄':46}{'meetingId':>11}{'場數':>6}")
        for name, v in rows[:20]:
            print(f"{name[:44]:46}{v['meetingId']:>11}{len(v['races']):>6}")
        if len(rows) > 20:
            print(f"... 仲有 {len(rows)-20} 個")
        print(f"\n預計請求 {races} 個 × {args.delay:.0f}s ≈ "
              f"{races*args.delay/3600:.1f} 小時（cache 命中唔計）")
        return 0

    mapping = [(name, v["date"],
                v["slug"].replace("_", " ").title(), v["meetingId"], v["races"])
               for name, v in rows]
    n = backfill(mapping, args.out_root, args.delay, args.max_meetings,
                 cache_only=args.cache_only)
    print(f"完成 {n} 個馬場 → {args.out_root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

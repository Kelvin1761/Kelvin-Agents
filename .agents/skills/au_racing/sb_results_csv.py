#!/usr/bin/env python3
"""由 Sportsbet cache 生成 `au_archive_calibrator` 食嘅歷史賽果 CSV。

點解需要：`au_runtime_micro_ablation.py`、`au_archive_calibrator.py` 同一系列
離線工具全部要一個 `--results-csv`，而現有嗰個係 Racenet 年代嘅產物。要喺
Sportsbet 語料上跑任何 ablation 或者重配權，就要一個由 Sportsbet 生成、
覆蓋同一批場次嘅賽果檔。

⚠️ 賽果由**每匹馬往績嘅第一行**嚟（`Finished 3/11 0.42L`）—— 即係
`claw_sportsbet_form.write_meeting` 為咗防洩漏而特意丟走嗰行。
**做標準答案啱，做評分輸入唔啱**，同 `au_source_compare.results_from_cache`
同一個道理。呢個檔只准喺評分完成之後 join，唔可以入 race_context。

全程讀 cache，零網絡請求。

用法：
    python3 sb_results_csv.py --out /tmp/sb_results.csv
"""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

FIELDS = ("Date", "Track", "Race", "Horse", "Pos", "Barrier", "SP", "Condition")


def iso_date(value: str) -> str:
    """Argparse validator; keeping the normalised ISO string makes comparisons cheap."""
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"日期要用 YYYY-MM-DD：{value}") from exc


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="由 cache 生成歷史賽果 CSV")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument(
        "--from-date",
        type=iso_date,
        help="只處理呢日或之後嘅 meeting；避免 daily ingest 每晚重掃完整 cache",
    )
    ap.add_argument("--mapping", type=Path,
                    help="自訂 meeting-ID mapping；預設用現役 AU data mapping")
    return ap


def meeting_items(ids: dict, from_date: str | None = None):
    """Return deterministically ordered meetings, optionally bounded by race date."""
    items = sorted(ids.items(), key=lambda kv: str(kv[1].get("date") or ""))
    if from_date:
        items = [item for item in items
                 if str(item[1].get("date") or "") >= from_date]
    return items


def rows_for_meeting(meta, fetcher):
    """→ 每個跑手一行。淨讀 cache；未抽過嘅場次直接跳。"""
    from claw_sportsbet_form import (BASE, parse_race, parse_runner_blocks,
                                     run_date)

    track = meta["slug"].replace("_", " ").title()
    out = []
    for rid in meta["races"]:
        url = f"{BASE}/{meta['meetingId']}/{rid}/"
        if not fetcher._cache_path(url).exists():
            continue
        html = fetcher.get(url)
        pr = parse_race(html)
        rno = pr["meta"].get("race_number")
        if rno is None:
            continue
        cond = pr["meta"].get("track_condition") or ""
        # 檔位由賽事頁 overview 攞，唔係由往績行 —— 往績行嗰個係嗰匹馬**嗰日**
        # 嘅檔位，同今日無關。
        barrier_by_name = {(v.get("name") or "").lower(): v.get("barrier")
                           for v in pr["overview"].values()}
        for blk in parse_runner_blocks(html):
            for run in blk.get("runs", []):
                h = run.get("header") or {}
                if run_date(run) != meta["date"] or str(h.get("race")) != str(rno):
                    continue
                try:
                    pos = int(run["pos"])
                except (TypeError, ValueError, KeyError):
                    break
                out.append({"Date": meta["date"], "Track": track, "Race": rno,
                            "Horse": blk["name"], "Pos": pos,
                            "Barrier": barrier_by_name.get(blk["name"].lower()) or "",
                            "SP": run.get("sp") or "", "Condition": cond})
                break
    return out


def main():
    args = build_parser().parse_args()

    from claw_sportsbet_form import SportsbetFormFetcher
    from sb_backfill_archive import load_meeting_ids

    f = SportsbetFormFetcher(delay=0.0, verbose=False)
    ids = load_meeting_ids(args.mapping) if args.mapping else load_meeting_ids()
    rows, meetings = [], 0
    for name, meta in meeting_items(ids, args.from_date):
        got = rows_for_meeting(meta, f)
        if got:
            meetings += 1
            rows += got
    if not rows:
        print("❌ cache 冇任何賽果 —— 先跑抽取")
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    races = len({(r["Date"], r["Race"], r["Track"]) for r in rows})
    scope = f"（{args.from_date} 起）" if args.from_date else ""
    print(f"✅ {meetings} 場次 / {races} 場 / {len(rows)} 個跑手{scope} → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

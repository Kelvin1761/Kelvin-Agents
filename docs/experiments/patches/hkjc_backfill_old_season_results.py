#!/usr/bin/env python3
"""EXP-20261111-21 — 補抓 HKJC 舊季賽果（研究用，唯讀 HKJC 公開賽果頁，唔寫入賽果庫）。

點解唔寫入 `HKJC_Race_Results_Database`：引擎嘅 point-in-time 騎練 priors 讀嗰度，
加舊季 = 改咗 live 模型嘅輸入。呢度只係俾研究用（例如「潘頓棄騎」嘅市場鏡頭）。

輸出：<HK data root>/_research_old_season_results/<YYYY-MM-DD>.json（同 fast_extract_results 一樣嘅格式）
已經抓過嘅日子會跳過；冇賽事嘅日子記入 _no_meeting.txt，下次唔再 probe。

每場最多試 3 次先當「呢日冇呢場」：第一版一次失敗就收工，令 2021-07-04、2024-02-15
兩個賽日靜靜得返 3 場、1 場（2026-11-11 發現）。`--verify` 逐個已存賽日 probe 下一場，
仲有就成日重抓。

    python3 docs/experiments/patches/hkjc_backfill_old_season_results.py 2019-09-01 2020-07-31
    python3 docs/experiments/patches/hkjc_backfill_old_season_results.py --verify
"""
from __future__ import annotations

import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / ".agents/skills/hkjc_racing/hkjc_race_extractor/scripts"))
from fast_extract_results import extract_race_data  # noqa: E402

HK_ROOT = Path((REPO / ".wongchoi_hk_data_root").read_text(encoding="utf-8").strip())
OUT = HK_ROOT / "_research_old_season_results"


def fetch(ds: str, rn: int, venue: str, tries: int = 3):
    for attempt in range(tries):
        data = extract_race_data(ds, rn, venue)
        if data and data.get("results"):
            return data
        time.sleep(1.5 * (attempt + 1))
    return None


def fetch_day(ds: str, first: dict) -> dict:
    day = {"1": first}
    venue = first.get("venue", "Unknown")
    for rn in range(2, 13):
        time.sleep(0.5)
        data = fetch(ds, rn, venue)
        if not data:
            break
        day[str(rn)] = data
    return day


def save(target: Path, day: dict) -> None:
    tmp = target.with_suffix(".partial")
    tmp.write_text(json.dumps(day, ensure_ascii=False), encoding="utf-8")
    tmp.rename(target)


def verify() -> int:
    fixed = 0
    for target in sorted(OUT.glob("20*.json")):
        day = json.loads(target.read_text(encoding="utf-8"))
        ds, n = target.stem, len(day)
        if not fetch(ds, n + 1, "Unknown"):
            continue
        full = fetch_day(ds, fetch(ds, 1, "Unknown") or day["1"])
        if len(full) > n:
            save(target, full)
            fixed += 1
            print(f"{ds}: {n} → {len(full)} races", flush=True)
    print(f"verify done: {fixed} meetings repaired", flush=True)
    return 0


def main(start: str, end: str) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    skip_file = OUT / "_no_meeting.txt"
    no_meeting = set(skip_file.read_text().split()) if skip_file.exists() else set()
    d, stop = date.fromisoformat(start), date.fromisoformat(end)
    meetings = races = 0
    while d <= stop:
        ds = d.isoformat()
        d += timedelta(days=1)
        target = OUT / f"{ds}.json"
        if target.exists() or ds in no_meeting:
            continue
        first = fetch(ds, 1, "Unknown")
        if not first or not first.get("results"):
            with skip_file.open("a") as fh:
                fh.write(ds + "\n")
            continue
        day = fetch_day(ds, first)
        venue = first.get("venue", "Unknown")
        save(target, day)
        meetings += 1
        races += len(day)
        print(f"{ds} {venue} {len(day)} races", flush=True)
        time.sleep(0.5)
    print(f"done {start}→{end}: {meetings} meetings, {races} races", flush=True)
    return 0


if __name__ == "__main__":
    if sys.argv[1:] == ["--verify"]:
        raise SystemExit(verify())
    raise SystemExit(main(sys.argv[1], sys.argv[2]))

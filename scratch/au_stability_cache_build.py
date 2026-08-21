#!/usr/bin/env python3
"""抽 per-run 名次 / 輸距 / 走位軌跡落本地 cache，為「馬群大細 + 輸距」修正做準備。

用引擎自己嘅 record-table parser（`_record_rows`），唔另外發明一套。

同時驗證兩件事：
  1. 輸距 (xx.xL) 喺 archive 嘅密度 —— 稀疏嘅話呢個修正就做唔起。
  2. 「走位軌跡最大位置」做馬群大細 proxy 有幾準 —— 用
     AU_Historical_Raw_Race_Results.csv 逐 (date, track, race) 數行數做 ground truth。

唯讀。輸出 scratch/au_stability_cache.json。
"""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = REPO_ROOT / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR))

from au_archive_calibrator import (  # noqa: E402
    ARCHIVE_ROOT,
    HISTORICAL_RESULTS_CSV,
    iter_logic_rows,
    load_historical_results,
    normalize_track_name,
    parse_int,
)
from au_racing_engine.engine_core import _record_rows  # noqa: E402

PLACE = re.compile(r"^\s*(\d+)")
MARGIN = re.compile(r"\(([-+]?\d+(?:\.\d+)?)L\)")
# 軌跡 grammar: "S6→8th4→4th3→F4" = Settled 6 / 800m 4th / 400m 3rd / Finish 4。
# `8th` 同 `4th` 係**距離標記**（800m / 400m），唔係位置 —— 一個貪心 (\d+) 會當成
# 位置抽走，令馬群大細 proxy 完全失準（2026-07-31 修正）。逐個 leg 明確抽。
TRAJ_LEGS = (
    ("settled", re.compile(r"S(\d+)")),
    ("p800", re.compile(r"8th(\d+)")),
    ("p400", re.compile(r"4th(\d+)")),
    ("finish", re.compile(r"F(\d+)")),
)
VENUE_R = re.compile(r"^(.*?)\s+R\d+\s*$")


def field_size_truth():
    """{(date, track_slug, race_no): runners} straight off the results CSV."""
    counts = Counter()
    with HISTORICAL_RESULTS_CSV.open("r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            race = parse_int(row.get("Race"))
            pos = parse_int(row.get("Pos"))
            if not race or not pos:
                continue
            counts[(str(row.get("Date") or "").strip(),
                    normalize_track_name(row.get("Track") or ""), race)] += 1
    return counts


def parse_runs(facts_section):
    runs = []
    for cols in _record_rows(facts_section or ""):
        kind = cols[1]
        if "試閘" in kind:
            continue
        placing = str(cols[7] or "")
        traj = str(cols[9] or "") if len(cols) > 9 else ""
        pm = PLACE.match(placing)
        mm = MARGIN.search(placing)
        legs = {}
        for name, pattern in TRAJ_LEGS:
            m = pattern.search(traj)
            if m:
                legs[name] = int(m.group(1))
        positions = list(legs.values())
        venue_raw = str(cols[3] or "")
        vm = VENUE_R.match(venue_raw)
        runs.append({
            "kind": kind,
            "date": str(cols[2] or ""),
            "venue": (vm.group(1) if vm else venue_raw).strip(),
            "race_no": parse_int(re.sub(r".*R", "", venue_raw)) if " R" in venue_raw else None,
            "distance": str(cols[4] or ""),
            "place": int(pm.group(1)) if pm else None,
            "margin": float(mm.group(1)) if mm else None,
            "traj": traj,
            "legs": legs,
            # 走位位置最大者 = 馬群大細下限（settled/800m/400m/finish 之中最後嘅位置）
            "traj_max": max(positions) if positions else None,
            "class_move": str(cols[8] or "") if len(cols) > 8 else "",
        })
    return runs


def main():
    truth = field_size_truth()
    results = load_historical_results(HISTORICAL_RESULTS_CSV)

    races_out = []
    margin_present = margin_total = 0
    traj_present = 0
    proxy_pairs = []          # (traj_max, true_field_size)

    for race_rows in iter_logic_rows(ARCHIVE_ROOT, results):
        rows_out = []
        for r in race_rows:
            runs = parse_runs((r["data"] or {}).get("facts_section"))
            for run in runs:
                margin_total += 1
                if run["margin"] is not None:
                    margin_present += 1
                if run["traj_max"] is not None:
                    traj_present += 1
                key = (run["date"], normalize_track_name(run["venue"]), run["race_no"])
                if run["traj_max"] and key in truth:
                    proxy_pairs.append((run["traj_max"], truth[key]))
            rows_out.append({
                "n": r["horse_number"],
                "name": r["horse_name"],
                "pos": r["actual_pos"],
                "sp": r["sp"],
                "runs": runs,
            })
        races_out.append({
            "meeting": race_rows[0]["meeting"],
            "date": race_rows[0]["date"],
            "race": race_rows[0]["race"],
            "field": len(race_rows),
            "rows": rows_out,
        })

    races_out.sort(key=lambda x: (x["date"], x["meeting"], x["race"]))
    dest = Path(__file__).resolve().parent / "au_stability_cache.json"
    dest.write_text(json.dumps({"races": races_out}), encoding="utf-8")

    print(f"races {len(races_out)}  official runs parsed {margin_total}")
    print(f"輸距有值: {margin_present}/{margin_total} = {100*margin_present/max(1,margin_total):.1f}%")
    print(f"軌跡有值: {traj_present}/{margin_total} = {100*traj_present/max(1,margin_total):.1f}%")
    print(f"\nproxy 驗證樣本 (run 對得上 results CSV): {len(proxy_pairs)}")
    if proxy_pairs:
        exact = sum(1 for a, b in proxy_pairs if a == b)
        within1 = sum(1 for a, b in proxy_pairs if abs(a - b) <= 1)
        over = sum(1 for a, b in proxy_pairs if a > b)
        diffs = Counter(a - b for a, b in proxy_pairs)
        print(f"  traj_max == 真實馬群: {exact}/{len(proxy_pairs)} = {100*exact/len(proxy_pairs):.1f}%")
        print(f"  相差 ≤1:            {within1}/{len(proxy_pairs)} = {100*within1/len(proxy_pairs):.1f}%")
        print(f"  高估 (traj>真實):    {over}/{len(proxy_pairs)} = {100*over/len(proxy_pairs):.1f}%")
        print("  差值分佈 (top 10):", dict(sorted(diffs.items(), key=lambda kv: -kv[1])[:10]))
    print(f"cache → {dest}")


if __name__ == "__main__":
    main()

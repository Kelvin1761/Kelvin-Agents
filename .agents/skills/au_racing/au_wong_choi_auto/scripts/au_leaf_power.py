#!/usr/bin/env python3
"""逐個 leaf 嘅**場內**判別力，喺重抽語料上量。

點解要喺改權重之前做：權重只係放大器 —— 一個場內冇判別力嘅 leaf，加幾多權重
都係加噪音。今日已經見過兩次「覆蓋率升咗但個 leaf 冇用」（PF 寫落死 key、
段速分嘅 PI 排序倒轉）。所以次序係 **量 → 再決定改唔改**，唔係倒轉。

量度用**場內 AUC**（同場兩兩比較）：喺同一場入面隨機抽一匹上名同一匹落榜，
個 leaf 畀上名嗰匹分數高嘅機率。0.50 = 冇資訊，0.60 已經係好強嘅單一 leaf。

⚠️ 一定要**場內**比，唔可以全池比。班次、路程、馬群大細喺場與場之間差好遠，
全池 AUC 會把「呢場係高班賽」當成「呢匹馬好」。

⚠️ 冇證據嗰批（分數 == 中性 60）**預設剔走**，因為佢哋唔係「分數低」，係
「唔知」。溝埋一齊量，會把覆蓋率當成判別力 —— 一個覆蓋 30% 但好準嘅 leaf，
會被 70% 嘅 60 分溝到似冇用。`--include-neutral` 可以睇埋另一個口徑。

用法：
    python3 au_leaf_power.py --scored /tmp/sb_archive
    python3 au_leaf_power.py --scored /tmp/sb_archive --min-depth 4
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
AU_RACING = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(AU_RACING))

NEUTRAL = 60.0


def norm(name):
    s = unicodedata.normalize("NFKD", name or "").lower()
    s = re.sub(r"\([^)]*\)", "", s)
    return re.sub(r"[^a-z0-9]", "", s)


def results_for(meeting):
    """{race_no: {norm_name: finish}} —— 由 cache 嘅賽事頁攞（做標準答案）。"""
    from claw_sportsbet_form import (BASE, SportsbetFormFetcher, parse_race,
                                     parse_runner_blocks, run_date)
    f = SportsbetFormFetcher(delay=0.0, verbose=False)
    out = {}
    for rid in meeting["races"]:
        url = f"{BASE}/{meeting['meetingId']}/{rid}/"
        if not f._cache_path(url).exists():
            continue
        html = f.get(url)
        rno = parse_race(html)["meta"].get("race_number")
        if rno is None:
            continue
        res = {}
        for blk in parse_runner_blocks(html):
            for run in blk.get("runs", []):
                h = run.get("header") or {}
                if run_date(run) == meeting["date"] and str(h.get("race")) == str(rno):
                    try:
                        res[norm(blk["name"])] = int(run["pos"])
                    except (TypeError, ValueError, KeyError):
                        pass
        if res:
            out[rno] = res
    return out


def within_race_auc(pairs):
    """pairs = [(score, placed_bool)] 同一場。回 (concordant, comparable)。

    平手當一半 —— 唔咁做嘅話，一個成場都畀同一個分嘅 leaf 會攞到 AUC 0，
    睇落似「完美反向預測」，其實係完全冇資訊。
    """
    good = [s for s, p in pairs if p]
    bad = [s for s, p in pairs if not p]
    if not good or not bad:
        return 0.0, 0
    c = 0.0
    for g in good:
        for b in bad:
            c += 1.0 if g > b else (0.5 if g == b else 0.0)
    return c, len(good) * len(bad)


def main():
    ap = argparse.ArgumentParser(description="逐個 leaf 嘅場內判別力")
    ap.add_argument("--scored", required=True, help="評分好嘅 out-root")
    ap.add_argument("--min-depth", type=float, default=0.0,
                    help="只計往績深度夠嘅場次（要 source_compare.json）")
    ap.add_argument("--include-neutral", action="store_true",
                    help="連冇證據嘅中性 60 一齊計")
    args = ap.parse_args()

    from sb_backfill_archive import load_meeting_ids

    depth = {}
    cmp_json = Path(args.scored).parent / "source_compare.json"
    if args.min_depth and cmp_json.exists():
        depth = {d["meeting"]: d.get("form_depth", 0)
                 for d in json.loads(cmp_json.read_text())}

    ids = load_meeting_ids()
    acc = {}          # leaf → [concordant, comparable, scored_runners]
    races = 0
    for name, meta in sorted(ids.items(), key=lambda kv: kv[1]["date"]):
        p = Path(args.scored) / name / "Meeting_Auto_Scoring.csv"
        if not p.exists():
            continue
        if args.min_depth and depth.get(name, 0) < args.min_depth:
            continue
        res = results_for(meta)
        if not res:
            continue
        by_race = {}
        with open(p, encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                by_race.setdefault(int(row["race_number"]), []).append(row)
        leaves = [k for k in (next(iter(by_race.values()))[0])
                  if k.endswith("_score")]
        for rno, rows in by_race.items():
            actual = res.get(rno)
            if not actual:
                continue
            races += 1
            for lf in leaves:
                pairs = []
                for r in rows:
                    pos = actual.get(norm(r["horse_name"]))
                    if pos is None or not r.get(lf):
                        continue
                    v = float(r[lf])
                    if not args.include_neutral and abs(v - NEUTRAL) < 1e-9:
                        continue
                    pairs.append((v, pos <= 3))
                c, n = within_race_auc(pairs)
                a = acc.setdefault(lf, [0.0, 0, 0])
                a[0] += c
                a[1] += n
                a[2] += len(pairs)

    if not races:
        print("冇評分好嘅場次")
        return 1
    print(f"{races} 場（{'剔走' if not args.include_neutral else '包含'}中性 60）\n")
    print(f"{'leaf':26}{'場內 AUC':>10}{'可比對數':>12}{'有證據匹數':>12}")
    for lf, (c, n, k) in sorted(acc.items(), key=lambda kv: -(kv[1][0] / kv[1][1])
                                if kv[1][1] else 0):
        if not n:
            continue
        auc = c / n
        mark = "  ★" if auc >= 0.57 else ("  ·" if auc >= 0.53 else "  ✗")
        print(f"{lf:26}{auc:>10.3f}{n:>12,}{k:>12,}{mark}")
    print("\n★ ≥0.570 強 · 0.530–0.569 有料 · <0.530 接近噪音（0.500 = 冇資訊）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

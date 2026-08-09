#!/usr/bin/env python3
"""騎師／練馬師**按今日場地**嘅往績，有冇比 12 個月總計更有料？

點解值得問：`AU_Sportsbet_People_Cache.json` 每個人都存咗
Good / Soft / Heavy / Firm / Synthetic / Turf 嘅 starts-1st-2nd-3rd，
但引擎只收到一個 `(LY: 781:101-110-86)` —— **12 個月總計**。going 分項全部冇用。

而呢個語料 **52% 係軟地或重地**，而且分項真係有差異（實測一個騎師：
好地上名 34.4%、軟地 33.4%、重地 38.4%）。

⚠️ 樣本細嘅分項要收縮（shrink）返總計，否則「重地跑過 3 次贏 2 次」= 67%
會蓋過一個跑過 900 次嘅真實水平。用 Beta 先驗（pseudo-count）。

⚠️ 呢啲統計係**抓取當日**嘅，對歷史場次係向前偷睇（同 LY token 一樣嘅已知
confound，見 REFIT_PLAN.md）。所以呢個量度講「有冇資訊」，而唔可以當成
乾淨嘅歷史回測。要落實之前要用未來場次驗。
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
AU_RACING = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(AU_RACING))
sys.path.insert(0, str(SCRIPT_DIR))

from au_leaf_power import norm, results_for, within_race_auc  # noqa: E402

SHRINK = 30.0          # pseudo-starts，把分項拉返總計
GOING_KEYS = {"good": "Good", "soft": "Soft", "heavy": "Heavy",
              "firm": "Firm", "synthetic": "Synthetic"}


def going_key(track_cond):
    t = (track_cond or "").strip().lower()
    for k, v in GOING_KEYS.items():
        if t.startswith(k):
            return v
    return None


def place_rate(stats, key, prior_key="Career"):
    """收縮後嘅上名率。分項樣本細就靠返總計。"""
    seg = (stats or {}).get(key) or {}
    base = (stats or {}).get(prior_key) or {}
    bs, bp = base.get("starts") or 0, base.get("place_pct")
    if not bs or bp is None:
        return None
    prior = bp / 100.0
    s = seg.get("starts") or 0
    if not s:
        return prior
    p = (seg.get("place_pct") or 0) / 100.0
    return (p * s + prior * SHRINK) / (s + SHRINK)


def main():
    ap = argparse.ArgumentParser(description="騎練 by-going 往績嘅判別力")
    ap.add_argument("--scored", required=True)
    ap.add_argument("--min-depth", type=float, default=4.0)
    args = ap.parse_args()

    from claw_sportsbet_form import (BASE, SportsbetFormFetcher, _match_person,
                                     parse_race)
    from sb_backfill_archive import load_meeting_ids, scored_meeting_index
    import sb_people_stats

    cache = sb_people_stats.load_cache()
    cj = Path(args.scored).parent / "source_compare.json"
    depth = ({d["meeting"]: d.get("form_depth", 0)
              for d in json.loads(cj.read_text())} if cj.exists() else {})
    f = SportsbetFormFetcher(delay=0.0, verbose=False)
    meeting_dirs = scored_meeting_index(args.scored)

    acc = {}
    wet_acc = {}
    races = 0
    for name, meta in sorted(load_meeting_ids().items(), key=lambda kv: kv[1]["date"]):
        meeting_dir = meeting_dirs.get(name)
        if meeting_dir is None or (args.min_depth and depth.get(name, 0) < args.min_depth):
            continue
        p = meeting_dir / "Meeting_Auto_Scoring.csv"
        res = results_for(meta)
        if not res:
            continue
        by_race = {}
        with open(p, encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                by_race.setdefault(int(row["race_number"]), []).append(row)
        for rid in meta["races"]:
            url = f"{BASE}/{meta['meetingId']}/{rid}/"
            if not f._cache_path(url).exists():
                continue
            html = f.get(url)
            pr = parse_race(html)
            rno = pr["meta"].get("race_number")
            actual = res.get(rno)
            rows = by_race.get(rno)
            if not actual or not rows:
                continue
            gk = going_key(pr["meta"].get("track_condition"))
            people = pr["meta"].get("people_by_name") or {}
            ov = {v.get("name", "").lower(): v for v in pr["overview"].values()}
            races += 1
            feats = []
            for r in rows:
                pos = actual.get(norm(r["horse_name"]))
                if pos is None:
                    continue
                o = ov.get(r["horse_name"].lower(), {})
                d = {}
                for kind, tag in (("Jockey", "j"), ("Trainer", "t")):
                    pid = _match_person(people, kind, o.get(kind.lower()) or "")
                    st = (cache.get(f"{kind.lower()}|{pid}") or {}).get("stats") if pid else None
                    if not st:
                        continue
                    d[f"{tag}_12mo"] = place_rate(st, "12 Months")
                    if gk:
                        d[f"{tag}_going"] = place_rate(st, gk)
                feats.append((d, pos <= 3))
            keys = {k for x, _ in feats for k in x if x[k] is not None}
            for k in keys:
                pairs = [(x[k], pl) for x, pl in feats if x.get(k) is not None]
                c, n = within_race_auc(pairs)
                for store in (acc, wet_acc if gk in ("Soft", "Heavy") else None):
                    if store is None:
                        continue
                    a = store.setdefault(k, [0.0, 0, 0])
                    a[0] += c
                    a[1] += n
                    a[2] += len(pairs)

    def show(title, store):
        print(f"\n{title}")
        print(f"{'特徵':22}{'場內 AUC':>10}{'可比對數':>12}")
        for k, (c, n, s) in sorted(store.items(), key=lambda kv: -(kv[1][0]/kv[1][1]) if kv[1][1] else 0):
            if n:
                print(f"{k:22}{c/n:>10.3f}{n:>12,}")
    print(f"{races} 場")
    show("── 全部場地 ──", acc)
    show("── 只計軟地／重地 ──", wet_acc)
    print("\n對照：jockey_score 0.589 · trainer_score 0.571 · form_score 0.608")
    return 0


if __name__ == "__main__":
    sys.exit(main())

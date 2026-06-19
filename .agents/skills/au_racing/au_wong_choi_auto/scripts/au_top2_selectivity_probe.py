#!/usr/bin/env python3
"""Does the model know WHEN its top-2 is trustworthy?
Bucket Flemington/Randwick races by the ability-score gap at the top of the
ranking, then measure top-2-both% (model #1 & #2 both finishing top-3) per bucket.
If high-gap races score much higher, selectivity is a real, actionable lever."""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.append(str(SCRIPT_DIR))
from au_archive_calibrator import (  # noqa: E402
    ARCHIVE_ROOT, HISTORICAL_RESULTS_CSV, choose_track_rows, detect_meeting_date,
    load_scoring_rows, load_historical_results, normalize_horse_name,
    normalize_track_name, parse_int,
)

EVAL = {"flemington", "randwick"}


def mtrack(md):
    n = md.name
    if n[:10].count("-") == 2:
        n = n[11:]
    for s in (" Race 1-10", " Race 1-9", " Race 1-8", " Race 1-7", " Race 1-6"):
        n = n.replace(s, "")
    return n.strip()


def af(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def main():
    hist = load_historical_results(HISTORICAL_RESULTS_CSV)
    races = []  # (gap_2_3, gap_1_2, top2_both, pick1_placed)
    for md in sorted(p for p in ARCHIVE_ROOT.iterdir() if p.is_dir()):
        if normalize_track_name(mtrack(md)) not in EVAL:
            continue
        mdate = detect_meeting_date(md)
        mt = mtrack(md)
        for sp in sorted(md.glob("Race_*_Auto_Scoring.csv")):
            rno = parse_int(sp.stem)
            if not rno:
                continue
            rr = choose_track_rows(hist.get((mdate, rno), []), mt)
            if not rr:
                continue
            lookup = {r["horse_slug"]: r for r in rr}
            joined = []
            for srow in load_scoring_rows(sp):
                res = lookup.get(normalize_horse_name(srow.get("horse_name", "")))
                if res:
                    joined.append({"a": af(srow.get("ability_score")), "pos": int(res["pos"]),
                                   "num": parse_int(srow.get("horse_number")) or 0})
            if len(joined) < 4 or sum(1 for j in joined if j["pos"] <= 3) < 3:
                continue
            rk = sorted(joined, key=lambda j: (-j["a"], j["num"]))
            gap_23 = rk[1]["a"] - rk[2]["a"]
            gap_12 = rk[0]["a"] - rk[1]["a"]
            t2 = all(j["pos"] <= 3 for j in rk[:2])
            races.append((gap_23, gap_12, t2, rk[0]["pos"] <= 3))

    n = len(races)
    base = sum(1 for r in races if r[2]) / n * 100
    print(f"Total eval races: {n} | overall top2-both: {base:.2f}%\n")

    def bucket_report(idx, label):
        print(f"== bucket by {label} (gap between those ranks' ability score) ==")
        vals = sorted(r[idx] for r in races)
        # quartile thresholds
        qs = [vals[int(n * f)] for f in (0.25, 0.5, 0.75)]
        edges = [(-1e9, qs[0], "Q1 low"), (qs[0], qs[1], "Q2"), (qs[1], qs[2], "Q3"), (qs[2], 1e9, "Q4 high")]
        for lo, hi, name in edges:
            sub = [r for r in races if lo <= r[idx] < hi]
            if not sub:
                continue
            t2 = sum(1 for r in sub if r[2]) / len(sub) * 100
            p1 = sum(1 for r in sub if r[3]) / len(sub) * 100
            print(f"  {name:<8} gap[{lo if lo>-1e8 else '-inf':>6}..{hi if hi<1e8 else 'inf':>6}]  "
                  f"races {len(sub):>3}  top2-both {t2:>6.2f}%  pick1-placed {p1:>6.2f}%")
        print()

    bucket_report(0, "rank2 vs rank3")
    bucket_report(1, "rank1 vs rank2")

    # Practical: top-N races by gap_23
    print("== selectivity: take only the highest-gap (rank2-3) races ==")
    by_gap = sorted(races, key=lambda r: -r[0])
    for frac in (0.25, 0.33, 0.50, 1.0):
        k = max(1, int(n * frac))
        sub = by_gap[:k]
        t2 = sum(1 for r in sub if r[2]) / k * 100
        print(f"  top {int(frac*100):>3}% most-confident ({k:>3} races): top2-both {t2:.2f}%")


if __name__ == "__main__":
    main()

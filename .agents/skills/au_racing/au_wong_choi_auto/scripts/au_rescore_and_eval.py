#!/usr/bin/env python3
"""Re-score evaluable AU meetings (Flemington/Randwick — the only tracks with
results) through the live engine, then evaluate Top-3 metrics. Use before/after
an engine change to measure real impact.

  python au_rescore_and_eval.py --rescore   # re-run engine then evaluate
  python au_rescore_and_eval.py             # evaluate current CSVs only
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from collections import Counter
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.append(str(SCRIPT_DIR))

from au_archive_calibrator import (  # noqa: E402
    ARCHIVE_ROOT,
    HISTORICAL_RESULTS_CSV,
    MATRIX_KEYS,
    choose_track_rows,
    detect_meeting_date,
    load_scoring_rows,
    load_historical_results,
    normalize_horse_name,
    normalize_track_name,
    parse_int,
)

AUTO_ORCH = SCRIPT_DIR / "au_auto_orchestrator.py"
EVAL_TRACKS = {"flemington", "randwick"}


def mtrack(md: Path) -> str:
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


def evaluable_meetings() -> list[Path]:
    out = []
    for md in sorted(p for p in ARCHIVE_ROOT.iterdir() if p.is_dir()):
        if normalize_track_name(mtrack(md)) in EVAL_TRACKS:
            out.append(md)
    return out


def rescore(meetings: list[Path]) -> None:
    for i, md in enumerate(meetings, 1):
        print(f"  re-score {i}/{len(meetings)} {md.name}", flush=True)
        r = subprocess.run([sys.executable, str(AUTO_ORCH), str(md)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            sys.stderr.write(f"   !! failed: {md.name}\n{r.stderr[-400:]}\n")


def evaluate(meetings: list[Path]) -> dict:
    historical = load_historical_results(HISTORICAL_RESULTS_CSV)
    b = Counter()
    for md in meetings:
        mdate = detect_meeting_date(md)
        mt = mtrack(md)
        if not mdate:
            continue
        for sp in sorted(md.glob("Race_*_Auto_Scoring.csv")):
            rno = parse_int(sp.stem)
            if not rno:
                continue
            rr = choose_track_rows(historical.get((mdate, rno), []), mt)
            if not rr:
                continue
            lookup = {r["horse_slug"]: r for r in rr}
            joined = []
            for srow in load_scoring_rows(sp):
                res = lookup.get(normalize_horse_name(srow.get("horse_name", "")))
                if res:
                    joined.append({"ability": af(srow.get("ability_score")),
                                   "pos": int(res["pos"]),
                                   "num": parse_int(srow.get("horse_number")) or 0})
            if len(joined) < 4 or sum(1 for j in joined if j["pos"] <= 3) < 3:
                continue
            ranked = sorted(joined, key=lambda j: (-j["ability"], j["num"]))
            hits = sum(1 for j in ranked[:3] if j["pos"] <= 3)
            b["n"] += 1
            b["top3_hits"] += hits
            b["gold"] += 1 if hits == 3 else 0
            b["good"] += 1 if hits >= 2 else 0
            b["pass"] += 1 if hits >= 1 else 0
            b["miss"] += 1 if hits == 0 else 0
            b["win_t3"] += 1 if any(j["pos"] == 1 for j in ranked[:3]) else 0
            # Top-2 picks (model rank 1 & 2) BOTH finishing in actual top-3
            b["top2_both"] += 1 if all(j["pos"] <= 3 for j in ranked[:2]) else 0
            b["pick1_placed"] += 1 if ranked[0]["pos"] <= 3 else 0
            b["pick1_won"] += 1 if ranked[0]["pos"] == 1 else 0
    n = max(1, b["n"])
    return {"races": b["n"], "good_rate": b["good"] / n * 100, "top3": b["top3_hits"] / (3 * n) * 100,
            "win_t3": b["win_t3"] / n * 100, "gold": b["gold"], "good": b["good"], "miss": b["miss"],
            "top2_both": b["top2_both"] / n * 100, "top2_both_n": b["top2_both"],
            "pick1_placed": b["pick1_placed"] / n * 100, "pick1_won": b["pick1_won"] / n * 100}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rescore", action="store_true")
    ap.add_argument("--tag", default="")
    args = ap.parse_args()
    meetings = evaluable_meetings()
    print(f"Evaluable meetings (Flemington/Randwick): {len(meetings)}", flush=True)
    if args.rescore:
        print("Re-scoring through live engine...", flush=True)
        rescore(meetings)
    m = evaluate(meetings)
    tag = f" [{args.tag}]" if args.tag else ""
    print("\n" + "=" * 56)
    print(f"EVAL{tag}  —  {m['races']} races")
    print("=" * 56)
    print(f"  Good% (>=2 of top3 picks placed) : {m['good_rate']:.2f}   ({m['good']} races)")
    print(f"  Top2-both% (#1 & #2 both placed) : {m['top2_both']:.2f}   ({m['top2_both_n']} races)")
    print(f"  Pick#1 placed%                   : {m['pick1_placed']:.2f}")
    print(f"  Pick#1 won%                      : {m['pick1_won']:.2f}")
    print(f"  Top3%  (precision of 3 picks)    : {m['top3']:.2f}")
    print(f"  Winner-in-top3-picks%            : {m['win_t3']:.2f}")
    print(f"  Gold (3/3)                       : {m['gold']}")
    print(f"  Miss (0/3)                       : {m['miss']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

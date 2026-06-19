#!/usr/bin/env python3
"""One-pass probe: bug footprint + historical cost + baseline Top3 metrics.

- Bug #1: horses dropped from Logic when weight unknown (Facts emit `負重: 未知`).
  Measured directly as result-horses (esp. top-3) absent from Auto_Scoring.csv.
- Bug #2: `Rating: -`/blank racecard meta lines (rating silently lost).
- Baseline: rank each race by ability_score, score Gold/Good/Top3 vs results.
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.append(str(SCRIPT_DIR))

from au_archive_calibrator import (  # noqa: E402
    ARCHIVE_ROOT,
    HISTORICAL_RESULTS_CSV,
    choose_track_rows,
    detect_meeting_date,
    load_scoring_rows,
    load_historical_results,
    normalize_horse_name,
    parse_int,
)


def meeting_track(meeting_dir: Path) -> str:
    name = meeting_dir.name
    if name[:10].count("-") == 2:
        name = name[11:]
    for suffix in (" Race 1-10", " Race 1-9", " Race 1-8", " Race 1-7", " Race 1-6"):
        name = name.replace(suffix, "")
    return name.strip()


def af(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def main() -> int:
    print("Loading historical results...", flush=True)
    historical = load_historical_results(HISTORICAL_RESULTS_CSV)
    print(f"  {len(historical)} date/race keys", flush=True)

    facts_unknown_weight = 0          # bug #1 footprint (Facts side)
    racecard_bad_rating = 0           # bug #2 footprint
    files_facts = 0
    files_racecard = 0

    races_eval = 0
    dropped_horses = 0                # result horse missing from scoring
    dropped_top3 = 0                  # and that horse finished top-3
    bucket = Counter()

    meeting_dirs = sorted(p for p in ARCHIVE_ROOT.iterdir() if p.is_dir())
    for idx, md in enumerate(meeting_dirs, 1):
        if idx == 1 or idx % 10 == 0:
            print(f"  {idx}/{len(meeting_dirs)} {md.name}", flush=True)
        mdate = detect_meeting_date(md)
        mtrack = meeting_track(md)

        # ---- footprint scans (cheap text) ----
        for f in md.glob("*Facts.md"):
            files_facts += 1
            try:
                facts_unknown_weight += f.read_text(encoding="utf-8").count("負重: 未知")
            except OSError:
                pass
        for f in md.glob("*Racecard.md"):
            files_racecard += 1
            try:
                txt = f.read_text(encoding="utf-8")
            except OSError:
                continue
            racecard_bad_rating += len(re.findall(r"Rating:\s*(?:[-—]|\|)", txt))

        if not mdate or not mtrack:
            continue

        # ---- per-race baseline + drop cost ----
        for scoring_path in sorted(md.glob("Race_*_Auto_Scoring.csv")):
            race_no = parse_int(scoring_path.stem)
            if not race_no:
                continue
            result_rows = choose_track_rows(historical.get((mdate, race_no), []), mtrack)
            if not result_rows:
                continue
            scoring_rows = load_scoring_rows(scoring_path)
            scored_slugs = {normalize_horse_name(r.get("horse_name", "")) for r in scoring_rows}

            # drop cost: result horses absent from scoring output
            for rr in result_rows:
                if rr["horse_slug"] not in scored_slugs:
                    dropped_horses += 1
                    if int(rr["pos"]) <= 3:
                        dropped_top3 += 1

            # baseline metric: join scoring->result, rank by ability_score
            lookup = {rr["horse_slug"]: rr for rr in result_rows}
            joined = []
            for sr in scoring_rows:
                rr = lookup.get(normalize_horse_name(sr.get("horse_name", "")))
                if rr:
                    joined.append({"ability": af(sr.get("ability_score")), "pos": int(rr["pos"]),
                                   "num": parse_int(sr.get("horse_number")) or 0})
            if len(joined) < 4 or sum(1 for j in joined if j["pos"] <= 3) < 3:
                continue
            races_eval += 1
            ranked = sorted(joined, key=lambda j: (-j["ability"], j["num"]))
            hits = sum(1 for j in ranked[:3] if j["pos"] <= 3)
            bucket[f"{hits}hit"] += 1
            bucket["top3_hits"] += hits
            bucket["winner_in_top3"] += 1 if any(j["pos"] == 1 for j in ranked[:3]) else 0
            bucket["top1_win"] += 1 if ranked[0]["pos"] == 1 else 0
            bucket["gold"] += 1 if hits == 3 else 0
            bucket["good"] += 1 if hits >= 2 else 0
            bucket["pass"] += 1 if hits >= 1 else 0

    n = max(1, races_eval)
    print("\n" + "=" * 64)
    print("BUG FOOTPRINT")
    print("=" * 64)
    print(f"Facts files scanned          : {files_facts}")
    print(f"  '負重: 未知' occurrences    : {facts_unknown_weight}  (BUG #1 emit side)")
    print(f"Racecard files scanned       : {files_racecard}")
    print(f"  'Rating: -'/blank lines     : {racecard_bad_rating}  (BUG #2)")
    print()
    print("HISTORICAL COST OF DROPPED HORSES (bug #1 realised)")
    print(f"  result horses missing from scoring : {dropped_horses}")
    print(f"  ...of which finished TOP-3          : {dropped_top3}")
    print()
    print("=" * 64)
    print(f"BASELINE (ability_score ranking)  —  {races_eval} eval races")
    print("=" * 64)
    print(f"Gold (3/3) : {bucket['gold']:>4}  ({bucket['gold']/n*100:5.2f}%)")
    print(f"Good (>=2) : {bucket['good']:>4}  ({bucket['good']/n*100:5.2f}%)")
    print(f"Pass (>=1) : {bucket['pass']:>4}  ({bucket['pass']/n*100:5.2f}%)")
    print(f"Miss (0)   : {bucket['0hit']:>4}  ({bucket['0hit']/n*100:5.2f}%)")
    print(f"Top3 prec  : {bucket['top3_hits']/(3*n)*100:5.2f}%")
    print(f"Win-in-T3  : {bucket['winner_in_top3']/n*100:5.2f}%")
    print(f"Top1 win   : {bucket['top1_win']/n*100:5.2f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

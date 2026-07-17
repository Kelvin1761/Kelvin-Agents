#!/usr/bin/env python3
"""Ordering-features Phase 0: extract pairwise raw material and measure coverage.

From every refreshed Logic (sandbox copy of the adopted archive), per horse:
- 賽績線 encounters: (date, my finish pos, my margin, rival name, rival slot
  頭馬/亞軍/季軍, rival franking text);
- L400 sectionals from the formal-record table;
- last formal margin.

Then measure: horses with formline rows; shortlist(top-4) H2H pair coverage;
coverage inside the 285 ordering-opportunity races; L400 coverage.
Writes scratch/au_ordering_features_raw.json for Phase 1.
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

SCRIPTS = Path("/Users/imac/Antigravity-repo/.agents/skills/au_racing/au_wong_choi_auto/scripts")
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "racing_engine"))

from au_archive_calibrator import normalize_horse_name  # noqa: E402
from au_cached_walkforward_ml import as_float, group_races, materialize_dataset  # noqa: E402

ROOT = Path("/private/tmp/claude-501/-Users-imac-Antigravity-repo/b09ea7dc-ca6d-496d-af27-41b7787ee6ae/scratchpad/data/Wong Choi Horse Race Analysis/AU_Racing")
OUT = Path("/Users/imac/Antigravity-repo/scratch/au_ordering_features_raw.json")

ENCOUNTER_ROW = re.compile(r"^\|\s*(\d*)\s*\|\s*([\d-]*)\s*\|\s*([^|]*)\|\s*([^|]*)\|\s*\[(\d+)\]\s*([^(|]+)\(([^)|]+)\)\s*\|\s*([^|]*)\|\s*([^|]*)\|")
MY_POS = re.compile(r"^(\d+)(?:\s*\(([-+][\d.]+)L\))?")
L400 = re.compile(r"\b(3[0-9]\.\d{2})\b")
FORMAL_ROW = re.compile(r"^\|\s*\d+\s*\|\s*正式\s*\|")


def parse_horse(fs: str) -> dict:
    encounters = []
    current_date = current_pos = current_margin = None
    in_formline = False
    l400s = []
    for line in fs.splitlines():
        text = line.strip()
        if "賽績線" in text:
            in_formline = True
        if in_formline and text.startswith("|"):
            m = ENCOUNTER_ROW.match(text)
            if m:
                idx, date, _race, my_pos_cell, r_num, r_name, r_slot, _next_class, franking = m.groups()
                if date:
                    current_date = date
                    pm = MY_POS.match(my_pos_cell.strip())
                    current_pos = int(pm.group(1)) if pm else None
                    current_margin = float(pm.group(2)) if pm and pm.group(2) else None
                encounters.append({
                    "date": current_date,
                    "my_pos": current_pos,
                    "my_margin": current_margin,
                    "rival": normalize_horse_name(r_name.strip()),
                    "rival_slot": r_slot.strip(),
                    "franking": franking.strip(),
                })
        if FORMAL_ROW.match(text):
            sm = L400.search(text)
            if sm:
                l400s.append(float(sm.group(1)))
    return {"encounters": encounters, "l400s": l400s[:6]}


def main() -> int:
    per_horse = {}
    meetings = sorted(p for p in ROOT.iterdir() if p.is_dir())
    for d in meetings:
        for lp in d.glob("Race_*_Logic.json"):
            try:
                data = json.loads(lp.read_text(encoding="utf-8"))
            except Exception:
                continue
            race_no = str((data.get("race_analysis") or {}).get("race_number") or lp.stem.split("_")[1])
            for num, h in (data.get("horses") or {}).items():
                fs = (h.get("_data") or {}).get("facts_section") or ""
                parsed = parse_horse(fs)
                parsed["name"] = normalize_horse_name(str(h.get("horse_name") or ""))
                per_horse[f"{d.name}|{race_no}|{num}"] = parsed
    OUT.write_text(json.dumps(per_horse), encoding="utf-8")
    print(f"parsed {len(per_horse)} horses -> {OUT.name}")

    # coverage vs cached races
    races = group_races(materialize_dataset())
    tot = with_rows = with_l400 = 0
    pair_cov = Counter = defaultdict(int)
    opp_total = opp_with_h2h = 0
    h2h_pairs_total = 0
    for race in races:
        key_prefix = race[0]["meeting"]
        names_in_field = {}
        for row in race:
            k = f"{key_prefix}|{row['race']}|{int(row['horse_number'])}"
            info = per_horse.get(k)
            row["_ord"] = info
            if info:
                names_in_field[info["name"]] = int(row["horse_number"])
        ranked = sorted(race, key=lambda r: (-as_float(r["ability_score"], 60.0), int(r["horse_number"])))
        top4 = ranked[:4]
        for row in race:
            tot += 1
            info = row.get("_ord")
            if info and info["encounters"]:
                with_rows += 1
            if info and info["l400s"]:
                with_l400 += 1
        # H2H pairs within top4: does horse A's encounters mention horse B (in today's field)?
        h2h_pairs = 0
        for a in top4:
            ia = a.get("_ord")
            if not ia:
                continue
            rivals = {e["rival"] for e in ia["encounters"]}
            for b in top4:
                if a is b:
                    continue
                ib = b.get("_ord")
                if ib and ib["name"] in rivals:
                    h2h_pairs += 1
        h2h_pairs_total += h2h_pairs
        hits4 = sum(1 for r in top4 if int(r["actual_pos"]) <= 3)
        top2_hits = sum(1 for r in ranked[:2] if int(r["actual_pos"]) <= 3)
        is_opp = hits4 >= 2 and top2_hits < 2
        if is_opp:
            opp_total += 1
            opp_with_h2h += h2h_pairs > 0
        pair_cov[min(h2h_pairs, 5)] += 1

    print(f"horses: {tot}; with 賽績線 rows: {with_rows} ({100*with_rows/tot:.1f}%); with L400: {with_l400} ({100*with_l400/tot:.1f}%)")
    print(f"races with >=1 top-4 H2H pair: {sum(v for k,v in pair_cov.items() if k>0)}/{len(races)} "
          f"({100*sum(v for k,v in pair_cov.items() if k>0)/len(races):.1f}%); avg pairs/race {h2h_pairs_total/len(races):.2f}")
    print("top-4 H2H pair count distribution:", dict(sorted(pair_cov.items())))
    print(f"ORDERING-OPPORTUNITY races: {opp_total}; with >=1 H2H pair: {opp_with_h2h} "
          f"({100*opp_with_h2h/max(1,opp_total):.1f}%)  [gate: >=25%]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

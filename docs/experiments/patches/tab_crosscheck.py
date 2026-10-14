"""Read-only comparison of a captured TAB web sample with AU result rows.

TAB web results expose only the first four: blank positions are unobserved,
not missing finishes. Scratched entrants never enter the starter denominator.
"""
import argparse
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


def read_rows(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def name(value):
    return re.sub(r"\s+", " ", value.strip()).upper()


def compare(tab, baseline, date):
    venues = {"ROSEHILL": "Rosehill Gardens", "CAULFIELD": "Caulfield",
              "EAGLE-FARM": "Eagle Farm"}
    groups = defaultdict(list)
    for row in tab:
        groups[(venues[row["venue"]], row["race"])].append(row)
    reports = []
    for (venue, race), entrants in sorted(groups.items()):
        local = [r for r in baseline if r["Date"] == date
                 and r["Track"] == venue and r["Race"] == race]
        local_map = defaultdict(list)
        for row in local:
            local_map[name(row["Horse"])].append(row)
        starters = [r for r in entrants if r["scratched"] == "0"]
        tab_names = Counter(name(r["horse"]) for r in starters)
        local_names = Counter(name(r["Horse"]) for r in local)
        ambiguous = sorted(k for k in tab_names.keys() | local_names.keys()
                           if tab_names[k] > 1 or local_names[k] > 1)
        matched = [r for r in starters if len(local_map[name(r["horse"])]) == 1
                   and tab_names[name(r["horse"])] == 1]
        observed = [r for r in matched if r["position"]]
        differences = []
        for row in observed:
            other = local_map[name(row["horse"])][0]
            if int(row["position"]) != int(other["Pos"]):
                differences.append({"horse": row["horse"],
                                    "tab": row["position"], "local": other["Pos"]})
        barrier_differences = []
        raw_barriers = [int(r["barrier"]) for r in starters if r["barrier"]]
        barrier_rank = ({str(value): str(i + 1) for i, value in
                         enumerate(sorted(raw_barriers))}
                        if len(raw_barriers) == len(starters)
                        and len(set(raw_barriers)) == len(starters) else {})
        compressed_differences = []
        for row in matched:
            other = local_map[name(row["horse"])][0]
            if row["barrier"] != other["Barrier"]:
                barrier_differences.append({"horse": row["horse"],
                                            "tab": row["barrier"],
                                            "local": other["Barrier"]})
            if barrier_rank and barrier_rank[row["barrier"]] != other["Barrier"]:
                compressed_differences.append(row["horse"])
        reports.append({"venue": venue, "race": race, "tab_entrants": len(entrants),
                        "tab_starters": len(starters), "local_rows": len(local),
                        "matched_starters": len(matched), "ambiguous_names": ambiguous,
                        "tab_duplicate_rows": sum(v - 1 for v in tab_names.values()),
                        "local_duplicate_rows": sum(v - 1 for v in local_names.values()),
                        "missing_from_local": sorted(tab_names.keys() - local_names.keys()),
                        "missing_from_tab": sorted(local_names.keys() - tab_names.keys()),
                        "scratchings_in_local": sorted(name(r["horse"]) for r in entrants
                                                       if r["scratched"] == "1"
                                                       and name(r["horse"]) in local_map),
                        "observed_positions": len(observed),
                        "position_disagreements": differences,
                        "barrier_disagreements": barrier_differences,
                        "compressed_barrier_disagreements": compressed_differences})
    return {"date": date, "position_scope": "TAB visible top four only",
            "races": reports,
            "totals": {key: sum(r[key] for r in reports) for key in
                       ("tab_entrants", "tab_starters", "local_rows", "matched_starters",
                        "tab_duplicate_rows", "local_duplicate_rows", "observed_positions")}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tab-sample", required=True, type=Path)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--date", required=True)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    result = compare(read_rows(args.tab_sample), read_rows(args.baseline), args.date)
    result["inputs"] = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in (args.tab_sample, args.baseline)}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

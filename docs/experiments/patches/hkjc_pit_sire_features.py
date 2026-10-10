"""EXP-20261010-15: point-in-time sire features for the expanded corpus (brand→sire from racecards)."""
import csv, glob, re, sys
from collections import defaultdict
ROOT = "/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/HK_Racing"
sire = {}
for card in glob.glob(ROOT + "/*/*排位表.md"):
    text = open(card, encoding="utf-8").read()
    for block in text.split("馬號:")[1:]:
        b = re.search(r"烙號:\s*([A-Z]\d{3})", block); s = re.search(r"父系:\s*(.+)", block)
        if b and s and s.group(1).strip() not in ("", "-", "N/A"):
            sire[b.group(1)] = s.group(1).strip()
print("brands with sire", len(sire), "sires", len(set(sire.values())), file=sys.stderr)
rows = list(csv.DictReader(open(sys.argv[1], encoding="utf-8")))
rows.sort(key=lambda r: r["day"])
def bucket(d):
    if not d: return -1
    d = int(float(d)); return 0 if d <= 1200 else 1 if d <= 1600 else 2 if d <= 2000 else 3
PRIOR, K = 0.25, 20.0
stats_all = defaultdict(lambda: [0, 0]); stats_b = defaultdict(lambda: [0, 0])
out, i, covered = [], 0, 0
while i < len(rows):
    day = rows[i]["day"]; j = i
    while j < len(rows) and rows[j]["day"] == day: j += 1
    today = rows[i:j]
    for r in today:                      # features use only days strictly before `day`
        s = sire.get(r["horse"])
        r["sire_overall"] = r["sire_dist"] = r["sire_up"] = ""
        if s:
            covered += 1
            a = stats_all[s]; b = stats_b[(s, bucket(r["distance"]))]
            r["sire_overall"] = (a[0] + PRIOR * K) / (a[1] + K)
            r["sire_dist"] = (b[0] + PRIOR * K) / (b[1] + K) - r["sire_overall"]
            if r.get("first_up_in_trip") == "1":
                r["sire_up"] = r["sire_dist"]
    for r in today:                      # then add today's outcomes
        s = sire.get(r["horse"])
        if s:
            t = int(r["top3"])
            stats_all[s][0] += t; stats_all[s][1] += 1
            k = stats_b[(s, bucket(r["distance"]))]; k[0] += t; k[1] += 1
    out.extend(today); i = j
print("rows", len(rows), "with sire", covered, f"{covered/len(rows):.1%}", file=sys.stderr)
w = csv.DictWriter(open(sys.argv[2], "w", encoding="utf-8", newline=""), fieldnames=list(out[0].keys()))
w.writeheader(); w.writerows(out)

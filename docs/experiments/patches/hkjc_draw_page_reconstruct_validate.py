"""Validate PIT reconstruction of HKJC 檔位統計 page from rail_draw_results.csv.

For every saved page snapshot, rebuild each (venue, surface, rail, distance, draw)
cell from our results corpus using races with Date >= START and Date < meeting date,
then compare starts / W / 2 / 3 / 4 counts cell by cell.
"""
import json, re, sys, glob
from collections import defaultdict
import pandas as pd

RESULTS = "/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/HK_Racing/HKJC_Race_Results_Database/comprehensive_stats/rail_draw_results.csv"
SNAPS = sorted(glob.glob("/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/HK_Racing/*/Draw_Stats.json")) + [
    "/private/tmp/claude-501/-Users-imac-Antigravity-repo/383605b8-7ae2-4bcd-b7b6-ff7525d837be/scratchpad/dsdata/live_draw_20261014.json",
    "/private/tmp/claude-501/-Users-imac-Antigravity-repo/383605b8-7ae2-4bcd-b7b6-ff7525d837be/scratchpad/dsdata/snap_20260531.json",
]
START = sys.argv[1] if len(sys.argv) > 1 else "2024-09-01"

df = pd.read_csv(RESULTS, encoding="utf-8-sig", dtype=str)
df["Distance"] = pd.to_numeric(df.Distance, errors="coerce")
df["Draw"] = pd.to_numeric(df.Draw, errors="coerce")
df["PosN"] = pd.to_numeric(df.Pos, errors="coerce")
df["Surface"] = df.Track.map({"Turf": "草地", "AWT": "全天候", "All Weather": "全天候"}).fillna(df.Track)
df["Rail"] = df.Rail.fillna("").str.replace(" ", "")


def rebuild(venue, surface, rail, dist, date):
    s = df[(df.Venue == venue) & (df.Surface == surface) & (df.Distance == dist)
           & (df.Date >= START) & (df.Date < date)]
    if surface == "草地" and rail:
        s = s[s.Rail == rail]
    out = {}
    for draw, g in s.groupby("Draw"):
        out[int(draw)] = (len(g), int((g.PosN == 1).sum()), int((g.PosN == 2).sum()),
                          int((g.PosN == 3).sum()), int((g.PosN == 4).sum()))
    return out


def main():
    tot = exact = starts_ok = 0
    per = []
    absdiff = []
    for path in SNAPS:
        try:
            d = json.load(open(path, encoding="utf-8"))
        except FileNotFoundError:
            continue
        meet = d["meta"]["meeting"]
        m = re.search(r"(\d{2})/(\d{2})/(\d{4})", meet)
        date = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
        venue = "跑馬地" if "跑馬地" in meet else "沙田"
        seen = set()
        n = e = so = 0
        for r in d["races"]:
            key = (r.get("distance"), r.get("surface"), r.get("course"))
            if key in seen:
                continue
            seen.add(key)
            rail = r.get("course") or ""
            if not rail and r.get("surface") == "草地":
                # scraper drops "C+3"; infer from our results for that meeting
                rr = df[(df.Date == date) & (df.Venue == venue) & (df.Surface == "草地")].Rail.unique()
                rail = rr[0] if len(rr) else ""
            rec = rebuild(venue, r["surface"], rail, r["distance"], date)
            for dd in r["draws"]:
                page = (dd["starts"], dd["wins"], dd["seconds"], dd["thirds"], dd["fourths"])
                ours = rec.get(dd["draw"], (0, 0, 0, 0, 0))
                n += 1
                e += page == ours
                so += page[0] == ours[0]
                absdiff.append(abs(page[0] - ours[0]))
                if page != ours and "-v" in sys.argv:
                    print("  MISMATCH", meet, r["surface"], rail, r["distance"], dd["draw"], "page", page, "ours", ours)
        per.append((meet, n, e, so))
        tot += n; exact += e; starts_ok += so
    for meet, n, e, so in per:
        print(f"{meet:18s} cells={n:3d} exact={e/n:6.1%} starts_match={so/n:6.1%}")
    print(f"ALL cells={tot} exact={exact/tot:.1%} starts_match={starts_ok/tot:.1%} mean|Δstarts|={sum(absdiff)/len(absdiff):.2f}")


main()

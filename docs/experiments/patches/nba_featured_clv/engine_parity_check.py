import sys, json, glob, os, dataclasses
root = sys.argv[1]; out = sys.argv[2]
sys.path.insert(0, os.path.join(root, ".agents/skills/nba")); sys.path.insert(0, os.path.join(root, ".agents/skills/nba/nba_engine"))
sys.path.insert(0, os.path.join(root, ".agents/scripts"))
from nba_engine import legs as L, featured as F
res = {}
base = os.path.expanduser("~/WongChoiData/Wong Choi NBA Analysis")
for day in ("2026-11-18","2026-11-20","2026-11-21","2026-11-22","2026-11-23","2026-11-24","2026-11-25"):
    for pk in sorted(glob.glob(f"{base}/{day} NBA Analysis/nba_game_data_*.json")):
        tag = os.path.basename(pk)[14:-5]
        od = f"{base}/{day} NBA Analysis/Sportsbet_Odds_{tag}.json"
        if not os.path.exists(od): continue
        package, odds = json.load(open(pk)), json.load(open(od))
        try:
            legs, skipped = L.build_legs(odds, package)
        except Exception as e:
            res[f"{day}:{tag}"] = f"ERR {type(e).__name__}: {e}"; continue
        res[f"{day}:{tag}"] = [[l.player, l.stat, l.line, l.price, l.p_c, l.p_s, l.p_ms, l.p_s2] for l in legs]
json.dump(res, open(out, "w"), sort_keys=True)
print(len(res), "games", sum(len(v) for v in res.values() if isinstance(v, list)), "legs")

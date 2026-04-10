import json
import os
import sys

sys.path.append("/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity/.agents/skills/nba/nba_wong_choi/scripts")
from generate_nba_reports import select_combo_1

with open("/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity/2026-04-11 NBA Analysis/Data_Brief_DAL_SAS.json", "r") as f:
    data = json.load(f)

# Extract all player props to form candidates list
candidates = []
categories = ["PTS", "REB", "AST", "THREES"]
for player, props in data.get("player_props", {}).items():
    for cat in categories:
        if cat in props and "line_analysis" in props[cat]:
            for line_val, line_data in props[cat]["line_analysis"].items():
                c = {
                    "player": player,
                    "desc": f"{player} {cat} {line_data['line_display']}",
                    "odds": line_data["odds"],
                    "edge": line_data["edge"],
                    "hit_l10": line_data["hit_l10"],
                    "cov_grade": line_data["cov_grade"]
                }
                candidates.append(c)

print(f"Total candidates: {len(candidates)}")

pool = [c for c in candidates
        if c["hit_l10"] >= 60 and c["odds"] >= 1.15 and "神經刀" not in c.get("cov_grade", "")
        and c["edge"] >= -10]
pool.sort(key=lambda x: (-x["hit_l10"], -x["edge"], -x["odds"]))

print(f"Pool size: {len(pool)}")
print("Top 15 pool legs:")
for p in pool[:15]:
    print(f"  {p['desc']} | @{p['odds']} | hit: {p['hit_l10']} | edge: {p['edge']}")

# Run select_combo_1
res = select_combo_1(candidates)
print("\nResult:")
print(res)

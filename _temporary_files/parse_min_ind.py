import json
import re

text = open("2026-04-08 NBA Analysis/bet365_raw_MIN_IND.txt").read()

results = []
min_team = ["Kyle Anderson", "Mike Conley", "Donte DiVincenzo", "Rudy Gobert", "Julius Randle", "Naz Reid", "Ayo Dosunmu"]
ind_team = ["Jarace Walker", "Nah'Shon Hyland", "Quenton Jackson", "Kobe Brown", "Ethan Thompson", "Jalen Slawson"]

def get_team(name):
    if name in min_team: return "MIN"
    return "IND"

ou_match = re.search(r'Points O/U\nSGM.*?\nPlayer / Last 5\n(.*?)Over\n(.*?)\nUnder\n(.*?)\nShow more', text, re.DOTALL)
if ou_match:
    players_block = ou_match.group(1).strip().split('\n')
    over_block = ou_match.group(2).strip().split('\n')
    under_block = ou_match.group(3).strip().split('\n')

    players = []
    i = 0
    while i < len(players_block):
        if i + 1 < len(players_block) and re.match(r'^\d+$', players_block[i]) and not re.match(r'^\d+$', players_block[i+1]):
            players.append(players_block[i+1])
            i += 7
        else:
            i += 1
            
    for idx, p in enumerate(players):
        if idx*2+1 < len(over_block):
            line = float(over_block[idx*2])
            o_odds = float(over_block[idx*2+1])
            u_odds = float(under_block[idx*2+1])
            results.append({
                "Player": p,
                "Team": get_team(p),
                "Category": "Points",
                "Line": line,
                "Over": o_odds,
                "Under": u_odds
            })

# Also extract Alternative lines from Points section
pts_opts = re.search(r'Points\nSGM\nPlayer / Last 5\n(.*?)\n10\n(.*?)15\n(.*?)20\n', text, re.DOTALL)
if pts_opts:
    p_block = pts_opts.group(1).strip().split('\n')
    players = []
    i = 0
    while i < len(p_block):
        if i + 1 < len(p_block) and re.match(r'^\d+$', p_block[i]) and not re.match(r'^\d+$', p_block[i+1]):
            players.append(p_block[i+1])
            i += 7
        else:
            i += 1
            
    lines_regex = r'(10\n.*?)(?=15\n)'
    for l in [10, 15, 20]:
        pat = rf'{l}\n(.*?)(?={l+5}\n|Threes Made)'
        m = re.search(pat, text, re.DOTALL)
        if m:
            odds = m.group(1).strip().split('\n')
            for idx, p in enumerate(players):
                if idx < len(odds):
                    try:
                        o_val = float(odds[idx])
                        results.append({
                            "Player": p,
                            "Team": get_team(p),
                            "Category": "Points",
                            "Line": float(l-0.5), # Milestone 10+ is actually Over 9.5
                            "Over": o_val,
                            "Under": 0.0
                        })
                    except:
                        pass

with open("2026-04-08 NBA Analysis/Bet365_Odds_MIN_IND.json", "w") as f:
    json.dump(results, f, indent=4)

print(f"Extracted {len(results)} odds!")

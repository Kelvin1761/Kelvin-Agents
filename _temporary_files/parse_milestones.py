import json
import re

text = open("2026-04-08 NBA Analysis/bet365_raw_MIN_IND.txt").read()
results = []
min_team = ["Kyle Anderson", "Mike Conley", "Donte DiVincenzo", "Rudy Gobert", "Julius Randle", "Naz Reid", "Ayo Dosunmu"]
ind_team = ["Jarace Walker", "Nah'Shon Hyland", "Quenton Jackson", "Kobe Brown", "Ethan Thompson", "Jalen Slawson"]

def extract_milestones(category, next_category, milestones):
    # e.g., category = "Points", next_category = "Threes Made"
    pat = rf'{category}\nSGM\nPlayer / Last 5\n(.*?)(?=\n{next_category})'
    m = re.search(pat, text, re.DOTALL)
    if not m: return
    block = m.group(1).split('\n')
    
    players = []
    i = 0
    while i < len(block):
        if i + 1 < len(block) and block[i].isdigit() and not block[i+1].isdigit():
            players.append(block[i+1])
            i += 7
        else:
            break
            
    # Now find the milestones sections 
    # The block below players consists of numbers like "10", odds, odds, odds... "15", odds, odds, odds...
    # Let's find index of each milestone string
    for r in range(len(milestones)):
        cur_m = str(milestones[r])
        next_m = str(milestones[r+1]) if r+1 < len(milestones) else None
        
        try:
            start_idx = block.index(cur_m)
            end_idx = block.index(next_m) if next_m else len(block)
        except ValueError:
            continue
            
        odds = block[start_idx+1:end_idx]
        for idx, p in enumerate(players):
            if idx < len(odds):
                try:
                    val = float(odds[idx])
                    t = "MIN" if p in min_team else "IND"
                    results.append({
                        "Player": p, "Team": t, "Category": category,
                        "Line": float(int(cur_m) - 0.5), # 10+ means over 9.5
                        "Over": val, "Under": 0.0
                    })
                except ValueError:
                    pass

extract_milestones("Points", "Threes Made", [10, 15, 20, 25, 30, 35, 40, 45, 50])
extract_milestones("Threes Made", "Rebounds", [1, 2, 3, 4, 5, 6, 7, 8, 9])
extract_milestones("Rebounds", "Assists", [3, 5, 7, 10, 13, 15, 17, 20])
extract_milestones("Assists", "Points O/U", [3, 5, 7, 10, 13])

with open("2026-04-08 NBA Analysis/Bet365_Odds_MIN_IND.json", "w") as f:
    json.dump(results, f, indent=4)

print(f"Extracted {len(results)} milestones properly!")

import json

lines = open("2026-04-08 NBA Analysis/bet365_raw_MIN_IND.txt").read().split('\n')
players_list = ["Kyle Anderson", "Mike Conley", "Donte DiVincenzo", "Rudy Gobert", "Julius Randle", "Naz Reid", "Ayo Dosunmu",
                "Jarace Walker", "Nah'Shon Hyland", "Quenton Jackson", "Kobe Brown", "Ethan Thompson", "Jalen Slawson"]
min_team = {"Kyle Anderson", "Mike Conley", "Donte DiVincenzo", "Rudy Gobert", "Julius Randle", "Naz Reid", "Ayo Dosunmu"}

results = []
def add_res(p, cat, line, over, under):
    t = "MIN" if p in min_team else "IND"
    results.append({"Player": p, "Team": t, "Category": cat, "Line": line, "Over": over, "Under": under})

try:
    over_idx = lines.index("Over")
    under_idx = lines.index("Under")
    ou_players = []
    # From matching 'O/U' to 'Over'
    for i in range(max(0, over_idx-100), over_idx):
        if lines[i] in players_list:
            ou_players.append(lines[i])

    o_lines = lines[over_idx+1:under_idx]
    
    for idx, p in enumerate(ou_players):
        if idx*2+1 < len(o_lines):
            try:
                line_val = float(o_lines[idx*2])
                over_val = float(o_lines[idx*2+1])
                under_val = float(lines[under_idx+1 + idx*2 + 1])
                add_res(p, "Points", line_val, over_val, under_val)
            except Exception as e:
                pass
except Exception as e:
    pass

def extract_milestones(cat, search_str=None):
    if not search_str: search_str = cat
    for i, line in enumerate(lines):
        if line == search_str and i+2 < len(lines) and lines[i+1] == "SGM" and lines[i+2] == "Player / Last 5":
            start_p = i + 3
            ps = []
            j = start_p
            while j < min(len(lines), start_p+200):
                if lines[j].isdigit() and j+1 < len(lines) and lines[j+1] in players_list:
                    ps.append(lines[j+1])
                    j += 7
                elif lines[j] in players_list:
                    ps.append(lines[j])
                    j += 6
                else:
                    if j > start_p+2 and (lines[j].isdigit() or "." in lines[j] or lines[j] == "1.02"):
                        break
                    j += 1
            
            miles = []
            m_start = {}
            for m in [1,2,3,4,5,6,7,8,9,10,13,15,17,20,25,30,35,40,45,50]:
                ms = str(m)
                # find index of ms between j and j+300
                subst = lines[j:min(len(lines), j+300)]
                if ms in subst:
                    idx = j + subst.index(ms)
                    if idx not in m_start.values():
                        m_start[m] = idx
                        miles.append(m)
            
            miles.sort()
            for k in range(len(miles)):
                curr_m = miles[k]
                idx1 = m_start[curr_m]
                idx2 = m_start[miles[k+1]] if k+1 < len(miles) else min(len(lines), idx1+50)
                
                odds_block = lines[idx1+1:idx2]
                odds_floats = []
                for ob in odds_block:
                    try:
                        val = float(ob)
                        if val < 50.0:  # Valid odds
                            odds_floats.append(val)
                    except:
                        pass
                
                for p_idx, p in enumerate(ps):
                    if p_idx < len(odds_floats):
                        try:
                            val = odds_floats[p_idx]
                            add_res(p, cat, float(curr_m - 0.5), val, 0.0)
                        except:
                            pass

extract_milestones("Points")
extract_milestones("Rebounds")
extract_milestones("Assists")
extract_milestones("Threes Made", "Threes")

with open("2026-04-08 NBA Analysis/Bet365_Odds_MIN_IND.json", "w") as f:
    json.dump(results, f, indent=4)

print(f"Extracted {len(results)} overall props!")

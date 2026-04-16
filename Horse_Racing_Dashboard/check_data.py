import json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

with open('Open Dashboard.html', 'r', encoding='utf-8') as f:
    html = f.read()

start = html.find('const DASHBOARD_DATA = ') + len('const DASHBOARD_DATA = ')
end = html.find(';\n\n// ', start)
data = json.loads(html[start:end])

print("=== CONSENSUS DATA (04-01) ===")
for key, val in data.get('consensus', {}).items():
    if '04-01' in key:
        horses = val.get('consensus', {}).get('consensus_horses', [])
        top2 = [h for h in horses if h.get('is_top2_consensus')]
        print(f"{key}: {len(horses)} consensus, {len(top2)} top2")
        for h in horses:
            t2 = "TOP2" if h.get('is_top2_consensus') else ""
            print(f"  #{h['horse_number']} {h['horse_name']} K#{h.get('kelvin_rank')} H#{h.get('heison_rank')} {t2}")

print("\n=== TOP PICKS (04-01) ===")
for key, val in data.get('races', {}).items():
    if '04-01' in key:
        for analyst, races in val.get('races_by_analyst', {}).items():
            for race in sorted(races, key=lambda r: r.get('race_number', 0)):
                picks = race.get('top_picks', [])
                rn = race.get('race_number', '?')
                if picks:
                    names = [f"#{p.get('rank')} {p.get('horse_name')}({p.get('grade','')})" for p in picks]
                    print(f"R{rn} [{analyst}]: {', '.join(names)}")
                else:
                    print(f"R{rn} [{analyst}]: NO top_picks")

print("\n=== HORSE CARD FIELDS (R3 Kelvin sample) ===")
for key, val in data.get('races', {}).items():
    if '04-01' in key:
        kelvin_races = val.get('races_by_analyst', {}).get('Kelvin', [])
        for race in kelvin_races:
            if race.get('race_number') == 3:
                for h in race.get('horses', [])[:2]:
                    print(f"  #{h.get('horse_number')} {h.get('horse_name')}")
                    print(f"    core_logic: {str(h.get('core_logic',''))[:80]}")
                    concl = h.get('conclusion', '') or ''
                    has_logic = bool(concl and '核心邏輯' in concl)
                    print(f"    conclusion has 核心邏輯: {has_logic}")

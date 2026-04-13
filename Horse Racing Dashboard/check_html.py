import sys, io, json, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

with open(r'g:\我的雲端硬碟\Antigravity Shared\Antigravity\Horse Racing Dashboard\Open Dashboard.html', 'r', encoding='utf-8') as f:
    content = f.read()

m = re.search(r'const DASHBOARD_DATA\s*=\s*(\{.+?\});\s*\n', content, re.DOTALL)
if not m:
    print("DASHBOARD_DATA not found!")
    sys.exit(1)

data = json.loads(m.group(1))

# Find ShaTin races
for mkey, mdata in data.get('races', {}).items():
    if 'ShaTin' not in mkey:
        continue
    for analyst, races in mdata.get('races_by_analyst', {}).items():
        for race in races:
            if race['race_number'] == 2:
                picks = race.get('top_picks', [])
                print(f"R2 {analyst}: {len(picks)} picks")
                for p in picks:
                    print(f"  rank={p['rank']} #{p['horse_number']} '{p['horse_name']}' grade={p.get('grade','?')}")

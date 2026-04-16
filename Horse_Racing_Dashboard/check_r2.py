import sys, io, json, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, 'backend')

from services.parser_hkjc import parse_hkjc_analysis

# Check all Kelvin races for top_picks
import pathlib
kelvin_dir = pathlib.Path(r'g:\我的雲端硬碟\Antigravity Shared\Antigravity\2026-03-29_ShaTin (Kelvin)')
for f in sorted(kelvin_dir.glob('*Analysis*')):
    r = parse_hkjc_analysis(str(f))
    if r:
        picks_str = ', '.join([f'#{p.horse_number}({p.grade})' for p in r.top_picks])
        print(f'R{r.race_number}: {len(r.horses)}h, {len(r.top_picks)}picks: {picks_str}')

print()
# Check Heison
heison_dir = pathlib.Path(r'g:\我的雲端硬碟\Antigravity Shared\Antigravity\2026-03-29_ShaTin (Heison)')
for f in sorted(heison_dir.glob('*Analysis*')):
    r = parse_hkjc_analysis(str(f))
    if r:
        picks_str = ', '.join([f'#{p.horse_number}({p.grade})' for p in r.top_picks])
        print(f'R{r.race_number}: {len(r.horses)}h, {len(r.top_picks)}picks: {picks_str}')

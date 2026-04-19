import sys
sys.path.insert(0, 'backend')
from services.parser_hkjc import parse_hkjc_analysis
from services.consensus import find_consensus_horses

for i in range(1, 12):
    k_path = f"/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity/2026-04-19_ShaTin/04-19_ShaTin Race {i} Analysis.md"
    h_path = f"/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity/2026-04-19_ShaTin (Heison)/04-19_ShaTin Race {i} Analysis.md"
    
    k = parse_hkjc_analysis(k_path)
    h = parse_hkjc_analysis(h_path)
    
    if not k or not k.top_picks or not h or not h.top_picks:
        print(f"Race {i}: Missing top picks for K={bool(k and k.top_picks)} H={bool(h and h.top_picks)}")
        continue
        
    print(f"\n--- Race {i} ---")
    print("K:", [p.horse_number for p in k.top_picks])
    print("H:", [p.horse_number for p in h.top_picks])
    res = find_consensus_horses(k, h)
    t2 = [x['horse_number'] for x in res['consensus_horses'] if x['is_top2_consensus']]
    t4 = [x['horse_number'] for x in res['consensus_horses'] if not x['is_top2_consensus']]
    print("Top 2 consensus:", t2)
    print("Top 4 overlap:", t4)

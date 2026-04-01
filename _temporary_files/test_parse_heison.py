import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"g:\我的雲端硬碟\Antigravity Shared\Antigravity\Horse Racing Dashboard\backend")
from services.parser_hkjc import parse_hkjc_analysis

r1 = parse_hkjc_analysis(r"g:\我的雲端硬碟\Antigravity Shared\Antigravity\2026-04-01_Sha_Tin (Heison)\04-01_Race_1_Analysis.md")
print("R1 parsed:", bool(r1), len(r1.horses) if r1 else 0, "horses")
if r1:
    print("R1 Top4:")
    for p in r1.top_picks:
        print(f"  Rank: {p.rank}, Num: {p.horse_number}, Name: {p.horse_name}, Grade: {p.grade}")

r2 = parse_hkjc_analysis(r"g:\我的雲端硬碟\Antigravity Shared\Antigravity\2026-04-01_Sha_Tin (Heison)\04-01_Race_2_Analysis.md")
print("R2 parsed:", bool(r2), len(r2.horses) if r2 else 0, "horses")
if not r2:
    print("R2 is None!")

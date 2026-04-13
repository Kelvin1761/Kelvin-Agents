import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, 'backend')

# Force reload the module
import importlib
import services.parser_hkjc as phkjc
importlib.reload(phkjc)

# Test R9 Kelvin (bracket format [3] 皇龍飛將)
path9 = r'G:\我的雲端硬碟\Antigravity Shared\Antigravity\2026-04-01_ShaTin (Kelvin)\04-01 Race 9 Analysis.md'
with open(path9, 'r', encoding='utf-8') as f:
    text9 = f.read()
picks9 = phkjc._parse_verdict_top_picks(text9)
print("=== R9 KELVIN ===")
for p in picks9:
    print(f"  #{p.rank} horse#{p.horse_number} {p.horse_name} ({p.grade})")

# Test R4 Heison (bare grade format: A+ | ✅)
path4 = r'G:\我的雲端硬碟\Antigravity Shared\Antigravity\2026-04-01_Sha_Tin (Heison)\04-01_Race_4_Analysis.md'
with open(path4, 'r', encoding='utf-8') as f:
    text4 = f.read()
picks4 = phkjc._parse_verdict_top_picks(text4)
print("\n=== R4 HEISON ===")
for p in picks4:
    print(f"  #{p.rank} horse#{p.horse_number} {p.horse_name} ({p.grade})")

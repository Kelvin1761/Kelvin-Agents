import re

file_path = "2026-04-12_ShaTin (Kelvin)/04-12 Race 2 Analysis.md"
with open(file_path, "r", encoding="utf-8") as f:
    text = f.read()

horses = re.split(r'\*\*【No\.\d+】.*?\*\*', text)[1:]
names = re.findall(r'\*\*【No\.(\d+)】(.*?)\*\* \| 騎師', text)

for i, h_text in enumerate(horses):
    engine_match = re.search(r'引擎:\s*(.*?)\s*\|', h_text)
    engine = engine_match.group(1).split(' (')[0] if engine_match else "Unknown"
    
    positions = re.findall(r'\|\s*(.*?)\s*\|\s*\[需判定\]', h_text)
    pos_str = []
    for p in positions[:3]:
        parts = p.split('|')
        if len(parts) >= 6:
            pos_str.append(parts[-5].strip() + " - " + parts[-2].strip())
    
    print(f"{names[i][0]} {names[i][1].strip()} -> Engine: {engine}")
    for p in pos_str: print("  " + p)


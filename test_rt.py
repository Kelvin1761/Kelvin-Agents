import json
from pathlib import Path
import re

l400_pis = []
l600_rts = []

for file in Path("2026-05-22 Geelong Race 1-8").glob("*_Logic.json"):
    data = json.loads(file.read_text())
    text = data.get("facts_section", "")
    
    # Extract l400 PI
    l400_match = re.search(r"L400 PI \(400m→終點\):\s*([^\n]+?)\s*→", text)
    if l400_match:
        vals = re.findall(r'[+-]?\d+(?:\.\d+)?', l400_match.group(1))
        l400_pis.extend(float(v) for v in vals)
        
    # Extract L600/RT from the table
    # Table headers: | # | 類型 | 日期 | 場地 | 路程 | 場地狀況 | 檔位 | 名次 | 班次 | 跑位軌跡 | PI | 段速 | 早段步速 | L600/RT |
    for line in text.split("\n"):
        if "|" in line and "Maiden" in line or "BM" in line or "Class" in line:
            cols = [c.strip() for c in line.split("|")]
            if len(cols) > 14:
                rt_val = cols[14]
                try:
                    l600_rts.append(float(rt_val.replace("+", "")))
                except:
                    pass

print(f"L400 PI count: {len(l400_pis)}")
if l400_pis:
    print(f"L400 PI min: {min(l400_pis)}, max: {max(l400_pis)}, avg: {sum(l400_pis)/len(l400_pis):.2f}")
    
print(f"L600 RT count: {len(l600_rts)}")
if l600_rts:
    print(f"L600 RT min: {min(l600_rts)}, max: {max(l600_rts)}, avg: {sum(l600_rts)/len(l600_rts):.2f}")

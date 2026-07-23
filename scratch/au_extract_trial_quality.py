import json, re, sys
from pathlib import Path
sys.path.insert(0,"/Users/imac/Antigravity-repo")
from wongchoi_paths import AU_RACING
out={}
dirs=sorted(p for p in AU_RACING.iterdir() if p.is_dir())
for i,d in enumerate(dirs,1):
    for lp in d.glob("Race_*_Logic.json"):
        m=re.search(r"Race_(\d+)_Logic",lp.name)
        if not m or lp.stat().st_size==0: continue
        try: data=json.loads(lp.read_text(encoding="utf-8"))
        except: continue
        race=str((data.get("race_analysis") or {}).get("race_number") or m.group(1))
        for num,h in (data.get("horses") or {}).items():
            fs=(h.get("_data") or {}).get("facts_section") or ""
            pos=[]  # trial finish positions, most-recent first (table is recent-first)
            for l in fs.splitlines():
                s=l.strip()
                if s.startswith("|") and "試閘" in s:
                    cells=[c.strip() for c in s.split("|")]
                    # 名次 is column index 8 in the record table (see HEADER)
                    if len(cells)>8:
                        v=cells[8]
                        mm=re.match(r"(\d+)",v)
                        if mm: pos.append(int(mm.group(1)))
            if pos:
                out[f"{d.name}|{race}|{int(num)}"]={"trial_pos":pos,"won":int(1 in pos),
                    "best":min(pos),"recent":pos[0],"n":len(pos)}
    if i%15==0: print(f"{i}/{len(dirs)}",flush=True)
Path("/Users/imac/Antigravity-repo/scratch/au_trial_quality_map.json").write_text(json.dumps(out),encoding="utf-8")
print("DONE horses with trial positions:",len(out))

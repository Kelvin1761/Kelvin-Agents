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
            dd=h.get("_data") or {}
            out[f"{d.name}|{race}|{int(num)}"]={"last10":str(dd.get("last10_raw") or ""),
                "career":str(dd.get("career_record_line") or ""),
                "last_finish":str(dd.get("last_finish_line") or "")}
    if i%15==0: print(f"{i}/{len(dirs)}",flush=True)
Path("/Users/imac/Antigravity-repo/scratch/au_last10_map.json").write_text(json.dumps(out),encoding="utf-8")
print("DONE",len(out))

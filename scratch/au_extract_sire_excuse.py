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
            def i2(k):
                try: return int(dd.get(k))
                except: return 0
            out[f"{d.name}|{race}|{int(num)}"]={
                "sire":str(dd.get("sire_line") or "").strip(),
                "wnc":i2("recent_shape_wide_no_cover_count"),
                "early_work":i2("recent_shape_early_work_count"),
                "formal":i2("formal_count")}
    if i%15==0: print(f"{i}/{len(dirs)}",flush=True)
Path("/Users/imac/Antigravity-repo/scratch/au_sire_excuse_map.json").write_text(json.dumps(out),encoding="utf-8")
print("DONE",len(out))

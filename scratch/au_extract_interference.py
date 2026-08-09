import json, re, sys
from pathlib import Path
sys.path.insert(0,"/Users/imac/Antigravity-repo")
from wongchoi_paths import AU_RACING
# interference markers in the MOST RECENT formal run's row/notes (real trouble, not tactical wide)
TROUBLE=["受阻","被夾","阻塞","擋","收慢","檢討","hampered","checked","blocked","interfered","crowded","held up","tightened","steadied","shuffled"]
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
            fs=str((h.get("_data") or {}).get("facts_section") or "")
            # take the FIRST formal-run row (most recent) block ~ first 1200 chars after 賽績線/record
            recent=fs[:1500].lower()
            trouble=sum(recent.count(t.lower()) for t in TROUBLE)
            out[f"{d.name}|{race}|{int(num)}"]={"trouble":int(trouble>0),"trouble_n":trouble}
    if i%15==0: print(f"{i}/{len(dirs)}",flush=True)
Path("/Users/imac/Antigravity-repo/scratch/au_interference_map.json").write_text(json.dumps(out),encoding="utf-8")
print("DONE",len(out),"flagged:",sum(1 for v in out.values() if v["trouble"]))

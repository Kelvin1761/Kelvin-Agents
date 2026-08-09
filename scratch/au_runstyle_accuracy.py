import json, re, sys
from pathlib import Path
from collections import defaultdict, Counter
sys.path.insert(0,"/Users/imac/Antigravity-repo")
from wongchoi_paths import AU_RACING
BF=AU_RACING/"AU_Backfill_Results"
def band_from_role(num, sm):
    for role,b in (("leaders","front"),("pressers","front"),("on_pace","front"),("mid_pack","mid"),("closers","back")):
        if num in [int(x) for x in (sm.get(role) or []) if str(x).isdigit()]: return b
    return None
def band_from_pos(pos_str, field):
    m=re.match(r"(\d+)",str(pos_str or "")); 
    if not m: return None
    p=int(m.group(1)); 
    if field<4: return None
    if p<=max(2,field*0.30): return "front"
    if p<=field*0.66: return "mid"
    return "back"
total=match=0; conf=defaultdict(int)
meetings=0
for mdir in sorted(BF.iterdir()) if BF.exists() else []:
    if not mdir.is_dir(): continue
    resf=list(mdir.glob("Race_Results_*.json"))
    if not resf: continue
    # matching Logic in main archive
    logicdir=AU_RACING/mdir.name
    if not logicdir.exists(): continue
    try: res=json.loads(resf[0].read_text(encoding="utf-8"))
    except: continue
    meetings+=1
    results=res.get("results") or {}
    for lp in logicdir.glob("Race_*_Logic.json"):
        rm=re.search(r"Race_(\d+)_Logic",lp.name)
        if not rm: continue
        rno=rm.group(1)
        runners=results.get(rno) or results.get(int(rno)) or []
        if not runners: continue
        try: data=json.loads(lp.read_text(encoding="utf-8"))
        except: continue
        sm=(data.get("race_analysis") or {}).get("speed_map") or {}
        field=len(runners)
        for rr in runners:
            num=rr.get("competitor_number")
            settled=next((p["position"] for p in (rr.get("position_summaries") or []) if p.get("distance")=="Settled"),None)
            pb=band_from_pos(settled,field); rb=band_from_role(int(num) if num else -1, sm)
            if pb and rb:
                total+=1; match+= pb==rb; conf[(rb,pb)]+=1
print(f"meetings {meetings}, horse-comparisons {total}")
print(f"跑法預測準繩度 (預測band == 實際settled band): {100*match/max(1,total):.1f}%")
print("混淆 (預測→實際):")
for pred in ("front","mid","back"):
    row={act:conf[(pred,act)] for act in ("front","mid","back")}
    tot=sum(row.values())
    if tot: print(f"  預測{pred:<6}: "+" ".join(f"{a}={100*row[a]/tot:.0f}%" for a in ('front','mid','back'))+f"  (n={tot})")

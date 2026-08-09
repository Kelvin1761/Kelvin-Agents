#!/usr/bin/env python3
"""Extract FINISH POSITIONS for archive meetings from racenet (no Drive needed).
One request per meeting; resumable; gentle."""
import json, re, sys, time, random
from pathlib import Path
sys.path.insert(0,"/Users/imac/Antigravity-repo/.agents/skills/au_racing")
from racenet_transport import fetch_nuxt_data, RacenetBlockedError
OUT=Path("/Users/imac/Antigravity-repo/scratch/au_finishes_map.json")
DONE=Path("/Users/imac/Antigravity-repo/scratch/au_finishes_done.json")
NAMES=Path("/Users/imac/Antigravity-repo/scratch/au_archive_meetings.json")
def slug(dirname):
    m=re.match(r"(\d{4})-(\d{2})-(\d{2})\s+(.*?)(?:\s+Race\s|$)",dirname)
    if not m: return None
    track=re.sub(r"[^a-z0-9 ]","",m.group(4).lower()).strip().replace(" ","-")
    return f"{track}-{m.group(1)}{m.group(2)}{m.group(3)}"
def res(ap,ref): return ap.get(ref.get("id") or ref.get("__ref"),{}) if isinstance(ref,dict) else {}
def harvest(ap):
    """Walk Event.selections (the correct race→runner link; Selection keys carry
    no Event prefix). finishPosition == -1 means scratched/no result."""
    out={}
    for v in ap.values():
        if not (isinstance(v,dict) and v.get("__typename")=="Event"): continue
        rno=v.get("eventNumber")
        sels=v.get("selections") or []
        if not rno or not isinstance(sels,list): continue
        race={}
        for ref in sels:
            sel=res(ap,ref)
            if not sel: continue
            num=sel.get("competitorNumber")
            sr=res(ap,sel.get("selectionResult")) or res(ap,sel.get("result"))
            if num is None or not sr: continue
            try: fp=int(sr.get("finishPosition"))
            except (TypeError,ValueError): continue
            if fp <= 0: continue
            comp=res(ap,sel.get("competitor"))
            race[str(num)]={"pos":fp,"name":comp.get("name")}
        if race: out[str(rno)]=race
    return out
def main():
    limit=int(sys.argv[1]) if len(sys.argv)>1 else 100
    done=set(json.loads(DONE.read_text())) if DONE.exists() else set()
    data=json.loads(OUT.read_text()) if OUT.exists() else {}
    names=json.loads(NAMES.read_text())
    targets=[n for n in sorted(names,reverse=True) if n not in done][:limit]
    print(f"targets {len(targets)} (done {len(done)})",flush=True)
    for i,name in enumerate(targets,1):
        s=slug(name)
        try:
            ap=(fetch_nuxt_data(f"https://www.racenet.com.au/results/horse-racing/{s}/all-races").get("apollo") or {}).get("defaultClient") or {}
        except RacenetBlockedError:
            print("BLOCKED — stopping"); break
        except Exception as e:
            print(f"[{i}] {name}: ERR {type(e).__name__}"); done.add(name); continue
        h=harvest(ap)
        data[name]=h; done.add(name)
        OUT.write_text(json.dumps(data),encoding="utf-8"); DONE.write_text(json.dumps(sorted(done)),encoding="utf-8")
        print(f"[{i}/{len(targets)}] {name}: {len(h)} races, {sum(len(v) for v in h.values())} horses",flush=True)
        if i<len(targets): time.sleep(random.uniform(7,13))
    print("RUN DONE")
if __name__=="__main__": main()

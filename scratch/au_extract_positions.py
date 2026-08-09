#!/usr/bin/env python3
"""Extract actual in-running positions (settled/800/600/400) for ARCHIVE meetings
that have Logic files, so we can measure our predicted running-style accuracy.

One racenet request per meeting (results/all-races page carries every race's
CompetitorPositionSummary). Gentle: 8-15s gaps, hard stop on block.
"""
import json, re, sys, time, random
from pathlib import Path
sys.path.insert(0,"/Users/imac/Antigravity-repo")
sys.path.insert(0,"/Users/imac/Antigravity-repo/.agents/skills/au_racing")
from wongchoi_paths import AU_RACING
from racenet_transport import fetch_nuxt_data, RacenetBlockedError

OUT=Path("/Users/imac/Antigravity-repo/scratch/au_positions_map.json")
DONE=Path("/Users/imac/Antigravity-repo/scratch/au_positions_done.json")

def slug(dirname):
    m=re.match(r"(\d{4})-(\d{2})-(\d{2})\s+(.*?)(?:\s+Race\s|$)",dirname)
    if not m: return None
    track=re.sub(r"[^a-z0-9 ]","",m.group(4).lower()).strip().replace(" ","-")
    return f"{track}-{m.group(1)}{m.group(2)}{m.group(3)}"

def res(ap,ref): return ap.get(ref.get("id") or ref.get("__ref"),{}) if isinstance(ref,dict) else {}

def harvest(ap):
    """-> {race_no: {horse_num: {'settled':int,'p800':int,'p400':int}}}"""
    # map event id -> race number
    ev={}
    for v in ap.values():
        if isinstance(v,dict) and v.get("__typename")=="Event" and v.get("eventNumber"):
            ev[str(v.get("id"))]=v["eventNumber"]
    out={}
    for k,v in ap.items():
        if not (isinstance(v,dict) and v.get("__typename")=="Selection"): continue
        num=v.get("competitorNumber")
        sr=res(ap,v.get("selectionResult")) or res(ap,v.get("result"))
        if not sr or num is None: continue
        # race number: from key prefix Event:<id>.selections.N or via sr
        rno=None
        m=re.search(r"Event:(\d+)",k)
        if m: rno=ev.get(m.group(1))
        if rno is None:
            for kk,vv in ap.items():
                if isinstance(vv,dict) and vv.get("__typename")=="Event" and json.dumps(vv).find(k)>=0:
                    rno=vv.get("eventNumber"); break
        cps=sr.get("competitorPositionSummary") or []
        pos={}
        for ref in (cps if isinstance(cps,list) else [cps]):
            o=res(ap,ref)
            d=o.get("distance"); p=o.get("position")
            if p is None: continue
            if d==800: pos["p800"]=p
            elif d==400: pos["p400"]=p
            elif d in (None,0): pos["settled"]=p
        # settled often distanceText 'Settled'
        for ref in (cps if isinstance(cps,list) else [cps]):
            o=res(ap,ref)
            if str(o.get("distanceText","")).lower().startswith("settle") and o.get("position") is not None:
                pos["settled"]=o["position"]
        if rno and pos:
            out.setdefault(str(rno),{})[str(num)]=pos
    return out

def main():
    limit=int(sys.argv[1]) if len(sys.argv)>1 else 20
    done=set(json.loads(DONE.read_text())) if DONE.exists() else set()
    data=json.loads(OUT.read_text()) if OUT.exists() else {}
    # meeting list from LOCAL cache (avoids Drive permission issues)
    names=json.loads(Path("/Users/imac/Antigravity-repo/scratch/au_archive_meetings.json").read_text())
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
        nh=sum(len(v) for v in h.values())
        data[name]=h; done.add(name)
        OUT.write_text(json.dumps(data),encoding="utf-8"); DONE.write_text(json.dumps(sorted(done)),encoding="utf-8")
        print(f"[{i}/{len(targets)}] {name}: {len(h)} races, {nh} horses",flush=True)
        if i<len(targets): time.sleep(random.uniform(8,15))
    print("RUN DONE")

if __name__=="__main__": main()

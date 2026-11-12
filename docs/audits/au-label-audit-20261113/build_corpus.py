import csv, glob, os, re, json, unicodedata, sys
from collections import defaultdict
R="/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/AU_Racing"
SINCE, UNTIL = sys.argv[1], sys.argv[2]
def norm(s):
    s=unicodedata.normalize("NFKD",s or "").lower(); s=re.sub(r"\([^)]*\)","",s); return re.sub(r"[^a-z0-9]","",s)
res=defaultdict(dict)
with open(f"{R}/AU_Historical_Raw_Race_Results.csv",encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        d=r["Date"]
        if SINCE<=d<=UNTIL:
            try: res[d][norm(r["Horse"])]=int(float(r["Pos"]))
            except: pass
dirs=[p for p in glob.glob(f"{R}/20*")+glob.glob(f"{R}/Archive/20*") if os.path.isdir(p)]
races=[]; seen=set()
for d in sorted(dirs):
    date=os.path.basename(d)[:10]
    if not (SINCE<=date<=UNTIL): continue
    key=os.path.basename(d)
    if key in seen: continue
    seen.add(key)
    for f in sorted(glob.glob(f"{d}/Race_*_Auto_Scoring.csv")):
        rows=list(csv.DictReader(open(f,encoding="utf-8-sig")))
        out=[]
        for r in rows:
            p=res.get(date,{}).get(norm(r["horse_name"]))
            if p is None: continue
            out.append({**r,"pos":p})
        if len(out)>=5 and len(out)>=0.8*len(rows):
            races.append({"meeting":key,"date":date,"file":os.path.basename(f),"rows":out})
json.dump(races,open(sys.argv[3],"w"))
print(len(races),"races",sum(len(r["rows"]) for r in races),"runners")

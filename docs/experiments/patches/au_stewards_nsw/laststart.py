import glob,re,json,collections
from pathlib import Path
ROOT="/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/AU_Racing"
codes=json.load(open("venue_codes.json"))
syn={"rosehill":"ROSE","randwick":"RAND","kensington":"RAND","wagga":"WAGG","hawkesbury":"HAWK","canterbury":"CANT","newcastle":"NCLE",
     "kembla":"K_GR","warwick farm":"W_FM","port macquarie":"P_MQ","illawarra":"ILGR","coffs":"COFF"}
for v,c in codes.items(): syn.setdefault(v.lower(),c)
def code_of(venue):
    v=venue.lower()
    for k,c in sorted(syn.items(), key=lambda kv:-len(kv[0])):
        if k in v: return c
    return None
ROW=re.compile(r"^\| 1 \| 正式 \| (\d{4}-\d{2}-\d{2}) \| ([^|]+?) R(\d+) \|", re.M)
HEAD=re.compile(r"^### 馬匹 #(\d+) ([^(]+?) \(", re.M)
need=set(); runners=0; nsw=0; out={}
for d in sorted(set(glob.glob(ROOT+"/2026-*")+glob.glob(ROOT+"/Archive/**/2026-*",recursive=True))):
    name=Path(d).name
    if name[:10]<"2026-08-05": continue
    for f in glob.glob(d+"/* Race * Facts.md"):
        rn=int(re.search(r" Race (\d+) Facts\.md$",f).group(1)); t=open(f,encoding="utf-8",errors="replace").read()
        hs=list(HEAD.finditer(t))
        for i,h in enumerate(hs):
            blk=t[h.end():hs[i+1].start() if i+1<len(hs) else len(t)]
            m=ROW.search(blk); runners+=1
            if not m: continue
            c=code_of(m.group(2))
            if c:
                nsw+=1; dd=m.group(1); need.add(dd[8:10]+dd[5:7]+dd[:4]+c)
                out[f"{name}|{rn}|{h.group(1)}"]={"horse":h.group(2).strip(),"date":dd,"venue":m.group(2).strip(),"race":int(m.group(3)),"pdf":dd[8:10]+dd[5:7]+dd[:4]+c}
json.dump(out,open("laststart_nsw.json","w"))
open("need.txt","w").write("\n".join(sorted(need)))
print("runners",runners,"last start NSW",nsw,"pdfs needed",len(need))

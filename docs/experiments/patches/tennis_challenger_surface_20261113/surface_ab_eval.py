import json,math,random,collections,os
import glob
out=[json.loads(l) for f in glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)),'surface_ab.*.jsonl')) for l in open(f) if l.strip()]
ok=[r for r in out if 'err' not in r]
print("rows",len(out),"ok",len(ok),"errors",collections.Counter(r.get('err','')[:50] for r in out if 'err' in r).most_common(3))
def ll(p,y): p=min(max(p,1e-6),1-1e-6); return -(y*math.log(p)+(1-y)*math.log(1-p))
def br(p,y): return (p-y)**2
changed=[r for r in ok if abs(r['cand']-r['base'])>1e-9]
print("probability changed in",len(changed),"of",len(ok)," mean |Δp|",sum(abs(r['cand']-r['base']) for r in ok)/len(ok))
def summary(rs,name):
    if len(rs)<20: print(name,"n",len(rs),"thin"); return
    d=[ll(r['cand'],r['y'])-ll(r['base'],r['y']) for r in rs]
    db=[br(r['cand'],r['y'])-br(r['base'],r['y']) for r in rs]
    mk=[ll(r['base'],r['y'])-ll(r['mk'],r['y']) for r in rs]; mkc=[ll(r['cand'],r['y'])-ll(r['mk'],r['y']) for r in rs]
    rng=random.Random(20260826); n=len(rs); bs=[];bb=[]
    for _ in range(4000):
        idx=[rng.randrange(n) for _ in range(n)]
        bs.append(sum(d[i] for i in idx)/n); bb.append(sum(db[i] for i in idx)/n)
    bs.sort(); bb.sort()
    print(f"{name:10s} n={n:4d} LL base={sum(ll(r['base'],r['y']) for r in rs)/n:.4f} cand={sum(ll(r['cand'],r['y']) for r in rs)/n:.4f} mkt={sum(ll(r['mk'],r['y']) for r in rs)/n:.4f} | ΔLL={sum(d)/n:+.4f} [{bs[100]:+.4f},{bs[3899]:+.4f}] ΔBrier={sum(db)/n:+.5f} [{bb[100]:+.5f},{bb[3899]:+.5f}] | base−mkt {sum(mk)/n:+.4f} cand−mkt {sum(mkc)/n:+.4f}")
summary(ok,"ALL")
for s in ("Hard","Clay"): summary([r for r in ok if r['surface']==s],s)
ok.sort(key=lambda r:r['date']); h=len(ok)//2
summary(ok[:h],"1st half"); summary(ok[h:],"2nd half")

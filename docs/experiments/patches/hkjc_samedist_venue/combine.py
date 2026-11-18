import json,sys
B,V,A,O=sys.argv[1:5]
base={ (x["date"],x["race"]):x for x in map(json.loads,open(B)) if "horses" in x}
with open(O,"w") as f:
    for v,a in zip(map(json.loads,open(V)),map(json.loads,open(A))):
        if "horses" not in v: continue
        b=base[(v["date"],v["race"])]
        hs=[dict(h,raw=round(hv["raw"]+ha["raw"]-h["raw"],4)) for h,hv,ha in zip(b["horses"],v["horses"],a["horses"])]
        y=dict(b,arm="venue_V2+age_A2",horses=hs); y["picks"]=[h["n"] for h in sorted(hs,key=lambda h:-h["raw"])]
        f.write(json.dumps(y,ensure_ascii=False)+"\n")

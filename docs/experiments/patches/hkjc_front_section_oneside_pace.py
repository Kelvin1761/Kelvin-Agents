# ruff: noqa: F821  —— 名稱由 exec 前置腳本提供（R、met、score、w0 等）
# EXP-20261113-05/06 分析腳本（喺 repo root 行；參數見 EXP 記錄：labels_final.jsonl 所在 scratch 目錄／前置腳本路徑）
"""前段組件修正 —— dev（< 2026-09-06）揀、holdout（≥ 09-06）判。
機制（預先寫死）：
  V0 現行 arm：pts = b·SD·z（雙向，慢前段扣分）
  V1 單邊：pts = b·SD·max(z, 0)（前段快 = 多一個戰術選擇，有就加；前段慢 = 可能係後上馬，唔扣）
  V2 單邊＋步速：V1 × k，k 按場內「其他」前段強馬（z > 1）數：0 → 1、1 → 0.5、≥ 2 → 0（快馬多就互相消耗）
  b ∈ {0.25, 0.5}；null = 場內將 z 隨機調換（同分佈、冇資訊）200 次，同一公式
注意：V1／V2 嘅想法係睇咗全語料診斷（含 holdout）先諗出嚟，holdout 唔係完全乾淨，報告要講。"""
import json,sys,numpy as np
exec(open(sys.argv[2]).read().split('base=np.array')[0])
SD=9.4487
def rule(V,b):
    def fn(r,h):
        z=h["z"]
        if V=="V0": return b*SD*z
        p=b*SD*max(z,0)
        if V=="V2":
            o=sum(1 for g in r["hs"] if g is not h and g["z"] is not None and g["z"]>1)
            p*= 1 if o==0 else 0.5 if o==1 else 0
        return p
    return fn
dev=np.array([r["x"]["date"]<"2026-09-06" for r in R])
base=np.array([met(r,score(r,0)) for r in R])
rng=np.random.default_rng(3)
def evalset(V,b,RR=None):
    return np.array([met(r,score(r,b,rule(V,b))) for r in (RR or R)])
def shuffled():
    out=[]
    for r in R:
        zs=[h["z"] for h in r["hs"] if h["z"] is not None]; rng.shuffle(zs); it=iter(zs)
        out.append({**r,"hs":[{**h,"z":next(it)} if h["z"] is not None else h for h in r["hs"]]})
    return out
K=("Gold","Good","cap5","頭二")
fmt=lambda d:"｜".join(f"{k} {v:+.2f}" for k,v in zip(K,d))
nulls={}
for V in ("V0","V1","V2"):
    for b in (0.25,0.5):
        D=(evalset(V,b)-base)*100
        NL=np.array([((evalset(V,b,S:=shuffled())-base)*100) for _ in range(100)])
        nd,nh=NL[:,dev].mean(1),NL[:,~dev].mean(1)
        print(f"{V} b={b}")
        print(f"  dev     {fmt(D[dev].mean(0))}   ｜null 均值 {fmt(nd.mean(0))}｜候選喺 null 百分位 Gold {np.mean(nd[:,0]<D[dev,0].mean())*100:.0f}% cap5 {np.mean(nd[:,2]<D[dev,2].mean())*100:.0f}%")
        print(f"  holdout {fmt(D[~dev].mean(0))}   ｜null 均值 {fmt(nh.mean(0))}｜百分位 Gold {np.mean(nh[:,0]<D[~dev,0].mean())*100:.0f}% cap5 {np.mean(nh[:,2]<D[~dev,2].mean())*100:.0f}%", flush=True)
print(f"dev {dev.sum()} 場、holdout {(~dev).sum()} 場")

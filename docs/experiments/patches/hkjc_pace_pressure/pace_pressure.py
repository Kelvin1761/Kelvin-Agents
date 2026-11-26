"""放頭馬多（同場慣性放頭 F 數目）對放頭馬、外檔放頭馬嘅影響；殘差 = 入頭三 − v5 校準 p（walk-forward），base = live 回放。
跑法定義跟 run_style.py：賽前最多 6 仗「第一個沿途位置 ÷ 完成匹數」平均，≤0.3 F、≤0.6 M、其餘 B；冇 = U。"""
import json, sys, re
from collections import defaultdict
import numpy as np
from sklearn.linear_model import LogisticRegression
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
import hkjc_history_replay_build as b
def season(d): return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1
idx = b.load_index()
tl = defaultdict(list); info = {}
for (d, n), v in sorted(idx["results"].items()):
    res = v["results"] if isinstance(v["results"], list) else []
    fin = []
    for row in res:
        try: pos = int(str(row["pos"]).split()[0])
        except (KeyError, ValueError, IndexError): continue
        rp = str(row.get("running_positions") or "").split()
        nm = row.get("horse_name", ""); code = nm[nm.rindex("(")+1:-1] if "(" in nm else None
        try: dr = int(row.get("draw"))
        except (TypeError, ValueError): dr = None
        fin.append((code, str(row.get("horse_no")), int(rp[0]) if rp and rp[0].isdigit() else None, dr))
    N = len(fin)
    info[(d, int(n))] = {no: (code, dr) for code, no, _, dr in fin}
    for code, no, first, dr in fin:
        if code and first and N: tl[code].append((d, first / N))
def style(code, d):
    prev = [x for dd, x in tl.get(code, []) if dd < d][-6:]
    if not prev: return "U"
    m = sum(prev) / len(prev)
    return "F" if m <= 0.3 else ("M" if m <= 0.6 else "B")
rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
by = defaultdict(list)
for x in rows: by[season(x["date"])].append(x)
def feats(x):
    hs = [h for h in x["horses"] if h["pos"]]; r = np.array([h["raw"] for h in hs]); N = len(hs)
    return hs, r - r.mean(), np.full(N, np.log(3/(N-3)) if N > 3 else 0.0)
cal = {}
for s in sorted(by):
    if s < 2020: continue
    X, Y = [], []
    for t in by:
        if 2019 <= t < s:
            for x in by[t]:
                hs, dd, l = feats(x); X += list(zip(dd, l)); Y += [int(h["pos"] <= 3) for h in hs]
    cal[s] = LogisticRegression(C=1e6, max_iter=5000).fit(np.array(X), Y)
recs = []
for x in rows:
    s = season(x["date"])
    if s not in cal: continue
    meta = info.get((x["date"], x["race"]), {})
    hs, dd, l = feats(x); p = cal[s].predict_proba(np.column_stack([dd, l]))[:, 1]
    st = {h["n"]: style(meta.get(str(h["n"]), (None, None))[0], x["date"]) for h in hs}
    nF = sum(1 for v in st.values() if v == "F")
    for h, pi in zip(hs, p):
        dr = meta.get(str(h["n"]), (None, None))[1]
        recs.append(dict(s=s, day=x["date"], hv=x["venue"] == "跑馬地", y=int(h["pos"] <= 3), p=float(pi),
                         st=st[h["n"]], oth=nF - (st[h["n"]] == "F"), dr=dr or 0, N=len(hs)))
rng = np.random.default_rng(0)
def show(name, f):
    out = []
    for lo, hi in ((2020, 2023), (2024, 2026)):
        sel = [r for r in recs if lo <= r["s"] <= hi and f(r)]
        if len(sel) < 150: out.append(f"n={len(sel)}"); continue
        days = defaultdict(list)
        for r in sel: days[r["day"]].append(r["y"] - r["p"])
        ks = list(days); bt = []
        for _ in range(500):
            pk = rng.integers(0, len(ks), len(ks)); bt.append(np.mean([v for j in pk for v in days[ks[j]]]))
        out.append(f"實{100*np.mean([r['y'] for r in sel]):.0f}%/估{100*np.mean([r['p'] for r in sel]):.0f}% 差{100*np.mean([r['y']-r['p'] for r in sel]):+.1f}[{100*np.percentile(bt,2.5):+.1f},{100*np.percentile(bt,97.5):+.1f}] n={len(sel)}")
    print(f"{name:<30} dev {out[0]:<46} ho {out[1]}")
F = lambda r: r["st"] == "F"
print("放頭馬（F）按同場其他放頭馬數：")
for k, f in [("0 匹", lambda r: r["oth"] == 0), ("1 匹", lambda r: r["oth"] == 1), ("2 匹", lambda r: r["oth"] == 2), ("≥3 匹", lambda r: r["oth"] >= 3)]:
    show(f"  F｜其他放頭 {k}", lambda r, f=f: F(r) and f(r))
print("外檔（≥9）放頭馬：")
show("  外檔 F｜其他放頭 0–1", lambda r: F(r) and r["dr"] >= 9 and r["oth"] <= 1)
show("  外檔 F｜其他放頭 ≥2", lambda r: F(r) and r["dr"] >= 9 and r["oth"] >= 2)
show("  外檔 F｜其他放頭 ≥2（跑馬地）", lambda r: F(r) and r["dr"] >= 9 and r["oth"] >= 2 and r["hv"])
show("  內檔（1–4）F｜其他放頭 ≥2", lambda r: F(r) and 1 <= r["dr"] <= 4 and r["oth"] >= 2)
print("後上馬（B）喺放頭馬多嘅場：")
show("  B｜場內放頭 ≥3", lambda r: r["st"] == "B" and r["oth"] >= 3)
show("  B｜場內放頭 0–1", lambda r: r["st"] == "B" and r["oth"] <= 1)
show("  守中 M｜場內放頭 ≥3", lambda r: r["st"] == "M" and r["oth"] >= 3)

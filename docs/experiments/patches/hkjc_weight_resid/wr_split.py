"""負磅 vs 評分拆解：排位表評分＋負磅、賽果實際負磅（見習減磅）→ live dump 殘差。"""
import json, re, sys, glob, os
from collections import defaultdict
import numpy as np
from sklearn.linear_model import LogisticRegression
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
M = "/Volumes/Kelvin Hardisk 1/WongChoi-Archive/hkjc-history/replay_all"
card = {}
for f in glob.glob(f"{M}/*/*排位表.md"):
    t = open(f, encoding="utf-8").read()
    d = re.search(r"日期:\s*(\S+)", t).group(1); rn = int(re.search(r"場次:\s*第(\d+)場", t).group(1))
    cls = (re.search(r"班次:\s*(\S+)", t) or [None, ""])[1]
    for b in re.split(r"\n(?=馬號:)", t)[1:]:
        g = lambda k: (re.search(rf"{k}:\s*(-?\d+)", b) or [None, None])[1]
        if g("馬號"):
            card[(d, rn, int(g("馬號")))] = dict(rt=g("評分"), w=g("負磅"), cls=cls)
import hkjc_history_replay_pit as p
df = p.load_all_rows_extended(); df = df[df["Rank"].notna()]
act = {}
for r in df.itertuples():
    act[(str(r.Date)[:10], int(r.RaceNo), int(r.Rank))] = r.ActualWt
def season(d): return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1
rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
by = defaultdict(list)
for x in rows: by[season(x["date"])].append(x)
recs = []
for s in sorted(by):
    if s < 2020: continue
    X, Y = [], []
    for x in [y for t in by if t < s for y in by[t]]:
        hs = [h for h in x["horses"] if h["pos"]]; r = np.array([h["raw"] for h in hs]); X += list(r - r.mean()); Y += [h["pos"] <= 3 for h in hs]
    m = LogisticRegression(C=1e6, max_iter=5000).fit(np.array(X).reshape(-1, 1), Y); a, b = m.intercept_[0], m.coef_[0][0]
    for x in by[s]:
        hs = [h for h in x["horses"] if h["pos"]]
        cc = [card.get((x["date"], x["race"], int(h["n"]))) for h in hs]
        aw = [act.get((x["date"], x["race"], h["pos"])) for h in hs]
        if any(c is None or c["rt"] is None or c["w"] is None for c in cc) or any(v is None or v != v for v in aw): continue
        r = np.array([h["raw"] for h in hs]); z = r - r.mean(); pr = 1 / (1 + np.exp(-(a + b * z)))
        rt = np.array([float(c["rt"]) for c in cc]); w = np.array([float(c["w"]) for c in cc]); aw = np.array(aw, float)
        claim = w - aw
        for i, h in enumerate(hs):
            recs.append(dict(s=s, e=float(h["pos"] <= 3) - pr[i], rt=rt[i] - rt.mean(), w=w[i] - w.mean(), claim=claim[i], aw=aw[i] - aw.mean(),
                             rtmax=rt.max() - rt[i], cls=cc[i]["cls"], wraw=w[i]))
import pickle; pickle.dump(recs, open(sys.argv[2], "wb")); print(len(recs), len(card))

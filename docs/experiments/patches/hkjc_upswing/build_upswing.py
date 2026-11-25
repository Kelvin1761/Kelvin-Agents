"""EXP-20261126-21 預先登記（Kelvin 2026-11-26「兩樣都做」；寫喺跑之前；尺 v5.2；Holm 家族 1）。
觸發：11-25 跑馬地天下寵兒（模型連續排頭二、四仗冇入位）→ 診斷（patches/hkjc_upswing 外嘅 scratch diag，見記錄）：
  「近三仗平均名次好過之前三仗 ≥3」（上升馬）模型高估 dev −1.7 [−3.1,−0.5]、holdout −2.4 [−4.0,−0.8]（舊校準、冇 N）。
  反方向（回落馬）冇偏差；熱門而輸冇偏差。**披露：holdout 殘差已睇過，所以 holdout 唔係獨立確認。**
功效預估：power_precheck --gap-pp 2.0 --coverage 0.15 → PASS 33%（<50%，預設唔開）；Kelvin 明確要求，照開並披露。
base = scratch/j3-refine-20261123/e5_E5.jsonl（live：表現數字 SW＋初出馬練馬師 DT＋返首本 E5；冇直路表現數字，只影響 206 場）。
  U1  指標 1[近三仗平均名次 − 之前三仗平均名次 ≤ −3]（要有 ≥6 仗；往績 = idx horses runs，日期嚴格早過今仗；名次封頂 14），
      β 逐季 walk-forward（只用之前季，同 J3 做法：raw 標準化＋指標，LogisticRegression），場內置中加落 raw。
判：v5.2 dev PASS 先開 holdout；唔調門檻（3）、窗（6 仗）、封頂。
用法：python3 build_upswing.py <base.jsonl> <out.jsonl>
"""
import json, os, sys, datetime
from collections import defaultdict
import numpy as np
from sklearn.linear_model import LogisticRegression
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
import hkjc_history_replay_build as b  # noqa: E402

def season(d): return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1
def pdate(s):
    for f in ("%d/%m/%Y", "%d/%m/%y"):
        try: return datetime.datetime.strptime(s, f).strftime("%Y-%m-%d")
        except ValueError: pass
idx = b.load_index(); hist = {}
for hid, h in idx["horses"].items():
    rs = []
    for r in h.get("runs", []):
        d = pdate(r.get("date", ""))
        try: rs.append((d, min(int(r["pos"]), 14)))
        except (KeyError, ValueError, TypeError): continue
    hist[hid.split("_")[-1]] = sorted(x for x in rs if x[0])
code = {}
for (d, n), v in idx["results"].items():
    for row in (v["results"] if isinstance(v["results"], list) else []):
        nm = row.get("horse_name", "")
        if "(" in nm: code[(d, int(n), str(row.get("horse_no")))] = nm[nm.rindex("(") + 1:-1]
def upswing(c, d):
    prev = [t[1] for t in hist.get(c, []) if t[0] < d][-6:]
    return len(prev) == 6 and np.mean(prev[3:]) - np.mean(prev[:3]) <= -3
rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
F = {id(x): np.array([float(upswing(code.get((x["date"], x["race"], str(h["n"]))), x["date"])) for h in x["horses"]]) for x in rows}
print("U1 馬次", int(sum(v.sum() for v in F.values())), "／", sum(len(v) for v in F.values()), flush=True)
by = defaultdict(list)
for x in rows: by[season(x["date"])].append(x)
def fit(races):
    R, Z, Y = [], [], []
    for x in races:
        keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]
        r = np.array([h["raw"] for h in x["horses"]])
        R.append((r - r.mean())[keep]); Z.append(F[id(x)][keep]); Y += [int(x["horses"][i]["pos"] <= 3) for i in keep]
    R, Z = np.concatenate(R), np.concatenate(Z)
    c = LogisticRegression(C=1e6, max_iter=20000, solver="newton-cg").fit(np.column_stack([R / R.std(), Z]), Y).coef_[0]
    return c[1] / (c[0] / R.std())
betas = {s: fit([x for t in by if 2019 <= t < s for x in by[t]]) for s in sorted(by) if s >= 2020}
print("β", {s: round(float(v), 2) for s, v in betas.items()}, flush=True)
with open(sys.argv[2], "w") as f:
    for x in rows:
        y = dict(x, arm="upswing_U1"); bt = betas.get(season(x["date"]))
        if bt is not None and F[id(x)].any():
            add = F[id(x)] * bt; add = add - add.mean()
            y["horses"] = [dict(h, raw=round(h["raw"] + float(v), 4)) for h, v in zip(x["horses"], add)]
            y["picks"] = [h["n"] for h in sorted(y["horses"], key=lambda h: -h["raw"])]
        f.write(json.dumps(y, ensure_ascii=False) + "\n")

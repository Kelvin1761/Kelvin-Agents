"""EXP-20261126-23 預先登記（Kelvin 2026-11-26「如果一場太多同跑法…多放頭但係抽外檔」→「開實驗」；寫喺跑之前；尺 v5.2；Holm 家族 2）。
診斷（pace_pressure.py，base e5_E5，v5 校準 walk-forward）：放頭馬（F）殘差按同場其他放頭數 0／1／2／≥3：
  dev +1.6／+1.2／+0.4／−1.8、holdout +3.2／+2.9／−0.6／−2.0（兩窗單調）；外檔 F 獨放 +3.7／+3.2、外檔 F 擠迫 −1.5／−0.6。
**披露：holdout 殘差已睇過 → holdout 唔係獨立確認。** 同家族舊測試：EXP-20261113-01 F1（步速×跑法，舊 389 場尺，幅度細 REJECT）。
功效預估 power_precheck --gap-pp 3.0 --coverage 0.16 → PASS 100%。
跑法 = run_style.py 定義（賽前最多 6 仗第一個沿途位置÷完成匹數平均；≤0.3 F）；歷史由 replay_index 賽果砌（日期嚴格早過今仗）。
  P1  特徵 1[F]·min(同場其他 F 數, 3)
  P2  P1 ＋ 1[F 而且檔位 ≥ 9]·min(同場其他 F 數, 3)（兩個係數聯合 fit）
  β 逐季 walk-forward（只用之前季；raw 標準化＋特徵 LogisticRegression），場內置中加落 raw。
判：v5.2 dev PASS 先開 holdout；唔調上限 3、門檻 0.3、外檔 9。
第二輪（P1／P2 dev REJECT 之後加，**睇咗 why.py 先寫，披露**；家族改 Holm 3）：P1 冇放頭主效應，獨放 F 同非 F 都係 0，
  兩個方向互相抵銷（pooled dev：F +0.146、F·擠迫 −0.064 logit；淨 F·擠迫 −0.004）。
  P3  特徵 [1[F], 1[F]·min(同場其他 F 數, 3)] 聯合 fit（其餘同上）。用法：python3 build_pace.py <base> <out_prefix> [arms,逗號分隔]
"""
import json, sys
from collections import defaultdict
import numpy as np
from sklearn.linear_model import LogisticRegression
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
import hkjc_history_replay_build as b
def season(d): return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1
idx = b.load_index()
tl = defaultdict(list); info = {}
for (d, n), v in sorted(idx["results"].items()):
    fin = []
    for row in (v["results"] if isinstance(v["results"], list) else []):
        try: int(str(row["pos"]).split()[0])
        except (KeyError, ValueError, IndexError): continue
        rp = str(row.get("running_positions") or "").split()
        nm = row.get("horse_name", ""); code = nm[nm.rindex("(")+1:-1] if "(" in nm else None
        try: dr = int(row.get("draw"))
        except (TypeError, ValueError): dr = 0
        fin.append((code, str(row.get("horse_no")), int(rp[0]) if rp and rp[0].isdigit() else None, dr))
    N = len(fin)
    info[(d, int(n))] = {no: (code, dr) for code, no, _, dr in fin}
    for code, no, first, dr in fin:
        if code and first and N: tl[code].append((d, first / N))
def is_front(code, d):
    prev = [x for dd, x in tl.get(code, []) if dd < d][-6:]
    return bool(prev) and sum(prev) / len(prev) <= 0.3
rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
F = {}
for x in rows:
    meta = info.get((x["date"], x["race"]), {})
    fr = [is_front(meta.get(str(h["n"]), (None, 0))[0], x["date"]) for h in x["horses"]]
    nF = sum(fr); v = []
    for h, f in zip(x["horses"], fr):
        crowd = min(nF - 1, 3) if f else 0
        outer = meta.get(str(h["n"]), (None, 0))[1] >= 9
        v.append([float(f) * crowd, float(f and outer) * crowd, float(f)])
    F[id(x)] = np.array(v)
print("F 匹次（P1 非零）", int(sum((v[:, 0] > 0).sum() for v in F.values())), flush=True)
by = defaultdict(list)
for x in rows: by[season(x["date"])].append(x)
def fit(races, cols):
    R, Z, Y = [], [], []
    for x in races:
        keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]
        r = np.array([h["raw"] for h in x["horses"]])
        R.append((r - r.mean())[keep]); Z.append(F[id(x)][keep][:, cols]); Y += [int(x["horses"][i]["pos"] <= 3) for i in keep]
    R, Z = np.concatenate(R), np.concatenate(Z)
    c = LogisticRegression(C=1e6, max_iter=20000, solver="newton-cg").fit(np.column_stack([R / R.std(), Z]), Y).coef_[0]
    return c[1:] / (c[0] / R.std())
ARMS = (("P1", [0]), ("P2", [0, 1]), ("P3", [2, 0]))
for arm, cols in [a for a in ARMS if a[0] in (sys.argv[3].split(",") if len(sys.argv) > 3 else [a[0] for a in ARMS])]:
    betas = {s: fit([x for t in by if 2019 <= t < s for x in by[t]], cols) for s in sorted(by) if s >= 2020}
    print(arm, "β", {s: [round(float(u), 2) for u in v] for s, v in betas.items()}, flush=True)
    with open(f"{sys.argv[2]}_{arm}.jsonl", "w") as f:
        for x in rows:
            y = dict(x, arm=f"pace_{arm}"); bt = betas.get(season(x["date"]))
            if bt is not None and F[id(x)][:, cols].any():
                add = F[id(x)][:, cols] @ bt; add = add - add.mean()
                y["horses"] = [dict(h, raw=round(h["raw"] + float(v), 4)) for h, v in zip(x["horses"], add)]
                y["picks"] = [h["n"] for h in sorted(y["horses"], key=lambda h: -h["raw"])]
            f.write(json.dumps(y, ensure_ascii=False) + "\n")

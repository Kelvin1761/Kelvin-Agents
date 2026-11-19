"""EXP-20261119-04 預先登記（Kelvin 2026-11-19「練馬師長休後嘅紀錄唔好」；Holm 家族 2）。
長休馬 = 香港往績（馬匹頁，日期嚴格早過今仗）上仗距今 ≥90 日。
特徵 f = 練馬師喺「之前季」（2019/20 起、嚴格早過今季）所有長休馬嘅殘差（入頭三 − 現行 live 走前校準 p）
  收縮均值 Σres / (n + k)；非長休馬 f = 0；冇之前紀錄 f = 0。
β：逐季 walk-forward（只用之前季）logit(入頭三) ~ raw 標準化 + f；raw' = raw + β·f/(α) 場內置中。
  L1  k = 50
  L2  k = 150
判：hkjc_replay_compare_v4.py（Δlog-loss CI 上界 < 0、Gold／Good 下界 > −1.0pp、好過 null）；dev 唔過就唔開 holdout。
用法：python3 build_trainer_layoff.py <base.jsonl> <out_prefix>
"""
import gzip, json, re, sys
from collections import defaultdict
from datetime import date
import numpy as np
from sklearn.linear_model import LogisticRegression
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
sys.path.insert(0, "/Users/imac/Antigravity-repo/docs/experiments/patches/hkjc_incidents")
import hkjc_history_replay_build as b  # noqa: E402
from diag_full import calibrate  # noqa: E402  走前校準（每季只用之前季）

GAP = 90
def season(d): return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1
def iso(dmy):
    d, m, y = dmy.split("/"); return f"{y}-{m}-{d}"

rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
runs = defaultdict(list)
for line in gzip.open("/Volumes/Kelvin Hardisk 1/WongChoi-Archive/hkjc-history/parsed/horses.jsonl.gz", "rt", encoding="utf-8"):
    r = json.loads(line); code = r["horse_id"].rsplit("_", 1)[-1]
    for q in r.get("runs") or []:
        vt = str(q.get("venue_track") or "")
        if vt.startswith(("沙田", "跑馬地")):
            try: runs[code].append(iso(q["date"]))
            except Exception: pass
for v in runs.values(): v.sort()
idx = b.load_index(); meta = {}
for (d, n), race in idx["results"].items():
    for row in race.get("results", []):
        m = re.search(r"\(([A-Z]\d{3})\)", str(row.get("horse_name") or ""))
        meta[(d, n, str(row.get("horse_no")))] = (m.group(1) if m else None, str(row.get("trainer") or "").strip())
calib = calibrate(rows)
# 每匹：(季, 練馬師, 長休?, 殘差)
L = {}; recs = []
for x in rows:
    s = season(x["date"]); a, bb = calib[season(x["date"])]
    r = np.array([h["raw"] for h in x["horses"]]); rc = r - r.mean()
    flags = []
    for h, z in zip(x["horses"], rc):
        code, tr = meta.get((x["date"], x["race"], str(h["n"])), (None, ""))
        prev = [t for t in runs.get(code, []) if t < x["date"]]
        lay = bool(prev) and (date.fromisoformat(x["date"]) - date.fromisoformat(prev[-1])).days >= GAP
        flags.append((tr, lay))
        if lay and h["pos"]:
            p = 1 / (1 + np.exp(-(a + bb * z)))
            recs.append((s, tr, int(h["pos"] <= 3) - p))
    L[id(x)] = flags
print("長休馬次", len(recs), "（有名次）", flush=True)
seasons = sorted({season(x["date"]) for x in rows})
cum = {}   # 季 s → {練馬師: (Σres, n)}，只計 < s
for s in seasons:
    acc = defaultdict(lambda: [0.0, 0])
    for (t, tr, res) in recs:
        if t < s: acc[tr][0] += res; acc[tr][1] += 1
    cum[s] = acc
def feat(x, k):
    acc = cum[season(x["date"])]
    return np.array([(acc[tr][0] / (acc[tr][1] + k)) if lay and tr in acc else 0.0 for tr, lay in L[id(x)]])
by = defaultdict(list)
for x in rows: by[season(x["date"])].append(x)
def fit(races, k):
    R, Z, Y = [], [], []
    for x in races:
        keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]
        r = np.array([h["raw"] for h in x["horses"]])
        R.append((r - r.mean())[keep]); Z.append(feat(x, k)[keep]); Y += [int(x["horses"][i]["pos"] <= 3) for i in keep]
    R, Z = np.concatenate(R), np.concatenate(Z)
    c = LogisticRegression(C=1e6, max_iter=20000, solver="newton-cg").fit(np.column_stack([R / R.std(), Z]), Y).coef_[0]
    return c[1] / (c[0] / R.std())       # raw 分 / 單位 f
for arm, k in (("L1", 50), ("L2", 150)):
    betas = {s: fit([x for t in by if 2020 <= t < s for x in by[t]], k) for s in seasons if s >= 2021}
    print(arm, "β", {s: round(float(v), 1) for s, v in betas.items()}, flush=True)
    last = max(seasons); top = sorted(cum[last].items(), key=lambda t: t[1][0] / (t[1][1] + k))[:5]
    print(arm, f"{last} 季最差練馬師 f：", [(tr, round(v[0] / (v[1] + k) * 100, 1), v[1]) for tr, v in top], flush=True)
    yeh = cum[last].get("葉楚航"); print(arm, "葉楚航", yeh and (round(yeh[0] / (yeh[1] + k) * 100, 1), yeh[1]), "→ raw", yeh and round(betas[last] * yeh[0] / (yeh[1] + k), 2))
    with open(f"{sys.argv[2]}_{arm}.jsonl", "w") as f:
        for x in rows:
            y = dict(x, arm=f"trainer_layoff_{arm}")
            bt = betas.get(season(x["date"]))
            if bt is not None:
                add = feat(x, k) * bt; add = add - add.mean()
                y["horses"] = [dict(h, raw=round(h["raw"] + float(v), 4)) for h, v in zip(x["horses"], add)]
                y["picks"] = [h["n"] for h in sorted(y["horses"], key=lambda h: -h["raw"])]
            f.write(json.dumps(y, ensure_ascii=False) + "\n")

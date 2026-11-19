"""EXP-20261119-05 預先登記（Kelvin 2026-11-19「得一仗、受傷、長休復出排頭 5 可以，排第 2 唔合理」；Holm 家族 3）。
診斷（寫呢個之前已睇，只係呢一個群組）：本地馬、香港 ≤2 仗、休 >180 日，模型排 1–2 嘅 14 匹入位 29%、模型估 55%；排 3–5 33%／28%；6+ 11%／10%。
做法 = 收窄信心（唔係扣分）：群組內嘅馬 raw' = 場均 + λ·(raw − 場均)；λ < 1 = 高分跌、低分升。
  S1  群組 A（本地、≤2 仗、休 >180 日），λ = 0.5 固定
  S2  群組 B（本地、≤3 仗、休 >120 日，較闊、未睇過），λ = 0.5 固定
  S3  群組 A，λ walk-forward：logit ~ rc + I·rc（只用之前季），λ = 1 + γ/α，夾 [0, 1]
本地 = 回放賽果庫 ≥300 馬次嘅練馬師（外隊馬中性）。往績 = 馬匹頁香港賽事，日期嚴格早過今仗。
判：hkjc_replay_compare_v4.py；dev 唔過唔開 holdout。用法：python3 build_thin_shrink.py <base.jsonl> <out_prefix>
"""
import gzip, json, re, sys
from collections import defaultdict
from datetime import date
import numpy as np
from sklearn.linear_model import LogisticRegression
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
import hkjc_history_replay_build as b  # noqa: E402
def season(d): return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1
def iso(dmy):
    d, m, y = dmy.split("/"); return f"{y}-{m}-{d}"
runs = defaultdict(list)
for line in gzip.open("/Volumes/Kelvin Hardisk 1/WongChoi-Archive/hkjc-history/parsed/horses.jsonl.gz", "rt", encoding="utf-8"):
    r = json.loads(line); code = r["horse_id"].rsplit("_", 1)[-1]
    for q in r.get("runs") or []:
        if str(q.get("venue_track") or "").startswith(("沙田", "跑馬地")):
            try: runs[code].append(iso(q["date"]))
            except Exception: pass
for v in runs.values(): v.sort()
idx = b.load_index(); meta = {}; tcount = defaultdict(int)
for (d, n), race in idx["results"].items():
    for row in race.get("results", []):
        m = re.search(r"\(([A-Z]\d{3})\)", str(row.get("horse_name") or ""))
        tr = str(row.get("trainer") or "").strip(); tcount[tr] += 1
        meta[(d, n, str(row.get("horse_no")))] = (m.group(1) if m else None, tr)
LOCAL = {t for t, c in tcount.items() if c >= 300}
rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
def flags(x, maxn, mingap):
    out = []
    for h in x["horses"]:
        code, tr = meta.get((x["date"], x["race"], str(h["n"])), (None, ""))
        prev = [t for t in runs.get(code, []) if t < x["date"]]
        ok = tr in LOCAL and prev and len(prev) <= maxn and (date.fromisoformat(x["date"]) - date.fromisoformat(prev[-1])).days > mingap
        out.append(float(bool(ok)))
    return np.array(out)
A = {id(x): flags(x, 2, 180) for x in rows}
B = {id(x): flags(x, 3, 120) for x in rows}
print("群組 A 馬次", int(sum(v.sum() for v in A.values())), "群組 B", int(sum(v.sum() for v in B.values())), flush=True)
by = defaultdict(list)
for x in rows: by[season(x["date"])].append(x)
def fit_lambda(races):
    R, Z, Y = [], [], []
    for x in races:
        keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]
        r = np.array([h["raw"] for h in x["horses"]]); rc = r - r.mean()
        R.append(rc[keep]); Z.append((A[id(x)] * rc)[keep]); Y += [int(x["horses"][i]["pos"] <= 3) for i in keep]
    R, Z = np.concatenate(R), np.concatenate(Z); s = R.std()
    c = LogisticRegression(C=1e6, max_iter=20000, solver="newton-cg").fit(np.column_stack([R / s, Z / s]), Y).coef_[0]
    return float(np.clip(1 + c[1] / c[0], 0.0, 1.0))
lam = {s: fit_lambda([x for t in by if 2019 <= t < s for x in by[t]]) for s in sorted(by) if s >= 2020}
print("S3 λ", {s: round(v, 2) for s, v in lam.items()}, flush=True)
def shrink(x, I, l):
    r = np.array([h["raw"] for h in x["horses"]]); m = r.mean()
    new = np.where(I > 0, m + l * (r - m), r)
    new = new - new.mean() + m          # 場均唔變
    return new
for arm in ("S1", "S2", "S3"):
    with open(f"{sys.argv[2]}_{arm}.jsonl", "w") as f:
        for x in rows:
            y = dict(x, arm=f"thin_shrink_{arm}")
            I = B[id(x)] if arm == "S2" else A[id(x)]
            l = 0.5 if arm in ("S1", "S2") else lam.get(season(x["date"]))
            if l is not None and I.any():
                new = shrink(x, I, l)
                y["horses"] = [dict(h, raw=round(float(v), 4)) for h, v in zip(x["horses"], new)]
                y["picks"] = [h["n"] for h in sorted(y["horses"], key=lambda h: -h["raw"])]
            f.write(json.dumps(y, ensure_ascii=False) + "\n")

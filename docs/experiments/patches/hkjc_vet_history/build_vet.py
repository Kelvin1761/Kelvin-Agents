"""EXP-20261119-03（預先登記見 EXP-20261119-03-hkjc-vet-history-protocol.md）：歷史傷患紀錄 I1／I2／I3。
用法：python3 build_vet.py <base.jsonl> <out_prefix>    → <prefix>_I1/I2/I3.jsonl ＋ 覆蓋率／殘差診斷
"""
import gzip, json, re, sys
from collections import defaultdict
from datetime import date
import numpy as np
from sklearn.linear_model import LogisticRegression
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts")
sys.path.insert(0, "/Users/imac/Antigravity-repo/docs/experiments/patches/hkjc_incidents")
import hkjc_history_replay_build as b  # noqa: E402
from hkjc_official_injury import MEDICAL, PERFORMANCE_ONLY  # noqa: E402
from diag_full import calibrate  # noqa: E402

ARCH = "/Volumes/Kelvin Hardisk 1/WongChoi-Archive/hkjc-history/parsed"
SERIOUS = re.compile(r"韌帶|肌腱|骨|關節|球節|跛|不良於行|手術")
GELD = re.compile(r"閹割")
def season(d): return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1
def iso(dmy):
    d, m, y = dmy.split("/"); return f"{y}-{m}-{d}"
def cat(detail):
    if GELD.search(detail) or PERFORMANCE_ONLY.search(detail): return None
    if SERIOUS.search(detail): return "SERIOUS"
    if MEDICAL.search(detail): return "MEDICAL"
    return None

vet = {}
for line in gzip.open(f"{ARCH}/vet.jsonl.gz", "rt", encoding="utf-8"):
    r = json.loads(line)
    if r["active"]: vet[r["horse_id"].rsplit("_", 1)[-1]] = [(x["date"], cat(x["detail"]), x["detail"]) for x in r["records"] if x["date"]]
print("現役有頁", len(vet), "有記錄", sum(1 for v in vet.values() if v), flush=True)
runs = defaultdict(list)
for line in gzip.open(f"{ARCH}/horses.jsonl.gz", "rt", encoding="utf-8"):
    r = json.loads(line); code = r["horse_id"].rsplit("_", 1)[-1]
    for q in r.get("runs") or []:
        if str(q.get("venue_track") or "").startswith(("沙田", "跑馬地")):
            try: runs[code].append(iso(q["date"]))
            except Exception: pass
for v in runs.values(): v.sort()
idx = b.load_index(); code_of = {}
for (d, n), race in idx["results"].items():
    for row in race.get("results", []):
        m = re.search(r"\(([A-Z]\d{3})\)", str(row.get("horse_name") or ""))
        if m: code_of[(d, n, str(row.get("horse_no")))] = m.group(1)

rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
rows = [x for x in rows if season(x["date"]) >= 2024]
F = {}; cover = defaultdict(lambda: [0, 0])
for x in rows:
    d0 = x["date"]; fx = []
    for h in x["horses"]:
        c = code_of.get((d0, x["race"], str(h["n"])))
        cover[season(d0)][1] += 1
        i1 = i2 = i3 = 0.0
        if c in vet:
            cover[season(d0)][0] += 1
            prev = [t for t in vet[c] if t[0] < d0 and t[1]]
            win = [t for t in prev if (date.fromisoformat(d0) - date.fromisoformat(t[0])).days <= 365]
            i1 = float(any(t[1] == "SERIOUS" for t in win))
            i2 = float(bool(win))
            ser = [t for t in prev if t[1] == "SERIOUS"]
            if ser:
                last = max(t[0] for t in ser)
                i3 = float(not any(last < r < d0 for r in runs.get(c, [])))
        fx.append((i1, i2, i3))
    F[id(x)] = np.array(fx)
print("覆蓋率（有傷患頁嘅馬次）", {s: f"{a}/{n} = {a/n:.0%}" for s, (a, n) in sorted(cover.items())}, flush=True)
cnt = np.sum([F[id(x)].sum(0) for x in rows], axis=0); print("I1／I2／I3 馬次", cnt.astype(int).tolist(), flush=True)

by = defaultdict(list)
for x in rows: by[season(x["date"])].append(x)
def fit(races, j):
    R, Z, Y = [], [], []
    for x in races:
        keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]
        r = np.array([h["raw"] for h in x["horses"]])
        R.append((r - r.mean())[keep]); Z.append(F[id(x)][keep, j]); Y += [int(x["horses"][i]["pos"] <= 3) for i in keep]
    R, Z = np.concatenate(R), np.concatenate(Z)
    c = LogisticRegression(C=1e6, max_iter=20000, solver="newton-cg").fit(np.column_stack([R / R.std(), Z]), Y).coef_[0]
    return c[1] / (c[0] / R.std())
for j, arm in enumerate(("I1", "I2", "I3")):
    betas = {s: fit([x for t in by if 2024 <= t < s for x in by[t]], j) for s in sorted(by) if s >= 2025}
    print(arm, "β", {s: round(float(v), 2) for s, v in betas.items()}, flush=True)
    with open(f"{sys.argv[2]}_{arm}.jsonl", "w") as f, open(f"{sys.argv[2]}_base.jsonl", "w") as fb:
        for x in rows:
            fb.write(json.dumps(x, ensure_ascii=False) + "\n")
            y = dict(x, arm=f"vet_{arm}"); bt = betas.get(season(x["date"]))
            if bt is not None:
                add = F[id(x)][:, j] * bt; add = add - add.mean()
                y["horses"] = [dict(h, raw=round(h["raw"] + float(v), 4)) for h, v in zip(x["horses"], add)]
                y["picks"] = [h["n"] for h in sorted(y["horses"], key=lambda h: -h["raw"])]
            f.write(json.dumps(y, ensure_ascii=False) + "\n")
# 殘差診斷（只報，唔揀 arm）
calib = calibrate([x for x in map(json.loads, open(sys.argv[1])) if "horses" in x])
for j, arm in enumerate(("I1", "I2", "I3")):
    for s in sorted(by):
        a, bb = calib[s]; res = []
        for x in by[s]:
            r = np.array([h["raw"] for h in x["horses"]]); rc = r - r.mean()
            for h, z, fv in zip(x["horses"], rc, F[id(x)][:, j]):
                if fv and h["pos"]: res.append(int(h["pos"] <= 3) - 1 / (1 + np.exp(-(a + bb * z))))
        print(f"殘差 {arm} {s}: {100*np.mean(res):+.1f}pp n={len(res)}" if res else f"殘差 {arm} {s}: n=0")

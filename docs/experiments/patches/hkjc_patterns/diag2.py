"""EXP-20261115-14：Kelvin 三條問題診斷 —— 個別練馬師出擊、冷門馬訊號、上仗熱門（老馬）高估。只做診斷。
殘差 = 實際入頭三 − 模型機率（base = market_A：live 現行，walk-forward；dev 2020/21–2023/24）。
練馬師持續性：每個 (練馬師, pattern) 喺 2020/21–2021/22 同 2022/23–2023/24 分開計殘差，睇兩段相關（真訊號應該持續）。
用法：python3 diag2.py <market_A.jsonl> <patterns_feat.pkl>
"""
import gzip
import json
import pickle
import sys
from collections import defaultdict
from datetime import date

import numpy as np
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
sys.path.insert(0, sys.path[0])
import features as F  # noqa: E402


def season(d):
    return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1


def boot(v, rng, n=500):
    days = defaultdict(list)
    for d, e in v:
        days[d].append(e)
    dk = list(days)
    bs = [np.mean([q for i in rng.integers(0, len(dk), len(dk)) for q in days[dk[i]]]) for _ in range(n)]
    return np.percentile(bs, [2.5, 97.5]) * 100


def main():
    import hkjc_history_replay_pit as p
    rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x and 2020 <= season(x["date"]) <= 2023]
    feat = pickle.load(open(sys.argv[2], "rb"))
    df = p.load_all_rows_extended()
    df = df[df["Rank"].notna()]
    key = {}
    for r in df.itertuples():
        key.setdefault((str(r.Date)[:10], int(r.RaceNo), int(r.Rank)), []).append((r.HorseID, r.Trainer, float(r.Odds) if r.Odds == r.Odds else None))
    runs, prof = F.load()
    X, Y = [], []
    for x in rows:
        hs = [h for h in x["horses"] if h["pos"]]
        r = np.array([h["raw"] for h in hs]); X += list(r - r.mean()); Y += [h["pos"] <= 3 for h in hs]
    m = LogisticRegression(C=1e6, max_iter=5000).fit(np.array(X).reshape(-1, 1), Y)
    a, b = m.intercept_[0], m.coef_[0][0]
    tr = defaultdict(list)       # (trainer, pattern, half) -> [(d, e)]
    longs = defaultdict(list)
    fav = defaultdict(list)
    for x in rows:
        hs = [h for h in x["horses"] if h["pos"]]
        r = np.array([h["raw"] for h in hs]); rc = r - r.mean()
        for h, z in zip(hs, rc):
            k = key.get((x["date"], x["race"], h["pos"]))
            if not k or len(k) != 1:
                continue
            hid, trainer, odds = k[0]
            e = float(h["pos"] <= 3) - 1 / (1 + np.exp(-(a + b * z)))
            f = (feat.get((x["date"], x["race"], h["pos"])) or [{}])[0]
            past = [q for q in runs.get(hid, []) if q["d"] < x["date"]]
            half = "A" if season(x["date"]) <= 2021 else "B"
            pats = {k2 for k2, v in f.items() if v} | {"全部"}
            if past:
                gap = (date.fromisoformat(x["date"]) - date.fromisoformat(past[-1]["d"])).days
                if gap >= 60:
                    pats.add("休後≥60日")
            for pt in pats:
                tr[(trainer, pt, half)].append((x["date"], e))
            # 冷門
            if odds is not None and odds >= 10:
                for pt in pats:
                    longs[pt].append((x["date"], e))
            # 上仗熱門 × 老馬／上仗表現
            if past:
                last = past[-1]
                lo = F.num(last.get("win_odds"))
                lp = F.pos(last.get("pos"))
                starts = len(past)
                years = (date.fromisoformat(x["date"]) - date.fromisoformat(past[0]["d"])).days / 365.25
                old = years >= 4 or starts >= 35
                if lo is not None and lo <= 5:
                    fav["上仗熱門（全部）"].append((x["date"], e))
                    fav[f"上仗熱門｜{'老馬（在港≥4年或≥35仗）' if old else '非老馬'}"].append((x["date"], e))
                    if lp == 1:
                        fav[f"上仗熱門＋上仗贏｜{'老馬' if old else '非老馬'}"].append((x["date"], e))
                    elif lp and lp <= 3:
                        fav[f"上仗熱門＋上仗入位｜{'老馬' if old else '非老馬'}"].append((x["date"], e))
                    elif lp:
                        fav[f"上仗熱門＋上仗跑輸｜{'老馬' if old else '非老馬'}"].append((x["date"], e))
                if old:
                    fav["老馬（全部）"].append((x["date"], e))
                    if lp == 1:
                        fav["老馬＋上仗贏（全部賠率）"].append((x["date"], e))
    rng = np.random.default_rng(0)
    print("=== 1. 個別練馬師 pattern 持續性（每格兩段各 ≥40 匹）")
    for pt in sorted({k[1] for k in tr}):
        A, B = [], []
        for t in {k[0] for k in tr if k[1] == pt}:
            va, vb = tr.get((t, pt, "A"), []), tr.get((t, pt, "B"), [])
            if len(va) >= 40 and len(vb) >= 40:
                A.append(np.mean([q[1] for q in va])); B.append(np.mean([q[1] for q in vb]))
        if len(A) >= 8:
            print(f"  {pt:22s} 練馬師 {len(A):3d} 位  前後段殘差相關 {np.corrcoef(A, B)[0, 1]:+.3f}")
    # 最強嘅（全段 n≥80，CI 唔跨零）
    print("  —— 個別練馬師 × pattern：全 dev 殘差 CI 唔跨零（n ≥ 80）：")
    hits = []
    for (t, pt) in {(k[0], k[1]) for k in tr}:
        v = tr.get((t, pt, "A"), []) + tr.get((t, pt, "B"), [])
        if len(v) >= 80 and pt != "全部":
            lo, hi = boot(v, rng, 300)
            if lo > 0 or hi < 0:
                va, vb = tr.get((t, pt, "A"), []), tr.get((t, pt, "B"), [])
                hits.append((np.mean([q[1] for q in v]) * 100, t, pt, len(v), lo, hi,
                             np.mean([q[1] for q in va]) * 100 if va else float("nan"), np.mean([q[1] for q in vb]) * 100 if vb else float("nan")))
    for h in sorted(hits, key=lambda z: -abs(z[0]))[:15]:
        print(f"    {h[1]:6s} {h[2]:20s} n={h[3]:4d} 殘差 {h[0]:+6.2f}pp [{h[4]:+.1f},{h[5]:+.1f}]  前段 {h[6]:+.1f} 後段 {h[7]:+.1f}")
    print(f"  （共試咗 {sum(1 for k in {(k[0], k[1]) for k in tr} if len(tr.get((k[0], k[1], 'A'), []) + tr.get((k[0], k[1], 'B'), [])) >= 80)} 格；95% 下預期約 5% 假陽性）")
    print("=== 2. 冷門（賠率 ≥10）入面 pattern 殘差")
    for pt, v in sorted(longs.items(), key=lambda t: -np.mean([q[1] for q in t[1]])):
        if len(v) >= 200:
            lo, hi = boot(v, rng)
            print(f"  {'✅' if lo > 0 or hi < 0 else '  '} {pt:22s} n={len(v):6d} 殘差 {np.mean([q[1] for q in v]) * 100:+6.2f}pp [{lo:+.2f},{hi:+.2f}]")
    print("=== 3. 上仗熱門／老馬")
    for pt, v in fav.items():
        lo, hi = boot(v, rng)
        print(f"  {'✅' if lo > 0 or hi < 0 else '  '} {pt:28s} n={len(v):6d} 殘差 {np.mean([q[1] for q in v]) * 100:+6.2f}pp [{lo:+.2f},{hi:+.2f}]")


if __name__ == "__main__":
    main()

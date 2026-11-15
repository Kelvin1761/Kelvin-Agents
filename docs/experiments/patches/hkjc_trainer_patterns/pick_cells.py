"""EXP-20261115-20：個別練馬師出擊 pattern（Kelvin「加唔到分但幫我搵晒出嚟加 label」）—— 純顯示表。
殘差 = 入頭三 − 模型機率（market_A，live 現行；每段各自校準）。2020/21–2025/26 全部（dev＋holdout）。
揀選（預先登記）：n ≥ 80；|殘差| ≥ 5pp；賽日 bootstrap 95% CI 唔跨零；前段（2020–22）同後段（2023–25）同號而且各 ≥ 2pp。
pattern 只揀 live 計得到嘅：gear_removed、gear_first、last_close_2nd_3rd、quick_backup14、layoff90、rest60、dist_up200、dist_down200、classdrop_jchange、third_up。
用法：python3 pick_cells.py <market_A.jsonl> <patterns_feat.pkl> <out.json>
"""
import json
import pickle
import sys
from collections import defaultdict
from datetime import date

import numpy as np
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
PATS = ["gear_removed", "gear_first", "last_close_2nd_3rd", "quick_backup14", "layoff90", "rest60", "dist_up200",
        "dist_down200", "classdrop_jchange", "third_up"]


def season(d):
    return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1


def main():
    import hkjc_history_replay_pit as p
    rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x and 2020 <= season(x["date"]) <= 2025]
    feat = pickle.load(open(sys.argv[2], "rb"))
    df = p.load_all_rows_extended()
    df = df[df["Rank"].notna()].assign(d=lambda x: x["Date"].astype(str).str[:10]).sort_values(["d", "RaceNo"])
    key, lastd = {}, {}
    for r in df.itertuples():
        k = (r.d, int(r.RaceNo), int(r.Rank))
        prev = lastd.get(r.HorseID)
        key.setdefault(k, []).append((r.Trainer, (date.fromisoformat(r.d) - date.fromisoformat(prev)).days if prev else None))
        lastd[r.HorseID] = r.d
    cal = {}
    for half, (lo, hi) in {"A": (2020, 2022), "B": (2023, 2025)}.items():
        X, Y = [], []
        for x in rows:
            if lo <= season(x["date"]) <= hi:
                hs = [h for h in x["horses"] if h["pos"]]; r = np.array([h["raw"] for h in hs]); X += list(r - r.mean()); Y += [h["pos"] <= 3 for h in hs]
        m = LogisticRegression(C=1e6, max_iter=5000).fit(np.array(X).reshape(-1, 1), Y)
        cal[half] = (m.intercept_[0], m.coef_[0][0])
    cells = defaultdict(list)
    for x in rows:
        half = "A" if season(x["date"]) <= 2022 else "B"
        a, b = cal[half]
        hs = [h for h in x["horses"] if h["pos"]]; r = np.array([h["raw"] for h in hs]); rc = r - r.mean()
        for h, z in zip(hs, rc):
            k = key.get((x["date"], x["race"], h["pos"]))
            f = feat.get((x["date"], x["race"], h["pos"]))
            if not k or len(k) != 1 or not f or len(f) != 1:
                continue
            trainer, gap = k[0]
            ff = dict(f[0]); ff["rest60"] = int(gap is not None and gap >= 60)
            e = float(h["pos"] <= 3) - 1 / (1 + np.exp(-(a + b * z)))
            for pt in PATS:
                if ff.get(pt):
                    cells[(trainer, pt)].append((x["date"], half, e))
    rng = np.random.default_rng(0)
    out, tested = [], 0
    for (t, pt), v in cells.items():
        if len(v) < 80:
            continue
        tested += 1
        m = np.mean([q[2] for q in v])
        A = [q[2] for q in v if q[1] == "A"]; B = [q[2] for q in v if q[1] == "B"]
        if abs(m) < 0.05 or len(A) < 25 or len(B) < 25:
            continue
        ma, mb = np.mean(A), np.mean(B)
        if np.sign(ma) != np.sign(m) or np.sign(mb) != np.sign(m) or min(abs(ma), abs(mb)) < 0.02:
            continue
        days = defaultdict(list)
        for d, _, e in v:
            days[d].append(e)
        dk = list(days)
        bs = [np.mean([q for i in rng.integers(0, len(dk), len(dk)) for q in days[dk[i]]]) for _ in range(1000)]
        lo, hi = np.percentile(bs, [2.5, 97.5])
        if lo > 0 or hi < 0:
            out.append({"trainer": t, "pattern": pt, "n": len(v), "resid_pp": round(m * 100, 1), "ci": [round(lo * 100, 1), round(hi * 100, 1)],
                        "early_pp": round(ma * 100, 1), "late_pp": round(mb * 100, 1)})
    out.sort(key=lambda r: -abs(r["resid_pp"]))
    json.dump({"version": 1, "source": "EXP-20261115-20", "tested_cells": tested, "cells": out}, open(sys.argv[3], "w"), ensure_ascii=False, indent=1)
    print("試咗", tested, "格；入選", len(out))
    for r in out:
        print(f"  {r['trainer']:6s} {r['pattern']:20s} n={r['n']:4d} {r['resid_pp']:+6.1f}pp [{r['ci'][0]:+.1f},{r['ci'][1]:+.1f}] 前 {r['early_pp']:+.1f} 後 {r['late_pp']:+.1f}")


if __name__ == "__main__":
    main()

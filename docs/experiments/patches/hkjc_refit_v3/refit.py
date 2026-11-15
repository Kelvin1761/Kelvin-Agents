"""EXP-20261115-12：HKJC 外層權重 refit（v3 回放：S 版＋FT＋L400 實測＋上仗賠率；Kelvin 2026-11-15「做 refit，段速最重要但由你優化」）。

候選 raw' = raw + Σ_d (w'_d − w_d)·m_d（只限非初出馬；初出馬權重、distance_fit centred、SIP／overlay／上仗賠率全部唔郁）。
fit：場內置中 logistic（入頭三），特徵 = [raw, m_d（非初出）]；w'_d = w_d + β_d / β_raw。標準化＋newton-cg。
非負：w'_d < 0 → 固定喺 0（Δ = −w_d）再 fit 其餘，迭代。
版本：F = 八維自由；S = 段速固定 0.1285。dev 逐季 walk-forward（訓練 = 之前所有季，2019/20 起）；holdout 用全 dev。
用法：python3 refit.py <v3_base.jsonl> <outdir>
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression

W = {"stability": 0.2451, "trainer_signal": 0.3296, "sectional": 0.1285, "race_shape": 0.1925, "horse_health": 0.0344,
     "trackwork": 0.0, "form_line": 0.0699, "class_advantage": 0.0}
D = list(W)


def season(d):
    return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1


def mats(x):
    hs = x["horses"]
    # (m − 60)·非初出：死欄位（例如回放晨操全部 60）= 0；唔會變成「初出指示」（第一版嘅漏洞）
    M = np.array([[0.0 if h["debut"] else float(h["m"].get(k, 60.0)) - 60.0 for k in D] for h in hs])
    nd = np.array([0.0 if h["debut"] else 1.0 for h in hs])
    return M, nd


def fit(races, fixed):
    R, Ms, Y, DB = [], [], [], []
    for x in races:
        keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]
        r = np.array([h["raw"] for h in x["horses"]])
        M, nd = mats(x)
        R.append((r - r.mean())[keep]); Ms.append((M - M.mean(0))[keep]); DB.append(((1 - nd) - (1 - nd).mean())[keep])
        Y += [int(x["horses"][i]["pos"] <= 3) for i in keep]
    R, Ms, Y, DB = np.concatenate(R), np.vstack(Ms), np.array(Y), np.concatenate(DB)
    fixed = dict(fixed)
    for _ in range(len(D)):
        free = [j for j, k in enumerate(D) if k not in fixed]
        # 固定嘅維度：Δ 已知 → 併入 offset（raw 加返 Δ·m）
        off = R + sum(fixed[k] * Ms[:, j] for j, k in enumerate(D) if k in fixed and fixed[k])
        X = np.column_stack([off] + [Ms[:, j] for j in free] + [DB])      # 最後一欄 = 初出指示（干擾項，唔套落候選）
        s = X.std(0); s[s == 0] = 1
        b = LogisticRegression(C=1e6, max_iter=20000, solver="newton-cg").fit(X / s, Y).coef_[0] / s
        delta = {D[j]: b[i + 1] / b[0] for i, j in enumerate(free)}
        neg = [k for k, v in delta.items() if W[k] + v < 0]
        if not neg:
            break
        for k in neg:
            fixed[k] = -W[k]
    out = dict(fixed); out.update(delta)
    return out


def main():
    rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
    outdir = Path(sys.argv[2])
    by = defaultdict(list)
    for x in rows:
        by[season(x["date"])].append(x)
    for ver, fixed in (("F", {}), ("S", {"sectional": 0.0})):
        deltas = {s: fit([x for t in by if t < min(s, 2024) for x in by[t]], fixed) for s in sorted(by) if s > 2019}
        with open(outdir / f"refit_{ver}.jsonl", "w") as f:
            for x in rows:
                dl = deltas.get(season(x["date"]))
                y = dict(x, arm=f"refit_{ver}")
                if dl:
                    M, _ = mats(x)
                    add = M @ np.array([dl[k] for k in D])
                    y["horses"] = [dict(h, raw=round(h["raw"] + float(a), 4)) for h, a in zip(x["horses"], add)]
                    y["picks"] = [h["n"] for h in sorted(y["horses"], key=lambda h: -h["raw"])]
                f.write(json.dumps(y, ensure_ascii=False) + "\n")
        full = {k: round(W[k] + deltas[2024][k], 4) for k in D}
        print(ver, "全 dev 新權重：", full, "總和", round(sum(full.values()), 4), "（現行總和", round(sum(W.values()), 4), "）")
        for s in (2021, 2022, 2023):
            print("   季", s, {k: round(W[k] + deltas[s][k], 3) for k in D})


if __name__ == "__main__":
    main()

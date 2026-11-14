"""HKJC 歷史回放尺 v4（Kelvin 2026-11-15 決定；docs/model-evaluation-contract.md「HKJC 歷史回放尺 v4」）。

主指標：入頭三 log-loss（逐匹）。機率 p = σ(a + α·(raw − 場均))，(a, α) 由訓練段 fit：
  dev 窗 → 逐季 walk-forward（測 2021/22–2023/24，各用之前季，最早 2020/21）；holdout／terminal 窗 → 用全 dev fit。
  baseline 同候選各自 fit（公平：兩邊都有自己嘅校準）。
判法（v4）：
  1. Δlog-loss（候選 − baseline）95% CI 上界 < 0（按賽日 bootstrap 2,000）
  2. 護欄：Gold、Good 各自 95% CI 下界 > −1.0pp
  3. Δlog-loss 好過 95% 場內洗牌 null（同幅度、冇資訊；200 次）
  另報場內 AUC Δ、capture@5、頭二選有中。
用法：python3 hkjc_replay_compare_v4.py <base.jsonl> <cand.jsonl> [--window dev|holdout|terminal] [--null 200] [--calib <cand_full.jsonl>]
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / ".agents/skills/shared_racing"))
try:
    from eval_metrics import race_metrics  # noqa: E402
except ImportError:
    sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/shared_racing")
    from eval_metrics import race_metrics  # noqa: E402

WIN = {"dev": ("2020-09-01", "2024-07-31"), "holdout": ("2024-09-01", "2026-07-31"), "terminal": ("2026-08-01", "2099-12-31")}


def season(d):
    return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1


def load(p):
    return {(x["meeting"], x["race"]): x for x in map(json.loads, open(p)) if "horses" in x}


def race_xy(x, raws=None):
    hs = [h for h in x["horses"] if h["pos"]]
    r = np.array([h["raw"] for h in hs]) if raws is None else raws
    return r - r.mean(), np.array([int(h["pos"] <= 3) for h in hs])


def fit(races):
    X = np.concatenate([race_xy(x)[0] for x in races])
    Y = np.concatenate([race_xy(x)[1] for x in races])
    m = LogisticRegression(C=1e6, max_iter=5000).fit(X.reshape(-1, 1), Y)
    return float(m.intercept_[0]), float(m.coef_[0][0])


def ll(x, ab, raws=None):
    a, b = ab
    xc, y = race_xy(x, raws)
    p = 1 / (1 + np.exp(-(a + b * xc)))
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).sum()), len(y)


def auc(x, raws=None):
    xc, y = race_xy(x, raws)
    pos, neg = xc[y == 1], xc[y == 0]
    if not len(pos) or not len(neg):
        return None
    return float(np.mean([(p > n) + 0.5 * (p == n) for p in pos for n in neg]))


def main():
    a = sys.argv
    window = a[a.index("--window") + 1] if "--window" in a else "dev"
    nnull = int(a[a.index("--null") + 1]) if "--null" in a else 200
    B, C = load(a[1]), load(a[2])
    # --calib：候選校準用嘅檔（walk-forward 檔冇訓練季時用全季版本；只影響 (a, α) 兩個純量）
    CC = load(a[a.index("--calib") + 1]) if "--calib" in a else C
    keys = sorted(set(B) & set(C))
    lo, hi = WIN[window]
    test = [k for k in keys if lo <= B[k]["date"] <= hi and sum(1 for h in B[k]["horses"] if h["pos"] and h["pos"] <= 3) >= 3]
    devk = [k for k in sorted(B) if WIN["dev"][0] <= B[k]["date"] <= WIN["dev"][1]]   # 校準用 baseline 全部 dev（唔受候選檔覆蓋影響）
    if window == "dev":
        params = {}
        for ts in (2021, 2022, 2023):
            tr = [k for k in devk if season(B[k]["date"]) < ts]
            params[ts] = (fit([B[k] for k in tr]), fit([CC[k] for k in tr if k in CC]))
        test = [k for k in test if season(B[k]["date"]) in params]
        par = lambda k: params[season(B[k]["date"])]
    else:
        pb, pc = fit([B[k] for k in devk]), fit([CC[k] for k in devk if k in CC])
        par = lambda k: (pb, pc)
    rows = []
    for k in test:
        pb, pc = par(k)
        lb, n = ll(B[k], pb)
        lc, _ = ll(C[k], pc)
        hs = [h for h in B[k]["horses"] if h["pos"]]
        pos = {h["n"]: h["pos"] for h in hs}
        top = [n_ for n_, p in pos.items() if p <= 3]
        mb = race_metrics(B[k]["picks"], top, actual_pos=pos)
        mc = race_metrics(C[k]["picks"], top, actual_pos=pos)
        ab, ac = auc(B[k]), auc(C[k])
        rows.append({"k": k, "date": B[k]["date"], "dl": (lc - lb), "n": n, "auc": (ac - ab) if ab is not None else 0.0,
                     "m": [float(mc[q]) - float(mb[q]) for q in ("gold", "good_positional", "top3_capture_at5", "top2_any_hit")]})
    days = sorted({r["date"] for r in rows})
    by_day = defaultdict(list)
    for i, r in enumerate(rows):
        by_day[r["date"]].append(i)
    dl = np.array([r["dl"] for r in rows])
    nn = np.array([r["n"] for r in rows])
    M = np.array([r["m"] for r in rows])
    AU = np.array([r["auc"] for r in rows])
    rng = np.random.default_rng(0)
    bs_l, bs_m, bs_a = [], [], []
    for _ in range(2000):
        ii = np.concatenate([by_day[days[j]] for j in rng.integers(0, len(days), len(days))])
        bs_l.append(dl[ii].sum() / nn[ii].sum())
        bs_m.append(M[ii].mean(0))
        bs_a.append(AU[ii].mean())
    bs_l, bs_m, bs_a = np.array(bs_l), np.array(bs_m), np.array(bs_a)
    d_ll = dl.sum() / nn.sum()
    # null：候選對 baseline 嘅 raw Δ 喺場內洗牌，加返落 baseline，同一套校準（用候選嘅 α）
    null = []
    for _ in range(nnull):
        tot = 0.0
        for r in rows:
            k = r["k"]
            bh = {h["n"]: h for h in B[k]["horses"]}
            ch = {h["n"]: h for h in C[k]["horses"]}
            hs = [h for h in B[k]["horses"] if h["pos"]]
            dlt = np.array([ch[h["n"]]["raw"] - bh[h["n"]]["raw"] for h in hs])
            raws = np.array([h["raw"] for h in hs]) + rng.permutation(dlt)
            pb, pc = par(k)
            lnull, _ = ll(B[k], pc, raws)
            lb, _ = ll(B[k], pb)
            tot += lnull - lb
        null.append(tot / nn.sum())
    null = np.array(null)
    lo_m = np.percentile(bs_m, 2.5, axis=0) * 100
    pass1 = np.percentile(bs_l, 97.5) < 0
    pass2 = lo_m[0] > -1.0 and lo_m[1] > -1.0
    pass3 = (null > d_ll).mean() >= 0.95
    print(f"窗 {window}：{len(rows)} 場、{len(days)} 日")
    print(f"Δlog-loss（每匹）{d_ll:+.5f} [{np.percentile(bs_l, 2.5):+.5f},{np.percentile(bs_l, 97.5):+.5f}]｜好過 null {(null > d_ll).mean() * 100:.0f}%")
    print(f"Δ場內 AUC {AU.mean():+.4f} [{np.percentile(bs_a, 2.5):+.4f},{np.percentile(bs_a, 97.5):+.4f}]")
    for i, lab in enumerate(("Gold", "Good", "capture@5", "頭二選有中")):
        print(f"{lab} {M[:, i].mean() * 100:+.2f} [{lo_m[i]:+.2f},{np.percentile(bs_m[:, i], 97.5) * 100:+.2f}]")
    verdict = "PASS" if (pass1 and pass2 and pass3) else "REJECT"
    print(f"v4 判決：{verdict}（log-loss CI 上界<0 {'✅' if pass1 else '❌'}｜Gold／Good 下界>−1pp {'✅' if pass2 else '❌'}｜好過 95% null {'✅' if pass3 else '❌'}）")


if __name__ == "__main__":
    main()

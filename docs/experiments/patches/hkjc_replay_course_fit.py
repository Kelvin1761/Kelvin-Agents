"""Kelvin 2026-11-15：泥地相對草地、直路往績要變成改善 —— 一般化做「場地類型適性」，用晒 5,200 場（EXP-20261115-01 第二部分）。

點解：EXP-20261114-11 嘅兩個訊號係同一個概念 —— 匹馬喺今場場地類型跑得好過喺其他類型。只喺泥地（~500 場）／直路（~250 場）
判會冇功效；一般化之後每場都有值，可以喺全部場次判。
預先登記（跑之前寫死）：
  場地類型 4 類：ST_TURF（沙田草地、唔係 1000）、ST_STRAIGHT（沙田草地 1000）、HV（跑馬地）、AWT（沙田全天候）
  特徵 course_fit = −[今場類型平均名次百分位 − 其他類型平均名次百分位] × n_今類 /(n_今類 + 3)
         （近 730 日、賽日之前、跑完嘅仗；兩邊都要 ≥ 1 仗，否則 0 = 冇證據）
  篩選：入頭三 ~ 模型（S 版）場內排名百分位 ＋ course_fit；dev／holdout 分開，按場 bootstrap 300
  候選（A 校準加分）：logit P(入頭三) = α·(raw − 場均) + β·z，之前季 fit，δ = β／α；全部場次；walk-forward（2021/22–2023/24）；
         holdout 用全 dev δ 一次
  判法：Gold、Good 都 ≥ 0，而且一個指標 CI 下界 > 0 或者贏 95% null
用法：python3 hkjc_replay_course_fit.py <base_S.jsonl> <replay_index.pkl> <outdir>
"""
import datetime as dt
import json
import pickle
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression


def season(d):
    return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1


def ctype_run(vt, dist):
    vt = vt or ""
    if "全天候" in vt:
        return "AWT"
    if "跑馬地" in vt:
        return "HV"
    return "ST_STRAIGHT" if str(dist) == "1000" else "ST_TURF"


def ctype_race(x):
    if x.get("awt"):
        return "AWT"
    if "跑馬地" in str(x.get("venue")):
        return "HV"
    return "ST_STRAIGHT" if int(x.get("distance") or 0) == 1000 else "ST_TURF"


def main():
    rows = [json.loads(l) for l in open(sys.argv[1]) if '"horses"' in l]
    idx = pickle.load(open(sys.argv[2], "rb"))
    out = Path(sys.argv[3])
    out.mkdir(parents=True, exist_ok=True)
    feat = {}
    for x in rows:
        sec = idx["sect"].get((x["date"], x["race"])) or {}
        no2id = {str(h.get("horse_no")): h.get("horse_id") for h in sec.get("horses", [])}
        today = ctype_race(x)
        d0 = dt.date.fromisoformat(x["date"])
        for h in x["horses"]:
            runs = (idx["horses"].get(no2id.get(str(h["n"]))) or {}).get("runs", [])
            same, other = [], []
            for r in runs:
                if r["iso"] >= x["date"] or (d0 - dt.date.fromisoformat(r["iso"])).days > 730:
                    continue
                p = str(r.get("pos") or "").split()[0].lstrip("0")
                if not p.isdigit():
                    continue
                pct = (int(p) - 1) / 13
                (same if ctype_run(r.get("venue_track"), r.get("distance")) == today else other).append(pct)
            v = 0.0
            if same and other:
                v = -(np.mean(same) - np.mean(other)) * len(same) / (len(same) + 3)
            feat[(x["meeting"], x["race"], h["n"])] = v
    dev_vals = [feat[(x["meeting"], x["race"], h["n"])] for x in rows if "2020-09-01" <= x["date"] <= "2024-07-31" for h in x["horses"]]
    mu, sd = float(np.mean(dev_vals)), float(np.std(dev_vals))
    z = {k: (v - mu) / sd for k, v in feat.items()}
    print(f"course_fit 非零比例 {np.mean([v != 0 for v in feat.values()]) * 100:.0f}%；dev mean {mu:.4f} SD {sd:.4f}")

    # 篩選：模型之上
    for wname, lo, hi in (("dev", "2020-09-01", "2024-07-31"), ("holdout", "2024-09-01", "2026-07-31")):
        R = [x for x in rows if lo <= x["date"] <= hi]
        X, Y, grp = [], [], []
        for gi, x in enumerate(R):
            n = len(x["picks"])
            rank = {hn: i / max(n - 1, 1) for i, hn in enumerate(x["picks"])}
            for h in x["horses"]:
                if h["pos"]:
                    X.append([rank[h["n"]], z[(x["meeting"], x["race"], h["n"])]])
                    Y.append(int(h["pos"] <= 3))
                    grp.append(gi)
        X, Y, grp = np.array(X), np.array(Y), np.array(grp)
        Xs = (X - X.mean(0)) / X.std(0)
        fit = lambda ii: LogisticRegression(C=1e6, max_iter=3000).fit(Xs[ii], Y[ii]).coef_[0][1]
        c = fit(np.arange(len(Y)))
        idx_by = defaultdict(list)
        for i, g in enumerate(grp):
            idx_by[g].append(i)
        gs = list(idx_by)
        rng = np.random.default_rng(0)
        bs = [fit(np.concatenate([idx_by[gs[k]] for k in rng.integers(0, len(gs), len(gs))])) for _ in range(300)]
        print(f"篩選 {wname}（{len(R)} 場）：模型之上每 SD {c:+.3f} [{np.percentile(bs, 2.5):+.3f},{np.percentile(bs, 97.5):+.3f}]", flush=True)

    def fit_delta(train):
        X, Y = [], []
        for x in train:
            hs = [h for h in x["horses"] if h["pos"]]
            raw = np.array([h["raw"] for h in hs])
            X.append(np.c_[raw - raw.mean(), [z[(x["meeting"], x["race"], h["n"])] for h in hs]])
            Y.append([int(h["pos"] <= 3) for h in hs])
        c = LogisticRegression(C=1e6, max_iter=5000).fit(np.vstack(X), np.concatenate(Y)).coef_[0]
        return float(c[1] / c[0])

    def apply(x, d):
        hs = [dict(h, raw=h["raw"] + d * z[(x["meeting"], x["race"], h["n"])]) for h in x["horses"]]
        ns = np.array([h["n"] for h in hs])
        raw = np.array([h["raw"] for h in hs])
        return dict(x, horses=hs, picks=[int(v) for v in ns[np.lexsort((ns, -raw))]])

    dev = [x for x in rows if "2020-09-01" <= x["date"] <= "2024-07-31"]
    wf = {ts: fit_delta([x for x in dev if season(x["date"]) < ts]) for ts in (2021, 2022, 2023)}
    full = fit_delta(dev)
    print("δ walk-forward：", {k: round(v, 3) for k, v in wf.items()}, "；全 dev：", round(full, 3))
    with open(out / "course_wf.jsonl", "w") as fh:
        for x in dev:
            if season(x["date"]) in wf:
                fh.write(json.dumps(apply(x, wf[season(x["date"])]), ensure_ascii=False) + "\n")
    with open(out / "course_full.jsonl", "w") as fh:
        for x in rows:
            fh.write(json.dumps(apply(x, full), ensure_ascii=False) + "\n")
    json.dump({"mu": mu, "sd": sd, "delta_full": full, "delta_wf": wf}, open(out / "course_params.json", "w"), indent=1)


if __name__ == "__main__":
    main()

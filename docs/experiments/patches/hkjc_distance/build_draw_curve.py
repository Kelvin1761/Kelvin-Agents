"""EXP-20261123-11 預先登記（Kelvin 2026-11-23：「1000 米有問題要修；每場只有 3 級（49／65／75）咁粗都可以？4 同 5 檔可以差 16 分？」）。
寫喺跑之前；尺 v5.2；base = SW（表現數字取代段速，EXP-20261123-10 上線版）`<scratch>/f_SW.jsonl`。

觸發（唯讀掃描 docs/audits/2026-11-23-hkjc-step-function-scan.md）：逐檔整體冇偏差，但田草 1000 同谷草 1000
「1–3 檔高估、10 檔以外低估」兩窗同方向。掃描用咗 holdout → 呢個家族 holdout 唔獨立，要披露；判決以 dev ＋ terminal 為主。

曲線（全部 walk-forward：季 s 只用 s 之前嘅季）：
  組 = 場地（沙田草／沙田泥／跑馬地）× 路程；格 = 組 × 檔號（1–14，≥14 併入 14）。
  格值 = 訓練季入面嗰格「實際入頭三 − base 模型預計」平均，向組平均收縮：n／(n＋200)，再減組平均（組內置中）。
  base 模型預計 = 訓練季 fit 嘅 σ(a＋α·(raw−場均)＋γ·logit(3/N))。
arm（場內置中、線性 L2 C=0.1、每季 walk-forward β，同 J3 一樣）：
  DC   加檔位曲線（主）
  DCR  加檔位曲線，同時扣走現行檔位分（draw_score）喺 raw 嘅貢獻：沙田 0.1925×0.55、跑馬地 0.1925×1.0（初出馬照扣）
  DS   （DC／DCR 睇完先加，第二輪）只喺 1000 米加檔號直線：(檔號 − 場均)÷10，沙田草 1000 同跑馬地 1000 各一個 β（其他場 0）
判：dev v5.2 PASS ＋ 頭二入頭三 Δ ≥ 0；terminal 報；holdout 照報（唔獨立）；11-22 否決（頭二入位唔少過 SW、頭二有頭馬唔少過 SW）。
另報 1000 米子集 dev 頭二／Good。唔調 200、唔調分組。
用法：python3 build_draw_curve.py <SW.jsonl> <out_prefix>
"""
import json
import re
import sys
from collections import defaultdict

import numpy as np
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
import hkjc_history_replay_build as hb  # noqa: E402

K = 200.0


def season(d):
    return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1


def main():
    rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
    out = sys.argv[2]
    idx = hb.load_index()["results"]
    draw, awt = {}, {}
    for k, r in idx.items():
        awt[k] = "全天候" in str(r.get("course") or "")
        for q in r.get("results") or []:
            try:
                draw[(k, str(q.get("horse_no")))] = min(14, int(q.get("draw")))
            except (TypeError, ValueError):
                pass

    def group(x):
        k = (x["date"], x["race"])
        v = "沙田泥" if (awt.get(k) or x.get("awt")) else ("跑馬地" if x["venue"] == "跑馬地" else "沙田草")
        return f"{v}{x['distance']}"

    info = {}
    for x in rows:
        k = (x["date"], x["race"])
        info[k] = (group(x), [draw.get((k, str(h["n"]))) for h in x["horses"]],
                   np.array([(h["f"].get("draw_score") or 60.0) for h in x["horses"]]) * 0.1925 * (1.0 if x["venue"] == "跑馬地" else 0.55))
    by = defaultdict(list)
    for x in rows:
        by[season(x["date"])].append(x)

    def calib(races):
        X, Y = [], []
        for x in races:
            hs = [h for h in x["horses"] if h["pos"]]
            r = np.array([h["raw"] for h in hs]); n = len(hs)
            X.append(np.column_stack([r - r.mean(), np.full(n, np.log(3 / n / (1 - 3 / n)) if n > 3 else 0.0)]))
            Y += [int(h["pos"] <= 3) for h in hs]
        return LogisticRegression(C=1e4, max_iter=5000).fit(np.vstack(X), np.array(Y))

    curves = {}
    for s in sorted(by):
        if s < 2020:
            continue
        train = [x for t in by if 2019 <= t < s for x in by[t]]
        m = calib(train)
        cell, grp = defaultdict(lambda: [0, 0.0]), defaultdict(lambda: [0, 0.0])
        for x in train:
            g, dr, _ = info[(x["date"], x["race"])]
            hs = [(h, d) for h, d in zip(x["horses"], dr) if h["pos"]]
            r = np.array([h["raw"] for h, _ in hs]); n = len(hs)
            p = m.predict_proba(np.column_stack([r - r.mean(), np.full(n, np.log(3 / n / (1 - 3 / n)) if n > 3 else 0.0)]))[:, 1]
            for (h, d), pp in zip(hs, p):
                if d is None:
                    continue
                e = int(h["pos"] <= 3) - pp
                c = cell[(g, d)]; c[0] += 1; c[1] += e
                gg = grp[g]; gg[0] += 1; gg[1] += e
        cv = {}
        for (g, d), (n, e) in cell.items():
            gm = grp[g][1] / grp[g][0]
            cv[(g, d)] = n / (n + K) * (e / n - gm)
        curves[s] = cv
    feats = {}
    for x in rows:
        s = season(x["date"])
        if s not in curves:
            continue
        g, dr, ds = info[(x["date"], x["race"])]
        c = np.array([curves[s].get((g, d), 0.0) if d is not None else 0.0 for d in dr])
        feats[(x["date"], x["race"])] = (c - c.mean(), ds - ds.mean())
    print("例：2026/27 田草1000", {d: round(curves[2026].get(("沙田草1000", d), 0) * 100, 1) for d in range(1, 15)}, flush=True)
    print("例：2026/27 跑馬地1000", {d: round(curves[2026].get(("跑馬地1000", d), 0) * 100, 1) for d in range(1, 13)}, flush=True)
    lin = {}
    for x in rows:
        k = (x["date"], x["race"]); g, dr, _ = info[k]
        d = np.array([v if v is not None else np.nan for v in dr], dtype=float)
        mu = np.nanmean(d) if np.isfinite(d).any() else 0.0
        d = np.where(np.isnan(d), mu, d); z = (d - mu) / 10.0
        lin[k] = np.column_stack([z * (g == "沙田草1000"), z * (g == "跑馬地1000")])
    arms = sys.argv[3].split(",") if len(sys.argv) > 3 else ["DC", "DCR"]
    for arm in arms:
        if arm == "DS":
            models = {}
            for s in sorted(by):
                if s < 2020:
                    continue
                R, Z, Y = [], [], []
                for x in (x for t in by if 2019 <= t < s for x in by[t]):
                    k = (x["date"], x["race"]); keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]
                    r = np.array([h["raw"] for h in x["horses"]])
                    R.append((r - r.mean())[keep]); Z.append(lin[k][keep]); Y += [int(x["horses"][i]["pos"] <= 3) for i in keep]
                R, Z, Y = np.concatenate(R), np.vstack(Z), np.array(Y)
                sd = Z.std(axis=0); sd[sd == 0] = 1; rs = R.std()
                c = LogisticRegression(C=0.1, max_iter=20000).fit(np.column_stack([R / rs, Z / sd]), Y).coef_[0]
                models[s] = (c[1:] / sd) / (c[0] / rs)
            print("DS", {s: [round(float(b), 2) for b in m] for s, m in models.items()}, flush=True)
            with open(f"{out}_DS.jsonl", "w") as f:
                for x in rows:
                    s = season(x["date"]); k = (x["date"], x["race"]); y = dict(x, arm="draw_DS")
                    if s in models:
                        new = np.array([h["raw"] for h in x["horses"]]) + lin[k] @ models[s]
                        y["horses"] = [dict(h, raw=round(float(v), 4)) for h, v in zip(x["horses"], new)]
                        y["picks"] = [h["n"] for h in sorted(y["horses"], key=lambda h: -h["raw"])]
                    f.write(json.dumps(y, ensure_ascii=False) + "\n")
            continue
        models = {}
        for s in sorted(curves):
            if s < 2021:
                continue    # 2020/21 冇曲線可以 fit β（曲線要之前季）→ 由 2021/22 起
            R, Z, Y = [], [], []
            for x in (x for t in by if 2020 <= t < s for x in by[t]):
                k = (x["date"], x["race"])
                keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]
                r = np.array([h["raw"] for h in x["horses"]]) - (feats[k][1] if arm == "DCR" else 0.0)
                R.append((r - r.mean())[keep]); Z.append(feats[k][0][keep]); Y += [int(x["horses"][i]["pos"] <= 3) for i in keep]
            R, Z, Y = np.concatenate(R), np.concatenate(Z)[:, None], np.array(Y)
            sd = Z.std() or 1.0; rs = R.std()
            c = LogisticRegression(C=0.1, max_iter=20000).fit(np.column_stack([R / rs, Z / sd]), Y).coef_[0]
            models[s] = (c[1] / sd) / (c[0] / rs)
        print(arm, {s: round(float(b), 2) for s, b in models.items()}, flush=True)
        with open(f"{out}_{arm}.jsonl", "w") as f:
            for x in rows:
                s = season(x["date"]); k = (x["date"], x["race"])
                y = dict(x, arm=f"draw_{arm}")
                if s in models:
                    r = np.array([h["raw"] for h in x["horses"]]) - (feats[k][1] if arm == "DCR" else 0.0)
                    new = r + models[s] * feats[k][0]
                    y["horses"] = [dict(h, raw=round(float(v), 4)) for h, v in zip(x["horses"], new)]
                    y["picks"] = [h["n"] for h in sorted(y["horses"], key=lambda h: -h["raw"])]
                f.write(json.dumps(y, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()

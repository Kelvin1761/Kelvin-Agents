"""研究計劃第 9b 步：評分、配備、馬房出擊（Kelvin 2026-11-14）—— 模型之上有冇剩餘。

預先登記（跑之前寫死；唔准睇完結果先加）：
  樣本  回放 dump 非初出馬（2020/21 起），有今仗同至少一仗往績（馬匹頁）
  H1  rating_drop   = 今仗評分 − 近 365 日最高評分（負 = 跌咗）
  H2  vs_win        = 今仗評分 − 上次贏馬嗰仗評分（冇贏過 = 缺失，另一旗 never_won）
      h2_flag       = vs_win ≤ 0
  H3  blink_on      = 今仗有 B（眼罩）而之前所有仗都冇；blink_off = 上仗有 B 今仗冇；new_gear = 今仗有任何之前未用過嘅配備
  H4  頂級騎師 = 賽日前 365 日騎師入頭三率頭 5 名（as-of，按日更新）
      c1 jockey_up      上仗騎師唔係頂級、今仗係
      c2 class_drop     今仗班次低過上仗（數字大 = 低班）
      c3 win_mark_drop  h2_flag 而且 class_drop
      c4 gear_jockey    new_gear 而且 jockey_up
      c5 freshen_up     相隔 35–70 日而且 jockey_up
  方法  入頭三 ~ 模型場內排名百分位 ＋ 單一特徵（logistic，標準化）；按場 bootstrap 300；全部 12 個特徵一齊 Holm
  判法  dev Holm < 0.05 而且 holdout 同方向 CI 唔跨零 → 開排名候選（walk-forward δ）；否則唔開
用法：python3 hkjc_replay_intent_screen.py <base.jsonl> <replay_index.pkl>
"""
import datetime as dt
import json
import pickle
import re
import sys
from collections import defaultdict, deque

import numpy as np
from sklearn.linear_model import LogisticRegression

WIN = {"dev": ("2020-09-01", "2024-07-31"), "holdout": ("2024-09-01", "2026-07-31")}
CLASSNUM = {"1": 1, "2": 2, "3": 3, "4": 4, "5": 5}


def gear_set(g):
    return {t.strip().rstrip("-1234567890") for t in str(g or "").replace("--", "").split("/") if t.strip()}


def main():
    rows = sorted((json.loads(l) for l in open(sys.argv[1]) if '"horses"' in l), key=lambda x: (x["date"], x["race"]))
    idx = pickle.load(open(sys.argv[2], "rb"))
    # 騎師 365 日入頭三率（as-of，按日）
    jhist = defaultdict(deque)
    top_cache = {}
    all_days = sorted({d for d, _ in idx["results"]})
    jrows = defaultdict(list)
    for (d, n), r in idx["results"].items():
        for x in r.get("results", []):
            p = str(x.get("pos") or "")
            if p[:1].isdigit():
                jrows[d].append((x.get("jockey"), int(re.match(r"\d+", p).group()) <= 3))
    agg = defaultdict(lambda: [0, 0])
    window = deque()
    for d in all_days:
        cut = (dt.date.fromisoformat(d) - dt.timedelta(days=365)).isoformat()
        while window and window[0][0] < cut:
            _, j, p = window.popleft()
            agg[j][0] -= p
            agg[j][1] -= 1
        elig = [(a[0] / a[1], j) for j, a in agg.items() if a[1] >= 50]
        top_cache[d] = {j for _, j in sorted(elig, reverse=True)[:5]}
        for j, p in jrows[d]:
            window.append((d, j, int(p)))
            agg[j][0] += p
            agg[j][1] += 1
    recs = []
    for x in rows:
        if x["date"] < "2020-09-01":
            continue
        sec = idx["sect"].get((x["date"], x["race"])) or {}
        res = idx["results"].get((x["date"], x["race"])) or {}
        no2id = {str(h.get("horse_no")): h.get("horse_id") for h in sec.get("horses", [])}
        jockey = {str(r.get("horse_no")): r.get("jockey") for r in res.get("results", [])}
        n = len(x["picks"])
        rank = {hn: i / max(n - 1, 1) for i, hn in enumerate(x["picks"])}
        top = top_cache.get(x["date"], set())
        for h in x["horses"]:
            if h.get("debut") or not h["pos"]:
                continue
            runs = (idx["horses"].get(no2id.get(str(h["n"]))) or {}).get("runs", [])
            today = next((r for r in runs if r["iso"] == x["date"]), None)
            past = [r for r in runs if r["iso"] < x["date"] and str(r.get("pos", ""))[:1].isdigit()]
            if not today or not past or not str(today.get("rating") or "").isdigit():
                continue
            rt = int(today["rating"])
            d0 = dt.date.fromisoformat(x["date"])
            yr = [int(r["rating"]) for r in past if str(r.get("rating") or "").isdigit() and (d0 - dt.date.fromisoformat(r["iso"])).days <= 365]
            wins = [r for r in past if str(r.get("pos", "")).lstrip("0") == "1" and str(r.get("rating") or "").isdigit()]
            vs_win = rt - int(wins[0]["rating"]) if wins else None
            g_today, g_last = gear_set(today.get("gear")), gear_set(past[0].get("gear"))
            g_hist = set().union(*[gear_set(r.get("gear")) for r in past])
            last = past[0]
            jockey_up = (jockey.get(str(h["n"])) in top) and (last.get("jockey") not in top)
            ct, cl = CLASSNUM.get(str(today.get("class"))), CLASSNUM.get(str(last.get("class")))
            class_drop = bool(ct and cl and ct > cl)
            days = (d0 - dt.date.fromisoformat(last["iso"])).days
            new_gear = bool(g_today - g_hist)
            h2 = vs_win is not None and vs_win <= 0
            recs.append({"date": x["date"], "race": (x["meeting"], x["race"]), "rank": rank[h["n"]], "place": int(h["pos"] <= 3),
                         "rating_drop": rt - max(yr) if yr else np.nan, "vs_win": vs_win if vs_win is not None else np.nan,
                         "h2_flag": float(h2), "never_won": float(not wins),
                         "blink_on": float("B" in g_today and "B" not in g_hist), "blink_off": float("B" in g_last and "B" not in g_today),
                         "new_gear": float(new_gear), "c1_jockey_up": float(jockey_up), "c2_class_drop": float(class_drop),
                         "c3_win_mark_drop": float(h2 and class_drop), "c4_gear_jockey": float(new_gear and jockey_up),
                         "c5_freshen_up": float(35 <= days <= 70 and jockey_up)})
    feats = ["rating_drop", "vs_win", "h2_flag", "never_won", "blink_on", "blink_off", "new_gear",
             "c1_jockey_up", "c2_class_drop", "c3_win_mark_drop", "c4_gear_jockey", "c5_freshen_up"]
    print(f"樣本 {len(recs)} 匹次")
    for wname, (lo, hi) in WIN.items():
        R = [r for r in recs if lo <= r["date"] <= hi]
        races = sorted({r["race"] for r in R})
        ri = defaultdict(list)
        for i, r in enumerate(R):
            ri[r["race"]].append(i)
        y = np.array([r["place"] for r in R])
        out = []
        for f in feats:
            v = np.array([r[f] for r in R], dtype=float)
            ok = ~np.isnan(v)
            X = np.c_[np.array([r["rank"] for r in R]), v][ok]
            Xs = (X - X.mean(0)) / (X.std(0) + 1e-9)
            yy = y[ok]
            pos_map = np.cumsum(ok) - 1
            fit = lambda ii: LogisticRegression(C=1e6, max_iter=3000).fit(Xs[ii], yy[ii]).coef_[0][1]
            c = fit(np.arange(len(yy)))
            rng = np.random.default_rng(0)
            bs = []
            for _ in range(300):
                ii = np.concatenate([ri[races[k]] for k in rng.integers(0, len(races), len(races))])
                ii = pos_map[ii[ok[ii]]]
                bs.append(fit(ii))
            bs = np.array(bs)
            p = max(2 * min((bs <= 0).mean(), (bs >= 0).mean()), 1 / 300)
            out.append((f, c, np.percentile(bs, 2.5), np.percentile(bs, 97.5), p, int(ok.sum()), float(v[ok].mean())))
        order = sorted(range(len(out)), key=lambda i: out[i][4])
        holm = {i: min(1.0, out[i][4] * (len(out) - k)) for k, i in enumerate(order)}
        print(f"\n== {wname}：{len(R)} 匹次、{len(races)} 場")
        for i, (f, c, lo_, hi_, p, nn, mean) in enumerate(out):
            print(f"  {f:<18} n {nn:>6}（均值 {mean:.3f}）｜每 SD {c:+.3f} [{lo_:+.3f},{hi_:+.3f}] Holm {holm[i]:.3f}")


if __name__ == "__main__":
    main()

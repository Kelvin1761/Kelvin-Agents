"""研究計劃第 8 步（初出馬）：歷史攞得到嘅三個 as-of 訊號，喺模型排名之上有冇剩餘。

預先登記（跑之前寫死）：
  樣本   回放 dump 入面 debut=True 嘅馬（2020/21 起）
  訊號   T 練馬師初出上名率：該練馬師之前（賽日前）所有初出馬入頭三率，收縮 (place + 0.25·k)/(n + k)，k = 10
         S 父系初出上名率：同父系之前初出馬入頭三率，同樣收縮（k = 10）—— 嚴格 as-of（唔用 leave-one-out）
         I 進口類別：自購馬（PPG，有海外賽績）／自購新馬／國際拍賣會新馬／其他 → one-hot（自購新馬做基準）
  模型   入頭三 ~ 模型場內排名百分位 ＋ 訊號（初出馬，logistic）；係數 bootstrap（按場）500 次；三個訊號 Holm
  判法   dev 同 holdout 分開報；dev Holm < 0.05 而且 holdout 同方向 CI 唔跨零 → 開排名候選；否則 REJECT
用法：python3 hkjc_replay_debut_screen.py <base.jsonl> <replay_index.pkl>
"""
import json
import pickle
import sys
from collections import defaultdict

import numpy as np
from sklearn.linear_model import LogisticRegression

WIN = {"dev": ("2020-09-01", "2024-07-31"), "holdout": ("2024-09-01", "2026-07-31")}
K = 10


def main():
    rows = sorted((json.loads(line) for line in open(sys.argv[1]) if '"horses"' in line), key=lambda x: (x["date"], x["race"]))
    idx = pickle.load(open(sys.argv[2], "rb"))
    hist_t, hist_s = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0])
    recs = []
    day_buf = []
    cur_day = None

    def flush():
        for tr, sire, p in day_buf:
            hist_t[tr][0] += p
            hist_t[tr][1] += 1
            hist_s[sire][0] += p
            hist_s[sire][1] += 1
        day_buf.clear()
    for x in rows:
        if x["date"] != cur_day:           # 同日嘅結果當日後先入歷史（as-of）
            flush()
            cur_day = x["date"]
        if x["date"] < "2019-09-01":
            continue
        sec = idx["sect"].get((x["date"], x["race"])) or {}
        res = idx["results"].get((x["date"], x["race"])) or {}
        no2id = {str(h.get("horse_no")): h.get("horse_id") for h in sec.get("horses", [])}
        trainer = {str(r.get("horse_no")): r.get("trainer") for r in res.get("results", [])}
        n = len(x["picks"])
        rank = {hn: i / max(n - 1, 1) for i, hn in enumerate(x["picks"])}
        for h in x["horses"]:
            if not h.get("debut") or not h["pos"]:
                continue
            hid = no2id.get(str(h["n"]))
            prof = ((idx["horses"].get(hid) or {}).get("profile") or {}) if hid else {}
            tr, sire = trainer.get(str(h["n"])) or "?", prof.get("父系") or "?"
            imp = prof.get("進口類別") or "?"
            p = int(h["pos"] <= 3)
            tt, ss = hist_t[tr], hist_s[sire]
            recs.append({"date": x["date"], "race": (x["meeting"], x["race"]), "rank": rank[h["n"]], "place": p,
                         "T": (tt[0] + 0.25 * K) / (tt[1] + K), "S": (ss[0] + 0.25 * K) / (ss[1] + K),
                         "I_ppg": float(imp == "自購馬"), "I_isg": float("拍賣" in imp), "I_oth": float(imp not in ("自購馬", "自購新馬") and "拍賣" not in imp)})
            day_buf.append((tr, sire, p))
    print(f"初出馬 {len(recs)} 匹次")
    for wname, (lo, hi) in WIN.items():
        R = [r for r in recs if lo <= r["date"] <= hi]
        races = sorted({r["race"] for r in R})
        ri = defaultdict(list)
        for i, r in enumerate(R):
            ri[r["race"]].append(i)
        y = np.array([r["place"] for r in R])
        print(f"\n== {wname}：{len(R)} 匹次、{len(races)} 場；初出馬入頭三率 {y.mean() * 100:.1f}%")
        res = []
        for lab, cols in (("T 練馬師初出率", ["T"]), ("S 父系初出率", ["S"]), ("I 進口類別", ["I_ppg", "I_isg", "I_oth"])):
            X = np.array([[r["rank"]] + [r[c] for c in cols] for r in R])
            Xs = (X - X.mean(0)) / (X.std(0) + 1e-9)
            fit = lambda ii: LogisticRegression(C=1e6, max_iter=3000).fit(Xs[ii], y[ii]).coef_[0][1:]
            coef = fit(np.arange(len(R)))
            rng = np.random.default_rng(0)
            bs = np.array([fit(np.concatenate([ri[races[k]] for k in rng.integers(0, len(races), len(races))])) for _ in range(500)])
            for j, c in enumerate(cols):
                p = max(2 * min((bs[:, j] <= 0).mean(), (bs[:, j] >= 0).mean()), 1 / 500)
                res.append((f"{lab}·{c}", coef[j], np.percentile(bs[:, j], 2.5), np.percentile(bs[:, j], 97.5), p))
        order = sorted(range(len(res)), key=lambda i: res[i][4])
        for k, i in enumerate(order):
            lab, c, lo_, hi_, p = res[i]
            print(f"  {lab:<22} 每 SD {c:+.3f} [{lo_:+.3f},{hi_:+.3f}] p {p:.3f} Holm {min(1, p * (len(res) - k)):.3f}")


if __name__ == "__main__":
    main()

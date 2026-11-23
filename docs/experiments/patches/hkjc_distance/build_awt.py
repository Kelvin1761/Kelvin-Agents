"""EXP-20261123-15 預先登記（Kelvin 2026-11-23「先做泥地」）。寫喺跑之前；尺 v5.2；base = SW＋DT（EXP-20261123-10／-13 上線版）。

背景：泥地係模型最弱（六季 514 場，場內 AUC 0.687 vs 全部 0.716，首選入頭三 51.6% vs 56.1%）。
舊證據（披露，同一批訊號 dev／holdout 都睇過）：EXP-20261114-05 冇泥地經驗 −9pp（三窗）；EXP-20261114-11 泥地相對草地 +0.17／+0.15 SD、
泥地前段對標準 +0.14／+0.14 SD（dev Holm＋holdout CI 全正）；排名候選全部被舊尺（Gold／Good 點估計唔准負，泥地 dev 239 場）攔住。
今次換 base（SW＋DT）＋換尺（v5.2 以 log-loss 為主）＋用六季全部泥地場判。

特徵（只限泥地賽事；其他場全部 0；場內置中；缺失 = 場均）：
  noexp  近 730 日、今仗路程 ±200 米冇跑過香港全天候（EXP-20261114-05 定義）
  a1     泥地 vs 草地表現（EXP-20261114-11 A1，cache feat_awt.pkl）
  a2     泥地前段對標準（EXP-20261114-11 A2）
arm（線性 L2 C=0.1、每季 walk-forward β，同 J3）：
  AWE  noexp
  AWR  a1 ＋ a2
  AWX  noexp ＋ a1 ＋ a2【主】
判：六季泥地場（2021/22–2026/27，judge_all_group.py awt）v5.2 PASS ＋ 頭二入頭三 Δ ≥ 0（主 arm）；全期 dev／holdout 照報。
用法：python3 build_awt.py <SW_DT.jsonl> <feat_awt.pkl> <out_prefix>
"""
import json
import re
import sys
from collections import defaultdict
from datetime import date

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, "/Users/imac/Antigravity-repo/docs/experiments/patches/hkjc_patterns")
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
import features as F  # noqa: E402
import hkjc_history_replay_build as hb  # noqa: E402


def season(d):
    return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1


def main():
    rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
    cache = pd.read_pickle(sys.argv[2])
    A = {(r.race[0][:10], r.race[1], int(r.n)): (r.A1_awt_vs_turf, r.A2_front_v) for r in cache.itertuples()}
    idx = hb.load_index()["results"]
    awt = {k: "全天候" in str(r.get("course") or "") for k, r in idx.items()}
    n2c = {}
    for k, r in idx.items():
        for q in r.get("results") or []:
            m = re.search(r"\(([A-Z]\d{3})\)", str(q.get("horse_name") or ""))
            if m:
                n2c[(k, str(q.get("horse_no")))] = m.group(1)
    pages, _ = F.load()
    feats, n_awt = {}, 0
    for x in rows:
        k = (x["date"], x["race"])
        isawt = bool(awt.get(k) or x.get("awt"))
        m = np.zeros((len(x["horses"]), 3))
        if isawt:
            n_awt += 1
            d0 = date.fromisoformat(x["date"])
            for i, h in enumerate(x["horses"]):
                c = n2c.get((k, str(h["n"])))
                exp = False
                for q in pages.get(c, []) if c else []:
                    if q["d"] >= x["date"]:
                        break
                    if (d0 - date.fromisoformat(q["d"])).days <= 730 and "全天候" in str(q.get("venue_track") or "") \
                            and abs((F.num(q.get("distance")) or 0) - (x.get("distance") or 0)) <= 200:
                        exp = True
                a1, a2 = A.get((x["date"], x["race"], int(h["n"])), (np.nan, np.nan))
                m[i] = [0.0 if exp else 1.0, a1, a2]
            for j in (1, 2):
                col = m[:, j]; ok = ~np.isnan(col)
                col[~ok] = col[ok].mean() if ok.any() else 0.0
        feats[k] = m - m.mean(axis=0)
    print("泥地場", n_awt, flush=True)
    by = defaultdict(list)
    for x in rows:
        by[season(x["date"])].append(x)
    for arm, cols in (("AWE", [0]), ("AWR", [1, 2]), ("AWX", [0, 1, 2])):
        models = {}
        for s in sorted(by):
            if s < 2021:
                continue    # cache 由 2020/21 起 → 2021/22 起先有之前季 fit
            R, Z, Y = [], [], []
            for x in (x for t in by if 2020 <= t < s for x in by[t]):
                keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]
                r = np.array([h["raw"] for h in x["horses"]])
                R.append((r - r.mean())[keep]); Z.append(feats[(x["date"], x["race"])][:, cols][keep])
                Y += [int(x["horses"][i]["pos"] <= 3) for i in keep]
            R, Z, Y = np.concatenate(R), np.vstack(Z), np.array(Y)
            sd = Z.std(axis=0); sd[sd == 0] = 1; rs = R.std()
            c = LogisticRegression(C=0.1, max_iter=20000).fit(np.column_stack([R / rs, Z / sd]), Y).coef_[0]
            models[s] = (c[1:] / sd) / (c[0] / rs)
        print(arm, {s: [round(float(b), 2) for b in m] for s, m in models.items()}, flush=True)
        with open(f"{sys.argv[3]}_{arm}.jsonl", "w") as f:
            for x in rows:
                s = season(x["date"]); y = dict(x, arm=f"awt_{arm}")
                if s in models:
                    new = np.array([h["raw"] for h in x["horses"]]) + feats[(x["date"], x["race"])][:, cols] @ models[s]
                    y["horses"] = [dict(h, raw=round(float(v), 4)) for h, v in zip(x["horses"], new)]
                    y["picks"] = [h["n"] for h in sorted(y["horses"], key=lambda h: -h["raw"])]
                f.write(json.dumps(y, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()

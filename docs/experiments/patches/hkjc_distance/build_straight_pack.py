"""EXP-20261124-03 預先登記（Kelvin 2026-11-24「直路專屬表現數字方向正，dig deep 睇點樣上線」）。寫喺跑之前；尺 v5.2；base = live（db_DT）。
只限沙田草地 1000 米（直路）；其他場 0；場內置中。
  gap   直路表現數字 − 整體（build_awt_figure.py straight 嘅特徵，pickle）
  has   有冇直路表現數字
  draw  (檔號 − 場均)÷10（EXP-20261123-11 DS 直路部分：每季 β 多數正）
  noexp 近 730 日冇跑過沙田直路 1000（EXP-20261114-05 定義）
STP = 四個一齊，線性 L2 C=0.1、每季 walk-forward β。
判：六季直路場（judge_all_group.py straight）v5.2 PASS ＋ 頭二入頭三 Δ ≥ 0；SF（gap＋has）係 EXP-20261123-18 對照。
功效限制：六季直路 ~206 場，CI 會闊；過唔到唔代表冇效。
用法：python3 build_straight_pack.py <db_DT.jsonl> <sf_feats.pkl> <out_prefix>
"""
import json
import pickle
import re
import sys
from collections import defaultdict
from datetime import date

import numpy as np
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
sys.path.insert(0, "/Users/imac/Antigravity-repo/docs/experiments/patches/hkjc_patterns")
import features as F  # noqa: E402
import hkjc_history_replay_build as hb  # noqa: E402


def season(d):
    return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1


def main():
    rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
    sf = pickle.load(open(sys.argv[2], "rb"))
    idx = hb.load_index()["results"]
    awt = {k: "全天候" in str(r.get("course") or "") for k, r in idx.items()}
    n2, dr = {}, {}
    for k, r in idx.items():
        for q in r.get("results") or []:
            m = re.search(r"\(([A-Z]\d{3})\)", str(q.get("horse_name") or ""))
            if m:
                n2[(k, str(q.get("horse_no")))] = m.group(1)
            try:
                dr[(k, str(q.get("horse_no")))] = float(q.get("draw"))
            except (TypeError, ValueError):
                pass
    pages, _ = F.load()
    feats = {}
    for x in rows:
        k = (x["date"], x["race"])
        if not (x["venue"] != "跑馬地" and x.get("distance") == 1000 and not (awt.get(k) or x.get("awt"))):
            continue
        n = len(x["horses"]); m = np.zeros((n, 4))
        g = sf.get(k)
        if g is not None:
            m[:, 0] = g[:, 0] + 0; m[:, 1] = g[:, 1] + 0     # 已經場內置中
        d = np.array([dr.get((k, str(h["n"])), np.nan) for h in x["horses"]])
        mu = np.nanmean(d) if np.isfinite(d).any() else 0.0
        m[:, 2] = (np.where(np.isnan(d), mu, d) - mu) / 10.0
        d0 = date.fromisoformat(x["date"])
        for i, h in enumerate(x["horses"]):
            c = n2.get((k, str(h["n"])))
            exp = any(q["d"] < x["date"] and (d0 - date.fromisoformat(q["d"])).days <= 730
                      and str(q.get("venue_track") or "").startswith("沙田") and "全天候" not in str(q.get("venue_track") or "")
                      and F.num(q.get("distance")) == 1000 for q in pages.get(c, [])) if c else False
            m[i, 3] = 0.0 if exp else 1.0
        m[:, 3] -= m[:, 3].mean()
        feats[k] = m
    print("直路場", len(feats), flush=True)
    by = defaultdict(list)
    for x in rows:
        by[season(x["date"])].append(x)
    zero = lambda x: np.zeros((len(x["horses"]), 4))  # noqa: E731
    for arm, cols in (("STP", [0, 1, 2, 3]),):
        models = {}
        for s in sorted(by):
            if s < 2020:
                continue
            R, Z, Y = [], [], []
            for x in (x for t in by if 2019 <= t < s for x in by[t]):
                keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]
                r = np.array([h["raw"] for h in x["horses"]])
                R.append((r - r.mean())[keep]); Z.append(feats.get((x["date"], x["race"]), zero(x))[:, cols][keep])
                Y += [int(x["horses"][i]["pos"] <= 3) for i in keep]
            R, Z, Y = np.concatenate(R), np.vstack(Z), np.array(Y)
            sd = Z.std(axis=0); sd[sd == 0] = 1; rs = R.std()
            c = LogisticRegression(C=0.1, max_iter=20000).fit(np.column_stack([R / rs, Z / sd]), Y).coef_[0]
            models[s] = (c[1:] / sd) / (c[0] / rs)
        print(arm, {s: [round(float(b), 2) for b in m] for s, m in models.items()}, flush=True)
        with open(f"{sys.argv[3]}_{arm}.jsonl", "w") as f:
            for x in rows:
                s = season(x["date"]); k = (x["date"], x["race"]); y = dict(x, arm="straight_pack")
                if s in models and k in feats:
                    new = np.array([h["raw"] for h in x["horses"]]) + feats[k][:, cols] @ models[s]
                    y["horses"] = [dict(h, raw=round(float(v), 4)) for h, v in zip(x["horses"], new)]
                    y["picks"] = [h["n"] for h in sorted(y["horses"], key=lambda h: -h["raw"])]
                f.write(json.dumps(y, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()

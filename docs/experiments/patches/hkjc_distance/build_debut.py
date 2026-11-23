"""EXP-20261123-13 預先登記（Kelvin 2026-11-23：「初出馬先做（差距最大）…全部會預先登記，再用六季全部初出馬判」）。寫喺跑之前。

背景（SW base 診斷）：初出馬之間 AUC 0.676（非初出 0.723）；模型只將 3% 初出馬排頭三，嗰 89 匹實際入頭三 49.4% vs 預計 35.7%。
舊證據：EXP-20261114-06 練馬師初出上名率 dev／holdout 都真（+0.31／+0.30 SD），排名候選喺舊護欄差 holdout Good −0.06 → 顯示層＋forward；
自購馬 dev −0.19（Holm 0.008）、holdout −0.17 CI 跨零；父系 as-of 冇料（EXP-20261117-03 REJECT）。試閘歷史冇（回放判唔到）。
**披露**：DT 同一個訊號喺 EXP-20261114-06 睇過 dev／holdout；今次係換 base（SW）＋換尺（v5.2）重判，唔係新家族。

特徵（只限 debut=True 嘅馬；非初出 = 0；場內置中）：
  dt   練馬師初出上名率（as-of：只用今仗日期之前嘅初出馬賽果；同日唔入；收縮 k=10 向 25%），z 化（2024-08 前 mean／SD）
  ppg  進口類別 = 自購馬（有海外賽績）；oth = 其他（非自購新馬、非拍賣）
arm（同 J3 做法：線性 L2 C=0.1、每季 walk-forward β、加落 SW raw）：
  DT   dt【主】
  DTI  dt ＋ ppg ＋ oth
判：(1) 全期 v5.2：dev PASS ＋ 頭二入頭三 Δ ≥ 0；holdout 照判（唔獨立）；terminal 報。
    (2) 六季全部「有初出馬嘅場」（2021/22–2026/27 walk-forward，judge_all_group.py debut）報 log-loss／頭二。
    (3) 11-22 否決（頭二入位唔少過 SW、頭二有頭馬唔少過 SW）。唔調 k、唔揀特徵。
用法：python3 build_debut.py <SW.jsonl> <replay_index.pkl> <out_prefix>
"""
import json
import pickle
import sys
from collections import defaultdict

import numpy as np
from sklearn.linear_model import LogisticRegression

K = 10


def season(d):
    return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1


def main():
    rows = sorted((json.loads(line) for line in open(sys.argv[1]) if '"horses"' in line), key=lambda x: (x["date"], x["race"]))
    idx = pickle.load(open(sys.argv[2], "rb"))
    out = sys.argv[3]
    hist, buf, cur = defaultdict(lambda: [0, 0]), [], None
    F = {}
    for x in rows:
        if x["date"] != cur:
            for tr, p in buf:
                hist[tr][0] += p; hist[tr][1] += 1
            buf.clear(); cur = x["date"]
        sec = idx["sect"].get((x["date"], x["race"])) or {}
        res = idx["results"].get((x["date"], x["race"])) or {}
        no2id = {str(h.get("horse_no")): h.get("horse_id") for h in sec.get("horses", [])}
        trainer = {str(r.get("horse_no")): r.get("trainer") for r in res.get("results", [])}
        m = []
        for h in x["horses"]:
            if not h.get("debut"):
                m.append([np.nan, 0.0, 0.0]); continue
            hid = no2id.get(str(h["n"]))
            prof = ((idx["horses"].get(hid) or {}).get("profile") or {}) if hid else {}
            imp = prof.get("進口類別") or "?"
            tr = trainer.get(str(h["n"])) or "?"
            t = hist[tr]
            m.append([(t[0] + 0.25 * K) / (t[1] + K), float(imp == "自購馬"),
                      float(imp not in ("自購馬", "自購新馬", "?") and "拍賣" not in imp)])
            if h["pos"]:
                buf.append((tr, int(h["pos"] <= 3)))
        F[(x["date"], x["race"])] = (np.array(m, dtype=float), np.array([bool(h.get("debut")) for h in x["horses"]]))
    ref = np.concatenate([a[:, 0][d] for (dd, _r), (a, d) in F.items() if dd < "2024-08-01" and d.any()])
    mu, sd = float(np.nanmean(ref)), float(np.nanstd(ref))
    print(f"初出馬匹次 {sum(int(d.sum()) for a, d in F.values())}；dt mean {mu:.3f} SD {sd:.3f}", flush=True)
    feats = {}
    for k, (a, d) in F.items():
        z = np.where(d, (np.nan_to_num(a[:, 0], nan=mu) - mu) / sd, 0.0)
        mat = np.column_stack([z, a[:, 1], a[:, 2]])
        feats[k] = mat - mat.mean(axis=0)
    by = defaultdict(list)
    for x in rows:
        by[season(x["date"])].append(x)
    for arm, cols in (("DT", [0]), ("DTI", [0, 1, 2])):
        models = {}
        for s in sorted(by):
            if s < 2020:
                continue
            R, Z, Y = [], [], []
            for x in (x for t in by if 2019 <= t < s for x in by[t]):
                keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]
                r = np.array([h["raw"] for h in x["horses"]])
                R.append((r - r.mean())[keep]); Z.append(feats[(x["date"], x["race"])][:, cols][keep])
                Y += [int(x["horses"][i]["pos"] <= 3) for i in keep]
            R, Z, Y = np.concatenate(R), np.vstack(Z), np.array(Y)
            sdz = Z.std(axis=0); sdz[sdz == 0] = 1; rs = R.std()
            c = LogisticRegression(C=0.1, max_iter=20000).fit(np.column_stack([R / rs, Z / sdz]), Y).coef_[0]
            models[s] = (c[1:] / sdz) / (c[0] / rs)
        print(arm, {s: [round(float(b), 2) for b in m] for s, m in models.items()}, flush=True)
        with open(f"{out}_{arm}.jsonl", "w") as f:
            for x in rows:
                s = season(x["date"]); k = (x["date"], x["race"]); y = dict(x, arm=f"debut_{arm}")
                if s in models:
                    new = np.array([h["raw"] for h in x["horses"]]) + feats[k][:, cols] @ models[s]
                    y["horses"] = [dict(h, raw=round(float(v), 4)) for h, v in zip(x["horses"], new)]
                    y["picks"] = [h["n"] for h in sorted(y["horses"], key=lambda h: -h["raw"])]
                f.write(json.dumps(y, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()

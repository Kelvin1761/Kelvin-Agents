"""EXP-20261123-18 預先登記（Kelvin 2026-11-23「泥地專屬表現數字」；直路版 = 同一做法，第二輪：AF 結果睇咗先加，SEG=straight 時「泥地」= 沙田草地 1000 米）。寫喺跑之前；尺 v5.2；base = live（SW＋DT，db_DT）。

背景：泥地 5 個舊方向全部 REJECT（EXP-20261123-15／-16）；用名次計嘅「泥地相對草地」喺表現數字 base 上冇用。今次用時間：
  每個泥地賽日 D：用 D 之前全部香港賽果重估賽事效應（同 live performance_figure 一模一樣），每仗表現數字 fig；
  figAWT = 該馬最近 6 仗**泥地** fig 嘅 1/k 加權（換算今仗負磅；≥1 仗）；figALL = 最近 6 仗（任何場地）同法（≥2 仗，同 live）。
特徵（只限泥地賽事；其他場 0；場內置中）：
  dawt = figAWT − figALL（冇泥地往績 = 0）；has = 有冇 figAWT
AF  dawt ＋ has，線性 L2 C=0.1、每季 walk-forward β。
判：六季泥地場（judge_all_group.py awt）v5.2 PASS ＋ 頭二入頭三 Δ ≥ 0。
用法：python3 build_awt_figure.py <db_DT.jsonl> <out_prefix>
"""
import json
import re
import sys
from collections import defaultdict

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, "/Users/imac/Antigravity-repo")
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts")
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
from hkjc_racing_engine import performance_figure as PF  # noqa: E402
import hkjc_history_replay_build as hb  # noqa: E402


def season(d):
    return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1


def per_run(R, D):
    P = R[R.date < D]
    m = (P.beaten <= 3).values
    adj = (P.tkm - PF.BETA_LB * P.w).values[m]
    hs, rc = P.hs.values[m], P.race.values[m]
    rfe = np.zeros(len(adj))
    for _ in range(15):
        hfe = pd.Series(adj - rfe).groupby(hs).transform("mean").values
        rfe = pd.Series(adj - hfe).groupby(rc).transform("mean").values
    rmap = pd.Series(rfe, index=rc).groupby(level=0).first()
    f = -(P.tkm_cap.values - P.race.map(rmap).values)
    return P.assign(fig=f - np.nanmean(f))


def wfig(runs, today_w, need):
    num = den = 0.0; ok = 0
    for k, (fv, w, km) in enumerate(runs, 1):
        if fv != fv:
            continue
        ok += 1; num += (fv - PF.BETA_LB * (today_w - w) * km) / k; den += 1.0 / k
    return num / den if ok >= need else None


SEG = sys.argv[3] if len(sys.argv) > 3 else "awt"


def main():
    rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
    idx = hb.load_index()["results"]
    awt = {k: "全天候" in str(r.get("course") or "") for k, r in idx.items()}
    R = PF.load_results()
    if SEG == "awt":
        R = R.assign(awt=[awt.get((d, int(rid.split("|")[2])), False) for d, rid in zip(R.date, R.race)])
    else:   # 直路：沙田草地 1000 米
        R = R.assign(awt=[(rid.split("|")[1] == "ST" and not awt.get((d, int(rid.split("|")[2])), False) and dd == 1000)
                          for d, rid, dd in zip(R.date, R.race, R.dist)])
    n2c, wt = {}, {}
    for k, r in idx.items():
        for q in r.get("results") or []:
            m = re.search(r"\(([A-Z]\d{3})\)", str(q.get("horse_name") or ""))
            if m:
                n2c[(k, str(q.get("horse_no")))] = m.group(1)
                try:
                    wt[(k, str(q.get("horse_no")))] = float(q.get("actual_wt"))
                except (TypeError, ValueError):
                    pass
    if SEG == "awt":
        targets = [x for x in rows if awt.get((x["date"], x["race"])) or x.get("awt")]
    else:
        targets = [x for x in rows if x["venue"] != "跑馬地" and x.get("distance") == 1000
                   and not (awt.get((x["date"], x["race"])) or x.get("awt"))]
    dates = sorted({x["date"] for x in targets})
    print("泥地場", len(targets), "日數", len(dates), flush=True)
    cache = {}
    for i, D in enumerate(dates):
        P = per_run(R, D)
        g = {c: grp for c, grp in P.groupby("code", sort=False)}
        cache[D] = g
        if i % 25 == 0:
            print(" ", i, D, flush=True)
        for x in (t for t in targets if t["date"] == D):
            k = (x["date"], x["race"]); m = np.zeros((len(x["horses"]), 2))
            for j, h in enumerate(x["horses"]):
                c = n2c.get((k, str(h["n"]))); w = wt.get((k, str(h["n"])))
                if not c or c not in g or w is None:
                    continue
                gg = g[c]
                allr = list(zip(gg.fig, gg.w, gg.km))[::-1][:6]
                aw = gg[gg.awt]
                awr = list(zip(aw.fig, aw.w, aw.km))[::-1][:6]
                fa, fw = wfig(allr, w, 2), wfig(awr, w, 1)
                if fw is not None and fa is not None:
                    m[j] = [fw - fa, 1.0]
            x["_feat"] = m - m.mean(axis=0)
        cache.pop(D, None)
    feats = {(x["date"], x["race"]): x.pop("_feat") for x in targets}
    import pickle
    pickle.dump(feats, open(f"{sys.argv[2]}_feats.pkl", "wb"))
    by = defaultdict(list)
    for x in rows:
        by[season(x["date"])].append(x)
    zero = lambda x: np.zeros((len(x["horses"]), 2))  # noqa: E731
    models = {}
    for s in sorted(by):
        if s < 2020:
            continue
        Rr, Z, Y = [], [], []
        for x in (x for t in by if 2019 <= t < s for x in by[t]):
            keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]
            r = np.array([h["raw"] for h in x["horses"]])
            Rr.append((r - r.mean())[keep]); Z.append(feats.get((x["date"], x["race"]), zero(x))[keep]); Y += [int(x["horses"][i]["pos"] <= 3) for i in keep]
        Rr, Z, Y = np.concatenate(Rr), np.vstack(Z), np.array(Y)
        sd = Z.std(axis=0); sd[sd == 0] = 1; rs = Rr.std()
        c = LogisticRegression(C=0.1, max_iter=20000).fit(np.column_stack([Rr / rs, Z / sd]), Y).coef_[0]
        models[s] = (c[1:] / sd) / (c[0] / rs)
    print("AF β", {s: [round(float(b), 2) for b in m] for s, m in models.items()}, flush=True)
    with open(f"{sys.argv[2]}_{'AF' if SEG == 'awt' else 'SF'}.jsonl", "w") as f:
        for x in rows:
            s = season(x["date"]); y = dict(x, arm="awt_figure")
            k = (x["date"], x["race"])
            if s in models and k in feats:
                new = np.array([h["raw"] for h in x["horses"]]) + feats[k] @ models[s]
                y["horses"] = [dict(h, raw=round(float(v), 4)) for h, v in zip(x["horses"], new)]
                y["picks"] = [h["n"] for h in sorted(y["horses"], key=lambda h: -h["raw"])]
            f.write(json.dumps(y, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()

"""EXP-20261124-06 預先登記（Kelvin 2026-11-24；Sol 獨立診斷 H2「日數衰減」、H5「可重複高峰」）。寫喺跑之前；尺 v5.2；base = live（db_DT）。
FV：兩個表現數字變體，加落 live base（同 DG 一樣做法，各自一個 arm，每個 2 特徵）：
  PK  可重複高峰 = 最近 6 仗換算 fig 嘅第二高 − figW（≥2 仗；冇 = 0），has 旗
  DD  日數衰減 = 最近 6 仗換算 fig 按 0.5^(距今日數/120) 加權平均 − figW（≥2 仗），has 旗
判：同 DG。原 DG 說明：
DG：同程表現數字差距 = 最近 6 仗「今仗路程 ±200 米」表現數字（≥1 仗）− 最近 6 仗整體（≥2 仗），都換算今仗負磅（同 performance_figure 定義）；
    has = 有冇差距；全部場、場內置中；線性 L2 C=0.1、每季 walk-forward β。
點解：天將龍駒類（上仗短途熱身、今仗返首本）同程表現數字會高過整體；E1「返首本唔扣」只係旗、REJECT；呢個用時間而且全部場都有，有功效。
判：全期 dev／holdout v5.2 PASS ＋ 兩窗頭二入頭三 Δ ≥ 0；另報大幅增程（≥400）馬嘅入頭三殘差變化；11-22 否決。
用法：python3 build_dist_figure.py <db_DT.jsonl> <out_prefix>
"""
"""（原檔頭）EXP-20261123-18 預先登記（Kelvin 2026-11-23「泥地專屬表現數字」；直路版 = 同一做法，第二輪：AF 結果睇咗先加，SEG=straight 時「泥地」= 沙田草地 1000 米）。寫喺跑之前；尺 v5.2；base = live（SW＋DT，db_DT）。

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
    targets = [x for x in rows if x["date"] >= "2019-09-01"]
    dates = sorted({x["date"] for x in targets})
    print("泥地場", len(targets), "日數", len(dates), flush=True)
    cache = {}
    feats_dd = {}
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
                fa = wfig(allr, w, 2)
                if fa is None:
                    continue
                tl = gg.tail(6).iloc[::-1]
                conv = [fv - PF.BETA_LB * (w - ww) * km for fv, ww, km in zip(tl.fig, tl.w, tl.km) if fv == fv]
                dd = [(fv - PF.BETA_LB * (w - ww) * km, 0.5 ** ((pd.Timestamp(D) - pd.Timestamp(dt_)).days / 120.0))
                      for fv, ww, km, dt_ in zip(tl.fig, tl.w, tl.km, tl.date) if fv == fv]
                if len(conv) >= 2:
                    m[j] = [sorted(conv)[-2] - fa, 1.0]
                    sw = sum(b for _, b in dd)
                    feats_dd.setdefault((x["date"], x["race"]), np.zeros((len(x["horses"]), 2)))[j] = [sum(a * b for a, b in dd) / sw - fa, 1.0]
            x["_feat"] = m - m.mean(axis=0)
        cache.pop(D, None)
    feats = {(x["date"], x["race"]): x.pop("_feat") for x in targets}
    for k, v in feats_dd.items():
        feats_dd[k] = v - v.mean(axis=0)
    import pickle
    pickle.dump(feats, open(f"{sys.argv[2]}_feats.pkl", "wb"))
    by = defaultdict(list)
    for x in rows:
        by[season(x["date"])].append(x)
    for ARM, feats in (("PK", feats), ("DD", feats_dd)):
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
        print(ARM, "β", {s: [round(float(b), 2) for b in m] for s, m in models.items()}, flush=True)
        with open(f"{sys.argv[2]}_{ARM}.jsonl", "w") as f:
            for x in rows:
                s = season(x["date"]); y = dict(x, arm=f"figvar_{ARM}")
                k = (x["date"], x["race"])
                if s in models and k in feats:
                    new = np.array([h["raw"] for h in x["horses"]]) + feats[k] @ models[s]
                    y["horses"] = [dict(h, raw=round(float(v), 4)) for h, v in zip(x["horses"], new)]
                    y["picks"] = [h["n"] for h in sorted(y["horses"], key=lambda h: -h["raw"])]
                f.write(json.dumps(y, ensure_ascii=False) + "\n")
    


if __name__ == "__main__":
    main()

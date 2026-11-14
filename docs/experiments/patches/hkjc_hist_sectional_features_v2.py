"""研究計劃第 4 步特徵：歷史逐匹分段 → 賽前 as-of 段速特徵（EXP-08 定義）＋ 負磅換算版（§2c）。

同 `hkjc_hist_sectional_features.py`（EXP-20261113-08）一樣嘅標準／當日快慢／近 6 仗 1/k 加權定義，另加：
  total_vw  全程對標準（扣當日快慢）再按負磅換算到今仗：每仗偏差 + 0.0033 ×（今仗負磅 − 嗰仗負磅）秒／400 米
            （0.0033 = EXP-20261114-01 dev 季實測全程每 400 米每磅，三個路程 0.0024–0.0036 嘅中間值；跑之前寫死）
  first_v   前段唔換算（EXP-20261114-01：前段負磅效應 CI 全跨零）
負磅來源：賽果庫實際負磅（賽前已知）。輸出 race|code 索引，同 EXP-08 一樣。
用法：python3 hkjc_hist_sectional_features_v2.py <replay_index.pkl> <out.pkl>
"""
import pickle
import sys
from collections import defaultdict

import numpy as np
import pandas as pd

CLS = {"第一班": "C1", "第二班": "C2", "第三班": "C3", "第四班": "C4", "第五班": "C5"}
W_PER_LB_PER_400 = 0.0033


def season_of(d):
    return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1


def main():
    idx = pickle.load(open(sys.argv[1], "rb"))
    rows = []
    for (d, n), sec in idx["sect"].items():
        H = sec["horses"]
        if not H or not sec.get("distance"):
            continue
        nsec = len(H[0]["sections"])
        if nsec < 3:
            continue
        res = idx["results"].get((d, n)) or {}
        ven = "HV" if "跑馬地" in str(res.get("venue")) else "ST"
        track = "AWT" if sec.get("surface") == "全天候" else ven
        wt = {str(r.get("horse_no")): r.get("actual_wt") for r in res.get("results", [])}
        dist = sec["distance"]
        lens = [dist - 400 * (nsec - 1)] + [400] * (nsec - 1)
        for h in H:
            t = [s.get("time") for s in h["sections"]]
            if len(t) != nsec or any(x is None for x in t) or not h.get("code"):
                continue
            fin = str(h.get("finish", "")).split()[0]
            w = wt.get(str(h.get("horse_no")))
            rows.append({"race": f"{d}|{ven}|{n}", "date": d, "season": season_of(d), "track": track, "dist": dist,
                         "cls": CLS.get(sec.get("class") or "", "OT"), "code": h["code"], "fin": int(fin) if fin.isdigit() else None,
                         "secs": t, "lens": lens, "w": int(w) if str(w or "").isdigit() else None})
    R = pd.DataFrame(rows).sort_values(["date", "race"]).reset_index(drop=True)
    STD = {}
    for s in sorted(R.season.unique()):
        prior = R[(R.season < s) & (R.fin <= 3)]
        cell, cell_all = defaultdict(list), defaultdict(list)
        for t, dd, c, secs in zip(prior.track, prior.dist, prior.cls, prior.secs):
            for i, v in enumerate(secs):
                cell[(t, dd, c, i)].append(v)
                cell_all[(t, dd, "ALL", i)].append(v)
        st = {k: float(np.median(v)) for k, v in cell.items() if len(v) >= 20}
        st.update({k: float(np.median(v)) for k, v in cell_all.items() if len(v) >= 20})
        STD[s] = st

    def std_for(season, track, dist, cls, n):
        st = STD.get(season) or {}
        v = [st.get((track, dist, cls, i)) or st.get((track, dist, "ALL", i)) for i in range(n)]
        return None if any(x is None for x in v) else v

    var = defaultdict(lambda: defaultdict(list))
    for row in R.itertuples():
        st = std_for(row.season, row.track, row.dist, row.cls, len(row.secs))
        if st is None:
            continue
        dv = [a - b for a, b in zip(row.secs, st)]
        var[(row.date, row.track)]["first"].append(dv[0] / (row.lens[0] / 400))
        var[(row.date, row.track)]["l400"].append(dv[-1])
    VAR = {k: {kk: float(np.median(vv)) for kk, vv in v.items()} for k, v in var.items()}
    by_code = defaultdict(list)
    for i, row in enumerate(R.itertuples()):
        by_code[row.code].append(i)
    races = R.groupby("race").first()[["date", "season", "cls"]]
    today_w = {(r.race, r.code): r.w for r in R.itertuples()}
    feats = []
    for race, rr in R.groupby("race"):
        date, season, tcls = races.loc[race, "date"], races.loc[race, "season"], races.loc[race, "cls"]
        for code in rr.code:
            tw = today_w.get((race, code))
            prev = [i for i in by_code[code] if R.at[i, "date"] < date][-6:][::-1]
            acc = defaultdict(list)
            for i in prev:
                row = R.loc[i]
                st = std_for(season, row.track, row.dist, tcls, len(row.secs)) or std_for(season, row.track, row.dist, row.cls, len(row.secs))
                if st is None:
                    continue
                dv = [a - b for a, b in zip(row.secs, st)]
                v = VAR.get((row.date, row.track), {})
                first = dv[0] / (row.lens[0] / 400) - v.get("first", 0.0)
                total = sum(dv) / (row.dist / 400) - (np.mean([v.get("first", 0.0), v.get("l400", 0.0)]) if v else 0.0)
                acc["first_v"].append(first)
                acc["total_v"].append(total)
                if tw is not None and row.w is not None:
                    acc["total_vw"].append(total + W_PER_LB_PER_400 * (tw - row.w))
            f = {"race": race, "code": code}
            for k, xs in acc.items():
                if len(xs) >= 2:
                    wts = 1.0 / np.arange(1, len(xs) + 1)
                    f[k] = -float(np.dot(xs, wts) / wts.sum())
            feats.append(f)
    F = pd.DataFrame(feats)
    F.to_pickle(sys.argv[2])
    print(f"{len(F)} 行；覆蓋 " + "、".join(f"{c} {F[c].notna().mean() * 100:.0f}%" for c in ("first_v", "total_v", "total_vw") if c in F))


if __name__ == "__main__":
    main()

"""EXP-20261112-11：概念測試 —— 用賽果庫 2019-09 → 2026-11（6,000 場）walk-forward，
睇「段速修正等級」由「輸頭馬秒數」換做「表現數字＋負磅換算」係咪排名更好。

Kelvin 2026-11-12：「唔好推去 forward，我哋應該有足夠數據測呢個概念。」
真引擎只喺 449 場有評分（Logic 由 2026-05 起），所以呢度用一個**簡化模型**做概念測試：同一組基礎特徵，
只換「段速修正」嗰一項，逐季 walk-forward。結論係概念層面嘅，唔等於真引擎嘅判決。

預先登記（跑之前寫死）：
  數據    賽果庫全部賽事；每匹馬特徵只用賽日之前嘅仗（PIT）；馬匹用馬匹編號識別
  β       只用 2019/20 季（第一季，只做訓練）估：完成時間/km ~ 馬匹×馬季 FE ＋ 賽事 FE ＋ 負磅
  表現數字 每個賽日重估賽事效應（只用之前、輸頭馬 ≤3 秒嘅仗）；每仗 fig = −(時間/km − 賽事效應)，輸頭馬 >3 秒嘅仗封頂喺 3 秒
          figU = 近 6 仗 1/k 加權；figW = 每仗再加 −β ×（今仗負磅 − 嗰仗負磅）× 路程km 換算到今仗負磅
  輸頭馬  M3 = 近 3 仗輸頭馬秒數平均（同現行 P3 一樣嘅窗；P3 用 margin × 0.17，呢度用實際秒數）
  等級    M3：0.3／0.8／1.3 秒（同引擎）；figU／figW：訓練期分位數，比例同 M3 等級喺訓練期一樣；加減分 +6.52／+1.42／−4／−8
  基礎特徵 近績分（引擎公式：名次 100/85/75/60/40，近 6 仗 1/k 加權）、距上仗日數 log、出賽次數 log、檔位、
          今仗負磅 − 全場平均（≈ 評分）、騎師 365 日 PIT 勝率；冇往績用場內平均＋缺失旗
  模型    特徵場內置中後 logistic；訓練 = 測試季之前所有季；測試季 2020/21 → 2026/27（7 季）
  arm     A = 基礎＋M3 等級（現行概念）｜B = 基礎＋figW 等級（主）｜C = 基礎＋figU 等級（負磅 ablation）
          A2／B2 = 連續值版本｜D = 基礎＋M3 等級＋figW 等級（加入）
  指標    eval_metrics.race_metrics：Gold、Good 位置、capture@5、NDCG@5；按場次配對 bootstrap 2,000
  判準    B 對 A：Gold、Good 點估計都 ≥ 0，其中一個 CI 下界 > 0，而且 7 季入面 ≥ 4 季 Good Δ ≥ 0 → 概念成立；否則唔成立
"""
import glob
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

REPO = Path(__file__).resolve().parents[3]
for p in (REPO, REPO / ".agents/skills/shared_racing", Path(__file__).resolve().parent):
    sys.path.insert(0, str(p))
from hkjc_weight_effect_panel import ols_cluster, secs, twoway  # noqa: E402

BUCKETS = ((1000, 54, 60), (1200, 66.5, 73.5), (1400, 79, 87), (1600, 91, 98.2), (1650, 98.2, 104.5),
           (1800, 104.5, 113), (2000, 118, 127), (2200, 131, 141), (2400, 144, 156))
PTS = np.array([6.52, 1.42, -4.0, -8.0])
M3_CUTS = np.array([0.3, 0.8, 1.3])
FORM = {1: 100.0, 2: 85.0, 3: 75.0, 4: 60.0, 5: 60.0}
KEYS = ("gold", "good_positional", "top3_capture_at5", "ndcg_at5")


def season(d):
    return int(d[:4]) - (int(d[5:7]) < 8)


def load(root):
    rows, seen = [], set()
    files = sorted(glob.glob(str(root / "_research_old_season_results/*.json"))) + \
        sorted(glob.glob(str(root / "HKJC_Race_Results_Database/hkjc results */*/*.json")))
    for f in files:
        try:
            payload = json.loads(Path(f).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for key, race in payload.items():
            if not isinstance(race, dict) or not race.get("results"):
                continue
            venue = "HV" if str(race.get("venue")) in ("跑馬地", "HappyValley") else "ST"
            rid = (str(race.get("racedate")), venue, str(race.get("race_no") or key))
            if rid in seen:
                continue
            seen.add(rid)
            for r in race["results"]:
                t, w = secs(r.get("finish_time")), r.get("actual_wt")
                code = re.search(r"\((\w+)\)", str(r.get("horse_name")))
                if t is None or not str(w).isdigit() or not str(r.get("pos")).strip().isdigit() or not code:
                    continue
                rows.append({"race": "|".join(rid), "date": rid[0], "code": code.group(1), "w": int(w), "time": t,
                             "pos": int(r["pos"]), "draw": pd.to_numeric(r.get("draw"), errors="coerce"),
                             "jockey": str(r.get("jockey") or "").strip()})
    return pd.DataFrame(rows)


def build(root):
    R = load(root)
    R["season"] = R.date.map(season)
    R["t_win"] = R.groupby("race").time.transform("min")
    R["beaten"] = R.time - R.t_win
    R["dist"] = R.t_win.map(lambda t: next((d for d, lo, hi in BUCKETS if lo <= t < hi), np.nan))
    R = R[R.groupby("race").dist.transform(lambda s: s.notna().all())].copy()
    R["km"] = R.dist / 1000.0
    R["tkm"] = R.time / R.km
    R["tkm_cap"] = (R.t_win + R.beaten.clip(upper=3.0)) / R.km
    R["hs"] = R.code + "|" + R.season.astype(str)
    R["w_rel"] = R.w - R.groupby("race").w.transform("mean")
    R = R.sort_values(["date", "race", "code"]).reset_index(drop=True)
    print(f"賽果庫 {R.race.nunique()} 場 / {len(R)} 匹次（{R.date.min()} → {R.date.max()}）", flush=True)

    first = R[(R.season == 2019) & (R.beaten <= 3)]
    for _ in range(3):
        first = first[first.groupby("hs").race.transform("count") >= 2]
        first = first[first.groupby("race").hs.transform("count") >= 4]
    b, se = ols_cluster(twoway(first, "tkm", ["w"], "hs", "race"), "tkm", ["w"], first.code.values)
    beta = float(b[0])
    print(f"β（只用 2019/20，{len(first)} 匹次）= {beta:+.5f} s/km／磅 [{beta-1.96*se[0]:+.5f},{beta+1.96*se[0]:+.5f}]", flush=True)

    # 唔使表現數字嘅特徵：逐匹馬按時間排
    g = R.groupby("code")
    R["n_runs"] = g.cumcount()
    R["prev_date"] = g.date.shift(1)
    R["days"] = (pd.to_datetime(R.date) - pd.to_datetime(R.prev_date)).dt.days
    fs = R.pos.map(lambda p: FORM.get(p, 40.0))
    lags = [g.pos.shift(k).map(lambda p: FORM.get(p, 40.0) if p == p else np.nan) for k in range(1, 7)]
    num = sum(l.fillna(0) / k for k, l in enumerate(lags, 1))
    den = sum(l.notna() / k for k, l in enumerate(lags, 1))
    R["form"] = num / den.replace(0, np.nan)
    b3 = [g.beaten.shift(k) for k in (1, 2, 3)]
    cnt = sum(x.notna() for x in b3)
    R["M3"] = (sum(x.fillna(0) for x in b3) / cnt.replace(0, np.nan)).where(cnt >= 2)
    # 騎師 365 日 PIT 勝率
    R["dt"] = pd.to_datetime(R.date)
    jr = np.full(len(R), np.nan)
    for j, idx in R.groupby("jockey").indices.items():
        dts = R.dt.values[idx]
        wins = (R.pos.values[idx] == 1).astype(float)
        cw = np.concatenate([[0], np.cumsum(wins)])
        lo = np.searchsorted(dts, dts - np.timedelta64(365, "D"), side="left")
        hi = np.searchsorted(dts, dts, side="left")
        rides = hi - lo
        jr[idx] = np.where(rides >= 20, (cw[hi] - cw[lo]) / np.maximum(rides, 1), np.nan)
    R["jrate"] = jr

    # PIT 表現數字：逐賽日重估賽事效應
    horse_idx = {c: np.array(ix) for c, ix in R.groupby("code").indices.items()}
    pos_in_horse = np.empty(len(R), int)
    for c, ix in horse_idx.items():
        pos_in_horse[ix] = np.arange(len(ix))
    figU = np.full(len(R), np.nan)
    figW = np.full(len(R), np.nan)
    dates = sorted(R.date.unique())
    est = (R.beaten <= 3).values
    adj_all = (R.tkm - beta * R.w).values
    for di, d in enumerate(dates):
        if di % 60 == 0:
            print(f"  {d}（{di}/{len(dates)}）", flush=True)
        n_prior = int(np.searchsorted(R.date.values, d, side="left"))
        if n_prior < 3000:
            continue
        m = est[:n_prior]
        adj, hs, rc = adj_all[:n_prior][m], R.hs.values[:n_prior][m], R.race.values[:n_prior][m]
        rfe = np.zeros(len(adj))
        for _ in range(15):
            hfe = pd.Series(adj - rfe).groupby(hs).transform("mean").values
            rfe = pd.Series(adj - hfe).groupby(rc).transform("mean").values
        rmap = pd.Series(rfe, index=rc).groupby(level=0).first()
        f_prior = -(R.tkm_cap.values[:n_prior] - R.race.iloc[:n_prior].map(rmap).values)
        f_prior = f_prior - np.nanmean(f_prior)
        today = np.where(R.date.values == d)[0]
        for i in today:
            ix = horse_idx[R.code.values[i]]
            k = pos_in_horse[i]
            past = ix[max(0, k - 6):k][::-1]          # 最近先
            if len(past) < 2:
                continue
            fv = f_prior[past]
            ok = ~np.isnan(fv)
            if ok.sum() < 2:
                continue
            wts = (1.0 / np.arange(1, len(past) + 1))[ok]
            figU[i] = float(np.dot(fv[ok], wts) / wts.sum())
            conv = fv[ok] - beta * (R.w.values[i] - R.w.values[past][ok]) * R.km.values[past][ok]
            figW[i] = float(np.dot(conv, wts) / wts.sum())
    R["figU"], R["figW"] = figU, figW
    R["place"] = (R.pos <= 3).astype(float)
    return R, beta


def main():
    import wongchoi_paths
    from eval_metrics import race_metrics
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    cache = out / "concept_features.pkl"
    if cache.exists():
        R = pd.read_pickle(cache)
        beta = float(json.loads((out / "beta.json").read_text())["beta"])
    else:
        R, beta = build(Path(wongchoi_paths.HK_RACING))
        R.to_pickle(cache)
        (out / "beta.json").write_text(json.dumps({"beta": beta}))
    print(f"覆蓋：M3 {R.M3.notna().mean()*100:.1f}%、figW {R.figW.notna().mean()*100:.1f}%、form {R.form.notna().mean()*100:.1f}%、"
          f"jrate {R.jrate.notna().mean()*100:.1f}%", flush=True)

    # 場內置中；缺失 = 場內平均＋缺失旗
    D = R.copy()
    D["log_days"] = np.log1p(D.days.clip(upper=400))
    D["log_runs"] = np.log1p(D.n_runs)
    base_cols = ["form", "log_days", "log_runs", "draw", "w_rel", "jrate"]
    for c in base_cols + ["M3", "figU", "figW"]:
        D[c + "_miss"] = D[c].isna().astype(float)
    def centred(df, cols):
        X = pd.DataFrame(index=df.index)
        for c in cols:
            v = df[c].fillna(df.groupby("race")[c].transform("mean")).fillna(0.0)
            X[c] = v - v.groupby(df.race).transform("mean")
        return X
    seasons = sorted(D.season.unique())
    tests = [s for s in seasons if s >= 2020]
    arms = {
        "A": ["lvl_M3"], "B": ["lvl_figW"], "C": ["lvl_figU"],
        "A2": ["M3c"], "B2": ["figWc"], "D": ["lvl_M3", "lvl_figW"],
    }
    preds = {a: pd.Series(np.nan, index=D.index) for a in arms}
    for ts in tests:
        tr = D.season < ts
        te = D.season == ts
        # 等級：M3 用引擎門檻；figU／figW 用訓練期分位數，比例同 M3 等級喺訓練期一樣（越大越好 → 取負）
        both = tr & D.M3.notna() & D.figW.notna()
        lv = np.searchsorted(M3_CUTS, D.M3[both], side="right")
        shares = np.array([np.mean(lv == k) for k in range(4)])
        q = np.cumsum(shares)[:3]
        D["lvl_M3"] = np.where(D.M3.notna(), PTS[np.searchsorted(M3_CUTS, D.M3.fillna(0), side="right")], np.nan)
        for c in ("figU", "figW"):
            cuts = np.quantile(-D.loc[both, c], q)
            D["lvl_" + c] = np.where(D[c].notna(), PTS[np.searchsorted(cuts, -D[c].fillna(0), side="right")], np.nan)
        D["M3c"], D["figWc"] = -D.M3, D.figW
        for a, extra in arms.items():
            cols = base_cols + [c + "_miss" for c in base_cols] + extra + [c.replace("lvl_", "").replace("c", "") + "_miss" if False else c for c in []]
            miss = [("M3_miss" if "M3" in e else "figW_miss" if "figW" in e else "figU_miss") for e in extra]
            cols = base_cols + [c + "_miss" for c in base_cols] + extra + sorted(set(miss))
            X = centred(D, cols)
            m = LogisticRegression(max_iter=3000, C=1.0).fit(X[tr], D.place[tr])
            preds[a][te] = m.decision_function(X[te])
        print(f"  季 {ts}/{(ts+1)%100:02d}：訓練 {tr.sum()} 匹，測試 {D[te].race.nunique()} 場", flush=True)

    T = D[D.season.isin(tests)]
    res = {a: {} for a in arms}
    for race, s in T.groupby("race"):
        pos = dict(zip(s.code, s.pos))
        top = [c for c, p in pos.items() if p <= 3]
        for a in arms:
            sc = preds[a][s.index]
            picks = list(s.code.values[np.lexsort((s.code.values, -sc.values))])
            mm = race_metrics(picks, top, actual_pos=pos)
            res[a][race] = [float(mm.get(k) or 0) for k in KEYS]
    races = sorted(res["A"])
    season_of = T.groupby("race").season.first()
    M = {a: np.array([res[a][r] for r in races]) for a in arms}
    rng = np.random.default_rng(0)
    boot = rng.integers(0, len(races), (2000, len(races)))
    print(f"\n測試 {len(races)} 場（{tests[0]}/{(tests[0]+1)%100:02d} → {tests[-1]}/{(tests[-1]+1)%100:02d}）")
    for a in arms:
        v = M[a].mean(axis=0)
        print(f"  {a:<3} Gold {v[0]*100:.2f}%  Good {v[1]*100:.2f}%  capture@5 {v[2]*100:.2f}%  NDCG {v[3]:.4f}")

    def pair(x, y, lab):
        d = M[x] - M[y]
        bs = d[boot].mean(axis=1)
        parts = []
        for k, name in enumerate(("Gold", "Good", "capture@5", "NDCG")):
            s = 1 if name == "NDCG" else 100
            parts.append(f"{name} {d[:,k].mean()*s:+.3f} [{np.percentile(bs[:,k],2.5)*s:+.3f},{np.percentile(bs[:,k],97.5)*s:+.3f}]")
        ss = pd.Series(d[:, 1], index=races).groupby(season_of[races].values).mean() * 100
        sg = pd.Series(d[:, 0], index=races).groupby(season_of[races].values).mean() * 100
        print(f"  {lab}：" + "｜".join(parts))
        print(f"      逐季 Good Δ：{ {int(k): round(v, 2) for k, v in ss.items()} }")
        print(f"      逐季 Gold Δ：{ {int(k): round(v, 2) for k, v in sg.items()} }")
        return d, bs, ss
    print("\n配對（候選 − 對照）：")
    d, bs, ss = pair("B", "A", "B（figW 等級）− A（輸頭馬等級）【主】")
    pair("C", "A", "C（figU 等級）− A")
    pair("B", "C", "B − C（負磅換算嘅邊際）")
    pair("B2", "A2", "B2（figW 連續）− A2（輸頭馬連續）")
    pair("D", "A", "D（兩樣都放）− A")
    g_, q_ = d[:, 0].mean(), d[:, 1].mean()
    lo = [np.percentile(bs[:, 0], 2.5), np.percentile(bs[:, 1], 2.5)]
    ok = g_ >= 0 and q_ >= 0 and max(lo) > 0 and (ss >= 0).sum() >= 4
    print(f"\n判準（預先登記）：Gold {g_*100:+.3f}、Good {q_*100:+.3f} 都 ≥0？CI 下界 >0？季數 Good Δ≥0：{(ss >= 0).sum()}/{len(ss)} → "
          f"{'概念成立' if ok else '概念唔成立'}")

    def auc(col, df):
        a = [roc_auc_score(s.place, s[col]) for _r, s in df.groupby("race") if 0 < s.place.sum() < len(s) and s[col].notna().all()]
        return np.mean(a), len(a)
    T2 = T.dropna(subset=["M3", "figW", "figU"]).copy()
    T2["negM3"] = -T2.M3
    T2 = T2[T2.groupby("race").race.transform("count") >= 5]
    print("\nleaf 場內 AUC（測試季，三個都有嘅馬）：")
    for ts in tests:
        s = T2[T2.season == ts]
        print(f"  {ts}/{(ts+1)%100:02d}: " + "  ".join(f"{c} {auc(c, s)[0]:.4f}" for c in ("negM3", "figU", "figW")) + f"（{s.race.nunique()} 場）")
    print("  全部: " + "  ".join(f"{c} {auc(c, T2)[0]:.4f}" for c in ("negM3", "figU", "figW")))


if __name__ == "__main__":
    main()

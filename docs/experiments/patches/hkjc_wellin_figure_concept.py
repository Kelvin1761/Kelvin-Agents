"""EXP-20261112-22：well-in 概念測試 —— 用表現數字做能力來源，睇讓磅官（負磅）有冇評錯（賽果庫 2019-09 → 2026-11）。

背景：EXP-20261111-08 用**模型能力**量 well-in，冇訊號；結論係「要有準過讓磅官嘅能力來源先值得重試」。
EXP-11 表現數字（PIT，扣賽事效應）準過輸頭馬秒數，係嗰個候選。

預先登記（跑之前寫死）：
  場次   讓磅賽（賽果庫標題第一至五班），測試季 2020/21 → 2026/27；特徵全部 PIT（concept_features.pkl，EXP-11）
  能力   F = figU（近 6 仗表現數字，未換算負磅，s/km，越大越快）
  讓磅官 W = 今仗負磅 − 全場平均（讓磅賽 = 評分差距嘅代理；實際負磅，已扣見習減磅）
  well_in = F − b × W，b 喺訓練季 pooled 場內回歸 F ~ W 估（「讓磅官預期 F」）；正 = 能力高過負磅反映
  測試
    1. 場內 AUC：F、W、well_in（逐季）
    2. 條件係數：place ~ 基礎（近績、日數、出賽數、檔位、騎師）＋ M3 等級 ＋ F ＋ W，睇 W 嘅係數
       （> 0 = 讓磅官知多過表現數字；< 0 = 負磅喺能力之外仲係負擔，即 well-in 有著數）
    3. walk-forward 簡化模型：A = 基礎＋W＋M3 等級（EXP-11 A）｜B = A ＋ F｜C = A ＋ well_in 三分位旗（頂三分一）
       主比較 C − B（well-in 喺表現數字之上有冇剩餘）；B − A 做參考
    4. cohort：well-in 頂三分一而 W 底三分一（EXP-20261111-08 定義）相對簡化模型 B 預期
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
for p in (REPO, REPO / ".agents/skills/shared_racing"):
    sys.path.insert(0, str(p))
PTS = np.array([6.52, 1.42, -4.0, -8.0])
M3_CUTS = np.array([0.3, 0.8, 1.3])
KEYS = ("gold", "good_positional", "top3_capture_at5", "ndcg_at5", "top2_any_hit")


def handicap_races(root):
    out = {}
    files = sorted(glob.glob(str(root / "_research_old_season_results/*.json"))) + \
        sorted(glob.glob(str(root / "HKJC_Race_Results_Database/hkjc results */*/*.json")))
    for f in files:
        try:
            payload = json.loads(Path(f).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for key, race in payload.items():
            if not isinstance(race, dict):
                continue
            venue = "HV" if str(race.get("venue")) in ("跑馬地", "HappyValley") else "ST"
            rid = "|".join((str(race.get("racedate")), venue, str(race.get("race_no") or key)))
            flat = " ".join(" ".join(map(str, row)) for row in race.get("sectional_times") or [])
            m = re.search(r"第([一二三四五])班", flat)
            if m and rid not in out:
                out[rid] = "一二三四五".index(m.group(1)) + 1
    return out


def main():
    import wongchoi_paths
    from eval_metrics import race_metrics
    cdir = Path(sys.argv[1])
    D = pd.read_pickle(cdir / "concept_features.pkl")
    cls = handicap_races(Path(wongchoi_paths.HK_RACING))
    D["hcls"] = D.race.map(cls)
    D = D[D.hcls.notna()].copy()
    D = D[D.groupby("race").race.transform("count") >= 5]
    D["W"] = D.w_rel
    D["F"] = D.figU
    D["log_days"] = np.log1p(D.days.clip(upper=400))
    D["log_runs"] = np.log1p(D.n_runs)
    print(f"讓磅賽 {D.race.nunique()} 場 / {len(D)} 匹；有 F {D.F.notna().mean()*100:.1f}%")

    def centred(df, cs):
        X = pd.DataFrame(index=df.index)
        for c in cs:
            v = df[c].fillna(df.groupby("race")[c].transform("mean")).fillna(0.0)
            X[c] = v - v.groupby(df.race).transform("mean")
        return X
    for c in ("form", "log_days", "log_runs", "draw", "W", "jrate", "M3", "F"):
        D[c + "_miss"] = D[c].isna().astype(float)
    base = ["form", "log_days", "log_runs", "draw", "jrate", "form_miss", "log_days_miss", "draw_miss", "jrate_miss"]
    tests = [s for s in sorted(D.season.unique()) if s >= 2020]
    preds = {a: pd.Series(np.nan, index=D.index) for a in ("A", "B", "C")}
    coefs, bs_used = [], []
    D["well_in"] = np.nan
    D["wi_top"] = 0.0
    for ts in tests:
        tr, te = D.season < ts, D.season == ts
        s = D[tr & D.F.notna()]
        Fc = s.F - s.groupby("race").F.transform("mean")
        Wc = s.W - s.groupby("race").W.transform("mean")
        b = float((Fc * Wc).sum() / (Wc * Wc).sum())
        bs_used.append(b)
        D.loc[D.season <= ts, "well_in"] = D.F - b * D.W
        q = D.loc[tr, "well_in"].groupby(D.loc[tr, "race"]).rank(pct=True)
        D["wi_rank"] = D.well_in.groupby(D.race).rank(pct=True)
        D["wi_top"] = ((D.wi_rank >= 2 / 3) & D.well_in.notna()).astype(float)
        D["lvl"] = np.where(D.M3.notna(), PTS[np.searchsorted(M3_CUTS, D.M3.fillna(0), side="right")], np.nan)
        cols = {"A": base + ["W", "lvl", "M3_miss"], "B": base + ["W", "lvl", "M3_miss", "F", "F_miss"],
                "C": base + ["W", "lvl", "M3_miss", "F", "F_miss", "wi_top"]}
        for a, cs in cols.items():
            X = centred(D, cs)
            m = LogisticRegression(max_iter=3000, C=1.0).fit(X[tr], D.place[tr])
            preds[a][te] = m.decision_function(X[te])
            if a == "B":
                coefs.append((ts, dict(zip(cs, m.coef_[0]))))
    print("b（讓磅官預期：每 1 磅 W 對應 F 幾多 s/km，逐季訓練）：", [round(x, 5) for x in bs_used])

    T = D[D.season.isin(tests)]
    print("\n== 1. 場內 AUC（測試季）==")

    def auc(col, s):
        return np.mean([roc_auc_score(x.place, x[col]) for _r, x in s.dropna(subset=[col]).groupby("race") if 0 < x.place.sum() < len(x) and x[col].nunique() > 1])
    TT = T.dropna(subset=["F"])
    for ss in tests:
        s = TT[TT.season == ss]
        print(f"  {ss}/{(ss+1)%100:02d}: F {auc('F', s):.4f}  W {auc('W', s):.4f}  well_in {auc('well_in', s):.4f}")
    print(f"  全部: F {auc('F', TT):.4f}  W {auc('W', TT):.4f}  well_in {auc('well_in', TT):.4f}")

    print("\n== 2. 模型 B 入面 W（負磅相對全場）嘅係數（每磅，場內置中 logistic，逐季訓練）==")
    for ts, c in coefs:
        print(f"  訓練至 {ts-1}/{ts%100:02d}：W {c['W']:+.4f}｜F {c['F']:+.3f}")
    X = centred(T, base + ["W", "lvl", "M3_miss", "F", "F_miss"])
    races = T.race.unique()
    idx = {r: np.where(T.race.values == r)[0] for r in races}
    rng = np.random.default_rng(0)
    full = LogisticRegression(max_iter=3000, C=1e6).fit(X, T.place)
    wpos = list(X.columns).index("W")
    bsv = []
    for _ in range(300):
        ii = np.concatenate([idx[r] for r in rng.choice(races, len(races))])
        bsv.append(LogisticRegression(max_iter=3000, C=1e6).fit(X.iloc[ii], T.place.iloc[ii]).coef_[0][wpos])
    print(f"  測試季合併：W {full.coef_[0][wpos]:+.4f} [{np.percentile(bsv,2.5):+.4f},{np.percentile(bsv,97.5):+.4f}]"
          "（> 0 = 讓磅官知多過表現數字；< 0 = 負磅仲係額外負擔）")

    print("\n== 3. walk-forward 簡化模型 ==")
    res = {a: [] for a in preds}
    rl = []
    for race, s in T.groupby("race"):
        pos = dict(zip(s.code, s.pos))
        top = [c for c, p in pos.items() if p <= 3]
        rl.append(race)
        for a in preds:
            sc = preds[a][s.index].values
            picks = list(s.code.values[np.lexsort((s.code.values, -sc))])
            mm = race_metrics(picks, top, actual_pos=pos)
            res[a].append([float(mm.get(k) or 0) for k in KEYS])
    M = {a: np.array(v) for a, v in res.items()}
    for a in M:
        v = M[a].mean(axis=0)
        print(f"  {a}: Gold {v[0]*100:.2f}%  Good {v[1]*100:.2f}%  capture@5 {v[2]*100:.2f}%  NDCG {v[3]:.4f}  頭二選有中 {v[4]*100:.2f}%")
    boot = np.random.default_rng(1).integers(0, len(rl), (2000, len(rl)))
    seas = T.groupby("race").season.first()[rl].values
    for x, y, lab in (("B", "A", "B − A（加表現數字）"), ("C", "B", "C − B（well-in 旗喺表現數字之上）【主】")):
        d = M[x] - M[y]
        bs = d[boot].mean(axis=1)
        parts = [f"{n} {d[:,i].mean()*(1 if n=='NDCG' else 100):+.3f} [{np.percentile(bs[:,i],2.5)*(1 if n=='NDCG' else 100):+.3f},"
                 f"{np.percentile(bs[:,i],97.5)*(1 if n=='NDCG' else 100):+.3f}]" for i, n in enumerate(("Gold", "Good", "capture@5", "NDCG", "頭二選有中"))]
        ss = pd.Series(d[:, 1], index=seas).groupby(level=0).mean()
        print(f"  {lab}：" + "｜".join(parts) + f"｜Good ≥0 季數 {(ss >= 0).sum()}/{len(ss)}")

    print("\n== 4. cohort：well-in 頂三分一 ＋ 負磅底三分一（相對模型 B 預期）==")
    T = T.assign(pB=1 / (1 + np.exp(-preds["B"][T.index])))
    T["pB"] = T.pB / T.groupby("race").pB.transform("sum") * T.groupby("race").place.transform("sum")
    T["w_rank"] = T.W.groupby(T.race).rank(pct=True)
    c1 = (T.wi_rank >= 2 / 3) & (T.w_rank <= 1 / 3)
    for lab, sel in (("well-in＋輕磅", c1), ("其餘", ~c1)):
        s = T[sel]
        print(f"  {lab:<10} n={len(s):>6}  上名 {s.place.mean()*100:5.1f}%  模型 B 預期 {s.pB.mean()*100:5.1f}%  差 {(s.place-s.pB).mean()*100:+.2f}pp")
    rr = T.race.unique()
    ii = {r: np.where(T.race.values == r)[0] for r in rr}
    rng = np.random.default_rng(2)

    def f(x):
        a, b = x[c1.loc[x.index]], x[~c1.loc[x.index]]
        return ((a.place - a.pB).mean() - (b.place - b.pB).mean()) * 100
    bsx = [f(T.iloc[np.concatenate([ii[r] for r in rng.choice(rr, len(rr))])]) for _ in range(500)]
    print(f"  差距 {f(T):+.2f}pp [{np.percentile(bsx,2.5):+.2f},{np.percentile(bsx,97.5):+.2f}]")


if __name__ == "__main__":
    main()

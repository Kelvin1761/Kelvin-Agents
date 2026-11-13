"""EXP-20261113-08：用 2019 起全部歷史場次（真逐匹分段）重新判段速概念。

預先登記（跑之前寫死）：
  基礎 B0 = 近績分、出賽相隔、出賽數、檔位、負磅相對全場、騎師 PIT 勝率（冇任何段速／完成時間）
  基礎 B  = B0 ＋ 輸頭馬等級 ＋ 表現數字 figW（即之前賽果庫概念測試嘅基礎）
  候選（每個單獨加）：first、mid、pen、l400、total（各 raw 同 _v 減當日快慢）、style
  另外：段速維度整組 SECT = {first_v, mid_v, l400_v, total_v} 一齊加
  判法：逐季 walk-forward（訓練 = 之前所有季、由 2020/21 起有標準；測試季 2021/22 起），
        模型之上係數（每 SD，場次 bootstrap 300）Holm；Gold／Good／capture@5／頭二選有中配對差（場次 bootstrap 1000）
  過關：Holm < 0.05 而且 Gold、Good 都 ≥ 0（Kelvin）；呢度只係概念，入引擎要另外 A/B
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / ".agents/skills/shared_racing"))
from eval_metrics import race_metrics  # noqa: E402

PTS = np.array([6.52, 1.42, -4.0, -8.0])
KEYS = ("gold", "good_positional", "top3_capture_at5", "top2_any_hit")


def main():
    D = pd.read_pickle(sys.argv[1])            # concept_features.pkl
    F = pd.read_pickle(sys.argv[2])            # sect_features.pkl
    D = D.merge(F, on=["race", "code"], how="left")
    D["log_days"] = np.log1p(D.days.clip(upper=400))
    D["log_runs"] = np.log1p(D.n_runs)
    D["lvl"] = np.where(D.M3.notna(), PTS[np.searchsorted([0.3, 0.8, 1.3], D.M3.fillna(0), side="right")], np.nan)
    D = D[D.season >= 2020].reset_index(drop=True)
    B0 = ["form", "log_days", "log_runs", "draw", "w_rel", "jrate"]
    B = B0 + ["lvl", "figW"]
    sect = ["first", "mid", "pen", "l400", "total"]
    cands = {f: [f] for f in sect + [s + "_v" for s in sect] + ["style"]}
    cands["SECT（整組）"] = ["first_v", "mid_v", "l400_v", "total_v"]

    def centred(df, cs):
        out = pd.DataFrame(index=df.index)
        for c in cs:
            out[c + "_miss"] = df[c].isna().astype(float)
            v = df[c].fillna(df.groupby("race")[c].transform("mean")).fillna(0.0)
            out[c] = v - v.groupby(df.race).transform("mean")
        return out

    tests = [s for s in sorted(D.season.unique()) if s >= 2021]
    print(f"{D.race.nunique()} 場（2020/21 起）；測試季 {tests}；覆蓋：" +
          "、".join(f"{c} {D[c].notna().mean()*100:.0f}%" for c in sect + ["style"]))

    def wf(cols):
        X = centred(D, cols)
        p = pd.Series(np.nan, index=D.index)
        for ts in tests:
            tr, te = D.season < ts, D.season == ts
            p[te] = LogisticRegression(max_iter=3000, C=1.0).fit(X[tr], D.place[tr]).decision_function(X[te])
        return p, X

    def metrics(score):
        T = D[D.season.isin(tests)]
        out, races = [], []
        for race, s in T.groupby("race"):
            pos = dict(zip(s.code, s.pos))
            top = [c for c, q in pos.items() if q <= 3]
            if len(top) < 3:
                continue
            v = score[s.index].values
            m = race_metrics(list(s.code.values[np.lexsort((s.code.values, -v))]), top, actual_pos=pos)
            out.append([float(m.get("gold") or 0), float(m.get("good_positional") or 0),
                        float(m.get("top3_capture_at5") or 0), float((m.get("top2_hits") or 0) >= 1)])
            races.append(race)
        return np.array(out), races

    for base_name, base in (("B0（冇段速）", B0), ("B（＋輸頭馬等級＋表現數字）", B)):
        pb, _ = wf(base)
        mb, races = metrics(pb)
        print(f"\n=== 基礎 {base_name}：Gold {mb[:,0].mean()*100:.2f}% Good {mb[:,1].mean()*100:.2f}% "
              f"capture@5 {mb[:,2].mean()*100:.2f}% 頭二 {mb[:,3].mean()*100:.2f}%（{len(races)} 場）")
        rows = []
        for lab, cols in cands.items():
            pc, Xc = wf(base + cols)
            mc, _ = metrics(pc)
            d = mc - mb
            bs = d[np.random.default_rng(0).integers(0, len(d), (1000, len(d)))].mean(axis=1)
            # 模型之上係數：只用第一個特徵（整組用 pc−pb 做單一分數）
            T = D[D.season.isin(tests)]
            fz = (pc - pb)[T.index] if len(cols) > 1 else Xc.loc[T.index, cols[0]]
            Tz = pd.DataFrame({"zB": pb[T.index], "fz": fz / (fz.std() or 1), "race": T.race, "place": T.place})
            rr = Tz.race.unique()
            ii = {r: np.where(Tz.race.values == r)[0] for r in rr}
            fit = lambda z: LogisticRegression(max_iter=2000, C=1e6).fit(z[["zB", "fz"]], z.place).coef_[0][1]
            rng = np.random.default_rng(1)
            cb = np.array([fit(Tz.iloc[np.concatenate([ii[r] for r in rng.choice(rr, len(rr))])]) for _ in range(300)])
            coef = fit(Tz)
            p = max(2 * min(np.mean(cb <= 0), np.mean(cb >= 0)), 1 / 300)
            rows.append([lab, coef, np.percentile(cb, 2.5), np.percentile(cb, 97.5), p,
                         [(d[:, i].mean() * 100, np.percentile(bs[:, i], 2.5) * 100, np.percentile(bs[:, i], 97.5) * 100) for i in range(4)]])
            print(f"  …{lab} 完成", flush=True)
        order = sorted(range(len(rows)), key=lambda i: rows[i][4])
        holm = {i: min(1.0, rows[i][4] * (len(rows) - k)) for k, i in enumerate(order)}
        print("候選｜模型之上係數（每 SD）｜Holm｜Gold｜Good｜capture@5｜頭二選有中（pp，候選 − 基礎）")
        for i, r in enumerate(rows):
            f = lambda t: f"{t[0]:+.2f} [{t[1]:+.2f},{t[2]:+.2f}]"
            ok = "✅" if holm[i] < 0.05 and r[5][0][0] >= 0 and r[5][1][0] >= 0 else "  "
            print(f" {ok} {r[0]:<12}｜{r[1]:+.3f} [{r[2]:+.3f},{r[3]:+.3f}]｜{holm[i]:.3f}｜" + "｜".join(f(t) for t in r[5]))


if __name__ == "__main__":
    main()

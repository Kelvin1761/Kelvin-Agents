"""EXP-20261112-15：「真」步速修正（用全場領放馬分段時間量步速）概念測試 —— 賽果庫 2019-09 → 2026-11。

Kelvin 2026-11-12：「我想做真正嘅步速修正偏差，但同意要搵返步速，可能睇完成時間？」
現行「步速修正偏差」其實係輸頭馬秒數（EXP-07）；EXP-09 嘅版本用匹馬自己早段代替步速（唔準）。
賽果庫每場有**全場（領放馬）累積時間**同班次／路程／場地狀況，所以可以直接量嗰場嘅步速。

預先登記（跑之前寫死）：
  標準    `hkjc_standard_times.json` 馬會標準時間同標準分段（場地、路程、班次）；搵唔到嗰場唔計
  步速    pace = 領放馬到「最後一段之前」嘅累積時間 − 標準分段（除最後一段）之和；正 = 慢步速
  場速    final = 頭馬完成時間 − 標準時間
  k       final ~ k × pace，只用 2019/20 季估（測試季唔用）
  每匹馬每仗：
    D0    完成時間 − 標準時間（對標準，未修正）
    D1    D0 − k × pace（真步速修正）
    D2    D1 − 當日同場地其他場次嘅 (final − k × pace) 平均（再扣當日場地快慢；只用同一日其他場次）
    D2W   D2 換算到今仗負磅：+ β × 路程km ×（今仗負磅 − 嗰仗負磅），β 用 2019/20 估（EXP-11 β）
    M     輸頭馬秒數（對照 = 現行概念）
  窗口    近 3 仗平均（同現行一樣）；只用賽日之前嘅仗；最少 2 仗
  判準    同一 population 場內 AUC（越細越好取負），逐季；再喺 EXP-11 簡化模型（同一組基礎特徵）入面
          換走輸頭馬等級 → 對照 A；配對 bootstrap。主比較：D2W 對 M。

用法：
  PYTHONDONTWRITEBYTECODE=1 python3 docs/experiments/patches/hkjc_true_pace_concept.py <concept_dir>
  <concept_dir> = hkjc_figure_concept_walkforward.py 嘅輸出（用佢 cache 嘅 PIT 特徵同基礎模型）
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
from hkjc_weight_effect_panel import secs  # noqa: E402

STD = json.loads((REPO / ".agents/scripts/hkjc_standard_times.json").read_text(encoding="utf-8"))
CLASS = {"第一班": "C1", "第二班": "C2", "第三班": "C3", "第四班": "C4", "第五班": "C5",
         "一級賽": "G", "二級賽": "G", "三級賽": "G", "新馬": "GR"}
PTS = np.array([6.52, 1.42, -4.0, -8.0])
M3_CUTS = np.array([0.3, 0.8, 1.3])
KEYS = ("gold", "good_positional", "top3_capture_at5", "ndcg_at5", "top2_any")


def race_info(root):
    out = {}
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
            rid = "|".join((str(race.get("racedate")), venue, str(race.get("race_no") or key)))
            if rid in out:
                continue
            flat = " ".join(" ".join(map(str, row)) for row in race.get("sectional_times") or [])
            m = re.search(r"(第[一二三四五]班|[一二三]級賽|新馬)\S*\s*-\s*(\d{3,4})米", flat)
            cum = []
            for row in race.get("cumulative_times") or race.get("sectional_times") or []:
                if "時間 :" in row:
                    cum = [secs(x.strip("()")) for x in row[row.index("時間 :") + 1:]]
                    break
            if not m or not cum or any(c is None for c in cum):
                continue
            course = str(race.get("course") or "")
            awt = "全天候" in course or "泥地" in course
            vkey = "sha_tin_awt" if awt else ("happy_valley_turf" if venue == "HV" else "sha_tin_turf")
            code = next((v for k, v in CLASS.items() if k in m.group(1)), None)
            dist = int(m.group(2))
            ref = (((STD["reference_sectionals"]["venues"].get(vkey) or {}).get(str(dist)) or {}).get(code) or {})
            sec = ref.get("sections")
            if not sec or len(sec) != len(cum):
                continue
            out[rid] = {"pace": cum[-2] - sum(sec[:-1]), "std_total": float(ref["total"]), "std_km": dist / 1000.0,
                        "day_key": f"{race.get('racedate')}|{vkey}"}
    return out


def main():
    import wongchoi_paths
    from eval_metrics import race_metrics
    cdir = Path(sys.argv[1])
    D = pd.read_pickle(cdir / "concept_features.pkl")
    beta = float(json.loads((cdir / "beta.json").read_text())["beta"])
    info = race_info(Path(wongchoi_paths.HK_RACING))
    I = pd.DataFrame.from_dict(info, orient="index")
    D = D.join(I, on="race")
    print(f"賽果庫 {D.race.nunique()} 場；有標準＋步速 {D.pace.notna().groupby(D.race).first().sum()} 場")
    R = D.dropna(subset=["pace"]).copy()
    R["D0"] = R.time - R.std_total
    R["final"] = R.t_win - R.std_total
    races = R.groupby("race").first()
    tr = races[races.season == 2019]
    k = float(np.polyfit(tr.pace, tr.final, 1)[0])
    print(f"k（2019/20，{len(tr)} 場）= {k:.3f}：早段每慢 1 秒，全程慢 {k:.2f} 秒；corr(pace, final) = {tr.pace.corr(tr.final):+.2f}")
    races["resid"] = races.final - k * races.pace
    day = races.groupby("day_key").resid.agg(["sum", "count"])
    races = races.join(day, on="day_key")
    races["day_var"] = np.where(races["count"] > 1, (races["sum"] - races.resid) / (races["count"] - 1), 0.0)
    R = R.join(races[["day_var"]], on="race")
    R["D1"] = R.D0 - k * R.pace
    R["D2"] = R.D1 - R.day_var
    # 近 3 仗（賽日之前）平均 —— 用同 EXP-11 一樣嘅 shift 方法
    D = D.join(R[["D0", "D1", "D2"]])
    g = D.groupby("code")
    for c in ("D0", "D1", "D2"):
        lags = [g[c].shift(i) for i in (1, 2, 3)]
        cnt = sum(x.notna() for x in lags)
        D[c + "_3"] = (sum(x.fillna(0) for x in lags) / cnt.replace(0, np.nan)).where(cnt >= 2)
    conv = [(D.w - g.w.shift(i)) * g.km.shift(i) * beta for i in (1, 2, 3)]
    lagsD2 = [g.D2.shift(i) for i in (1, 2, 3)]
    num = sum((l + c).fillna(0) for l, c in zip(lagsD2, conv))
    cnt = sum(l.notna() for l in lagsD2)
    D["D2W_3"] = (num / cnt.replace(0, np.nan)).where(cnt >= 2)
    D["M_3"] = D.M3
    cols = ["M_3", "D0_3", "D1_3", "D2_3", "D2W_3"]
    T = D[(D.season >= 2020)].dropna(subset=cols)
    T = T[T.groupby("race").race.transform("count") >= 5]

    def auc(col, s):
        return np.mean([roc_auc_score(x.place, -x[col]) for _r, x in s.groupby("race") if 0 < x.place.sum() < len(x)])
    print(f"\n場內 AUC（2020/21 起，{T.race.nunique()} 場 / {len(T)} 匹，五個都有）")
    for ss in sorted(T.season.unique()):
        s = T[T.season == ss]
        print(f"  {ss}/{(ss+1)%100:02d}: " + "  ".join(f"{c} {auc(c, s):.4f}" for c in cols) + f"（{s.race.nunique()} 場）")
    print("  全部: " + "  ".join(f"{c} {auc(c, T):.4f}" for c in cols))
    print("  corr：\n" + T[cols].corr(method="spearman").round(2).to_string())

    # EXP-11 簡化模型：基礎特徵 ＋ 段速項；逐季 walk-forward
    D["log_days"] = np.log1p(D.days.clip(upper=400))
    D["log_runs"] = np.log1p(D.n_runs)
    base_cols = ["form", "log_days", "log_runs", "draw", "w_rel", "jrate"]
    for c in base_cols + cols:
        D[c + "_miss"] = D[c].isna().astype(float)

    def centred(df, cs):
        X = pd.DataFrame(index=df.index)
        for c in cs:
            v = df[c].fillna(df.groupby("race")[c].transform("mean")).fillna(0.0)
            X[c] = v - v.groupby(df.race).transform("mean")
        return X
    arms = {"A_M": "M_3", "B_D2W": "D2W_3", "C_D2": "D2_3", "E_D1": "D1_3", "F_D0": "D0_3"}
    preds = {a: pd.Series(np.nan, index=D.index) for a in arms}
    tests = [s for s in sorted(D.season.unique()) if s >= 2020]
    for ts in tests:
        trn, te = D.season < ts, D.season == ts
        both = trn & D.M_3.notna()
        lv = np.searchsorted(M3_CUTS, D.M_3[both], side="right")
        q = np.cumsum([np.mean(lv == i) for i in range(4)])[:3]
        for a, c in arms.items():
            if c == "M_3":
                lvl = np.where(D[c].notna(), PTS[np.searchsorted(M3_CUTS, D[c].fillna(0), side="right")], np.nan)
            else:
                cuts = np.quantile(D.loc[trn & D[c].notna(), c], q)
                lvl = np.where(D[c].notna(), PTS[np.searchsorted(cuts, D[c].fillna(0), side="right")], np.nan)
            D["lvl"] = lvl
            X = centred(D, base_cols + [x + "_miss" for x in base_cols] + ["lvl", c + "_miss"])
            m = LogisticRegression(max_iter=3000, C=1.0).fit(X[trn], D.place[trn])
            preds[a][te] = m.decision_function(X[te])
    TT = D[D.season.isin(tests)]
    res = {a: [] for a in arms}
    races_list = []
    for race, s in TT.groupby("race"):
        pos = dict(zip(s.code, s.pos))
        top = [c for c, p in pos.items() if p <= 3]
        races_list.append(race)
        for a in arms:
            sc = preds[a][s.index].values
            picks = list(s.code.values[np.lexsort((s.code.values, -sc))])
            mm = race_metrics(picks, top, actual_pos=pos)
            mm["top2_any"] = (mm.get("top2_hits") or 0) >= 1
            res[a].append([float(mm.get(k) or 0) for k in KEYS])
    M = {a: np.array(v) for a, v in res.items()}
    print(f"\n簡化模型 walk-forward（{len(races_list)} 場）")
    for a in arms:
        v = M[a].mean(axis=0)
        print(f"  {a:<6} Gold {v[0]*100:.2f}%  Good {v[1]*100:.2f}%  capture@5 {v[2]*100:.2f}%  NDCG {v[3]:.4f}  頭二選有中 {v[4]*100:.2f}%")
    rng = np.random.default_rng(0)
    boot = rng.integers(0, len(races_list), (2000, len(races_list)))
    season_of = TT.groupby("race").season.first()[races_list].values
    for a in ("B_D2W", "C_D2", "E_D1", "F_D0"):
        d = M[a] - M["A_M"]
        bs = d[boot].mean(axis=1)
        parts = [f"{n} {d[:,i].mean()*(1 if n=='NDCG' else 100):+.3f} [{np.percentile(bs[:,i],2.5)*(1 if n=='NDCG' else 100):+.3f},"
                 f"{np.percentile(bs[:,i],97.5)*(1 if n=='NDCG' else 100):+.3f}]" for i, n in enumerate(("Gold", "Good", "capture@5", "NDCG", "頭二選有中"))]
        ss = pd.Series(d[:, 1], index=season_of).groupby(level=0).mean()
        print(f"  {a} − A_M：" + "｜".join(parts) + f"｜Good ≥0 季數 {(ss >= 0).sum()}/{len(ss)}")


if __name__ == "__main__":
    main()

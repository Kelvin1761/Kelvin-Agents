"""EXP-20261112-25：用賽果庫 6,000 場估各維度份量，搬落真引擎做外層權重候選。

Kelvin 2026-11-12：「狀態類用少咗、檔位類用多咗 —— 唔好理之前做過咩，搵方法解決」。
真引擎得 449 場有完整評分，判唔到權重改動；之前三次重配權重都係喺同一批場次估、同一批場次判。
呢度用另一批數據（賽果庫、2026-04-01 之前）估，再喺真引擎 389 場判一次 —— 估同判嘅場次唔重疊。

預先登記（跑之前寫死）：
  數據    賽果庫全部賽事；每匹馬特徵只用賽日之前嘅仗（PIT）；只用非初出馬（引擎初出用另一套權重，唔郁）
  估計窗  2019-09 → 2026-03-31（真引擎語料由 2026-04-12 開始，唔重疊）
  對應特徵（每個用引擎同一條式或者最接近嘅代理）：
    stability       0.556 × 近績分（引擎公式）＋ 0.444 × 上名／大敗紀錄分（引擎 _consistency_from_runs，輸距 = 輸頭馬秒 ÷ 0.17）
    trainer_signal  0.55 × 騎師 365 日 PIT 上名率 ＋ 0.45 × 練馬師 365 日 PIT 上名率（各自場內標準化）
    sectional       輸頭馬等級分（近 3 仗平均輸頭馬秒，0.3／0.8／1.3 → +6.52／+1.42／−4／−8）
    race_shape      檔位 PIT 上名率（同場地、同跑道、同路程、同檔位，之前 2 季，向場地路程平均收縮 n／(n＋50)）
    horse_health    休賽日數分（≤21 日 +2、22–45 +1、46–75 0、> 75 −3）
    distance_fit    同場地同路程往績：有上名 +0.43、有跑冇上名 −0.17、冇跑 0
    class_advantage 0.676 × 經驗分（60 ＋ 有港績 4 ＋ 出賽 ≥20 次 4／≤8 次 −2 ＋ 季內上名 ≥3 次 4／季內有跑冇上名 −4）
                    ＋ 0.324 × 負磅分（距全場最重 ≤1 磅 70、≥13 磅 54、其餘 64）
    form_line、trackwork：冇對應，權重唔郁
  模型    場內置中、標準化後 logistic（place）；β_d = 每 SD 嘅 log-odds
  對應度  喺真引擎 449 場（同賽果庫重疊）量場內 Spearman（對應特徵 vs 引擎維度原始分）；< 0.5 嘅維度唔搬，權重唔郁
  搬法    引擎每 SD 影響力 = w_d × SD_d（SD_d = 引擎維度原始分場內 SD，449 場量）
          新 w_d = c × max(β_d, 0) ÷ SD_d；c 令搬嘅維度權重總和唔變
  arm     T100 = 新權重；T50 = 新舊各半。判決：hkjc_eval_harness compare --stage4 fixed_rule（389 場）

用法：PYTHONDONTWRITEBYTECODE=1 python3 docs/experiments/patches/hkjc_weight_transfer.py <concept_dir> <components.jsonl> <out.json>
"""
import glob
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

REPO = Path(__file__).resolve().parents[3]
for p in (REPO, REPO / ".agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts"):
    sys.path.insert(0, str(p))
FIT_END = "2026-04-01"
FORM = {1: 100.0, 2: 85.0, 3: 75.0, 4: 60.0, 5: 60.0}
PTS = np.array([6.52, 1.42, -4.0, -8.0])
DIMS = ("stability", "trainer_signal", "sectional", "race_shape", "horse_health", "distance_fit", "class_advantage")


def raw_extra(root):
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
            rid = "|".join((str(race.get("racedate")), venue, str(race.get("race_no") or key)))
            if rid in seen:
                continue
            seen.add(rid)
            awt = "全天候" in str(race.get("course") or "") or "泥地" in str(race.get("course") or "")
            for r in race["results"]:
                code = re.search(r"\((\w+)\)", str(r.get("horse_name")))
                if code:
                    rows.append({"race": rid, "code": code.group(1), "trainer": str(r.get("trainer") or "").strip(),
                                 "jockey_name": str(r.get("jockey") or "").strip(), "awt": awt, "venue": venue})
    return pd.DataFrame(rows)


def pit_rate(df, who, days=365, min_n=20):
    out = np.full(len(df), np.nan)
    for _name, idx in df.groupby(who).indices.items():
        dts = df.dt.values[idx]
        plc = df.place.values[idx]
        cw = np.concatenate([[0], np.cumsum(plc)])
        lo = np.searchsorted(dts, dts - np.timedelta64(days, "D"), side="left")
        hi = np.searchsorted(dts, dts, side="left")
        n = hi - lo
        out[idx] = np.where(n >= min_n, (cw[hi] - cw[lo]) / np.maximum(n, 1), np.nan)
    return out


def consistency(ranks, margins):
    w = [1.00, 0.85, 0.70, 0.55, 0.45, 0.35]
    tot = sum(w[:len(ranks)])
    close = poor = severe = 0.0
    for i, (rk, m) in enumerate(zip(ranks, margins)):
        if 1 <= rk <= 3:
            close += w[i]
            continue
        if rk <= 5 and m <= 3.0:
            close += w[i] * 0.75
        elif rk <= 7 and m <= 2.5:
            close += w[i] * 0.40
        if rk >= 8 and m >= 5.0:
            poor += w[i]
        elif rk >= 6 and m >= 7.0:
            poor += w[i] * 0.70
        if rk >= 10 and m >= 8.0:
            severe += w[i]
    s = 58 + 18 * close / tot - 14 * poor / tot - 10 * severe / tot
    if len(ranks) >= 5:
        ra, ol = np.mean(ranks[:3]), np.mean(ranks[3:6])
        s += 3 if ra + 1 < ol else (-3 if ra > ol + 1 else 0)
    return s


def build(cdir):
    import wongchoi_paths
    root = Path(wongchoi_paths.HK_RACING)
    D = pd.read_pickle(cdir / "concept_features.pkl")
    X = raw_extra(root)
    D = D.merge(X, on=["race", "code"], how="left")
    D = D.sort_values(["date", "race", "code"]).reset_index(drop=True)
    D["dt"] = pd.to_datetime(D.date)
    D["trate"] = pit_rate(D, "trainer")
    D["jplace"] = pit_rate(D, "jockey")
    g = D.groupby("code")
    # 上名／大敗紀錄分（近 6 仗，新到舊）
    cons = np.full(len(D), np.nan)
    for _c, idx in g.indices.items():
        pos = D.pos.values[idx]
        mar = D.beaten.values[idx] / 0.17
        for k in range(1, len(idx)):
            lo = max(0, k - 6)
            ranks = list(pos[lo:k][::-1])
            margins = list(mar[lo:k][::-1])
            if len(ranks) >= 1:
                cons[idx[k]] = consistency(ranks, margins)
    D["cons"] = cons
    D["stability_a"] = 0.5556 * D.form + 0.4444 * D.cons
    # 段速：輸頭馬等級分
    D["sectional_a"] = np.where(D.M3.notna(), PTS[np.searchsorted([0.3, 0.8, 1.3], D.M3.fillna(0), side="right")], np.nan)
    # 健康：休賽日數分
    d = D.days
    D["horse_health_a"] = np.select([d <= 21, d <= 45, d <= 75, d > 75], [2.0, 1.0, 0.0, -3.0], default=np.nan)
    # 同程：同場地、跑道、路程之前有冇上名
    D["cell"] = D.venue + "|" + D.awt.astype(str) + "|" + D.dist.astype(str)
    key = D.code + "|" + D.cell
    D["_pl"] = (D.pos <= 3).astype(float)
    D["prev_cell_runs"] = D.groupby(key).cumcount()
    D["prev_cell_places"] = D.groupby(key)._pl.cumsum() - D._pl
    D["distance_fit_a"] = np.where(D.prev_cell_runs == 0, 0.0, np.where(D.prev_cell_places > 0, 0.43, -0.17))
    # 檔位 PIT 上名率（之前 2 季，同 cell＋檔位），向 cell 平均收縮
    D["dcell"] = D.cell + "|" + D.draw.astype("Int64").astype(str)
    dr = np.full(len(D), np.nan)
    D["season_i"] = D.season.astype(int)
    for s in sorted(D.season_i.unique()):
        prior = D[(D.season_i < s) & (D.season_i >= s - 2)]
        if prior.empty:
            continue
        cell_mean = prior.groupby("cell")._pl.mean()
        st = prior.groupby("dcell")._pl.agg(["sum", "count"])
        cur = D.season_i == s
        cm = D.loc[cur, "cell"].map(cell_mean)
        su = D.loc[cur, "dcell"].map(st["sum"]).fillna(0)
        n = D.loc[cur, "dcell"].map(st["count"]).fillna(0)
        dr[cur.values] = ((su + 50 * cm) / (n + 50)).values
    D["race_shape_a"] = dr
    # 評分與經驗
    season_runs = D.groupby(["code", "season"]).cumcount()
    season_places = D.groupby(["code", "season"])._pl.cumsum() - D._pl
    cls = 60 + np.where(D.n_runs >= 1, 4, 0) + np.where(D.n_runs >= 20, 4, np.where(D.n_runs <= 8, -2, 0)) \
        + np.where((season_runs > 0) & (season_places >= 3), 4, np.where((season_runs > 0) & (season_places == 0), -4, 0))
    top_w = D.groupby("race").w.transform("max")
    wsc = np.select([top_w - D.w <= 1, top_w - D.w >= 13], [70.0, 54.0], default=64.0)
    D["class_advantage_a"] = 0.676 * cls + 0.324 * wsc
    # 騎練：各自場內標準化再加權
    for c in ("jplace", "trate"):
        m = D.groupby("race")[c].transform("mean")
        s = D.groupby("race")[c].transform("std").replace(0, np.nan)
        D[c + "_z"] = ((D[c] - m) / s).fillna(0.0)
    D["trainer_signal_a"] = 0.55 * D.jplace_z + 0.45 * D.trate_z
    return D


def main():
    cdir, comp_path, out_path = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
    from hkjc_racing_engine import scoring
    D = build(cdir)
    cols = [d + "_a" for d in DIMS]
    F = D[(D.n_runs >= 1) & (D.date < FIT_END)].copy()
    for c in cols:
        v = F[c].fillna(F.groupby("race")[c].transform("mean")).fillna(0.0)
        v = v - v.groupby(F.race).transform("mean")
        F[c + "_z"] = v / v.std()
    zc = [c + "_z" for c in cols]
    races = F.race.unique()
    idx = {r: np.where(F.race.values == r)[0] for r in races}
    fit = lambda d: LogisticRegression(max_iter=3000, C=1e6).fit(d[zc], d.place).coef_[0]
    beta = fit(F)
    rng = np.random.default_rng(0)
    bs = np.array([fit(F.iloc[np.concatenate([idx[r] for r in rng.choice(races, len(races))])]) for _ in range(100)])
    print(f"估計窗：{F.race.nunique()} 場 / {len(F)} 匹（{F.date.min()} → {F.date.max()}，非初出）")
    for d, b, lo, hi in zip(DIMS, beta, np.percentile(bs, 2.5, axis=0), np.percentile(bs, 97.5, axis=0)):
        print(f"  {d:<16} β {b:+.3f} [{lo:+.3f},{hi:+.3f}]  覆蓋 {F[d + '_a'].notna().mean()*100:.0f}%")

    # 真引擎：每個維度場內 SD，同對應特徵嘅對應度
    eng = []
    for line in open(comp_path, encoding="utf-8"):
        r = json.loads(line)
        venue = "HV" if "HappyValley" in r["meeting"] else "ST"
        for h in r["horses"]:
            if h["debut"] or not h.get("m"):
                continue
            eng.append({"race": f"{r['date']}|{venue}|{r['race']}", "n": h["n"], **{f"e_{k}": h["m"].get(k) for k in DIMS}})
    E = pd.DataFrame(eng)
    sd = {d: float((E[f"e_{d}"] - E.groupby("race")[f"e_{d}"].transform("mean")).std()) for d in DIMS}
    # 對應：用馬號對（賽果庫冇馬號 → 用名次唔得；改用 code 經 Logic）
    import wongchoi_paths
    root = Path(wongchoi_paths.HK_RACING)
    codes = []
    for line in open(comp_path, encoding="utf-8"):
        r = json.loads(line)
        lf = root / r["meeting"] / f"Race_{r['race']}_Logic.json"
        horses = json.loads(lf.read_text(encoding="utf-8")).get("horses") or {}
        venue = "HV" if "HappyValley" in r["meeting"] else "ST"
        for num, h in horses.items():
            c = h.get("horse_code") or (h.get("_data") or {}).get("horse_code")
            if c and str(num).isdigit():
                codes.append({"race": f"{r['date']}|{venue}|{r['race']}", "n": int(num), "code": c})
    E = E.merge(pd.DataFrame(codes), on=["race", "n"]).merge(D[["race", "code", *cols]], on=["race", "code"])
    corr = {}
    for d in DIMS:
        s = E[["race", f"e_{d}", d + "_a"]].dropna()
        rr = [x[f"e_{d}"].rank().corr(x[d + "_a"].rank()) for _r, x in s.groupby("race") if len(x) >= 5 and x[f"e_{d}"].nunique() > 1 and x[d + "_a"].nunique() > 1]
        corr[d] = float(np.nanmean(rr)) if rr else float("nan")
    print(f"\n對應度（真引擎 {E.race.nunique()} 場／{len(E)} 匹，場內 Spearman）同引擎場內 SD：")
    for d in DIMS:
        print(f"  {d:<16} ρ {corr[d]:+.2f}  SD {sd[d]:.2f}  現行權重 {scoring.MATRIX_WEIGHTS.get(d, scoring.CENTRED_MATRIX_WEIGHTS.get(d, 0)):.4f}")
    cur = {d: float(scoring.MATRIX_WEIGHTS.get(d, scoring.CENTRED_MATRIX_WEIGHTS.get(d, 0))) for d in DIMS}
    move = [d for d in DIMS if corr[d] >= 0.5 and d in scoring.MATRIX_WEIGHTS]
    raw = {d: max(float(beta[DIMS.index(d)]), 0.0) / sd[d] for d in move}
    c = sum(cur[d] for d in move) / sum(raw.values())
    new = dict(cur)
    for d in move:
        new[d] = c * raw[d]
    half = {d: 0.5 * cur[d] + 0.5 * new[d] for d in DIMS}
    print(f"\n搬嘅維度：{move}（對應度 < 0.5 嘅唔搬）")
    print(f"  {'維度':<16} {'現行':>8} {'T100':>8} {'T50':>8}   現行每SD影響 → T100")
    for d in DIMS:
        print(f"  {d:<16} {cur[d]:>8.4f} {new[d]:>8.4f} {half[d]:>8.4f}   {cur[d]*sd[d]:.3f} → {new[d]*sd[d]:.3f}")
    json.dump({"T100": {d: new[d] for d in move}, "T50": {d: half[d] for d in move}, "beta": dict(zip(DIMS, map(float, beta))),
               "corr": corr, "sd": sd, "current": cur}, open(out_path, "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()

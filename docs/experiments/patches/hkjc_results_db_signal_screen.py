"""EXP-20261113-01：賽果庫概念篩選 —— 六個未試過嘅訊號，喺簡化模型（EXP-11 基礎＋表現數字）之上有冇增量。

Kelvin 2026-11-13：「試埋其他賽果庫概念測試」。
預先登記（跑之前寫死）：
  基礎模型 B = EXP-11 基礎特徵（近績分、日數、出賽數、檔位、負磅相對全場、騎師 PIT 勝率）＋輸頭馬等級＋表現數字（負磅換算，連續）
  六個訊號（全部只用賽日之前資料）：
    F1 步速 × 跑法：近 3 仗第一個沿途位百分位（0 = 領放）；全場預計前置馬數 = 百分位 ≤ 0.25 嘅馬數；
       特徵 = （1 − 跑法百分位）×（前置馬數 − 全季平均）→ 前置馬多時前置馬蝕（預期負）；另報跑法本身
    F2 馬匹體重：今仗體重 − 上仗體重（磅，絕對值），≥ 15 磅旗
    F3 班次升降：上仗班次 − 今仗班次（降班 = 正；只計第一至五班）
    F4 騎師手風：騎師近 30 日上名率 − 近 365 日上名率
    F5 練馬師手風：同上，練馬師
    F6 上仗受阻：上仗競賽事件報告有受阻／受困／受擠迫／失去平衡／出閘笨拙／出閘緩慢／收慢／未能望空
       而且上仗冇入頭三（事件報告由 2024-09 起先有 → 只判 2025/26 起）
  判法 每個訊號：B ＋ 訊號 vs B，逐季 walk-forward；報模型之上係數（每 SD，場次 bootstrap）同 Gold／Good／capture@5／頭二選有中配對差；
       六個係數 p 值 Holm；Holm 後 < 0.05 而且 Gold、Good 都 ≥ 0 先算有料（之後先考慮引擎）
用法：PYTHONDONTWRITEBYTECODE=1 python3 docs/experiments/patches/hkjc_results_db_signal_screen.py <concept_dir>
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
for p in (REPO, REPO / ".agents/skills/shared_racing"):
    sys.path.insert(0, str(p))
PTS = np.array([6.52, 1.42, -4.0, -8.0])
KEYS = ("gold", "good_positional", "top3_capture_at5", "top2_any_hit")
TROUBLE = re.compile(r"受阻|受困|受擠迫|失去平衡|出閘笨拙|出閘緩慢|收慢|未能望空")
CLS = {"第一班": 1, "第二班": 2, "第三班": 3, "第四班": 4, "第五班": 5}


def raw(root):
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
            flat = " ".join(" ".join(map(str, row)) for row in race.get("sectional_times") or [])
            cm = re.search(r"(第[一二三四五]班)", flat)
            inc = str(race.get("incident_report") or "")
            # 事件報告：逐匹「名次 馬號 馬名 (編號) 內容」—— 用編號切
            chunks = {m.group(1): m.group(2) for m in re.finditer(r"\((\w\d{3})\)\s*(.*?)(?=\s\d+\s+\d+\s+\S+\s*\(\w\d{3}\)|$)", inc)}
            n = len(race["results"])
            for r in race["results"]:
                code = re.search(r"\((\w+)\)", str(r.get("horse_name")))
                if not code:
                    continue
                rp = [int(x) for x in str(r.get("running_positions") or "").split() if x.isdigit()]
                rows.append({"race": rid, "code": code.group(1), "trainer": str(r.get("trainer") or "").strip(),
                             "hw": pd.to_numeric(r.get("horse_wt"), errors="coerce"),
                             "first_call": (rp[0] - 1) / max(n - 1, 1) if rp else np.nan,
                             "cls": CLS.get(cm.group(1)) if cm else np.nan,
                             "has_incident": bool(inc), "trouble": bool(TROUBLE.search(chunks.get(code.group(1), "")))})
    return pd.DataFrame(rows)


def rate_diff(df, who):
    out = np.full(len(df), np.nan)
    for _n, idx in df.groupby(who).indices.items():
        dts = df.dt.values[idx]
        pl = df.place.values[idx]
        cw = np.concatenate([[0], np.cumsum(pl)])
        hi = np.searchsorted(dts, dts, side="left")
        lo30 = np.searchsorted(dts, dts - np.timedelta64(30, "D"), side="left")
        lo365 = np.searchsorted(dts, dts - np.timedelta64(365, "D"), side="left")
        n30, n365 = hi - lo30, hi - lo365
        r30 = np.where(n30 >= 8, (cw[hi] - cw[lo30]) / np.maximum(n30, 1), np.nan)
        r365 = np.where(n365 >= 40, (cw[hi] - cw[lo365]) / np.maximum(n365, 1), np.nan)
        out[idx] = r30 - r365
    return out


def main():
    import wongchoi_paths
    from eval_metrics import race_metrics
    root = Path(wongchoi_paths.HK_RACING)
    D = pd.read_pickle(Path(sys.argv[1]) / "concept_features.pkl")
    X = raw(root)
    D = D.merge(X, on=["race", "code"], how="left").sort_values(["date", "race", "code"]).reset_index(drop=True)
    D["dt"] = pd.to_datetime(D.date)
    g = D.groupby("code")
    # F1 跑法 × 預計步速
    fc = [g.first_call.shift(k) for k in (1, 2, 3)]
    cnt = sum(x.notna() for x in fc)
    D["style"] = (sum(x.fillna(0) for x in fc) / cnt.replace(0, np.nan)).where(cnt >= 2)
    D["leaders"] = D.groupby("race").style.transform(lambda s: (s <= 0.25).sum())
    D["F1"] = (1 - D["style"]) * (D.leaders - D.groupby("season").leaders.transform("mean"))
    D["F1_style"] = 1 - D["style"]
    # F2 體重變化
    D["F2"] = ((D.hw - g.hw.shift(1)).abs() >= 15).astype(float).where(g.hw.shift(1).notna() & D.hw.notna())
    # F3 班次升降
    D["F3"] = (g.cls.shift(1) - D.cls)
    # F4／F5 手風
    D["F4"] = rate_diff(D, "jockey")
    D["F5"] = rate_diff(D, "trainer")
    # F6 上仗受阻（上仗有事件報告、冇入頭三）
    prev_trouble = g.trouble.shift(1)
    prev_has = g.has_incident.shift(1)
    prev_pos = g.pos.shift(1)
    D["F6"] = np.where(prev_has == True, ((prev_trouble == True) & (prev_pos > 3)).astype(float), np.nan)  # noqa: E712
    D["log_days"] = np.log1p(D.days.clip(upper=400))
    D["log_runs"] = np.log1p(D.n_runs)
    D["lvl"] = np.where(D.M3.notna(), PTS[np.searchsorted([0.3, 0.8, 1.3], D.M3.fillna(0), side="right")], np.nan)
    base = ["form", "log_days", "log_runs", "draw", "w_rel", "jrate", "lvl", "figW"]
    feats = {"F1 步速×跑法": "F1", "F1b 跑法（前置）": "F1_style", "F2 體重變化 ≥15 磅": "F2", "F3 降班": "F3",
             "F4 騎師手風": "F4", "F5 練馬師手風": "F5", "F6 上仗受阻": "F6"}

    def centred(df, cs):
        out = pd.DataFrame(index=df.index)
        for c in cs:
            out[c + "_miss"] = df[c].isna().astype(float)
            v = df[c].fillna(df.groupby("race")[c].transform("mean")).fillna(0.0)
            out[c] = v - v.groupby(df.race).transform("mean")
        return out

    print(f"賽果庫 {D.race.nunique()} 場；覆蓋：" + "、".join(f"{k.split()[0]} {D[v].notna().mean()*100:.0f}%" for k, v in feats.items()))
    rows_out = []
    for lab, f in feats.items():
        first_test = 2025 if f == "F6" else 2020
        tests = [s for s in sorted(D.season.unique()) if s >= first_test]
        pb, pc = pd.Series(np.nan, index=D.index), pd.Series(np.nan, index=D.index)
        Xb, Xc = centred(D, base), centred(D, base + [f])
        for ts in tests:
            tr, te = (D.season < ts) & (D.season >= (2024 if f == "F6" else 0)), D.season == ts
            pb[te] = LogisticRegression(max_iter=3000, C=1.0).fit(Xb[tr], D.place[tr]).decision_function(Xb[te])
            pc[te] = LogisticRegression(max_iter=3000, C=1.0).fit(Xc[tr], D.place[tr]).decision_function(Xc[te])
        T = D[D.season.isin(tests)]
        mb, mc, races = [], [], []
        for race, s in T.groupby("race"):
            pos = dict(zip(s.code, s.pos))
            top = [c for c, p in pos.items() if p <= 3]
            races.append(race)
            for sc, store in ((pb, mb), (pc, mc)):
                v = sc[s.index].values
                mm = race_metrics(list(s.code.values[np.lexsort((s.code.values, -v))]), top, actual_pos=pos)
                mm["top2_any_hit"] = (mm.get("top2_hits") or 0) >= 1
                store.append([float(mm.get(k) or 0) for k in KEYS])
        d = np.array(mc) - np.array(mb)
        boot = np.random.default_rng(0).integers(0, len(races), (1000, len(races)))
        bs = d[boot].mean(axis=1)
        # 模型之上係數（測試季合併，B 嘅分數做 offset 代理：place ~ zB + 特徵 z）
        Tz = T.assign(zB=pb[T.index], fz=Xc.loc[T.index, f] / (Xc.loc[T.index, f].std() or 1))
        rr = Tz.race.unique()
        ii = {r: np.where(Tz.race.values == r)[0] for r in rr}
        fit = lambda z: LogisticRegression(max_iter=2000, C=1e6).fit(z[["zB", "fz"]], z.place).coef_[0][1]
        rng = np.random.default_rng(1)
        cb = [fit(Tz.iloc[np.concatenate([ii[r] for r in rng.choice(rr, len(rr))])]) for _ in range(300)]
        coef = fit(Tz)
        p = 2 * min(np.mean(np.array(cb) <= 0), np.mean(np.array(cb) >= 0))
        rows_out.append((lab, len(races), coef, np.percentile(cb, 2.5), np.percentile(cb, 97.5), max(p, 1 / 300),
                         *[(d[:, i].mean() * 100, np.percentile(bs[:, i], 2.5) * 100, np.percentile(bs[:, i], 97.5) * 100) for i in range(4)]))
    order = sorted(range(len(rows_out)), key=lambda i: rows_out[i][5])
    holm = {}
    for rank, i in enumerate(order):
        holm[i] = min(1.0, rows_out[i][5] * (len(rows_out) - rank))
    print("\n訊號｜場數｜模型之上係數（每 SD）｜Holm p｜Gold｜Good｜capture@5｜頭二選有中（候選 − B，pp）")
    for i, r in enumerate(rows_out):
        fmt = lambda t: f"{t[0]:+.2f} [{t[1]:+.2f},{t[2]:+.2f}]"
        print(f"  {r[0]:<16} {r[1]:>5}｜{r[2]:+.3f} [{r[3]:+.3f},{r[4]:+.3f}]｜{holm[i]:.3f}｜{fmt(r[6])}｜{fmt(r[7])}｜{fmt(r[8])}｜{fmt(r[9])}")


if __name__ == "__main__":
    main()

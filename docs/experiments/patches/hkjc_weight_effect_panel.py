"""EXP-20261112-06：負磅對表現嘅直接量度（賽果庫 2019 起全部賽事），唔預設「加磅＝近況好」或者「負磅抵銷評分」。

用法：
  PYTHONDONTWRITEBYTECODE=1 python3 docs/experiments/patches/hkjc_weight_effect_panel.py <base.jsonl>

一、物理效應：完成時間 ~ 馬匹×馬季 FE + 賽事 FE + 負磅。賽事 FE 吸收場地快慢、步速、班次；馬匹 FE 吸收能力。
    因為量嘅係**時間**唔係名次，對手強弱唔會直接影響（只會經步速，已被賽事 FE 吸收）。
二、「加磅＝近況好」驗證：有評分嘅子集（賽績檔＋Logic rating_trend）再控制當仗評分，睇負磅係數郁唔郁。
三、評分每分值幾多、負磅抵銷幾多：讓磅賽場內 完成時間 ~ 賽事 FE + 評分。
四、近 6 仗逐仗表現數字（時間 − 賽事 FE）＋當時負磅 → 今仗上名：結果反推「每磅值幾多秒」，同物理值比。
"""
import glob
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

REPO = Path(__file__).resolve().parents[3]
for p in (REPO / ".agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts",
          REPO / ".agents/skills/hkjc_racing/hkjc_reflector/scripts", REPO, Path(__file__).resolve().parent):
    sys.path.insert(0, str(p))
from hkjc_weight_history_screen import HANDICAP, boot, formguide  # noqa: E402


def secs(t):
    m = re.match(r"(?:(\d+):)?(\d+)\.(\d+)$", str(t).strip())
    return (int(m.group(1) or 0) * 60 + int(m.group(2)) + int(m.group(3)) / 100) if m else None


def load_results(root):
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
            ct = race.get("cumulative_times") or []
            for r in race["results"]:
                t, w = secs(r.get("finish_time")), r.get("actual_wt")
                if t is None or not str(w).isdigit() or not str(r.get("pos")).strip().isdigit():
                    continue
                rows.append({"race": "|".join(rid), "date": rid[0], "horse": re.sub(r"\(.*", "", r["horse_name"]).strip(),
                             "code": (re.search(r"\((\w+)\)", r["horse_name"]) or [None, None])[1],
                             "w": int(w), "time": t, "pos": int(r["pos"]), "awt": "全天候" in str(race.get("course") or ""),
                             "odds": pd.to_numeric(r.get("win_odds"), errors="coerce")})
    return pd.DataFrame(rows)


def twoway(df, y, xs, g1, g2, iters=60):
    d = df[[y, *xs]].astype(float).copy()
    for _ in range(iters):
        for g in (g1, g2):
            d -= d.groupby(df[g].values).transform("mean")
    return d


def ols_cluster(dm, y, xs, cluster):
    X, Y = dm[xs].values, dm[y].values
    b = np.linalg.lstsq(X, Y, rcond=None)[0]
    e = Y - X @ b
    bread = np.linalg.inv(X.T @ X)
    s = pd.DataFrame(X * e[:, None]).groupby(np.asarray(cluster)).sum().values
    se = np.sqrt(np.diag(bread @ (s.T @ s) @ bread))
    return b, se


def show(lab, b, se, n, unit="s"):
    print(f"  {lab}: 每磅 {b:+.4f}{unit} [{b-1.96*se:+.4f},{b+1.96*se:+.4f}]（10 磅 = {b*10:+.3f}{unit}；n={n}）")


def main():
    import wongchoi_paths
    root = Path(wongchoi_paths.HK_RACING)
    R = load_results(root)
    dist = {}
    master = pd.read_csv(root / "HKJC_Race_Results_Database/comprehensive_stats/all_race_results_master.csv", low_memory=False)
    R["win_t"] = R.groupby("race").time.transform("min")
    R = R[R.time - R.win_t <= 3.0].copy()            # 大敗／收慢嘅馬唔代表能力
    # 路程：由頭馬時間推（賽果庫舊季冇路程欄）
    def bucket(t):
        for d, lo, hi in ((1000, 54, 60), (1200, 66.5, 73.5), (1400, 79, 87), (1600, 91, 98.2), (1650, 98.2, 104.5),
                          (1800, 104.5, 113), (2000, 118, 127), (2200, 131, 141), (2400, 144, 156)):
            if lo <= t < hi:
                return d
        return None
    R["dist"] = R.win_t.map(bucket)
    R = R.dropna(subset=["dist"])
    R["season"] = R.date.map(lambda s: int(s[:4]) - (int(s[5:7]) < 8))
    R["hs"] = R.horse + "|" + R.season.astype(str)
    for _ in range(3):
        R = R[R.groupby("hs").race.transform("count") >= 2]
        R = R[R.groupby("race").hs.transform("count") >= 4]
    print(f"賽果庫 {R.race.nunique()} 場 / {len(R)} 匹次 / {R.horse.nunique()} 匹馬（{R.date.min()} → {R.date.max()}）")

    print("\n== 一、負磅對完成時間（馬匹×馬季 FE ＋ 賽事 FE；SE 按馬匹 cluster）==")
    dm = twoway(R, "time", ["w"], "hs", "race")
    b, se = ols_cluster(dm, "time", ["w"], R.horse.values)
    show("全部路程（秒）", b[0], se[0], len(R))
    beta = {}
    for lab, sel in (("1000–1200m", R.dist <= 1200), ("1400m", R.dist == 1400), ("1600–1650m", R.dist.between(1600, 1650)), ("≥1800m", R.dist >= 1800)):
        s = R[sel]
        for _ in range(3):
            s = s[s.groupby("hs").race.transform("count") >= 2]
            s = s[s.groupby("race").hs.transform("count") >= 4]
        d2 = twoway(s, "time", ["w"], "hs", "race")
        bb, ss = ols_cluster(d2, "time", ["w"], s.horse.values)
        show(lab, bb[0], ss[0], len(s))
        beta[lab] = bb[0]
    R["tkm"] = R.time / (R.dist / 1000.0)
    dm = twoway(R, "tkm", ["w"], "hs", "race")
    bk, sk = ols_cluster(dm, "tkm", ["w"], R.horse.values)
    print(f"  每公里計：每磅 {bk[0]:+.5f}s/km [{bk[0]-1.96*sk[0]:+.5f},{bk[0]+1.96*sk[0]:+.5f}] → 1200m {bk[0]*1.2:+.4f}s、1600m {bk[0]*1.6:+.4f}s、2000m {bk[0]*2:+.4f}s；"
          f"一個馬位 ≈ 0.16s → 10 磅 ≈ {bk[0]*1.4*10/0.16:.1f} 個馬位（1400m）")
    # 馬匹 FE 唔分馬季（對照）
    dm = twoway(R, "tkm", ["w"], "horse", "race")
    b2, s2 = ols_cluster(dm, "tkm", ["w"], R.horse.values)
    print(f"  對照：馬匹 FE 唔分馬季 {b2[0]:+.5f}s/km [{b2[0]-1.96*s2[0]:+.5f},{b2[0]+1.96*s2[0]:+.5f}]")

    # 賽事效應（之後砌逐仗表現數字用）：time_km − β·w − 馬匹效應 嘅賽事平均
    R["adj"] = R.tkm - bk[0] * R.w
    a = R[["adj"]].copy()
    hfe = pd.Series(0.0, index=R.index)
    rfe = pd.Series(0.0, index=R.index)
    for _ in range(60):
        hfe = (R.adj - rfe).groupby(R.hs.values).transform("mean")
        rfe = (R.adj - hfe).groupby(R.race.values).transform("mean")
    R["rfe"] = rfe.values
    R["fig"] = -(R.tkm - R.rfe)            # 表現數字（s/km，越大越快），**未**扣負磅
    R["fig"] -= R.fig.mean()

    print("\n== 二、「加磅＝近況好」驗證：控制當仗官方評分之後，負磅係數有冇變 ==")
    # 當仗評分：Logic rating_trend（最新 → 最舊）對近 6 仗；賽績檔畀負磅同日期
    rat = {}
    ok = bad = 0
    for md in sorted(p for p in root.iterdir() if re.match(r"\d{4}-\d{2}-\d{2}_", p.name)):
        day = datetime.strptime(md.name[:10], "%Y-%m-%d").date()
        for lf in md.glob("Race_*_Logic.json"):
            rn = int(re.search(r"Race_(\d+)_", lf.name).group(1))
            _h, fg = formguide(md, rn)
            try:
                horses = json.loads(lf.read_text(encoding="utf-8")).get("horses") or {}
            except ValueError:
                continue
            for num, h in horses.items():
                d = h.get("_data") or {}
                e = fg.get(int(num)) if str(num).isdigit() else None
                tr = [int(x) for x in re.findall(r"\d+", str(d.get("rating_trend") or "").split(" → ")[0].replace("→", " "))]
                if not e or not tr:
                    continue
                runs = sorted([x for x in e["runs"] if x[0] < day], reverse=True)[:6]
                cur, chg = d.get("current_rating"), d.get("rating_change")
                if isinstance(cur, (int, float)) and isinstance(chg, (int, float)):
                    ok += tr[0] == cur - chg
                    bad += tr[0] != cur - chg
                for (rd, _w, _p, _l), r in zip(runs, tr):
                    rat[(h.get("horse_name"), rd.isoformat())] = r
    print(f"  rating_trend 方向核對（第一格 = 今仗評分 − 變動）：{ok} 啱 / {bad} 唔啱")
    R["rating"] = [rat.get((h, d)) for h, d in zip(R.horse, R.date)]
    S = R.dropna(subset=["rating"]).copy()
    for _ in range(3):
        S = S[S.groupby("hs").race.transform("count") >= 2]
    S["y"] = S.tkm - S.rfe                  # 用全庫估嘅賽事效應，只留馬匹 FE
    for lab, xs in (("唔控制評分", ["w"]), ("控制當仗評分", ["w", "rating"])):
        d = S[["y", *xs]].astype(float)
        d = d - d.groupby(S.hs.values).transform("mean")
        bb, ss = ols_cluster(d, "y", xs, S.horse.values)
        extra = f"；評分每分 {bb[1]:+.5f}s/km [{bb[1]-1.96*ss[1]:+.5f},{bb[1]+1.96*ss[1]:+.5f}]" if len(xs) > 1 else ""
        print(f"  {lab}: 負磅每磅 {bb[0]:+.5f}s/km [{bb[0]-1.96*ss[0]:+.5f},{bb[0]+1.96*ss[0]:+.5f}]{extra}（n={len(S)}，{S.horse.nunique()} 匹）")
    S = S.sort_values(["horse", "date"])
    S["dw"] = S.groupby("horse").w.diff()
    S["dr"] = S.groupby("horse").rating.diff()
    S["dfig"] = S.groupby("horse").fig.diff()
    S["prev_pos"] = S.groupby("horse").pos.shift()
    c = S.dropna(subset=["dw", "dr"])
    print(f"  連續兩仗：corr(負磅變動, 評分變動) = {c.dw.corr(c.dr):+.2f}；負磅加 ≥5 磅嗰批：評分升咗 {(c[c.dw >= 5].dr > 0).mean()*100:.0f}%、冇變 {(c[c.dw >= 5].dr == 0).mean()*100:.0f}%、跌咗 {(c[c.dw >= 5].dr < 0).mean()*100:.0f}%；"
          f"上仗跑頭三 {(c[c.dw >= 5].prev_pos <= 3).mean()*100:.0f}%（n={int((c.dw >= 5).sum())}）")
    for lab, s in (("加 ≥5 磅而評分升咗（贏馬加分）", c[(c.dw >= 5) & (c.dr > 0)]), ("加 ≥5 磅而評分冇升（降班／換騎師）", c[(c.dw >= 5) & (c.dr <= 0)]),
                   ("負磅 ±2", c[c.dw.abs() <= 2]), ("減 ≥5 磅", c[c.dw <= -5])):
        print(f"    {lab:<24} n={len(s):>4}  表現數字變動 {s.dfig.mean():+.4f}s/km（1400m ≈ {s.dfig.mean()*1.4/0.16:+.2f} 個馬位）")

    print("\n== 三、評分每分值幾多、負磅抵銷幾多（讓磅賽場內）==")
    cards = []
    import hkjc_auto_orchestrator as orch
    for line in open(sys.argv[1], encoding="utf-8"):
        x = json.loads(line)
        if "error" in x or not x.get("horses"):
            continue
        md = root / x["meeting"]
        path = orch._racecard_path_for_logic(md / f"Race_{x['race']}_Logic.json", x["race"])
        if not path or not Path(path).exists():
            continue
        cls, info = orch._parse_racecard_meta(Path(path).read_text(encoding="utf-8"))
        if not any(c in str(cls) for c in HANDICAP):
            continue
        logic = json.loads((md / f"Race_{x['race']}_Logic.json").read_text(encoding="utf-8")).get("horses") or {}
        venue = "HV" if "HappyValley" in x["meeting"] else "ST"
        for k, e in info.items():
            if str(k).isdigit() and e.get("rating") is not None and e.get("weight") is not None and str(k) in logic:
                cards.append({"race": f"{x['date']}|{venue}|{x['race']}", "horse": logic[str(k)].get("horse_name"),
                              "rating": int(e["rating"]), "declared": int(e["weight"]) + int(e.get("jockey_claim") or 0),
                              "claim": int(e.get("jockey_claim") or 0)})
    C = pd.DataFrame(cards).merge(R[["race", "horse", "tkm", "w", "dist", "pos"]], on=["race", "horse"])
    C = C[C.groupby("race").horse.transform("count") >= 5]
    d = C[["tkm", "rating", "declared", "claim"]].astype(float)
    d = d - d.groupby(C.race.values).transform("mean")
    bb, ss = ols_cluster(d, "tkm", ["rating"], C.race.values)
    net = bb[0]
    print(f"  {C.race.nunique()} 場 / {len(C)} 匹；場內 corr(評分, 宣佈負磅) = {d.rating.corr(d.declared):+.3f}")
    print(f"  場內：評分每高 1 分（同時多負約 1 磅），完成時間 {net:+.5f}s/km [{net-1.96*ss[0]:+.5f},{net+1.96*ss[0]:+.5f}]  ← 負數 = 高評分馬負重咗仍然快啲")
    phys = bk[0]
    print(f"  物理：多負 1 磅慢 {phys:+.5f}s/km。所以評分 1 分嘅真實能力 ≈ {-(net - phys):.5f}s/km，負磅攞返 {phys:.5f}s/km"
          f" → 負磅抵銷咗 {phys / (phys - net) * 100:.0f}% 嘅評分優勢")
    bb, ss = ols_cluster(d, "tkm", ["rating", "claim"], C.race.values)
    print(f"  見習減磅（評分不變，實際負磅減 1 磅）：{-bb[1]:+.5f}s/km [{-bb[1]-1.96*ss[1]:+.5f},{-bb[1]+1.96*ss[1]:+.5f}]  ← 物理值係 {phys:+.5f}；差額 = 見習騎師本身嘅差距")

    print("\n== 四、近 6 仗逐仗表現數字＋當時負磅 → 今仗上名 ==")
    key = {(r, h): (f, w, d) for r, h, f, w, d in zip(R.race, R.horse, R.fig, R.w, R.date)}
    hist = {h: g.sort_values("date")[["date", "fig", "w"]].values for h, g in R.groupby("horse")}
    rows = []
    for line in open(sys.argv[1], encoding="utf-8"):
        x = json.loads(line)
        if "error" in x or not x.get("horses"):
            continue
        if set(x.get("meeting_dead_fields") or []) - {"track_going_score", "trackwork_trend_score"}:
            continue
        md = root / x["meeting"]
        head, fg = formguide(md, int(x["race"]))
        if not fg or not any(c in head for c in HANDICAP):
            continue
        logic = json.loads((md / f"Race_{x['race']}_Logic.json").read_text(encoding="utf-8")).get("horses") or {}
        for h in x["horses"]:
            e, name = fg.get(h["n"]), (logic.get(str(h["n"])) or {}).get("horse_name")
            if h["pos"] is None or not e or name not in hist:
                continue
            past = [r for r in hist[name] if r[0] < x["date"]][-6:]
            if len(past) < 2:
                continue
            f = np.array([r[1] for r in past], float)
            w = np.array([r[2] for r in past], float)
            wt = 1.0 / np.arange(len(past), 0, -1)       # 越近越重（同近績分一樣 1/k）
            rows.append({"race": f"{x['meeting']}|{x['race']}", "place": float(h["pos"] <= 3), "raw": h["raw"], "today": e["today"],
                         "F": float((f * wt).sum() / wt.sum()), "Wp": float((w * wt).sum() / wt.sum()),
                         "Fbest": float(f.max()), "Wbest": float(w[f.argmax()]), "n": len(past)})
    D = pd.DataFrame(rows)
    g = D.groupby("race")
    for c in ("raw", "F", "today", "Wp", "Fbest", "Wbest"):
        D[c + "_c"] = D[c] - g[c].transform("mean")
    D["zraw"] = D.raw_c / g.raw.transform("std").replace(0, np.nan)
    D["dW"] = D.today_c - D.Wp_c            # 相對全場：今仗負磅 − 近 6 仗（加權）負磅
    D["dWbest"] = D.today_c - D.Wbest_c
    D = D.dropna(subset=["zraw"]).reset_index(drop=True)
    print(f"  {D.race.nunique()} 場 / {len(D)} 匹（有 ≥2 仗表現數字）；F = 近 6 仗表現數字加權平均（s/km，未扣負磅）")

    def fit(cols, data=D):
        def f(z):
            return LogisticRegression(max_iter=3000, C=1e6).fit(z[cols], z.place).coef_[0]
        b0 = f(data)
        races = data.race.unique()
        idx = {r: np.where(data.race.values == r)[0] for r in races}
        rng = np.random.default_rng(0)
        bs = np.array([f(data.iloc[np.concatenate([idx[r] for r in rng.choice(races, len(races))])]) for _ in range(600)])
        return b0, bs

    def report(lab, cols, fcol, wcol):
        b0, bs = fit(cols)
        i, j = cols.index(fcol), cols.index(wcol)
        ratio, rb = -b0[j] / b0[i], -bs[:, j] / bs[:, i]
        print(f"  {lab}")
        print(f"    表現數字（每 s/km）{b0[i]:+.2f} [{np.percentile(bs[:, i], 2.5):+.2f},{np.percentile(bs[:, i], 97.5):+.2f}]；"
              f"負磅差（每磅）{b0[j]:+.4f} [{np.percentile(bs[:, j], 2.5):+.4f},{np.percentile(bs[:, j], 97.5):+.4f}]")
        print(f"    → 結果反推：每多 1 磅 = 表現數字少 {ratio:+.5f}s/km [{np.percentile(rb, 2.5):+.5f},{np.percentile(rb, 97.5):+.5f}]（物理值 {phys:+.5f}）")

    report("A. 只有表現數字＋「今仗比近 6 仗重幾多」（唔計模型）", ["F_c", "dW"], "F_c", "dW")
    report("B. 最好一仗嘅表現數字＋「今仗比嗰仗重幾多」", ["Fbest_c", "dWbest"], "Fbest_c", "dWbest")
    report("C. 加埋今仗負磅水平（= 評分）做控制", ["F_c", "dW", "today_c"], "F_c", "dW")
    report("D. 現行模型之上", ["zraw", "F_c", "dW"], "F_c", "dW")
    D["Fadj"] = D.F_c - phys * D.dW          # 按物理值將近 6 仗換算做今仗負磅
    from sklearn.metrics import roc_auc_score

    def auc(col):
        vals = []
        for _r, s in D.groupby("race"):
            if 0 < s.place.sum() < len(s):
                vals.append(roc_auc_score(s.place, s[col]))
        return float(np.mean(vals))
    print(f"  場內 AUC：模型 {auc('zraw'):.4f}｜表現數字（未調）{auc('F_c'):.4f}｜按物理值調到今仗負磅 {auc('Fadj'):.4f}"
          f"｜調 2 倍 {auc_k(D, phys, 2):.4f}｜調 4 倍 {auc_k(D, phys, 4):.4f}｜反方向 {auc_k(D, phys, -2):.4f}")
    D.to_csv(Path(sys.argv[1]).with_name("weight_panel_fig.csv"), index=False)


def auc_k(D, phys, k):
    from sklearn.metrics import roc_auc_score
    v = D.F_c - k * phys * D.dW
    vals = []
    for _r, idx in D.groupby("race").groups.items():
        p = D.place.loc[idx]
        if 0 < p.sum() < len(p):
            vals.append(roc_auc_score(p, v.loc[idx]))
    return float(np.mean(vals))


if __name__ == "__main__":
    main()

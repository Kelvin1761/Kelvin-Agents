"""EXP-20261112-06 第二部分：point-in-time 表現數字（逐賽日只用之前嘅賽果重估）＋負磅調整 → 排名 overlay。

點解要 PIT：`hkjc_weight_effect_panel.py` 嘅賽事效應係用成個賽果庫（包括未來、包括今仗）估，有前視。
呢度每個評估賽日 D 只用 date < D 嘅賽果重估馬匹效應同賽事效應；負磅係數 β 只用評估窗之前（< 2026-05-03）估。

預先登記（跑之前寫死）：
  表現數字  fig = −(完成時間/公里 − 賽事效應)，賽事效應由「時間/公里 − β·負磅」對 馬匹×馬季＋賽事 兩組效應交替估
  F         近 6 仗（最少 2 仗）fig 加權平均，權重 1/k（越近越重，同近績分一樣）；Wp = 同權重嘅當時負磅平均
  U（唔理負磅） F 場內置中
  W（按今仗負磅換算） [F − β·(今仗負磅 − Wp)] 場內置中
  overlay   新 raw = raw + k × 特徵；k ∈ {4, 8, 12, 16} raw 分／(s/km)；冇表現數字嘅馬 +0
  切法      dev < 2026-09-06 ≤ holdout
  揀法      只睇 dev、只睇 W：Gold、Good 都 ≥0 嘅 k 入面揀 Gold+Good 最大，打和揀細 k；冇合格 = REJECT，唔開 holdout
  判決      W(k*) 喺 holdout 用 harness compare（fixed_rule）判一次；U(k*) 同一個 k 報出嚟做 ablation（負磅嗰部分嘅邊際貢獻）

用法：
  PYTHONDONTWRITEBYTECODE=1 python3 docs/experiments/patches/hkjc_weight_fig_pit.py <base.jsonl> <outdir>
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

REPO = Path(__file__).resolve().parents[3]
for p in (REPO / ".agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts",
          REPO / ".agents/skills/hkjc_racing/hkjc_reflector/scripts",
          REPO / ".agents/skills/shared_racing", REPO, Path(__file__).resolve().parent):
    sys.path.insert(0, str(p))
from hkjc_weight_effect_panel import load_results, ols_cluster, twoway  # noqa: E402
from hkjc_weight_history_screen import HANDICAP, formguide  # noqa: E402

HARNESS = REPO / ".agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_eval_harness.py"
RANKING = ("top3_capture_at5", "ndcg_at5", "competitive_recall_at5")
GRID = (4.0, 8.0, 12.0, 16.0)
SPLIT, EVAL_START = "2026-09-06", "2026-05-03"
BUCKETS = ((1000, 54, 60), (1200, 66.5, 73.5), (1400, 79, 87), (1600, 91, 98.2), (1650, 98.2, 104.5),
           (1800, 104.5, 113), (2000, 118, 127), (2200, 131, 141), (2400, 144, 156))


def prep(root):
    R = load_results(root)
    R["win_t"] = R.groupby("race").time.transform("min")
    R = R[R.time - R.win_t <= 3.0].copy()
    R["dist"] = R.win_t.map(lambda t: next((d for d, lo, hi in BUCKETS if lo <= t < hi), None))
    R = R.dropna(subset=["dist"])
    R["season"] = R.date.map(lambda s: int(s[:4]) - (int(s[5:7]) < 8))
    R["hs"] = R.horse + "|" + R.season.astype(str)
    R["tkm"] = R.time / (R.dist / 1000.0)
    return R.reset_index(drop=True)


def figs_asof(R, day, beta, iters=40):
    s = R[R.date < day]
    adj = (s.tkm - beta * s.w)
    hfe = pd.Series(0.0, index=s.index)
    rfe = pd.Series(0.0, index=s.index)
    for _ in range(iters):
        hfe = (adj - rfe).groupby(s.hs.values).transform("mean")
        rfe = (adj - hfe).groupby(s.race.values).transform("mean")
    fig = -(s.tkm - rfe)
    fig -= fig.mean()
    out = {}
    for h, d, f, w in zip(s.horse.values, s.date.values, fig.values, s.w.values):
        out.setdefault(h, []).append((d, f, w))
    return out


def compare(base, cand, out):
    r = subprocess.run([sys.executable, str(HARNESS), "compare", str(base), str(cand), "--stage4", "fixed_rule",
                        "--leakage-audit-passed", "--out", str(out)], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(r.stderr[-2000:])
    return json.loads(Path(out).read_text(encoding="utf-8"))


def line(rep):
    d = rep["verdict"]["detail"]
    g, q, n, c = d["primary"]["gold"], d["primary"]["good_positional"], d["ranking"]["ndcg_at5"], d["ranking"]["top3_capture_at5"]
    return (f"{rep['races']:>4} 場 郁 {rep['races_with_ranking_change']:>3}｜Gold {g['delta']*100:+.2f} [{g['ci_low']*100:+.2f},{g['ci_high']*100:+.2f}]"
            f"｜Good {q['delta']*100:+.2f} [{q['ci_low']*100:+.2f},{q['ci_high']*100:+.2f}]"
            f"｜capture@5 {c['delta']*100:+.2f} [{c['ci_low']*100:+.2f},{c['ci_high']*100:+.2f}]"
            f"｜NDCG {n['delta']:+.4f} [{n['ci_low']:+.4f},{n['ci_high']:+.4f}]｜{rep['verdict']['verdict']}/{rep['verdict']['reason']}"), g["delta"], q["delta"]


def main():
    import wongchoi_paths
    from eval_metrics import race_metrics
    root = Path(wongchoi_paths.HK_RACING)
    out = Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    R = prep(root)
    pre = R[R.date < EVAL_START]
    for _ in range(3):
        pre = pre[pre.groupby("hs").race.transform("count") >= 2]
        pre = pre[pre.groupby("race").hs.transform("count") >= 4]
    b, se = ols_cluster(twoway(pre, "tkm", ["w"], "hs", "race"), "tkm", ["w"], pre.horse.values)
    beta = float(b[0])
    print(f"β（只用 {EVAL_START} 之前，{len(pre)} 匹次）：每磅 {beta:+.5f}s/km [{beta-1.96*se[0]:+.5f},{beta+1.96*se[0]:+.5f}]")

    rows = [json.loads(x) for x in open(sys.argv[1], encoding="utf-8")]
    rows = [r for r in rows if "error" not in r and r.get("horses")]
    feats, recs, cache = {}, [], {}
    for r in rows:
        md = root / r["meeting"]
        head, fg = formguide(md, int(r["race"]))
        logic = json.loads((md / f"Race_{r['race']}_Logic.json").read_text(encoding="utf-8")).get("horses") or {}
        if r["date"] not in cache:
            cache.clear()
            cache[r["date"]] = figs_asof(R, r["date"], beta)
        hist = cache[r["date"]]
        got = {}
        for h in r["horses"]:
            e, name = fg.get(h["n"]) if fg else None, (logic.get(str(h["n"])) or {}).get("horse_name")
            past = sorted(hist.get(name) or [])[-6:]
            if not e or len(past) < 2:
                continue
            f = np.array([x[1] for x in past]); w = np.array([x[2] for x in past], float)
            wt = 1.0 / np.arange(len(past), 0, -1)
            F, Wp = float((f * wt).sum() / wt.sum()), float((w * wt).sum() / wt.sum())
            got[h["n"]] = (F, F - beta * (e["today"] - Wp), e["today"] - Wp)
        if len(got) >= 2:
            mu = np.mean([v[0] for v in got.values()]), np.mean([v[1] for v in got.values()])
            feats[(r["meeting"], r["race"])] = {n: (v[0] - mu[0], v[1] - mu[1]) for n, v in got.items()}
            hc = any(c in head for c in HANDICAP)
            sd = np.std([h["raw"] for h in r["horses"]]) or np.nan
            mraw = np.mean([h["raw"] for h in r["horses"]])
            for h in r["horses"]:
                if h["n"] in got and h["pos"] is not None:
                    recs.append({"race": f"{r['meeting']}|{r['race']}", "date": r["date"], "handicap": hc, "place": float(h["pos"] <= 3),
                                 "zraw": (h["raw"] - mraw) / sd, "U": got[h["n"]][0] - mu[0], "W": got[h["n"]][1] - mu[1], "dW": got[h["n"]][2]})
    D = pd.DataFrame(recs).dropna()
    D["dWc"] = D.dW - D.groupby("race").dW.transform("mean")
    print(f"PIT 表現數字：{D.race.nunique()} 場 / {len(D)} 匹；U 場內 SD {D.U.std():.3f} s/km")

    def auc(v):
        vals = [roc_auc_score(s.place, s[v]) for _r, s in D.assign(_v=0).groupby("race") if 0 < s.place.sum() < len(s)]
        return float(np.mean(vals))
    D["W2"] = D.U - 2 * beta * D.dWc
    D["Wr"] = D.U + 2 * beta * D.dWc
    print(f"場內 AUC（PIT）：模型 {auc('zraw'):.4f}｜U 未調 {auc('U'):.4f}｜W 按 β 調 {auc('W'):.4f}｜調 2 倍 {auc('W2'):.4f}｜反方向 {auc('Wr'):.4f}")

    def fit(cols):
        def f(z):
            return LogisticRegression(max_iter=3000, C=1e6).fit(z[cols], z.place).coef_[0]
        races = D.race.unique()
        idx = {r: np.where(D.race.values == r)[0] for r in races}
        rng = np.random.default_rng(0)
        bs = np.array([f(D.iloc[np.concatenate([idx[r] for r in rng.choice(races, len(races))])]) for _ in range(500)])
        return f(D), bs
    b0, bs = fit(["zraw", "U", "dWc"])
    print(f"模型之上（PIT）：表現數字 {b0[1]:+.2f} [{np.percentile(bs[:,1],2.5):+.2f},{np.percentile(bs[:,1],97.5):+.2f}]；"
          f"負磅差每磅 {b0[2]:+.4f} [{np.percentile(bs[:,2],2.5):+.4f},{np.percentile(bs[:,2],97.5):+.4f}]；"
          f"反推每磅 {-b0[2]/b0[1]:+.5f}s/km [{np.percentile(-bs[:,2]/bs[:,1],2.5):+.5f},{np.percentile(-bs[:,2]/bs[:,1],97.5):+.5f}]（β {beta:+.5f}）")
    b0, bs = fit(["zraw", "W"])
    print(f"模型之上（PIT）：W {b0[1]:+.2f} [{np.percentile(bs[:,1],2.5):+.2f},{np.percentile(bs[:,1],97.5):+.2f}]；zraw {b0[0]:+.2f}")

    def rescore(row, k, which):
        f = feats.get((row["meeting"], row["race"]), {})
        horses = row["horses"]
        order = sorted(horses, key=lambda h: (-(h["raw"] + k * (f[h["n"]][which] if h["n"] in f else 0.0)), h["n"]))
        picks = [h["n"] for h in order]
        pos = {h["n"]: h["pos"] for h in horses if h["pos"] is not None}
        m = race_metrics(picks, [n for n, p in pos.items() if p <= 3], actual_pos=pos)
        m["mean_top3_model_rank"] = m.get("top3_mean_model_rank")
        new = {a: v for a, v in row.items() if a != "horses"}
        new["picks"] = picks
        for key in ("gold", "gold_strict", "good_positional", "champion", *RANKING, "mean_top3_model_rank"):
            new[key] = m.get(key)
        return new

    for r in rows:
        z = rescore(r, 0.0, 0)
        if any(z[a] != r[a] for a in ("picks", "gold", "good_positional", *RANKING)):
            raise SystemExit(f"k=0 重現唔到 baseline：{r['meeting']} R{r['race']}")
    print("k=0 逐場重現 baseline：OK")

    def dump(name, sel, k=0.0, which=0):
        p = out / f"{name}.jsonl"
        with open(p, "w", encoding="utf-8") as f:
            for r in rows:
                if sel(r):
                    f.write(json.dumps(rescore(r, k, which), ensure_ascii=False) + "\n")
        return p
    parts = {"dev": lambda r: r["date"] < SPLIT, "holdout": lambda r: r["date"] >= SPLIT, "all": lambda r: True}
    base = {n: dump(f"base_{n}", s) for n, s in parts.items()}
    res = {}
    for k in GRID:
        for which, lab in ((1, "W"), (0, "U")):
            for n, s in parts.items():
                res[(lab, k, n)] = compare(base[n], dump(f"{lab}{k}_{n}", s, k, which), out / f"{lab}{k}_{n}.cmp.json")
    print("\n== dev：W（按今仗負磅換算）==")
    ok = []
    for k in GRID:
        text, g, q = line(res[("W", k, "dev")])
        print(f"  k={k:>4}: {text}")
        if g >= 0 and q >= 0:
            ok.append((-(g + q), k))
    print("== dev：U（唔理負磅，ablation）==")
    for k in GRID:
        print(f"  k={k:>4}: {line(res[('U', k, 'dev')])[0]}")
    if not ok:
        print("\ndev 冇一個 k 合格 → REJECT，holdout 唔開。")
        return
    pick = sorted(ok)[0][1]
    print(f"\n揀中 k={pick}")
    print("== holdout（只判 W，k=揀中；U 同 k 做 ablation）==")
    print(f"  W k={pick}: {line(res[('W', pick, 'holdout')])[0]}")
    print(f"  U k={pick}: {line(res[('U', pick, 'holdout')])[0]}")
    print("== 全語料（參考）==")
    for k in GRID:
        print(f"  W k={k:>4}: {line(res[('W', k, 'all')])[0]}")
        print(f"  U k={k:>4}: {line(res[('U', k, 'all')])[0]}")
    rep = res[("W", pick, "all")]
    print("分層（W，全語料，k=揀中）：", json.dumps(rep["cohorts"], ensure_ascii=False))
    print("== holdout 其餘 k（事後參考）==")
    for k in GRID:
        if k != pick:
            print(f"  W k={k:>4}: {line(res[('W', k, 'holdout')])[0]}")


if __name__ == "__main__":
    main()

"""EXP-20261112-10 第二部分：輸頭馬距離按負磅修正（leaf 層篩選，唔改模型）。

點解：P3（輸頭馬幾多秒）場內 AUC 0.648，高過所有「對馬會標準」版本（P0 0.630／P1 0.613／P2 0.612）；
兩個一齊放，P2 喺 P3 之上係零。對標準時間帶住當日場地快慢（場地狀況、跑道、風），輸頭馬距離自動扣走。
所以負磅應該加喺「輸頭馬距離」上面，唔係加喺「對標準時間」上面。

預先登記（跑之前寫死）：賽果庫（2019 起，全場每匹完成時間＋實際負磅），只用賽日之前嘅仗，最近 3 仗平均（同 P3 一樣）
  M    輸頭馬秒數 t − t_頭馬（對照：應該 ≈ P3）
  MW   M − β × 路程km ×（嗰仗自己負磅 − 頭馬負磅）            ← 換算做同頭馬同磅
  MF   M − β × 路程km ×（嗰仗自己負磅 − 嗰場全場平均負磅）    ← 換算做全場同磅
  MFT  MF ＋ β × 今仗路程km ×（今仗負磅 − 今仗全場平均負磅）   ← 再加今仗相對全場嘅負磅
  β = 0.01123 s/km／磅（EXP-06，只用 2026-05-03 之前估）
判準：同一 population（P3 同 MW 都有），場內 AUC；再喺「模型扣走現行等級」之上同 P3 一齊放，睇新項係咪 CI 唔跨零。
過咗先做 arm（等級分位數取代 P3，同 EXP-09 一樣嘅做法），唔過就停。

用法：PYTHONDONTWRITEBYTECODE=1 python3 docs/experiments/patches/hkjc_margin_weight_screen.py <base.jsonl> <figtable.json> <out.json>
"""
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from hkjc_weight_effect_panel import load_results  # noqa: E402
from hkjc_weight_history_screen import formguide  # noqa: E402

BETA = 0.01123
BUCKETS = ((1000, 54, 60), (1200, 66.5, 73.5), (1400, 79, 87), (1600, 91, 98.2), (1650, 98.2, 104.5),
           (1800, 104.5, 113), (2000, 118, 127), (2200, 131, 141), (2400, 144, 156))


def main():
    import wongchoi_paths
    root = Path(wongchoi_paths.HK_RACING)
    R = load_results(root)
    R["t_win"] = R.groupby("race").time.transform("min")
    R["w_win"] = R.race.map(R[R.pos == 1].groupby("race").w.first())
    R["w_bar"] = R.groupby("race").w.transform("mean")
    R["dist"] = R.t_win.map(lambda t: next((d for d, lo, hi in BUCKETS if lo <= t < hi), np.nan))
    R = R.dropna(subset=["dist", "w_win"])
    R["M"] = R.time - R.t_win
    R["MW"] = R.M - BETA * R.dist / 1000 * (R.w - R.w_win)
    R["MF"] = R.M - BETA * R.dist / 1000 * (R.w - R.w_bar)
    hist = {h: g.sort_values("date")[["date", "M", "MW", "MF"]].values for h, g in R.groupby("horse")}
    figt = json.load(open(sys.argv[2]))["table"]
    recs = []
    for line in open(sys.argv[1], encoding="utf-8"):
        x = json.loads(line)
        if "error" in x or not x.get("horses"):
            continue
        md = root / x["meeting"]
        logic = json.loads((md / f"Race_{x['race']}_Logic.json").read_text(encoding="utf-8"))
        horses = logic.get("horses") or {}
        dist_today = float(re.sub(r"\D", "", str((logic.get("race_analysis") or {}).get("distance") or "")) or "nan")
        _h, fg = formguide(md, int(x["race"]))
        wt = {n: e["today"] for n, e in (fg or {}).items()}
        wbar = np.mean(list(wt.values())) if wt else np.nan
        ft = figt.get(f"{x['meeting']}|{x['race']}") or {}
        for h in x["horses"]:
            lg = horses.get(str(h["n"])) or {}
            lvl = str((lg.get("_data") or {}).get("finish_time_adj_level") or "")
            m = re.search(r"修正平均:\s*([+-]?\d+\.\d+)s", lvl)
            past = [r for r in hist.get(lg.get("horse_name"), []) if r[0] < x["date"]][-3:]
            if h["pos"] is None or not m or len(past) < 2 or h["n"] not in wt:
                continue
            a = np.array([r[1:] for r in past], float).mean(axis=0)
            rec = {"race": f"{x['meeting']}|{x['race']}", "date": x["date"], "place": float(h["pos"] <= 3), "raw": h["raw"],
                   "P3": float(m.group(1)), "M": a[0], "MW": a[1], "MF": a[2],
                   "MFT": a[2] + BETA * dist_today / 1000 * (wt[h["n"]] - wbar)}
            if str(h["n"]) in ft:
                rec["figU"], rec["figW"] = -ft[str(h["n"])][0], -ft[str(h["n"])][1]    # 轉做越細越好
            recs.append(rec)
    D = pd.DataFrame(recs)
    D = D[D.groupby("race").race.transform("count") >= 5].dropna(subset=["figW"])
    lvlpts = np.where(D.P3 < 0.3, 6.52, np.where(D.P3 < 0.8, 1.42, np.where(D.P3 < 1.3, -4, -8)))
    D["raw_x"] = D.raw - 0.1292 * lvlpts
    print(f"{D.race.nunique()} 場 / {len(D)} 匹（P3、輸頭馬（賽果庫）、表現數字都有）")
    print(f"corr(P3, M) = {D.P3.corr(D.M):+.3f}  ← 應該接近 1（P3 = 輸頭馬距離 × 0.17）")

    def auc(col, data=D):
        return float(np.mean([roc_auc_score(s.place, -s[col]) for _r, s in data.groupby("race") if 0 < s.place.sum() < len(s)]))
    cols = ("P3", "M", "MW", "MF", "MFT", "figU", "figW")
    print("場內 AUC：", {c: round(auc(c), 4) for c in cols})
    for lab, sel in (("dev < 09-06", D.date < "2026-09-06"), ("holdout ≥ 09-06", D.date >= "2026-09-06")):
        print(f"  {lab}：", {c: round(auc(c, D[sel]), 4) for c in cols})
    g = D.groupby("race")
    for c in ("raw_x", *cols):
        D[c + "_z"] = (D[c] - g[c].transform("mean")) / g[c].transform("std").replace(0, np.nan)
    D = D.dropna()

    def fit(cs, n=400):
        def f(z):
            return LogisticRegression(max_iter=3000, C=1e6).fit(z[cs], z.place).coef_[0]
        races = D.race.unique()
        idx = {r: np.where(D.race.values == r)[0] for r in races}
        rng = np.random.default_rng(0)
        bs = np.array([f(D.iloc[np.concatenate([idx[r] for r in rng.choice(races, len(races))])]) for _ in range(n)])
        b = f(D)
        return "  ".join(f"{c.replace('_z', '')} {b[i]:+.3f} [{np.percentile(bs[:, i], 2.5):+.3f},{np.percentile(bs[:, i], 97.5):+.3f}]"
                         for i, c in enumerate(cs))
    print("\n模型（扣走現行等級）之上：")
    for c in cols:
        print(f"  ＋{c:<5}: {fit(['raw_x_z', c + '_z'])}")
    print("同 P3 一齊放（新項 CI 唔跨零先算加到嘢）：")
    for c in ("M", "MW", "MF", "MFT", "figW"):
        print(f"  P3＋{c:<5}: {fit(['raw_x_z', 'P3_z', c + '_z'])}")
    print("同 M（賽果庫輸頭馬）一齊放：")
    for c in ("MW", "MF", "MFT"):
        print(f"  M＋{c:<5}: {fit(['raw_x_z', 'M_z', c + '_z'])}")
    D.to_csv(sys.argv[3].replace(".json", ".csv"), index=False)


if __name__ == "__main__":
    main()

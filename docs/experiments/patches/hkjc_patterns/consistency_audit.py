"""EXP-20261118-02：上名／大敗紀錄分（consistency_score）係咪真訊號？同近績分、輸頭馬差距重唔重複？（Kelvin 2026-11-18）
1. 場內置中 Spearman：consistency vs form、vs 段速分、vs 近 3 仗平均輸頭馬（lbw 馬位，HKJC 馬匹頁，日期早過今仗）。
2. 單一 leaf 場內 AUC（入頭三），dev／holdout。
3. 增量：條件 logit「入頭三 ~ raw 扣走 consistency 份額 + consistency」，consistency 係數 bootstrap CI。
4. 寫候選 dump 畀 v4 尺：
   C1 合併：穩定性 = 近績分 100%（consistency 份額交畀近績）
   C2 剷走：consistency 份額歸零（穩定性只剩近績 5/9）
   C3 對調：穩定性 = consistency 100%
用法：python3 consistency_audit.py <k7_K2.jsonl> <outdir>
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, "/Users/imac/Antigravity-repo/docs/experiments/patches/hkjc_patterns")
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
from diag import horse_runs, season  # noqa: E402

W_STAB = 0.2451
SF, SC = 0.5 / 0.9, 0.4 / 0.9
WIN = {"dev": (2020, 2023), "holdout": (2024, 2025)}


def lbw(q):
    s = str(q.get("lbw", "")).strip()
    if s in ("-", ""):
        return 0.0   # 頭馬
    table = {"鼻": 0.05, "短頭": 0.1, "頭": 0.2, "頸": 0.3}
    if s in table:
        return table[s]
    try:
        if "-" in s:
            a, b = s.split("-")
            n, d = b.split("/")
            return float(a) + float(n) / float(d)
        if "/" in s:
            n, d = s.split("/")
            return float(n) / float(d)
        return float(s)
    except Exception:
        return None


def auc_within(rows, getter):
    num = den = 0.0
    for hs in rows:
        v = [(getter(h), h["pos"] <= 3) for h in hs]
        pos = [a for a, y in v if y]; neg = [a for a, y in v if not y]
        for a in pos:
            for b in neg:
                num += 1.0 if a > b else 0.5 if a == b else 0.0
                den += 1
    return num / den


def main():
    import hkjc_history_replay_pit as p
    src, out = sys.argv[1], Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
    df = p.load_all_rows_extended()
    df = df[df["Rank"].notna()]
    key = defaultdict(list)
    for r in df.itertuples():
        key[(str(r.Date)[:10], int(r.RaceNo), int(r.Rank))].append(r.HorseID)
    runs, _ = horse_runs()
    allrows = [json.loads(l) for l in open(src)]
    cand = {"C1_merge": [], "C2_drop": [], "C3_swap": []}
    per = {w: [] for w in WIN}
    for x in allrows:
        if "horses" not in x:
            for c in cand.values():
                c.append(x)
            continue
        hs = x["horses"]
        for h in hs:
            if h["debut"] or not h["pos"]:
                h["_m"] = None; continue
            k = key.get((x["date"], x["race"], h["pos"]))
            m = None
            if k and len(k) == 1:
                past = [q for q in runs.get(k[0], []) if q["d"] < x["date"]][-3:]
                v = [lbw(q) for q in past]
                v = [a for a in v if a is not None]
                if len(v) >= 2:
                    m = float(np.mean(v))
            h["_m"] = m
        live = [h for h in hs if h["pos"] and not h["debut"]]
        for w, (lo, hi) in WIN.items():
            if lo <= season(x["date"]) <= hi and len(live) >= 5:
                per[w].append(live)
        for name, delta in (("C1_merge", lambda f: W_STAB * SC * (f["form_score"] - f["consistency_score"])),
                            ("C2_drop", lambda f: -W_STAB * SC * (f["consistency_score"] - 60.0)),
                            ("C3_swap", lambda f: W_STAB * SF * (f["consistency_score"] - f["form_score"]))):
            y = dict(x); y["arm"] = name
            nh = []
            for h in hs:
                g = {k_: v for k_, v in h.items() if k_ != "_m"}
                if not h["debut"]:
                    g["raw"] = round(h["raw"] + delta(h["f"]), 4)
                nh.append(g)
            y["horses"] = nh
            y["picks"] = [g["n"] for g in sorted(nh, key=lambda g: -g["raw"])]
            cand[name].append(y)
    for name, rows in cand.items():
        with open(out / f"{name}.jsonl", "w") as fh:
            for y in rows:
                fh.write(json.dumps(y, ensure_ascii=False) + "\n")

    rng = np.random.default_rng(0)
    for w, races in per.items():
        print(f"\n=== {w}：{len(races)} 場、{sum(map(len, races))} 匹 ===")
        cols = defaultdict(list)
        for hs in races:
            def c(fn):
                v = np.array([fn(h) for h in hs], dtype=float)
                return v - np.nanmean(v)
            cols["cons"] += list(c(lambda h: h["f"]["consistency_score"]))
            cols["form"] += list(c(lambda h: h["f"]["form_score"]))
            cols["speed"] += list(c(lambda h: h["f"]["speed_score"]))
            cols["neg_margin"] += list(c(lambda h: -h["_m"] if h["_m"] is not None else np.nan))
        A = {k_: np.array(v) for k_, v in cols.items()}
        ok = ~np.isnan(A["neg_margin"])
        for a_, b_ in (("cons", "form"), ("cons", "speed"), ("cons", "neg_margin"), ("form", "neg_margin"), ("speed", "neg_margin")):
            msk = ok if "neg_margin" in (a_, b_) else np.ones_like(ok)
            print(f"  ρ({a_},{b_}) = {spearmanr(A[a_][msk], A[b_][msk])[0]:+.3f}")
        for nm, g in (("上名／大敗紀錄分", lambda h: h["f"]["consistency_score"]), ("近績分", lambda h: h["f"]["form_score"]),
                      ("段速分", lambda h: h["f"]["speed_score"]), ("−平均輸頭馬", lambda h: -h["_m"] if h["_m"] is not None else -9),
                      ("穩定性維度", lambda h: h["m"]["stability"]), ("總分 raw", lambda h: h["raw"])):
            print(f"  AUC {nm:12s} {auc_within(races, g):.4f}")
        # 增量：raw 扣走 consistency 份額之後，consistency 仲有冇額外資訊
        X, Y, D = [], [], []
        for i, hs in enumerate(races):
            r0 = np.array([h["raw"] - W_STAB * SC * (h["f"]["consistency_score"] - 60) for h in hs])
            cs = np.array([h["f"]["consistency_score"] for h in hs])
            fm = np.array([h["f"]["form_score"] for h in hs])
            for a, b, f_, h in zip(r0 - r0.mean(), cs - cs.mean(), fm - fm.mean(), hs):
                X.append((a, b / 10, f_ / 10)); Y.append(h["pos"] <= 3); D.append(i)
        X, Y, D = np.array(X), np.array(Y), np.array(D)
        def coef(idx):
            m = LogisticRegression(C=1e6, max_iter=5000).fit(X[idx][:, :2], Y[idx])
            return m.coef_[0][1]
        full = coef(np.arange(len(Y)))
        bs = []
        groups = defaultdict(list)
        for j, d in enumerate(D):
            groups[d].append(j)
        gk = list(groups)
        for _ in range(300):
            idx = np.concatenate([groups[gk[i]] for i in rng.integers(0, len(gk), len(gk))])
            bs.append(coef(idx))
        print(f"  增量 logit：consistency（每 10 分）係數 {full:+.4f} [{np.percentile(bs, 2.5):+.4f},{np.percentile(bs, 97.5):+.4f}]（已控制 raw 扣走 consistency；raw 入面已有近績）")


if __name__ == "__main__":
    main()

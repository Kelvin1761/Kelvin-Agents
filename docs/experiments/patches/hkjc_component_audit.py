"""全部維度逐個組件訊號審計（讀 hkjc_component_dump.py 嘅輸出）。

每個組件：覆蓋（唔係中性／有郁嘅比例）、場內唯一值數、場內 AUC（leaf 分；逐項加減分用 delta）、
模型之上剩餘訊號（place ~ zraw + 組件，場次 bootstrap），同佢對 raw 嘅影響力（場內 SD × 權重）。
用法：PYTHONDONTWRITEBYTECODE=1 python3 docs/experiments/patches/hkjc_component_audit.py <components.jsonl>
"""
import json
import sys
from collections import defaultdict

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score


def main():
    rows = []
    for line in open(sys.argv[1], encoding="utf-8"):
        r = json.loads(line)
        for h in r["horses"]:
            if h["pos"] is None or h["raw"] is None:
                continue
            rec = {"race": f"{r['meeting']}|{r['race']}", "place": float(h["pos"] <= 3), "raw": float(h["raw"]),
                   "debut": h["debut"], "hv": "HappyValley" in r["meeting"]}
            for dim, comps in (h.get("dims") or {}).items():
                for c in comps:
                    if c.get("score") is not None:
                        rec[f"L|{dim}|{c['label']}"] = float(c["score"])
            sp = defaultdict(float)
            for d in h.get("speed") or []:
                sp[d["factor"]] += float(d.get("delta") or 0)
            for k, v in sp.items():
                rec[f"S|段速|{k}"] = v
            jt = defaultdict(float)
            for d in h.get("jt") or []:
                jt[f"{d['factor']}（{d.get('target')}）"] += float(d.get("delta") or 0)
            for k, v in jt.items():
                rec[f"S|騎練|{k}"] = v
            for t in h.get("shape") or []:
                if t.get("score") is not None:
                    rec[f"S|檔位走位|{t['label']}{'' if t.get('scored') else '（唔入分）'}"] = float(t["score"])
            if h.get("dist_adj") is not None:
                rec["S|同程|同程調整"] = float(h["dist_adj"])
            rows.append(rec)
    df = pd.DataFrame(rows)
    g = df.groupby("race")
    df["zraw"] = (df.raw - g.raw.transform("mean")) / g.raw.transform("std").replace(0, np.nan)
    df = df.dropna(subset=["zraw"]).reset_index(drop=True)
    races = df.race.unique()
    idx = {r: np.where(df.race.values == r)[0] for r in races}
    rng = np.random.default_rng(0)
    boots = [np.concatenate([idx[r] for r in rng.choice(races, len(races))]) for _ in range(200)]
    out = []
    comp_cols = [c for c in df.columns if c.startswith(("L|", "S|"))]
    for col in comp_cols:
        s = df[["race", "place", "zraw", col]].copy()
        s[col] = s[col].fillna(0.0 if col.startswith("S|") else 60.0)
        cov = (s[col] != (0.0 if col.startswith("S|") else 60.0)).mean()
        if cov < 0.01:
            out.append((col, cov, np.nan, np.nan, np.nan, np.nan, np.nan))
            continue
        cen = s[col] - s.groupby("race")[col].transform("mean")
        sd = cen.std()
        if sd == 0 or np.isnan(sd):
            out.append((col, cov, 0, np.nan, np.nan, np.nan, np.nan))
            continue
        s["z"] = cen / sd
        aucs = [roc_auc_score(x.place, x[col]) for _r, x in s.groupby("race") if 0 < x.place.sum() < len(x) and x[col].nunique() > 1]
        fit = lambda d: LogisticRegression(max_iter=2000, C=1e6).fit(d[["zraw", "z"]], d.place).coef_[0][1]
        b = fit(s)
        bs = [fit(s.iloc[ii]) for ii in boots]
        out.append((col, cov, s.groupby("race")[col].nunique().mean(), np.mean(aucs) if aucs else np.nan, b,
                    np.percentile(bs, 2.5), np.percentile(bs, 97.5)))
    res = pd.DataFrame(out, columns=["組件", "覆蓋", "場內唯一值", "場內AUC", "模型之上(每SD)", "CI低", "CI高"])
    res["判讀"] = np.select(
        [res["覆蓋"] < 0.01, res["CI低"] > 0, res["CI高"] < 0, res["場內AUC"].between(0.48, 0.52)],
        ["死／幾乎冇用", "模型用少咗（剩餘正）", "模型用多咗（剩餘負）", "冇訊號（AUC≈0.5）"], default="模型之上冇剩餘")
    pd.set_option("display.width", 250)
    pd.set_option("display.max_colwidth", 48)
    print(f"{df.race.nunique()} 場 / {len(df)} 匹；組件 {len(comp_cols)} 個")
    print(res.sort_values("組件").to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    res.to_csv(sys.argv[1].replace(".jsonl", "_audit.csv"), index=False)


if __name__ == "__main__":
    main()

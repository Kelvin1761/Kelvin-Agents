#!/usr/bin/env python3
"""EXP-20261125-06：市場揀中、模型揀唔中（AU，唯讀診斷；唔郁模型、唔擇參）。

    PYTHONDONTWRITEBYTECODE=1 python3 disagree.py BASE.json [--out out.json] [--boot 400]

定義（每場）：
  市場排名 k = SP 由低到高；模型排名 m = ability 由高到低；入位 = pos<=3。
  D  = k<=2 且 m>=4（市場頭二、模型唔睇好）       A = D 且入位（市場啱、模型錯）
  C  = k<=2 且 m<=3 且入位（兩邊都睇好又入位 = 對照）
  M  = m<=2 且 k>=4 且入位（模型啱、市場錯，鏡像）
賠率只做評估基準：本腳本冇任何輸出會餵返模型。失手診斷唔准直接用嚟擇參（EXP-20261013-01）。
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / ".agents/skills/au_racing/au_wong_choi_auto/scripts"))

ADJ = ["wet", "proven_class", "full_time", "draw", "old_horse", "trainer_residual", "people_prize", "speed"]
CTX = ["career_starts", "days_since_last", "barrier", "field_n", "dist_m", "pf_runs", "neutral_leaves", "ability"]


def load(path, since="2026-08-05"):
    out = []
    for r in json.load(open(path))["races"]:
        if r["date"] < since:
            continue
        rows = [x for x in r["rows"] if isinstance(x.get("sp"), (int, float)) and x["sp"] > 1
                and isinstance(x.get("pos"), int) and x["pos"] > 0 and x.get("ability") is not None]
        if len(rows) < 5 or len(rows) != len(r["rows"]):
            continue
        out.append(dict(r, rows=rows))
    return out


def enrich(races):
    feats = sorted({k for r in races for x in r["rows"] for k in x["features"]})
    for r in races:
        rows = r["rows"]
        for i, x in enumerate(sorted(rows, key=lambda x: -x["ability"])):
            x["m"] = i + 1
        for i, x in enumerate(sorted(rows, key=lambda x: x["sp"])):
            x["k"] = i + 1
        inv = np.array([1 / x["sp"] for x in rows]); p = inv / inv.sum()
        for x, pi in zip(rows, p):
            x["date"] = r["date"]
            x["mkt_p"] = float(pi)
            x["placed"] = int(x["pos"] <= 3)
            try:
                x["dist_m"] = float(str(x.get("distance", "")).rstrip("m"))
            except ValueError:
                x["dist_m"] = float("nan")
            x["going0"] = (x.get("going") or "?").split(" ")[0] or "?"
            x["neutral_leaves"] = sum(1 for v in x["features"].values() if v == 60.0)
            e = x.get("early")
            x["drift"] = math.log(x["sp"] / e) if e else float("nan")   # >0 = 飄；<0 = 落飛
        for key in feats + ADJ + ["ability"]:
            v = np.array([float((x["features"][key] if key in x["features"] else x.get(key)) or 0) for x in rows])
            sd = v.std()
            z = (v - v.mean()) / sd if sd > 1e-9 else np.zeros_like(v)
            for x, zi in zip(rows, z):
                x.setdefault("z", {})[key] = float(zi)
        if all(x.get("early") for x in rows):
            for i, x in enumerate(sorted(rows, key=lambda x: x["early"])):
                x["k_early"] = i + 1
            inv = np.array([1 / x["early"] for x in rows]); p = inv / inv.sum()
            for x, pi in zip(rows, p):
                x["early_p"] = float(pi)
    return feats


def cohorts(races):
    out = defaultdict(list)
    for r in races:
        for x in r["rows"]:
            if x["k"] <= 2:
                out["K2"].append(x)
                if x["m"] >= 4:
                    out["D"].append(x)
                    out["A" if x["placed"] else "D_miss"].append(x)
                elif x["m"] <= 3 and x["placed"]:
                    out["C"].append(x)
            if x["m"] <= 2:
                out["M2"].append(x)
                if x["k"] >= 4:
                    out["MD"].append(x)
                    out["M" if x["placed"] else "MD_miss"].append(x)
    return out


def boot_smd(ga, gb, getter, dates, W):
    """standardised mean diff (a−b)/pooled sd；賽日 bootstrap（W = 預先抽好嘅賽日權重）95% CI。"""
    idx = {d: i for i, d in enumerate(dates)}

    def agg(g):
        s = np.zeros((len(dates), 3))
        for x in g:
            v = getter(x)
            if v is None or (isinstance(v, float) and math.isnan(v)):
                continue
            s[idx[x["date"]]] += (1, v, v * v)
        return s
    sa, sb = agg(ga), agg(gb)

    def smd(A, B):
        ma, mb = A[:, 1] / A[:, 0], B[:, 1] / B[:, 0]
        va = A[:, 2] / A[:, 0] - ma ** 2; vb = B[:, 2] / B[:, 0] - mb ** 2
        sd = np.sqrt(np.maximum((va + vb) / 2, 1e-12))
        return (ma - mb) / sd, ma, mb
    one = np.ones((1, len(dates)))
    pt, ma, mb = smd(one @ sa, one @ sb)
    bs = smd(W @ sa, W @ sb)[0]
    lo, hi = np.nanpercentile(bs, [2.5, 97.5])
    return {"smd": round(float(pt[0]), 3), "lo": round(float(lo), 3), "hi": round(float(hi), 3),
            "mean_a": round(float(ma[0]), 3), "mean_b": round(float(mb[0]), 3), "n_a": int(sa[:, 0].sum()),
            "n_b": int(sb[:, 0].sum())}


def logit_fit(X, y, iters=30):
    X = np.column_stack([np.ones(len(y)), X]); b = np.zeros(X.shape[1])
    for _ in range(iters):
        p = 1 / (1 + np.exp(-X @ b)); w = p * (1 - p)
        H = X.T @ (X * w[:, None]) + 1e-6 * np.eye(len(b))
        b += np.linalg.solve(H, X.T @ (y - p))
    p = np.clip(1 / (1 + np.exp(-X @ b)), 1e-9, 1 - 1e-9)
    return b, float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base"); ap.add_argument("--out"); ap.add_argument("--boot", type=int, default=400)
    a = ap.parse_args()
    rng = np.random.default_rng(20261125)
    races = load(a.base)
    import au_early_prices
    est = au_early_prices.attach(races)
    feats = enrich(races)
    co = cohorts(races)
    dates = sorted({r["date"] for r in races})
    W = rng.multinomial(len(dates), np.ones(len(dates)) / len(dates), size=a.boot).astype(float)
    n_r = len(races)
    res = {"races": n_r, "runners": sum(len(r["rows"]) for r in races), "days": len(dates), "early": est}

    # 1. 大細同基準率
    res["sizes"] = {k: len(v) for k, v in co.items()}
    res["rates"] = {
        "market_top2_place": float(np.mean([x["placed"] for x in co["K2"]])),
        "model_top2_place": float(np.mean([x["placed"] for x in co["M2"]])),
        "D_place": float(np.mean([x["placed"] for x in co["D"]])),
        "MD_place": float(np.mean([x["placed"] for x in co["MD"]])),
        "A_per_race": len(co["A"]) / n_r, "M_per_race": len(co["M"]) / n_r,
        "races_with_A": sum(1 for r in races if any(x["k"] <= 2 and x["m"] >= 4 and x["placed"] for x in r["rows"])) / n_r,
        "races_with_M": sum(1 for r in races if any(x["m"] <= 2 and x["k"] >= 4 and x["placed"] for x in r["rows"])) / n_r,
    }
    allx = [x for r in races for x in r["rows"]]
    y = np.array([x["placed"] for x in allx], float)
    Xm = np.array([math.log(x["mkt_p"]) for x in allx])[:, None]; Xa = np.array([x["z"]["ability"] for x in allx])[:, None]
    bm, llm = logit_fit(Xm, y); ba, lla = logit_fit(Xa, y); bma, llma = logit_fit(np.column_stack([Xm, Xa]), y)
    pm = lambda x: 1 / (1 + math.exp(-(bm[0] + bm[1] * math.log(x["mkt_p"]))))
    pa = lambda x: 1 / (1 + math.exp(-(ba[0] + ba[1] * x["z"]["ability"])))
    res["expect"] = {g: {"n": len(co[g]), "actual": float(np.mean([x["placed"] for x in co[g]])),
                         "market_expected": float(np.mean([pm(x) for x in co[g]])),
                         "model_expected": float(np.mean([pa(x) for x in co[g]]))} for g in ("D", "MD", "K2", "M2")}
    res["ll_top3"] = {"market": llm, "model": lla, "market+model": llma, "beta_ability_given_market": float(bma[2])}

    # 2. 特徵差
    def gz(k): return lambda x: x["z"].get(k)
    def graw(k): return lambda x: x["features"][k] if k in x["features"] else x.get(k)
    res["smd"] = {}
    for label, (ga, gb) in {"A_vs_C": (co["A"], co["C"]), "D_place_vs_miss": (co["A"], co["D_miss"]),
                            "M_vs_MDmiss": (co["M"], co["MD_miss"])}.items():
        tab = {}
        for f in feats + ADJ:
            tab["z:" + f] = boot_smd(ga, gb, gz(f), dates, W)
        for f in CTX + ["drift", "k_early"]:
            tab["raw:" + f] = boot_smd(ga, gb, graw(f), dates, W)
        for f in feats:
            tab["neutral:" + f] = boot_smd(ga, gb, lambda x, f=f: float(x["features"].get(f) == 60.0), dates, W)
        for c in ("prep_stage", "style", "going0"):
            for v in sorted({x[c] for x in ga + gb}):
                tab[f"cat:{c}={v}"] = boot_smd(ga, gb, lambda x, c=c, v=v: float(x[c] == v), dates, W)
        res["smd"][label] = tab

    # 2b. 全語料：每個輸入喺 ability 之外／市場之外有冇入位資訊（前後半段分開睇穩唔穩）
    half = dates[len(dates) // 2]
    res["beyond"] = {}
    cats = [("prep_stage", v) for v in ("debut", "first_up", "second_up", "third_up", "established_prep", "unknown")]
    cats += [("style", v) for v in sorted({x["style"] for x in allx})]
    names = feats + ADJ + ["neutral_leaves", "career_starts", "days_since_last", "barrier"] + [f"{c}={v}" for c, v in cats]

    def col(x, f):
        if "=" in f:
            c, v = f.split("=", 1); return float(x[c] == v)
        if f in x["z"]:
            return x["z"][f]
        v = x.get(f); return float(v) if v is not None else 0.0
    for f in names:
        out = {}
        for part, sel in (("all", lambda x: True), ("h1", lambda x: x["date"] < half), ("h2", lambda x: x["date"] >= half)):
            xs = [x for x in allx if sel(x)]
            yy = np.array([x["placed"] for x in xs], float)
            v = np.array([col(x, f) for x in xs]); v = (v - v.mean()) / (v.std() or 1)
            ab = np.array([x["z"]["ability"] for x in xs]); mk = np.array([math.log(x["mkt_p"]) for x in xs])
            b1, _ = logit_fit(np.column_stack([ab, v]), yy)
            b2, _ = logit_fit(np.column_stack([mk, v]), yy)
            b3, _ = logit_fit(np.column_stack([mk, ab, v]), yy)
            resid = mk - np.polyval(np.polyfit(ab, mk, 1), ab)     # 市場對模型嘅「異議」
            out[part] = {"beyond_model": round(float(b1[2]), 4), "beyond_market": round(float(b2[2]), 4),
                         "beyond_both": round(float(b3[3]), 4), "corr_mkt_resid": round(float(np.corrcoef(v, resid)[0, 1]), 4)}
        res["beyond"][f] = out

    # 3. 早更價 vs SP
    xs = [x for x in allx if x.get("early_p")]
    yy = np.array([x["placed"] for x in xs], float)
    ab = np.array([x["z"]["ability"] for x in xs])
    le = np.array([math.log(x["early_p"]) for x in xs]); ls = np.array([math.log(x["mkt_p"]) for x in xs])
    ll = {name: logit_fit(X, yy)[1] for name, X in {
        "model": ab[:, None], "early": le[:, None], "sp": ls[:, None], "early+model": np.column_stack([le, ab]),
        "sp+early": np.column_stack([ls, le]), "sp+model": np.column_stack([ls, ab])}.items()}
    base_rate = yy.mean(); ll0 = float(-(base_rate * math.log(base_rate) + (1 - base_rate) * math.log(1 - base_rate)))
    ll["null_flat"] = ll0
    res["price"] = {"runners": len(xs), "ll": ll,
                    "share_of_market_edge_in_early": (ll["model"] - ll["early"]) / (ll["model"] - ll["sp"]),
                    "share_of_market_info_in_early": (ll0 - ll["early"]) / (ll0 - ll["sp"])}

    def summ(g):
        g = [x for x in g if x.get("early")]
        return {"n": len(g), "early_top2": float(np.mean([x.get("k_early", 99) <= 2 for x in g])),
                "median_drift": float(np.median([x["drift"] for x in g])),
                "firmed_gt10pct": float(np.mean([x["drift"] < -math.log(1.1) for x in g])),
                "drifted_gt10pct": float(np.mean([x["drift"] > math.log(1.1) for x in g]))}
    res["price"]["cohorts"] = {g: summ(co[g]) for g in ("A", "D_miss", "C", "M", "MD_miss", "K2")}
    Dx = [x for x in co["D"] if x.get("k_early")]
    res["price"]["D_by_early_top2"] = {
        str(t): {"n": sum(1 for x in Dx if (x["k_early"] <= 2) == t),
                 "place": float(np.mean([x["placed"] for x in Dx if (x["k_early"] <= 2) == t]))} for t in (True, False)}
    print(json.dumps({k: res[k] for k in ("races", "runners", "days", "early", "sizes", "rates", "expect", "ll_top3", "price")},
                     indent=1, ensure_ascii=False))
    if a.out:
        Path(a.out).write_text(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()

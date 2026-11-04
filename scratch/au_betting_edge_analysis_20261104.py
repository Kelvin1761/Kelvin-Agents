#!/usr/bin/env python3
"""EXP-20261104-10 分析：Q1 資訊測試、Q2 揀注同價、Q3 分層、Q4 注碼。規則見 protocol（含修訂）。

    python3 scratch/au_betting_edge_analysis_20261104.py DATASET.json OUT.json
"""
import json
import math
import random
import sys
from collections import defaultdict
from datetime import date

import numpy as np
from sklearn.linear_model import LogisticRegression

WARMUP_WEEKS = 4
EV_MIN = 0.05
COMMISSION = 0.05
BOOT = 2000
HALF = "2026-09-20"
DED_SCALE = float(__import__("os").environ.get("DED_SCALE", "1.0"))


def places_paid(field):
    return 3 if field >= 8 else 2 if field >= 5 else 1


def logit(p):
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def week(d):
    y, w, _ = date.fromisoformat(d).isocalendar()
    return f"{y}-{w:02d}"


def build_rows(races, market, mkt_price, settle_price, outcome):
    """逐匹：x = [logit(p_mkt), z_model]，y，結算淨賠，race meta。場內有馬冇價就成場剔走。"""
    out = []
    for r in races:
        rows = r["rows"]
        k = places_paid(len(rows)) if "place" in market else 1
        prices = [x.get(mkt_price) for x in rows]
        settle = [x.get(settle_price) for x in rows]
        if any(not p or p <= 1.0 for p in prices) or any(not s or s <= 1.0 for s in settle):
            continue
        if outcome == "bf_placed" and any(x.get("bf_placed") is None for x in rows):
            continue
        # 退出馬扣減（只影響 Sportsbet 定額注；BSP 喺退出之後先定價）：近似 = 退出馬隱含機率，DED_SCALE 做敏感度
        if settle_price.startswith("sb"):
            scr = r.get("scratched_place" if "place" in market else "scratched_win") or []
            ded = min(0.9, DED_SCALE * sum(1 / p for p in scr if p and p > 1) / (k if "place" in market else 1))
        else:
            ded = 0.0
        inv = [1 / p for p in prices]
        tot = sum(inv)
        pm = [k * v / tot for v in inv]
        scores = np.array([x["score"] for x in rows], float)
        sd = scores.std() or 1.0
        z = (scores - scores.mean()) / sd
        for i, x in enumerate(rows):
            if outcome == "win":
                y = int(x["pos"] == 1)
            elif outcome == "sb_place":
                y = int(x["pos"] <= k)
            else:
                y = int(bool(x["bf_placed"]))
            net = 1 + (settle[i] - 1) * (1 - ded) if settle_price.startswith("sb") else 1 + (settle[i] - 1) * (1 - COMMISSION)
            out.append({"date": r["date"], "week": week(r["date"]), "race": (r["meeting"], r["race"]),
                        "x": [logit(min(pm[i], 0.999)), float(z[i])], "y": y, "net": net,
                        "dec_price": prices[i], "rank": x["rank"], "mkt_fav": prices[i] == min(prices),
                        "meta": {k2: r.get(k2) for k2 in ("state", "tier", "field", "going_family")}
                        | {"price": prices[i]}})
    return out


def walk_forward(rows):
    weeks = sorted({r["week"] for r in rows})
    preds = []
    for i, wk in enumerate(weeks):
        if i < WARMUP_WEEKS:
            continue
        train = [r for r in rows if r["week"] < wk]
        test = [r for r in rows if r["week"] == wk]
        X = np.array([r["x"] for r in train])
        y = np.array([r["y"] for r in train])
        Xt = np.array([r["x"] for r in test])
        m0 = LogisticRegression(C=1e6, max_iter=1000).fit(X[:, :1], y)
        m1 = LogisticRegression(C=1e6, max_iter=1000).fit(X, y)
        p0 = m0.predict_proba(Xt[:, :1])[:, 1]
        p1 = m1.predict_proba(Xt)[:, 1]
        for r, a, b in zip(test, p0, p1):
            preds.append(r | {"p_mkt": float(a), "p_blend": float(b), "coef": [float(c) for c in m1.coef_[0]]})
    return preds


def boot_days(items, stat, seed=7):
    by = defaultdict(list)
    for it in items:
        by[it["date"]].append(it)
    days = sorted(by)
    rng = random.Random(seed)
    vals = []
    for _ in range(BOOT):
        pick = [x for d in (rng.choice(days) for _ in days) for x in by[d]]
        vals.append(stat(pick))
    vals.sort()
    return stat(items), vals[int(0.025 * BOOT)], vals[int(0.975 * BOOT) - 1]


def ll(p, y):
    p = min(max(p, 1e-9), 1 - 1e-9)
    return -(y * math.log(p) + (1 - y) * math.log(1 - p))


def q1(preds):
    if not preds:
        return {"n": 0, "races": 0, "dlogloss": float("nan"), "ci": [float("nan")] * 2, "edge": False,
                "model_coef_median": float("nan"), "market_coef_median": float("nan")}

    def dlog(items):
        return sum(ll(i["p_blend"], i["y"]) - ll(i["p_mkt"], i["y"]) for i in items) / max(1, len(items))
    est, lo, hi = boot_days(preds, dlog)
    coefs = np.array([p["coef"] for p in preds])
    return {"n": len(preds), "races": len({p["race"] for p in preds}), "dlogloss": est, "ci": [lo, hi],
            "edge": hi < 0, "model_coef_median": float(np.median(coefs[:, 1])),
            "market_coef_median": float(np.median(coefs[:, 0]))}


def roi(items):
    return sum(i["net"] * i["y"] - 1 for i in items) / max(1, len(items))


def q2(preds):
    value = [p for p in preds if p["p_blend"] * p["net_dec"] - 1 >= EV_MIN]
    rank1 = [p for p in preds if p["rank"] == 1]
    fav = [p for p in preds if p["mkt_fav"]]
    # 事後診斷（唔喺預先登記）：同一條 EV 規則但只用重新校準嘅市場機率 —— 分得出收益嚟自模型定市場本身
    mkt_only = [p for p in preds if p["p_mkt"] * p["net_dec"] - 1 >= EV_MIN]
    out = {}
    for name, bets in (("value", value), ("model_rank1", rank1), ("market_fav", fav), ("diag_market_only_value", mkt_only)):
        if not bets:
            out[name] = {"bets": 0}
            continue
        est, lo, hi = boot_days(bets, roi)
        out[name] = {"bets": len(bets), "hit": sum(b["y"] for b in bets) / len(bets), "roi": est, "ci": [lo, hi]}
    return out, value


SEGMENTS = {
    "state": lambda m: m["state"] if m["state"] in ("NSW", "VIC", "QLD") else "other",
    "tier": lambda m: m["tier"],
    "field": lambda m: "<=8" if m["field"] <= 8 else "9-12" if m["field"] <= 12 else "13+",
    "price": lambda m: "<3" if m["price"] < 3 else "3-6" if m["price"] < 6 else "6-15" if m["price"] < 15 else "15+",
    "going": lambda m: m["going_family"],
}


def q3(bets):
    out = {}
    for seg, fn in SEGMENTS.items():
        keys = sorted({fn(b["meta"]) for b in bets}, key=str)
        for k in keys:
            sub = [b for b in bets if fn(b["meta"]) == k]
            h1 = [b for b in sub if b["date"] < HALF]
            h2 = [b for b in sub if b["date"] >= HALF]
            row = {"bets": len(sub), "roi": roi(sub), "h1": {"bets": len(h1), "roi": roi(h1)}}
            if len(h2) >= 20:
                est, lo, hi = boot_days(h2, roi)
                row["h2"] = {"bets": len(h2), "roi": est, "ci": [lo, hi]}
                row["avoid"] = bool(h1 and roi(h1) < 0 and hi < 0)
            else:
                row["h2"] = {"bets": len(h2), "roi": roi(h2) if h2 else None}
                row["avoid"] = False
            out[f"{seg}:{k}"] = row
    return out


def q4(bets, seed=11):
    bets = sorted(bets, key=lambda b: (b["date"], b["race"]))
    def run(order, mode):
        bank, peak, mdd = 1.0, 1.0, 0.0
        for b in order:
            o = b["net"]
            if mode == "flat":
                stake = 0.01
            else:
                f = (b["p_blend"] * b["net_dec"] - 1) / max(b["net_dec"] - 1, 1e-9)
                stake = max(0.0, f) * {"kelly25": 0.25, "kelly50": 0.5}[mode] * bank
                stake = min(stake, 0.05 * bank)        # 單注上限 5% 資金（預先固定，防止極端）
            stake = stake if mode != "flat" else stake * 1.0
            bank += stake * (o - 1) if b["y"] else -stake
            peak = max(peak, bank)
            mdd = max(mdd, 1 - bank / peak)
            if bank <= 0.1:
                return bank, mdd, True
        return bank, mdd, False
    out = {}
    rng = random.Random(seed)
    for mode in ("flat", "kelly25", "kelly50"):
        bank, mdd, _ = run(bets, mode)
        sims = []
        for _ in range(BOOT):
            order = [rng.choice(bets) for _ in bets]
            sims.append(run(order, mode))
        finals = sorted(s[0] for s in sims)
        out[mode] = {"final": bank, "max_drawdown": mdd, "boot_median_final": finals[BOOT // 2],
                     "boot_p05_final": finals[int(0.05 * BOOT)], "ruin_prob": sum(s[2] for s in sims) / BOOT}
    return out


MARKETS = {
    # name: (market price for features/decision, settle price, outcome)
    "SB贏": ("sb_win", "sb_win", "win"),
    "SB位": ("sb_place", "sb_place", "sb_place"),
    "BSP贏(用SB價揀)": ("sb_win", "bsp_win", "win"),
    "BSP位(用SB價揀)": ("sb_place", "bsp_place", "bf_placed"),
}
DIAG = {"BSP贏(最終市場)": ("bsp_win", "bsp_win", "win"), "BSP位(最終市場)": ("bsp_place", "bsp_place", "bf_placed")}


def main():
    ds = json.load(open(sys.argv[1]))["scenarios"]
    report = {}
    for scen in ("early", "late"):
        races = ds[scen]["races"]
        for name, (mp, sp, oc) in list(MARKETS.items()) + list(DIAG.items()):
            if name in DIAG and scen == "early":
                continue
            market = "place" if "位" in name else "win"
            rows = build_rows(races, market, mp, sp, oc)
            preds = walk_forward(rows)
            for p in preds:
                # 揀注用落注嗰刻見到嘅價（BSP 注用 SB 價估；Sportsbet 注就係本身個價）
                p["net_dec"] = p["dec_price"] if not sp.startswith("bsp") or mp.startswith("bsp") \
                    else 1 + (p["dec_price"] - 1) * (1 - COMMISSION)
            res = {"q1": q1(preds)}
            if name not in DIAG:
                res["q2"], value = q2(preds) if preds else ({}, [])
                res["q3"] = q3(value) if value else {}
                res["q4"] = q4(value) if value else {}
            report[f"{scen}|{name}"] = res
            q = res["q1"]
            line = (f"{scen:5s} {name:16s} races {q['races']:4d}  Δlogloss {q['dlogloss']:+.5f} "
                    f"[{q['ci'][0]:+.5f},{q['ci'][1]:+.5f}] {'EDGE' if q['edge'] else '—'}  b={q['model_coef_median']:+.3f}")
            if "q2" in res and res["q2"].get("value", {}).get("bets"):
                v = res["q2"]["value"]
                line += (f" | value {v.get('bets', 0)} bets ROI {100 * v.get('roi', 0):+.1f}% "
                         f"[{100 * v.get('ci', [0, 0])[0]:+.1f},{100 * v.get('ci', [0, 0])[1]:+.1f}]")
            print(line, flush=True)
    json.dump(report, open(sys.argv[2], "w"), ensure_ascii=False, indent=1, default=str)


if __name__ == "__main__":
    main()

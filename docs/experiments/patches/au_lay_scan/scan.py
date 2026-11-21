#!/usr/bin/env python3
"""EXP-20261121-36：AU lay（做莊）探索性掃描。揀馬只用落注時資訊（模型名次、Sportsbet 價），BSP 結算，佣金 5%。

每注 = 接 1 單位 back 注：馬輸 +0.95；馬贏 −(BSP − 1)。ROI = 盈虧 ÷ 風險（liability = BSP − 1）。
    scan.py DATASET.json [DATASET_HOLDOUT.json]
"""
import json, random, sys
from collections import defaultdict
COMM = 0.05


def rows(path):
    out = []
    for r in json.load(open(path))["scenarios"]["late"]["races"]:
        rs = [x for x in r["rows"] if x.get("bsp_win") and x.get("sb_win") and x.get("pos")]
        if len(rs) < 5:
            continue
        fav = min(rs, key=lambda x: x["sb_win"])["n"]
        for x in rs:
            out.append(dict(x, day=r["date"], field=len(rs), market_fav=x["n"] == fav))
    return out


def lay(x, kind="win"):
    if kind == "win":
        won, price = x["pos"] == 1, x["bsp_win"]
    else:
        if not x.get("bsp_place") or x.get("bf_placed") is None:
            return None
        won, price = bool(x["bf_placed"]), x["bsp_place"]
    return (-(price - 1.0) if won else (1.0 - COMM)), price - 1.0


RULES = {
    "lay_all": lambda x: True,
    "bsp_fav_band_<=3": lambda x: x["sb_win"] <= 3.0,
    "longshot_>=21": lambda x: x["sb_win"] >= 21,
    "mkt_fav_model_rank>=4": lambda x: x["market_fav"] and x["rank"] >= 4,
    "mkt_fav_model_rank>=3": lambda x: x["market_fav"] and x["rank"] >= 3,
    "sb<=5_model_rank>=5": lambda x: x["sb_win"] <= 5 and x["rank"] >= 5,
    "sb<=8_model_rank_last3": lambda x: x["sb_win"] <= 8 and x["rank"] >= x["field"] - 2,
}


def summarise(rs, rule, kind):
    by = defaultdict(list)
    for x in rs:
        if rule(x):
            v = lay(x, kind)
            if v:
                by[x["day"]].append(v)
    bets = [v for d in by.values() for v in d]
    if not bets:
        return None
    roi = lambda s: sum(p for p, _ in s) / sum(l for _, l in s)  # noqa: E731
    days = list(by); rng = random.Random(7); bs = []
    for _ in range(2000):
        s = [v for d in (rng.choice(days) for _ in days) for v in by[d]]
        bs.append(roi(s))
    bs.sort()
    return {"n": len(bets), "profit_u": round(sum(p for p, _ in bets), 1), "roi_on_liability_pct": round(100 * roi(bets), 2),
            "ci": [round(100 * bs[50], 2), round(100 * bs[1949], 2)]}


def main():
    sets = {"dev": rows(sys.argv[1])}
    if len(sys.argv) > 2:
        sets["holdout"] = rows(sys.argv[2])
    out = {}
    for name, rs in sets.items():
        for kind in ("win", "place"):
            for rn, rule in RULES.items():
                s = summarise(rs, rule, kind)
                out[f"{name}|{kind}|{rn}"] = s
                print(f"{name:8} {kind:5} {rn:26} {s}")
    json.dump(out, open("/dev/stdout", "w") if False else sys.stderr, ensure_ascii=False)


if __name__ == "__main__":
    main()

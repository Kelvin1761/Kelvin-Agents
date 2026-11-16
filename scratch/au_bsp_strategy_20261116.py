#!/usr/bin/env python3
"""EXP-20261116-25：AU Betfair BSP 落注策略，用真實佣金（逐州 Market Base Rate，按每個市場淨贏計）。

規則全部喺 docs/experiments/EXP-20261116-25-au-bsp-strategy-real-commission-protocol.md 預先固定；呢個腳本喺睇任何結果之前寫好。

    PYTHONDONTWRITEBYTECODE=1 python3 scratch/au_bsp_strategy_20261116.py DEV.json HOLDOUT.json OUT.json

DEV / HOLDOUT = scratch/au_betting_edge_dataset_20261104.py 砌出嚟嘅數據集（用 "late" 情境）。
"""
import json
import random
import sys
from collections import defaultdict
from datetime import date

BOOT = 2000
SEED = 20261116
ALPHA = 0.05
LAY_MAX_BSP = 30.0     # S9：Limit-on-Close 鋪注最高價
LOC_MIN_BSP = 2.0      # S5：Limit-on-Close 買注最低價（EXP-20261105-01 用戶規則）
MIN_ODDS, SPREAD_ODDS = 2.0, 3.0   # S8：au_betting 現行規則（位賠）

# 數據集 state = "?" 嘅場地 → 州（由場地所屬賽馬管理機構；Albury 屬 Racing NSW）
EXTRA_STATE = {
    "Albury": "NSW", "Casino": "NSW", "Leeton": "NSW", "Griffith": "NSW", "Coonabarabran": "NSW",
    "Manangatang": "VIC", "Wycheproof": "VIC", "Mortlake": "VIC", "Yarra Valley": "VIC", "Casterton": "VIC",
    "Albany": "WA", "Collie": "WA", "Leinster": "WA", "Carnarvon": "WA",
    "Mt Isa": "QLD", "Ewan": "QLD", "Innisfail": "QLD",
    "Penola": "SA", "Halidon": "SA",
}

# 佣金方案。primary = 預先登記主方案：API 實測（VIC 8%、NSW 10%）+ Betfair 官方頁（RNSW 10%）；
# 未實測嘅州一律 10%（保守）。其餘係敏感度。
SCHEMES = {
    "primary": {"NSW": .10, "ACT": .10, "VIC": .08, "_default": .10},
    "others8": {"NSW": .10, "ACT": .10, "_default": .08},
    "flat10": {"_default": .10},
    "flat8": {"_default": .08},
    "flat5_old": {"_default": .05},
    "gross0": {"_default": 0.0},
}


def places_paid(n):
    return 3 if n >= 8 else 2 if n >= 5 else 1


def state_of(r):
    s = r.get("state")
    if s and s != "?":
        return s
    return EXTRA_STATE.get(r.get("venue"), "?")


def rate(scheme, st):
    sc = SCHEMES[scheme]
    return sc.get(st, sc["_default"])


def fav_of(rows):
    """市場熱門 = 落注嗰刻 Sportsbet 贏賠最低；同價 → 模型排名較前。冇價就冇熱門。"""
    priced = [x for x in rows if x.get("sb_win") and x["sb_win"] > 1]
    if not priced:
        return None
    return min(priced, key=lambda x: (x["sb_win"], x["rank"]))


def bets_for(strategy, r):
    """→ [(market, side, horse_row)]；market ∈ {win, place}，side ∈ {back, lay}。只用落注嗰刻拎得到嘅資訊 + BSP 限價。"""
    rows = r["rows"]
    top = next((x for x in rows if x["rank"] == 1), None)
    fav = fav_of(rows)
    if strategy == "S1_rank1_win":
        return [("win", "back", top)] if top else []
    if strategy == "S2_rank1_place":
        return [("place", "back", top)] if top else []
    if strategy == "S3_fav_win":
        return [("win", "back", fav)] if fav else []
    if strategy == "S4_fav_place":
        return [("place", "back", fav)] if fav else []
    if strategy == "S5_rank1_win_loc2":
        return [("win", "back", top)] if top and top.get("bsp_win") and top["bsp_win"] >= LOC_MIN_BSP else []
    if strategy == "S6_rank1_win_agree":
        return [("win", "back", top)] if top and fav and fav["n"] == top["n"] else []
    if strategy == "S7_rank1_win_disagree":
        return [("win", "back", top)] if top and fav and fav["n"] != top["n"] else []
    if strategy == "S8_live_rule_place":
        picks = sorted((x for x in rows if x["rank"] <= 2), key=lambda x: x["rank"])
        ok = [x for x in picks if x.get("sb_place") and x["sb_place"] >= MIN_ODDS]
        if len(ok) == 2 and max(x["sb_place"] for x in ok) <= SPREAD_ODDS:
            ok = ok[:1]
        return [("place", "back", x) for x in ok]
    if strategy == "S9_lay_last_win":
        last = max(rows, key=lambda x: x["rank"])
        return [("win", "lay", last)] if last.get("bsp_win") and last["bsp_win"] <= LAY_MAX_BSP else []
    raise KeyError(strategy)


STRATEGIES = ["S1_rank1_win", "S2_rank1_place", "S3_fav_win", "S4_fav_place", "S5_rank1_win_loc2",
              "S6_rank1_win_agree", "S7_rank1_win_disagree", "S8_live_rule_place", "S9_lay_last_win"]


def settle(strategy, races, scheme):
    """→ [(date, pnl, outlay, n_bets, hits)] 逐個市場。佣金 = MBR × max(0, 該市場淨贏)。
    冇 BSP（或者位市場冇 win_lose）嘅注作廢（唔計）。outlay：買注 = 1 單位；鋪注 = 責任額 (BSP−1)。"""
    out = []
    for r in races:
        st = state_of(r)
        k = places_paid(len(r["rows"]))
        mk = defaultdict(lambda: [0.0, 0.0, 0, 0])
        for market, side, x in bets_for(strategy, r):
            price = x.get("bsp_win" if market == "win" else "bsp_place")
            if not price or price <= 1:
                continue
            if market == "win":
                hit = x["pos"] == 1
            else:
                if x.get("bf_placed") is None:
                    continue
                hit = bool(x["bf_placed"])
            if side == "back":
                pnl, outlay = ((price - 1) if hit else -1.0), 1.0
            else:
                pnl, outlay = (-(price - 1) if hit else 1.0), price - 1
            m = mk[market]
            m[0] += pnl
            m[1] += outlay
            m[2] += 1
            m[3] += int(hit)
        for market, (pnl, outlay, n, h) in mk.items():
            if pnl > 0:
                pnl -= rate(scheme, st) * pnl
            out.append((r["date"], pnl, outlay, n, h))
    return out


def summarise(items, seed=SEED):
    if not items:
        return {"bets": 0}
    by = defaultdict(lambda: [0.0, 0.0])
    for d, pnl, outlay, _, _ in items:
        by[d][0] += pnl
        by[d][1] += outlay
    days = sorted(by)
    rng = random.Random(seed)
    vals = []
    for _ in range(BOOT):
        p = o = 0.0
        for d in (rng.choice(days) for _ in days):
            p += by[d][0]
            o += by[d][1]
        vals.append(p / o)
    vals.sort()
    pnl = sum(i[1] for i in items)
    outlay = sum(i[2] for i in items)
    bets = sum(i[3] for i in items)
    return {"bets": bets, "markets": len(items), "days": len(days), "hit": sum(i[4] for i in items) / bets,
            "pnl": pnl, "outlay": outlay, "roi": pnl / outlay, "ci": [vals[int(.025 * BOOT)], vals[int(.975 * BOOT) - 1]],
            "p_one_sided": (sum(v <= 0 for v in vals) + 1) / (BOOT + 1)}


def holm(ps):
    order = sorted(ps, key=lambda k: ps[k])
    adj, run = {}, 0.0
    for i, k in enumerate(order):
        run = max(run, min(1.0, (len(order) - i) * ps[k]))
        adj[k] = run
    return adj


def corrections(races):
    """舊結果用真實佣金重述（定義跟返原腳本；5% 一欄係對數，確認同原記錄一致）。"""
    out = {}
    # EXP-20261105-01：全部場、晚價、第 1 選；贏 BSP（SB 價 ≥ 2 篩）、贏 BSP 限價 ≥ 2、位 BSP 限價 ≥ 2
    def r1105(kind, rule, scheme):
        items = []
        for r in races:
            rows = r["rows"]
            top = next((x for x in rows if x["rank"] == 1), None)
            if not top:
                continue
            sb, bsp = (top["sb_win"], top["bsp_win"]) if kind == "win" else (top["sb_place"], top["bsp_place"])
            if not sb or not bsp:
                continue
            if (sb if rule == "bsp_by_sb" else bsp) < 2.0:
                continue
            hit = top["pos"] == 1 if kind == "win" else bool(top["bf_placed"])
            pnl = (bsp - 1) * (1 - rate(scheme, state_of(r))) if hit else -1.0
            items.append((r["date"], pnl, 1.0, 1, int(hit)))
        return summarise(items, seed=7)
    for scheme in ("flat5_old", "primary", "others8", "flat10"):
        out[f"EXP-20261105-01|win|bsp_by_sb>=2|{scheme}"] = r1105("win", "bsp_by_sb", scheme)
        out[f"EXP-20261105-01|win|bsp_loc>=2|{scheme}"] = r1105("win", "bsp_loc", scheme)
        out[f"EXP-20261105-01|place|bsp_loc>=2|{scheme}"] = r1105("place", "bsp_loc", scheme)

    # EXP-20261104-10 Q2（晚價、BSP 欄）：場內每匹都要有 SB 價同 BSP；頭 4 個 ISO 星期 warm-up 剔走；熱門 = SB 價 == 最低（同價全落）
    def r1104(kind, rule, scheme):
        mp, sp = ("sb_win", "bsp_win") if kind == "win" else ("sb_place", "bsp_place")
        keep = []
        for r in races:
            rows = r["rows"]
            if any(not x.get(mp) or x[mp] <= 1 for x in rows) or any(not x.get(sp) or x[sp] <= 1 for x in rows):
                continue
            if kind == "place" and any(x.get("bf_placed") is None for x in rows):
                continue
            keep.append(r)
        wk = lambda d: "%d-%02d" % date.fromisoformat(d).isocalendar()[:2]  # noqa: E731
        weeks = sorted({wk(r["date"]) for r in keep})[4:]
        items = []
        for r in keep:
            if wk(r["date"]) not in weeks:
                continue
            lo = min(x[mp] for x in r["rows"])
            for x in r["rows"]:
                if (rule == "rank1" and x["rank"] == 1) or (rule == "fav" and x[mp] == lo):
                    hit = x["pos"] == 1 if kind == "win" else bool(x["bf_placed"])
                    pnl = (x[sp] - 1) * (1 - rate(scheme, state_of(r))) if hit else -1.0
                    items.append((r["date"], pnl, 1.0, 1, int(hit)))
        return summarise(items, seed=7)
    for scheme in ("flat5_old", "primary", "others8", "flat10"):
        for kind in ("win", "place"):
            for rule in ("rank1", "fav"):
                out[f"EXP-20261104-10|{kind}|{rule}|{scheme}"] = r1104(kind, rule, scheme)
    return out


def main():
    dev = json.load(open(sys.argv[1]))["scenarios"]["late"]["races"]
    hold = json.load(open(sys.argv[2]))["scenarios"]["late"]["races"]
    res = {"meta": {"dev_races": len(dev), "holdout_races": len(hold),
                    "dev_window": [min(r["date"] for r in dev), max(r["date"] for r in dev)],
                    "holdout_window": [min(r["date"] for r in hold), max(r["date"] for r in hold)],
                    "unknown_state_races": {"dev": sum(state_of(r) == "?" for r in dev),
                                            "holdout": sum(state_of(r) == "?" for r in hold)},
                    "boot": BOOT, "seed": SEED}}
    for split, races in (("dev", dev), ("holdout", hold)):
        for scheme in SCHEMES:
            tab = {s: summarise(settle(s, races, scheme)) for s in STRATEGIES}
            adj = holm({s: v["p_one_sided"] for s, v in tab.items() if v.get("bets")})
            for s in tab:
                tab[s]["p_holm"] = adj.get(s)
            res[f"{split}|{scheme}"] = tab
    res["corrections"] = corrections(dev)

    # 判決（預先登記）
    verdict = {}
    for s in STRATEGIES:
        d, h, d10 = res["dev|primary"][s], res["holdout|primary"][s], res["dev|flat10"][s]
        sig = d.get("bets") and d["roi"] > 0 and d["p_holm"] < ALPHA
        if sig and h.get("bets") and h["roi"] > 0 and d10["roi"] > 0:
            verdict[s] = "USE_FORWARD_PAPER"
        elif d.get("bets") and d["roi"] > 0 and h.get("bets") and h["roi"] > 0:
            verdict[s] = "NEEDS_MORE_DATA"
        else:
            verdict[s] = "REJECT"
    res["verdict"] = verdict

    for key in [k for k in res if "|" in k and k != "corrections"]:
        print(f"\n== {key}")
        for s, v in res[key].items():
            if not v.get("bets"):
                print(f"  {s:24s} no bets")
                continue
            print(f"  {s:24s} bets {v['bets']:5d} hit {100*v['hit']:5.1f}% ROI {100*v['roi']:+6.1f}% "
                  f"[{100*v['ci'][0]:+6.1f},{100*v['ci'][1]:+6.1f}] p_holm {v['p_holm']:.3f}")
    print("\n== corrections (dev)")
    for k, v in res["corrections"].items():
        print(f"  {k:48s} bets {v['bets']:5d} ROI {100*v['roi']:+6.1f}% [{100*v['ci'][0]:+.1f},{100*v['ci'][1]:+.1f}]")
    print("\n== verdict", json.dumps(verdict, indent=1))
    json.dump(res, open(sys.argv[3], "w"), indent=1)


if __name__ == "__main__":
    main()

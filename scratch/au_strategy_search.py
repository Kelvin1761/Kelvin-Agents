#!/usr/bin/env python3
"""Betting-strategy search for the post-cleanup AU Wong Choi engine.

Scored fresh from raw Logic files by au_bigfield_dump.py, so this measures the
CURRENT engine (Codex's 2026-07-30 cleanup), not a cached ranking.

Every strategy is reported with:
  * flat 1 unit per selection, Betfair 5% commission on winnings;
  * WIN and PLACE markets priced at BSP;
  * split-half ROI — a strategy negative in either half is not a strategy;
  * 2000-sample bootstrap 95% CI;
  * and CONTROLS (back every runner / back the favourite) on the same races,
    because a price dataset can make everything look profitable. The morning
    market is unusable for this: its prices imply ~141% total probability.

Priority is on rules that are simple to follow every race, as requested.
"""
import csv, json, random, re, sys
from pathlib import Path

SCRATCH = Path("/Users/imac/Antigravity-repo/scratch")
BSP_DIR = SCRATCH / "betfair_bsp"
COMMISSION = 0.05
METRO = {"Randwick", "Flemington", "Caulfield", "Rosehill Gardens", "Moonee Valley",
         "Eagle Farm", "Doomben", "Morphettville", "Ascot", "Kensington"}


def nn(value):
    return re.sub(r"[^a-z0-9]", "", re.sub(r"^\s*\d+\.?\s*", "", str(value or "").lower()))


def fnum(value):
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f > 1.0 else None


def load_prices(market):
    idx = {}
    for path in sorted(BSP_DIR.glob(f"dwbfpricesaus{market}*.csv")):
        with path.open(encoding="utf-8-sig", errors="replace", newline="") as fh:
            for row in csv.DictReader(fh):
                m = re.match(r"(\d{2})-(\d{2})-(\d{4})", str(row.get("event_dt") or ""))
                horse = nn(row.get("selection_name"))
                if not m or not horse:
                    continue
                key = (f"{m.group(3)}-{m.group(2)}-{m.group(1)}", horse)
                vol = fnum(row.get("pptradedvol")) or 0.0
                prior = idx.get(key)
                if prior is None or vol > prior["vol"]:
                    idx[key] = {"bsp": fnum(row.get("bsp")),
                                "won": str(row.get("win_lose") or "").strip() == "1",
                                "vol": vol}
    return idx


def build(win_idx, place_idx):
    dump = json.loads((SCRATCH / "au_bigfield_dump.json").read_text())
    fin = json.loads((SCRATCH / "au_finishes_map.json").read_text())
    races = []
    for meeting, mdata in dump.items():
        fm = fin.get(meeting) or {}
        date = mdata.get("date") or meeting[:10]
        venue = (mdata.get("venue") or "").strip()
        for rno, rdata in (mdata.get("races") or {}).items():
            fr = fm.get(str(rno)) or {}
            if not fr:
                continue
            ent = []
            for num, h in (rdata.get("horses") or {}).items():
                f = fr.get(str(num))
                if not f:
                    continue
                name = f.get("name") or h.get("name")
                if f.get("name") and h.get("name") and nn(f["name"]) != nn(h["name"]):
                    continue
                if h.get("ability") is None:
                    continue
                wp = win_idx.get((date, nn(name))) or {}
                pp = place_idx.get((date, nn(name))) or {}
                ent.append({"num": int(num), "ab": float(h["ability"]), "pos": int(f["pos"]),
                            "name": name,
                            "win_bsp": wp.get("bsp"), "place_bsp": pp.get("bsp"),
                            "placed": pp.get("won")})
            if len(ent) < 5 or sum(1 for e in ent if e["pos"] <= 3) < 3:
                continue
            if not any(e["pos"] == 1 for e in ent):
                continue
            ent.sort(key=lambda e: (-e["ab"], e["num"]))
            mk = sorted((e for e in ent if e["win_bsp"]), key=lambda e: e["win_bsp"])
            races.append({"date": date, "venue": venue, "field": len(ent), "ent": ent,
                          "market": [e["num"] for e in mk]})
    races.sort(key=lambda r: r["date"])
    return races


def ledger(races, picks_fn, market):
    """market: 'win' settles on finishing 1st, 'place' on the Betfair place result."""
    out = []
    for r in races:
        for e in picks_fn(r):
            if market == "win":
                price, won = e.get("win_bsp"), e["pos"] == 1
            else:
                price, won = e.get("place_bsp"), e.get("placed")
                if won is None:
                    won = e["pos"] <= 3
            if not price:
                continue
            out.append(((price - 1.0) * (1 - COMMISSION)) if won else -1.0)
    return out


def roi(profits):
    return (sum(profits) / len(profits)) if profits else None


def ci95(profits, rng, iters=2000):
    if len(profits) < 30:
        return None
    n = len(profits)
    means = sorted(sum(profits[rng.randrange(n)] for _ in range(n)) / n for _ in range(iters))
    return means[int(0.025 * iters)], means[int(0.975 * iters)]


def line(label, races, picks_fn, market, rng):
    p = ledger(races, picks_fn, market)
    if len(p) < 40:
        print(f"  {label:<32} 注 {len(p):>4} — 太少，唔報")
        return None
    mid = len(races) // 2
    h1 = roi(ledger(races[:mid], picks_fn, market))
    h2 = roi(ledger(races[mid:], picks_fn, market))
    c = ci95(p, rng)
    strike = sum(1 for x in p if x > 0) / len(p)
    flag = ""
    if c and h1 is not None and h2 is not None:
        if c[0] > 0 and h1 > 0 and h2 > 0:
            flag = " ✅穩定正回報"
        elif h1 <= 0 or h2 <= 0:
            flag = " ⚠️有半期為負"
    print(f"  {label:<32} 注 {len(p):>4} | ROI {roi(p)*100:>+7.1f}% | 中 {strike*100:>5.1f}% | "
          f"上半 {h1*100:>+6.1f}% 下半 {h2*100:>+6.1f}% | "
          f"CI [{c[0]*100:+.1f}%,{c[1]*100:+.1f}%]{flag}")
    return roi(p)


def main():
    rng = random.Random(20260730)
    win_idx, place_idx = load_prices("win"), load_prices("place")
    races = build(win_idx, place_idx)
    wp = sum(1 for r in races if r["ent"][0]["win_bsp"])
    pp = sum(1 for r in races if r["ent"][0]["place_bsp"])
    print(f"新引擎重新評分:{len(races)} 場 | 頭揀有獨贏價 {wp} 場、有位置價 {pp} 場\n")

    def top(k):
        return lambda r: r["ent"][:k]

    print("=== 對照組（如果呢啲都正回報，就係數據偏差唔係策略）===")
    line("全場每隻都買 獨贏", races, lambda r: r["ent"], "win", rng)
    line("全場每隻都買 位置", races, lambda r: r["ent"], "place", rng)
    line("市場大熱門 獨贏", races,
         lambda r: [min((e for e in r["ent"] if e["win_bsp"]), key=lambda e: e["win_bsp"])]
         if any(e["win_bsp"] for e in r["ent"]) else [], "win", rng)
    line("市場大熱門 位置", races,
         lambda r: [min((e for e in r["ent"] if e["win_bsp"]), key=lambda e: e["win_bsp"])]
         if any(e["win_bsp"] for e in r["ent"]) else [], "place", rng)

    print("\n=== 你提議嘅策略：頭兩揀買獨贏，每場都買 ===")
    line("頭揀 獨贏", races, top(1), "win", rng)
    line("頭兩揀 獨贏", races, top(2), "win", rng)
    line("頭三揀 獨贏", races, top(3), "win", rng)

    print("\n=== 位置（每場都買，最簡單跟）===")
    line("頭揀 位置", races, top(1), "place", rng)
    line("頭兩揀 位置", races, top(2), "place", rng)
    line("頭三揀 位置", races, top(3), "place", rng)
    line("只第二揀 位置", races, lambda r: r["ent"][1:2], "place", rng)

    print("\n=== 簡單過濾：場數 ===")
    for lab, flt in (("8匹以下", lambda r: r["field"] <= 8),
                     ("9-11匹", lambda r: 9 <= r["field"] <= 11),
                     ("12匹以上", lambda r: r["field"] >= 12)):
        sub = [r for r in races if flt(r)]
        line(f"頭揀 位置 {lab}", sub, top(1), "place", rng)
        line(f"頭兩揀 位置 {lab}", sub, top(2), "place", rng)

    print("\n=== 簡單過濾：大城市 vs 鄉下 ===")
    for lab, flt in (("大城市", lambda r: r["venue"] in METRO),
                     ("非大城市", lambda r: r["venue"] not in METRO)):
        sub = [r for r in races if flt(r)]
        line(f"頭揀 位置 {lab}", sub, top(1), "place", rng)
        line(f"頭兩揀 位置 {lab}", sub, top(2), "place", rng)
        line(f"頭兩揀 獨贏 {lab}", sub, top(2), "win", rng)

    print("\n=== 位置賠率區間（頭揀）===")
    for lo, hi, lab in ((1.0, 1.5, "位置賠率 <1.5"), (1.5, 2.0, "1.5-2.0"),
                        (2.0, 3.0, "2.0-3.0"), (3.0, 999.0, ">3.0")):
        line(lab, races,
             lambda r, lo=lo, hi=hi: [e for e in r["ent"][:1]
                                      if e.get("place_bsp") and lo <= e["place_bsp"] < hi],
             "place", rng)

    print("\n=== 模型 × 市場共識 ===")
    def agree1(r):
        return r["ent"][:1] if r["market"] and r["ent"][0]["num"] == r["market"][0] else []
    def agree2(r):
        m2 = set(r["market"][:2])
        return [e for e in r["ent"][:2] if e["num"] in m2]
    def agree3(r):
        m3 = set(r["market"][:3])
        return [e for e in r["ent"][:3] if e["num"] in m3]
    line("頭揀=市場熱門 位置", races, agree1, "place", rng)
    line("頭揀=市場熱門 獨贏", races, agree1, "win", rng)
    line("頭兩揀 ∩ 市場頭兩位 位置", races, agree2, "place", rng)
    line("頭兩揀 ∩ 市場頭兩位 獨贏", races, agree2, "win", rng)
    line("頭三揀 ∩ 市場頭三位 位置", races, agree3, "place", rng)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Betting strategies settled at RACENET starting prices — no Betfair.

Kelvin does not use Betfair, so exchange BSP is irrelevant to him no matter how
attractive it looks. Everything here settles at racenet's own startingPrice, the
price a bookmaker/tote at-SP bet actually returns, with NO commission deducted.

Honest limits stated up front, because they change how the numbers should be read:
  * startingPrice is the CLOSING price. It is the correct settle price for an
    at-SP bet, but it does not prove the same price showed the day before.
  * racenet result pages carry win SP only — no place dividends — so PLACE
    strategies cannot be settled here and are reported as unmeasurable rather
    than estimated from a made-up formula.

Every line carries split-half ROI and a bootstrap 95% CI, plus controls
(back-everything, back-the-favourite) on the same races so a price artefact
cannot be mistaken for an edge.
"""
import json, random, re, statistics, sys
from pathlib import Path

SCRATCH = Path("/Users/imac/Antigravity-repo/scratch")
METRO = {"Randwick", "Flemington", "Caulfield", "Rosehill Gardens", "Moonee Valley",
         "Eagle Farm", "Doomben", "Morphettville", "Ascot", "Kensington"}


def nn(value):
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def load_scores():
    """Prefer the fresh full rescore; fall back to the cached ability map."""
    fresh = SCRATCH / "au_bigfield_dump.json"
    if fresh.exists():
        dump = json.loads(fresh.read_text())
        if len(dump) >= 80:
            out = {}
            for meeting, mdata in dump.items():
                races = {}
                for rno, rdata in (mdata.get("races") or {}).items():
                    races[rno] = {num: {"ab": h.get("ability"), "name": h.get("name")}
                                  for num, h in (rdata.get("horses") or {}).items()
                                  if h.get("ability") is not None}
                out[meeting] = races
            return out, "新引擎重新評分"
    iso = json.loads((SCRATCH / "au_trainer_isolated.json").read_text())
    return ({m: {r: {n: {"ab": v["ab_on"], "name": v.get("name")} for n, v in hs.items()}
                 for r, hs in mr.items()} for m, mr in iso.items()}, "舊快取分數")


def build():
    scores, source = load_scores()
    sp = json.loads((SCRATCH / "au_racenet_sp.json").read_text())
    by_meeting = {v["meeting"]: v["races"] for v in sp.values()}
    races = []
    for meeting, mrows in scores.items():
        srows = by_meeting.get(meeting)
        if not srows:
            continue
        vm = re.match(r"(\d{4}-\d{2}-\d{2})\s+(.+?)\s+Race", meeting)
        date = vm.group(1) if vm else meeting[:10]
        venue = (vm.group(2) if vm else meeting[11:]).strip()
        for rno, hs in mrows.items():
            sr = srows.get(str(rno)) or {}
            if not sr:
                continue
            ent = []
            for num, v in hs.items():
                s = sr.get(str(num))
                if not s or s.get("pos") is None:
                    continue
                if s.get("name") and v.get("name") and nn(s["name"]) != nn(v["name"]):
                    continue
                ent.append({"num": int(num), "ab": float(v["ab"]), "pos": int(s["pos"]),
                            "sp": s.get("sp"), "name": s.get("name") or v.get("name")})
            if len(ent) < 5 or sum(1 for e in ent if e["pos"] <= 3) < 3:
                continue
            if not any(e["pos"] == 1 for e in ent):
                continue
            ent.sort(key=lambda e: (-e["ab"], e["num"]))
            mk = sorted((e for e in ent if e["sp"]), key=lambda e: e["sp"])
            races.append({"date": date, "venue": venue, "field": len(ent), "ent": ent,
                          "market": [e["num"] for e in mk]})
    races.sort(key=lambda r: r["date"])
    return races, source


def ledger(races, picks_fn):
    """Flat 1 unit, settled at racenet SP, no commission (not an exchange)."""
    out = []
    for r in races:
        for e in picks_fn(r):
            if not e.get("sp"):
                continue
            out.append((e["sp"] - 1.0) if e["pos"] == 1 else -1.0)
    return out


def roi(p):
    return (sum(p) / len(p)) if p else None


def ci95(p, rng, iters=3000):
    if len(p) < 30:
        return None
    n = len(p)
    means = sorted(sum(p[rng.randrange(n)] for _ in range(n)) / n for _ in range(iters))
    return means[int(0.025 * iters)], means[int(0.975 * iters)]


def line(label, races, picks_fn, rng):
    p = ledger(races, picks_fn)
    if len(p) < 40:
        print(f"  {label:<34} 注 {len(p):>4} — 太少，唔報")
        return
    mid = len(races) // 2
    h1 = roi(ledger(races[:mid], picks_fn))
    h2 = roi(ledger(races[mid:], picks_fn))
    c = ci95(p, rng)
    strike = sum(1 for x in p if x > 0) / len(p)
    flag = ""
    if c and h1 is not None and h2 is not None:
        if c[0] > 0 and h1 > 0 and h2 > 0:
            flag = " ✅穩定正回報"
        elif h1 <= 0 or h2 <= 0:
            flag = " ⚠️有半期為負"
    print(f"  {label:<34} 注 {len(p):>4} | ROI {roi(p)*100:>+7.1f}% | 中 {strike*100:>5.1f}% | "
          f"上半 {h1*100:>+6.1f}% 下半 {h2*100:>+6.1f}% | CI [{c[0]*100:+.1f}%,{c[1]*100:+.1f}%]{flag}")


def main():
    rng = random.Random(20260730)
    races, source = build()
    have = sum(1 for r in races if r["ent"][0].get("sp"))
    print(f"分數來源:{source} | 對得上 racenet SP 嘅場次:{len(races)} | 頭揀有 SP {have} 場\n")

    ors = []
    for r in races:
        hs = [e for e in r["ent"] if e["sp"]]
        if len(hs) >= 6:
            ors.append(sum(1 / e["sp"] for e in hs))
    if ors:
        print(f"=== racenet SP 超收率:隱含機率總和中位數 {statistics.median(ors):.3f} "
              f"(1.00 = 完全公平) ===")

    fav = lambda r: ([min((e for e in r["ent"] if e["sp"]), key=lambda e: e["sp"])]
                     if any(e["sp"] for e in r["ent"]) else [])
    print("\n=== 對照組 ===")
    line("全場每隻都買", races, lambda r: r["ent"], rng)
    line("市場大熱門", races, fav, rng)

    print("\n=== 每場都買（你要嘅簡單規則）===")
    for k in (1, 2, 3, 4):
        line(f"頭 {k} 揀 獨贏", races, lambda r, k=k: r["ent"][:k], rng)
    line("只第二揀 獨贏", races, lambda r: r["ent"][1:2], rng)

    print("\n=== 場數過濾 ===")
    for lab, flt in (("8匹以下", lambda r: r["field"] <= 8),
                     ("9-11匹", lambda r: 9 <= r["field"] <= 11),
                     ("12匹以上", lambda r: r["field"] >= 12)):
        sub = [r for r in races if flt(r)]
        line(f"頭揀 {lab}", sub, lambda r: r["ent"][:1], rng)
        line(f"頭兩揀 {lab}", sub, lambda r: r["ent"][:2], rng)

    print("\n=== 大城市 vs 鄉下 ===")
    for lab, flt in (("大城市", lambda r: r["venue"] in METRO),
                     ("非大城市", lambda r: r["venue"] not in METRO)):
        sub = [r for r in races if flt(r)]
        line(f"頭揀 {lab}", sub, lambda r: r["ent"][:1], rng)
        line(f"頭兩揀 {lab}", sub, lambda r: r["ent"][:2], rng)

    print("\n=== SP 賠率區間（頭揀）===")
    for lo, hi, lab in ((1.0, 3.0, "頭揀 SP <3"), (3.0, 5.0, "3-5"),
                        (5.0, 8.0, "5-8"), (8.0, 15.0, "8-15"), (15.0, 9e9, ">15")):
        line(lab, races,
             lambda r, lo=lo, hi=hi: [e for e in r["ent"][:1]
                                      if e.get("sp") and lo <= e["sp"] < hi], rng)

    print("\n=== 模型 × 市場共識 ===")
    def a1(r):
        return r["ent"][:1] if r["market"] and r["ent"][0]["num"] == r["market"][0] else []
    def a2(r):
        m2 = set(r["market"][:2])
        return [e for e in r["ent"][:2] if e["num"] in m2]
    def a2_strict(r):
        return a2(r) if len(a2(r)) == 2 else []
    def disagree_fav(r):
        return fav(r) if r["market"] and r["ent"][0]["num"] != r["market"][0] else []
    line("頭揀 = 市場大熱門", races, a1, rng)
    line("頭兩揀 ∩ 市場頭兩位", races, a2, rng)
    line("頭兩揀 = 市場頭兩位（兩隻都要）", races, a2_strict, rng)
    line("大熱門（但模型唔同意）", races, disagree_fav, rng)

    print("\n=== 共識 + 賠率區間（最有機會嘅組合）===")
    for lo, hi, lab in ((1.0, 2.5, "共識 SP <2.5"), (2.5, 4.0, "共識 SP 2.5-4"),
                        (4.0, 9e9, "共識 SP >4")):
        line(lab, races,
             lambda r, lo=lo, hi=hi: [e for e in a1(r) if lo <= e["sp"] < hi], rng)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Independent re-measurement of the AU win-focus / WIN-betting question.

Deliberately written from scratch (not reusing au_win_focus_test.py) so its
headline numbers can be corroborated rather than taken on trust. Adds the
Top-4-contains-all-3-placegetters metric, which the earlier report omitted.

Whole archive, no sampling. Split-half + bootstrap on every ROI, because a
single-number ROI over ~700 races cannot be distinguished from variance.
Prices: BSP (reachable via a day-before "take SP" order) and morningwap (the
traded morning price), reported separately — they disagree materially.
"""
import csv, json, random, re, sys
from pathlib import Path

sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/shared_racing")
from eval_metrics import race_metrics, summarize_races

SCRATCH = Path("/Users/imac/Antigravity-repo/scratch")
BSP_DIR = SCRATCH / "betfair_bsp"
COMMISSION = 0.05
METRO = {"Randwick", "Flemington", "Caulfield", "Rosehill Gardens", "Moonee Valley",
         "Eagle Farm", "Doomben", "Morphettville", "Ascot"}


def nn(value):
    text = re.sub(r"^\s*\d+\.?\s*", "", str(value or "").lower())
    return re.sub(r"[^a-z0-9]", "", text)


def fnum(value):
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f > 1.0 else None


def load_win_prices():
    """Key on the real event date from event_dt (dd-mm-yyyy), not the menu hint."""
    index = {}
    for path in sorted(BSP_DIR.glob("dwbfpricesauswin*.csv")):
        with path.open(encoding="utf-8-sig", errors="replace", newline="") as fh:
            for row in csv.DictReader(fh):
                m = re.match(r"(\d{2})-(\d{2})-(\d{4})", str(row.get("event_dt") or ""))
                horse = nn(row.get("selection_name"))
                if not m or not horse:
                    continue
                key = (f"{m.group(3)}-{m.group(2)}-{m.group(1)}", horse)
                vol = fnum(row.get("pptradedvol")) or 0.0
                prior = index.get(key)
                if prior is None or vol > prior["vol"]:
                    index[key] = {"bsp": fnum(row.get("bsp")),
                                  "morning": fnum(row.get("morningwap")),
                                  "vol": vol}
    return index


def build_races(prices):
    iso = json.loads((SCRATCH / "au_trainer_isolated.json").read_text())
    fin = json.loads((SCRATCH / "au_finishes_map.json").read_text())
    races = []
    for meeting, mrows in iso.items():
        fm = fin.get(meeting) or {}
        vm = re.match(r"(\d{4}-\d{2}-\d{2})\s+(.+?)\s+Race", meeting)
        date = vm.group(1) if vm else meeting[:10]
        venue = (vm.group(2) if vm else meeting[11:]).strip()
        for rno, hs in mrows.items():
            fr = fm.get(str(rno)) or {}
            if not fr:
                continue
            ent = []
            for num, v in hs.items():
                f = fr.get(str(num))
                if not f:
                    continue
                name = f.get("name") or v.get("name")
                if f.get("name") and v.get("name") and nn(f["name"]) != nn(v["name"]):
                    continue
                p = prices.get((date, nn(name))) or {}
                ent.append({"num": int(num), "ab": float(v["ab_on"]), "pos": int(f["pos"]),
                            "name": name, "bsp": p.get("bsp"), "morning": p.get("morning")})
            if len(ent) < 5 or sum(1 for e in ent if e["pos"] <= 3) < 3:
                continue
            if not any(e["pos"] == 1 for e in ent):
                continue
            ent.sort(key=lambda e: (-e["ab"], e["num"]))
            mk = sorted((e for e in ent if e["bsp"]), key=lambda e: e["bsp"])
            races.append({"date": date, "venue": venue, "field": len(ent), "ent": ent,
                          "market": [e["num"] for e in mk],
                          "market_morning": [e["num"] for e in
                                             sorted((e for e in ent if e["morning"]),
                                                    key=lambda e: e["morning"])]})
    races.sort(key=lambda r: r["date"])
    return races


def rank_stats(races, order_fn=None):
    rows, t4 = [], 0
    for r in races:
        order = order_fn(r) if order_fn else [e["num"] for e in r["ent"]]
        pb = {e["num"]: e["pos"] for e in r["ent"]}
        top3 = [n for n, p in pb.items() if p <= 3]
        rows.append(race_metrics(order, top3, actual_pos=pb, field_size=r["field"]))
        if len(order) >= 4 and sum(1 for n in order[:4] if n in top3) >= 3:
            t4 += 1
    s = summarize_races(rows)
    s["top4_all3"] = t4
    return s


def ledger(races, picks_fn, field):
    out = []
    for r in races:
        for e in picks_fn(r):
            price = e.get(field)
            if not price:
                continue
            out.append(((price - 1.0) * (1 - COMMISSION)) if e["pos"] == 1 else -1.0)
    return out


def roi(p):
    return (sum(p) / len(p)) if p else None


def ci95(p, rng, iters=4000):
    if len(p) < 30:
        return None
    n = len(p)
    means = sorted(sum(p[rng.randrange(n)] for _ in range(n)) / n for _ in range(iters))
    return means[int(0.025 * iters)], means[int(0.975 * iters)]


def line(label, races, picks_fn, rng, field="bsp"):
    p = ledger(races, picks_fn, field)
    if len(p) < 30:
        print(f"  {label:<34} 注 {len(p):>4} — 太少")
        return
    mid = len(races) // 2
    h1, h2 = ledger(races[:mid], picks_fn, field), ledger(races[mid:], picks_fn, field)
    c = ci95(p, rng)
    strike = sum(1 for x in p if x > 0) / len(p)
    txt = (f"  {label:<34} 注 {len(p):>4} | ROI {roi(p)*100:>+7.1f}% | 中 {strike*100:>5.1f}% | "
           f"上半 {roi(h1)*100:>+7.1f}% 下半 {roi(h2)*100:>+7.1f}%")
    if c:
        txt += f" | CI [{c[0]*100:+.1f}%,{c[1]*100:+.1f}%]"
        if c[0] > 0 and roi(h1) > 0 and roi(h2) > 0:
            txt += " ✅"
        elif roi(h1) is not None and roi(h2) is not None and (roi(h1) <= 0 or roi(h2) <= 0):
            txt += " ⚠️"
    print(txt)


def main():
    rng = random.Random(20260729)
    prices = load_win_prices()
    races = build_races(prices)
    have = sum(1 for r in races if r["ent"][0]["bsp"])
    print(f"獨立核對 — {len(races)} 場;獨贏價庫 {len(prices)} 條;頭揀有 BSP {have} 場 "
          f"({100*have/len(races):.0f}%)\n")

    print("=== 1. 排名質素(含你要嘅 Top4包中三甲)===")
    for lab, sub in (("全部", races),
                     ("12匹以上", [r for r in races if r["field"] >= 12]),
                     ("大城市12匹+", [r for r in races if r["field"] >= 12 and r["venue"] in METRO]),
                     ("8匹以下", [r for r in races if r["field"] <= 8])):
        s = rank_stats(sub)
        n, c = s["races"], s["counts"]
        print(f"  {lab:<12} {n:>4}場 | 頭揀贏 {c['champion']:>3}場({c['champion']/n*100:>4.1f}%) | "
              f"冠軍入頭兩揀 {sum(1 for r in sub if any(e['pos']==1 for e in r['ent'][:2]))/n*100:>4.1f}% | "
              f"Top3中2隻 {c['good_any2']/n*100:>4.1f}% | Top4包中三甲 {s['top4_all3']:>3}場({s['top4_all3']/n*100:>4.1f}%)")

    print("\n=== 2. 獨贏 @ BSP(可用賽前一日「照開賽價落單」取得)===")
    line("頭揀", races, lambda r: r["ent"][:1], rng)
    line("頭兩揀", races, lambda r: r["ent"][:2], rng)
    line("頭三揀", races, lambda r: r["ent"][:3], rng)
    line("只第二揀", races, lambda r: r["ent"][1:2], rng)

    print("\n=== 3. 獨贏 @ 早市價(morningwap,賽前實際掛牌價)===")
    line("頭揀", races, lambda r: r["ent"][:1], rng, "morning")
    line("頭兩揀", races, lambda r: r["ent"][:2], rng, "morning")

    print("\n=== 4. 加市場共識閘(結算用 BSP)===")
    def a1(r):
        return r["ent"][:1] if r["market"] and r["ent"][0]["num"] == r["market"][0] else []
    def a2(r):
        top2 = set(r["market"][:2])
        return [e for e in r["ent"][:2] if e["num"] in top2]
    def a2m(r):
        top2 = set(r["market_morning"][:2])
        return [e for e in r["ent"][:2] if e["num"] in top2]
    line("頭揀 = 市場熱門", races, a1, rng)
    line("頭兩揀 ∩ 市場頭兩位(BSP排序)", races, a2, rng)
    line("頭兩揀 ∩ 早市頭兩位(無前視)", races, a2m, rng)
    line("頭兩揀 ∩ 早市頭兩位 @早市價", races, a2m, rng, "morning")

    print("\n=== 5. 場數/場地切片(頭兩揀 ∩ 早市頭兩位,BSP結算)===")
    for lab, flt in (("12匹以上", lambda r: r["field"] >= 12),
                     ("9-11匹", lambda r: 9 <= r["field"] <= 11),
                     ("8匹以下", lambda r: r["field"] <= 8),
                     ("大城市", lambda r: r["venue"] in METRO),
                     ("非大城市", lambda r: r["venue"] not in METRO)):
        line(lab, [r for r in races if flt(r)], a2m, rng)


if __name__ == "__main__":
    main()

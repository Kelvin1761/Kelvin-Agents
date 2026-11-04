"""模型第 1 選 × 賠率門檻：Sportsbet（扣減）vs Betfair BSP（5% 佣金）vs BSP 限價（Limit on Close）。"""
import json, random, sys
ds = json.load(open(sys.argv[1]))["scenarios"]
BOOT = 2000; COM = 0.05

def places(n): return 3 if n >= 8 else 2 if n >= 5 else 1

def bets(scen, kind, rule, th):
    out = []
    for r in ds[scen]["races"]:
        rows = r["rows"]; top = next((x for x in rows if x["rank"] == 1), None)
        if not top: continue
        k = places(len(rows))
        if kind == "win":
            sb, bsp, hit = top["sb_win"], top["bsp_win"], top["pos"] == 1
            scr = r.get("scratched_win") or []; ded = min(.75, sum(1 / p for p in scr if p and p > 1))
        else:
            sb, bsp, hit = top["sb_place"], top["bsp_place"], (top["pos"] <= k)
            bfhit = top["bf_placed"]
            scr = r.get("scratched_place") or []; ded = min(.75, sum(1 / p for p in scr if p and p > 1) / k)
        if not sb or not bsp: continue
        if rule == "sportsbet":
            if sb < th: continue
            ret = 1 + (sb - 1) * (1 - ded) if hit else 0
        elif rule == "bsp_by_sb":
            if sb < th: continue
            h = hit if kind == "win" else bool(bfhit)
            ret = 1 + (bsp - 1) * (1 - COM) if h else 0
        else:  # bsp_loc
            if bsp < th: continue
            h = hit if kind == "win" else bool(bfhit)
            ret = 1 + (bsp - 1) * (1 - COM) if h else 0
        out.append((r["date"], ret, hit))
    return out

def summary(b):
    if not b: return None
    by = {}
    for d, ret, h in b: by.setdefault(d, []).append(ret - 1)
    days = sorted(by); rng = random.Random(7); vals = []
    for _ in range(BOOT):
        flat = [v for d in (rng.choice(days) for _ in days) for v in by[d]]; vals.append(sum(flat) / len(flat))
    vals.sort()
    return len(b), sum(h for _, _, h in b) / len(b), sum(r - 1 for _, r, _ in b) / len(b), vals[50], vals[1949]

res = {}
for scen in ("late", "early"):
    for kind in ("win", "place"):
        for rule in ("sportsbet", "bsp_by_sb", "bsp_loc"):
            for th in (1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 6.0):
                s = summary(bets(scen, kind, rule, th))
                res[f"{scen}|{kind}|{rule}|{th}"] = s
                if s and th in (1.0, 2.0) or (s and scen == "late"):
                    print(f"{scen:5s} {kind:5s} {rule:9s} ≥{th:<4} bets {s[0]:5d} hit {100*s[1]:5.1f}% ROI {100*s[2]:+6.1f}% [{100*s[3]:+.1f},{100*s[4]:+.1f}]")
json.dump(res, open(sys.argv[2], "w"))

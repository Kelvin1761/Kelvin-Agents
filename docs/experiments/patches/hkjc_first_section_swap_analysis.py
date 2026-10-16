import json, glob, math, statistics as st
from collections import Counter
S = "out19"  # directory holding base/k2/k4/k6 jsonl
ROOT = open(".wongchoi_hk_data_root").read().strip()
def load(p): return {(r["meeting"], r["race"]): r for r in map(json.loads, open(p)) if "error" not in r and "speed_score" not in r.get("meeting_dead_fields", [])}
b = load(f"{S}/base.jsonl"); arms = {k: load(f"{S}/{k}.jsonl") for k in ("k2", "k4", "k6")}
res = {}
for md in {k[0] for k in b}:
    for rn, r in json.load(open(glob.glob(f"{ROOT}/{md}/*全日賽果.json")[0])).items():
        for x in r.get("results", []):
            try:
                rp = str(x.get("running_positions") or "").split()
                res[(md, int(rn), int(x["horse_no"]))] = (int(x["pos"]), int(rp[0]) if rp and rp[0].isdigit() else None, float(x["win_odds"]))
            except (ValueError, KeyError, TypeError):
                pass

def binom_p(w, l):
    n = w + l; k = max(w, l)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k, n + 1)) / 2 ** n) if n else 1.0

for name, c in arms.items():
    keys = [k for k in b if k in c]
    print(f"\n===== {name}  ({len(keys)} races)")
    for m in ("good_positional", "gold"):
        w = sum(c[k][m] > b[k][m] for k in keys); l = sum(c[k][m] < b[k][m] for k in keys)
        print(f"  {m:16s} races improved {w}  worsened {l}  unchanged {len(keys)-w-l}   sign-test p={binom_p(w,l):.3f}")
    # who moved in/out of top-2 and top-4
    for top in (2, 4):
        inn, out = [], []
        for k in keys:
            bs, cs = set(b[k]["picks"][:top]), set(c[k]["picks"][:top])
            for h in cs - bs: inn.append(res.get((k[0], int(k[1]), h)))
            for h in bs - cs: out.append(res.get((k[0], int(k[1]), h)))
        def desc(xs):
            xs = [x for x in xs if x]
            if not xs: return "n=0"
            pl = sum(p <= 3 for p, _, _ in xs) / len(xs) * 100
            fc = [f for _, f, _ in xs if f]
            od = st.median(o for _, _, o in xs)
            return f"n={len(xs):3d} 上名 {pl:5.1f}%  今仗首位中位 {st.median(fc):.0f}  賠率中位 {od:.1f}"
        print(f"  top{top} 新入: {desc(inn)}\n  top{top} 被踢: {desc(out)}")

print("\n===== arm overlap (races whose top-4 changed)")
ch = {n: {k for k in b if k in c and b[k]['picks'][:4] != c[k]['picks'][:4]} for n, c in arms.items()}
print(f"  k2 {len(ch['k2'])}  k4 {len(ch['k4'])}  k6 {len(ch['k6'])}  k2∩k6 {len(ch['k2'] & ch['k6'])}  k4∩k6 {len(ch['k4'] & ch['k6'])}")
gd = {n: {k: c[k]['good_positional'] - b[k]['good_positional'] for k in b if k in c} for n, c in arms.items()}
same = sum(1 for k in gd['k4'] if gd['k4'][k] != 0 and gd['k4'][k] == gd['k6'].get(k))
print(f"  Good 有變嘅場：k4 {sum(v!=0 for v in gd['k4'].values())}，同 k6 一樣方向 {same}")

# power: races needed for observed Good effect at 80% power, two-sided 5%
for n, d in gd.items():
    vals = list(d.values()); mu = st.mean(vals); sd = st.pstdev(vals)
    need = ((1.96 + 0.84) * sd / mu) ** 2 if mu else float("inf")
    print(f"  {n}: Good Δ {mu*100:+.2f}pp  per-race SD {sd*100:.1f}pp  → 要約 {need:,.0f} 場先有 80% 功效")

print("\n===== paired swaps inside the same race (exploratory, NOT the pre-registered metric)")
import random
for name, c in arms.items():
    for top in (2, 4):
        pairs = []  # (in_placed - out_placed) per race, summed over swaps in that race
        for k in b:
            if k not in c: continue
            bs, cs = b[k]["picks"][:top], c[k]["picks"][:top]
            ins = [h for h in cs if h not in bs]; outs = [h for h in bs if h not in cs]
            if not ins: continue
            pi = sum(res.get((k[0], int(k[1]), h), (99,))[0] <= 3 for h in ins)
            po = sum(res.get((k[0], int(k[1]), h), (99,))[0] <= 3 for h in outs)
            pairs.append((k[0], pi - po))
        w = sum(d > 0 for _, d in pairs); l = sum(d < 0 for _, d in pairs)
        by = {}
        for md, d in pairs: by.setdefault(md, []).append(d)
        days = list(by); rng = random.Random(3); bs_ = []
        for _ in range(4000):
            xs = [v for dd in (rng.choice(days) for _ in days) for v in by[dd]]
            bs_.append(sum(xs))
        bs_.sort()
        print(f"  {name} top{top}: 有換馬嘅場 {len(pairs):3d}  換入嗰隻上名多 {w} 場 / 換出嗰隻上名多 {l} 場  sign p={binom_p(w,l):.3f}  淨多上名 {sum(d for _,d in pairs):+d} 匹 [賽日 bootstrap 95% {bs_[100]:+d}, {bs_[3899]:+d}]")

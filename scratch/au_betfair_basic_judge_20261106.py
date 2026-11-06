"""EXP-20261106-02 判決：資料檢查 → Q1（條件 logit 時間切）→ Q2（四條 BSP 規則，Holm）。
    python3 -I judge.py runners.jsonl PROMO_BSP_DIR OUT.json"""
import csv, glob, json, math, random, statistics as st, sys
from collections import defaultdict
import numpy as np
from scipy.optimize import minimize

rows = [json.loads(l) for l in open(sys.argv[1])]
races = defaultdict(list)
for r in rows:
    races[r["market"]].append(r)
day = lambda race: race[0]["market_time"][:10]  # noqa: E731  (UTC 日期；AU 賽事全部喺同一 UTC 日)
rep = {"runners": len(rows), "races": len(races)}

# ---- 資料檢查 ----
both = sum(1 for r in rows if r["ltp5"] and r["ltp60"])
rep["check1_runner_coverage"] = both / len(rows)
promo = {}
for f in glob.glob(f"{sys.argv[2]}/dwbfpricesauswin*.csv"):
    for p in csv.DictReader(open(f)):
        try:
            d = p["event_dt"]; key = (int(p["selection_id"]), f"{d[6:10]}-{d[3:5]}-{d[0:2]}")
            promo[key] = (float(p["ppmin"]), float(p["ppmax"]))
        except (ValueError, KeyError):
            pass
inside = tot = 0
for r in rows:
    k = (r["sel"], r["market_time"][:10])
    if r["ltp5"] and k in promo:
        lo, hi = promo[k]
        if lo > 1 and hi > 1:
            tot += 1; inside += lo - 1e-9 <= r["ltp5"] <= hi + 1e-9
rep["check2_ltp5_in_pp_range"] = {"share": inside / max(1, tot), "n": tot}
early = sum(1 for race in races.values() if race[0]["inplay_pt"] and race[0]["inplay_pt"] <= race[0]["t0"] - 5 * 60000)
rep["check3_races_inplay_before_T5"] = early
books = [sum(1 / r["ltp5"] for r in race) for race in races.values() if all(r["ltp5"] for r in race)]
rep["check4_book_T5_median"] = st.median(books)
print(json.dumps(rep, ensure_ascii=False, indent=1))
ok = (rep["check1_runner_coverage"] >= 0.80 and rep["check2_ltp5_in_pp_range"]["share"] >= 0.95
      and early == 0 and 0.95 <= rep["check4_book_T5_median"] <= 1.10)
rep["checks_pass"] = ok
if not ok:
    print("資料檢查唔過 → 停（協議）"); json.dump(rep, open(sys.argv[3], "w"), indent=1, ensure_ascii=False); sys.exit(0)

# ---- 數據集：剔走有缺 LTP／BSP 嘅場 ----
R = []
for race in races.values():
    if all(r["ltp5"] and r["ltp60"] and r["ltp15"] and r["bsp"] and r["bsp"] > 1 for r in race) and sum(r["win"] for r in race) == 1 and len(race) >= 4:
        R.append(race)
R.sort(key=lambda race: race[0]["t0"])
days = sorted({day(x) for x in R}); cut = days[len(days) // 2]
dev = [x for x in R if day(x) < cut]; test = [x for x in R if day(x) >= cut]
rep.update(analysed_races=len(R), dev_races=len(dev), test_races=len(test), days=len(days), split_day=cut)

def feats(race, base):
    lp = np.log(np.array([1 / (r["ltp5"] if base == "p5" else r["bsp"]) for r in race]))
    m60 = np.log([r["ltp5"] / r["ltp60"] for r in race]); m15 = np.log([r["ltp5"] / r["ltp15"] for r in race])
    y = np.array([r["win"] for r in race])
    return lp, m60, m15, y

def nll(w, data, full):
    tot = 0.0
    for lp, m60, m15, y in data:
        s = w[0] * lp + (w[1] * m60 + w[2] * m15 if full else 0)
        s = s - s.max(); tot -= (s[y == 1][0] - math.log(np.exp(s).sum()))
    return tot / len(data)

def race_ll(w, d, full):
    lp, m60, m15, y = d; s = w[0] * lp + (w[1] * m60 + w[2] * m15 if full else 0); s = s - s.max()
    return -(s[y == 1][0] - math.log(np.exp(s).sum()))

def boot(by_day, n=2000):
    ds = sorted(by_day); rng = random.Random(7); out = []
    for _ in range(n):
        v = [x for d in (ds[rng.randrange(len(ds))] for _ in ds) for x in by_day[d]]; out.append(sum(v) / len(v))
    out.sort(); flat = [x for d in ds for x in by_day[d]]; m = sum(flat) / len(flat)
    p = 2 * min(sum(o <= 0 for o in out), sum(o >= 0 for o in out)) / n
    return {"mean": m, "ci": [out[int(0.025 * n)], out[int(0.975 * n) - 1]], "p": min(1.0, p), "n": len(flat)}

for base in ("p5", "bsp"):
    D = [feats(x, base) for x in dev]; T = [feats(x, base) for x in test]
    w0 = minimize(nll, [1, 0, 0], args=(D, False), method="Nelder-Mead").x
    w1 = minimize(nll, [1, 0, 0], args=(D, True), method="Nelder-Mead").x
    by = defaultdict(list)
    for race, d in zip(test, T):
        by[day(race)].append(race_ll(w1, d, True) - race_ll(w0, d, False))
    rep[f"Q1_{base}"] = {"w_base": list(w0), "w_full": list(w1), "dlogloss": boot(by)}
    print(f"Q1 base={base}", rep[f"Q1_{base}"])

# ---- Q2 規則（只喺 test 半） ----
def pnl(r): return (r["bsp"] - 1) * 0.95 if r["win"] else -1.0
mv = lambda r: math.log(r["ltp5"] / r["ltp60"])  # noqa: E731
rules = {"R1_follow_steam": [], "R2_fade_steam_alt": [], "R3_follow_drift": [], "R4_steam_ltp_le10": []}
for race in test:
    d = day(race); steam = [r for r in race if mv(r) <= -0.223]
    for r in steam:
        rules["R1_follow_steam"].append((d, pnl(r)))
        if r["ltp5"] <= 10: rules["R4_steam_ltp_le10"].append((d, pnl(r)))
    if steam:
        alt = [r for r in race if mv(r) > -0.051]
        if alt: rules["R2_fade_steam_alt"].append((d, pnl(min(alt, key=lambda r: r["ltp5"]))))
    for r in race:
        if mv(r) >= 0.223: rules["R3_follow_drift"].append((d, pnl(r)))
res = {}
for k, v in rules.items():
    by = defaultdict(list)
    for d, x in v: by[d].append(x)
    res[k] = boot(by) if by else None
ps = sorted((res[k]["p"], k) for k in res if res[k])
m = len(ps); adj = {}; running = 0
for i, (p, k) in enumerate(ps):
    running = max(running, min(1.0, (m - i) * p)); adj[k] = running
for k in res:
    if res[k]: res[k]["p_holm"] = adj[k]
rep["Q2"] = res
for k, v in res.items():
    print(k, None if not v else f"ROI {100*v['mean']:+.1f}% [{100*v['ci'][0]:+.1f}, {100*v['ci'][1]:+.1f}] n{v['n']} p_holm {v['p_holm']:.3f}")
q1b = rep["Q1_bsp"]["dlogloss"]["ci"][1] < 0
q2 = any(v and v["p_holm"] < 0.05 and v["ci"][0] > 0 for v in res.values())
rep["verdict"] = "WORTH_API" if (q1b or q2) else "NO_SIGNAL"
print("verdict", rep["verdict"])
json.dump(rep, open(sys.argv[3], "w"), indent=1, ensure_ascii=False, default=float)

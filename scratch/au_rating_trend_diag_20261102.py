#!/usr/bin/env python3
"""EXP-20261102-03：AU 官方評分趨勢（上仗 → 今場）診斷。協議見 docs/experiments/EXP-20261102-03-*-protocol.md。"""
import csv, glob, json, os, re, sys
from collections import defaultdict
import numpy as np
from scipy.optimize import minimize

ROOT = "/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/AU_Racing"
START, SPLIT, SEED, B = "2026-08-05", "2026-10-01", 7, 2000

def key(s): return "".join(c for c in str(s).lower() if c.isalnum())

def meeting_dirs():
    return sorted(glob.glob(ROOT + "/Archive/20*") + glob.glob(ROOT + "/20*"))

def racecard_ratings(path):
    lines = open(path, encoding="utf-8").read().splitlines()
    out = {}
    for i, line in enumerate(lines[1:], 1):
        if "| Rating:" not in line: continue
        m = re.match(r"\s*\d+\.\s*([^(]+)", lines[i - 1])
        v = line.rsplit("Rating:", 1)[1].strip()
        if m and re.fullmatch(r"\d+(?:\.\d+)?", v):
            out[key(m.group(1))] = float(v)
    return out

# 1. 評分歷史
history = defaultdict(list)          # horse -> [(date, rating)]
cards = {}                           # (dir, race) -> {horse: rating}
for d in meeting_dirs():
    date = os.path.basename(d)[:10]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date): continue
    for rc in glob.glob(d + "/* Race * Racecard.md"):
        m = re.search(r"Race (\d+) Racecard\.md$", rc)
        if not m: continue
        rn = int(m.group(1))
        r = racecard_ratings(rc)
        cards[(d, rn)] = r
        for h, v in r.items(): history[h].append((date, v))
for h in history: history[h] = sorted(set(history[h]))

def prev_rating(h, date):
    best = None
    for dt, v in history.get(h, ()):
        if dt < date: best = (dt, v)
    if best and (np.datetime64(date) - np.datetime64(best[0])).astype(int) <= 365:
        return best[1]
    return None

# 2. 賽果
res = {}
with open(ROOT + "/AU_Historical_Raw_Race_Results.csv", encoding="utf-8-sig") as f:
    for row in csv.DictReader(f):
        try: pos = int(re.sub(r"\D", "", row["Pos"]) or 0)
        except ValueError: continue
        if pos: res[(row["Date"], int(row["Race"] or 0), key(row["Horse"]))] = pos

# 3. 目標賽事
races = []
stats = defaultdict(int)
for (d, rn), today in cards.items():
    date = os.path.basename(d)[:10]
    if date < START: continue
    sc = os.path.join(d, f"Race_{rn}_Auto_Scoring.csv")
    if not os.path.exists(sc): continue
    rows = []
    for r in csv.DictReader(open(sc, encoding="utf-8")):
        h = key(r["horse_name"]); pos = res.get((date, rn, h))
        if pos is None: continue
        rt = today.get(h); pv = prev_rating(h, date) if rt is not None else None
        stats["runners"] += 1; stats["rated"] += rt is not None; stats["trend"] += pv is not None
        rows.append(dict(h=h, placed=int(pos <= 3), score=float(r["final_rank_score"] or 0),
                         form=float(r.get("form_score") or 60), rscore=float(r.get("rating_score") or 60),
                         trend=(rt - pv) if pv is not None else None))
    if len(rows) >= 5 and sum(x["trend"] is not None for x in rows) >= 4 and 0 < sum(x["placed"] for x in rows) < len(rows):
        races.append(dict(date=date, rows=rows))
print(json.dumps(stats), "races", len(races))

def pair_auc(rows, f):
    w = n = 0.0
    xs = [x for x in rows if f(x) is not None]
    for a in xs:
        if not a["placed"]: continue
        for b in xs:
            if b["placed"]: continue
            n += 1; w += 1.0 if f(a) > f(b) else 0.5 if f(a) == f(b) else 0.0
    return w, n

def boot(days_vals, stat, rng):
    days = sorted(days_vals); out = []
    for _ in range(B):
        pick = rng.choice(len(days), len(days))
        out.append(stat([days_vals[days[i]] for i in pick]))
    return np.percentile(out, [2.5, 97.5])

rng = np.random.default_rng(SEED)
by_day = defaultdict(list)
for r in races: by_day[r["date"]].append(r)

def auc_of(day_lists, f):
    W = N = 0.0
    for rs in day_lists:
        for r in rs:
            w, n = pair_auc(r["rows"], f); W += w; N += n
    return W / N if N else float("nan")

ftr = lambda x: x["trend"]
print("trend AUC %.4f" % auc_of(by_day.values(), ftr), boot(by_day, lambda L: auc_of(L, ftr), rng).round(4))
# sign split
tr = [x["trend"] for r in races for x in r["rows"] if x["trend"] is not None]
print("trend dist: n=%d up=%.1f%% same=%.1f%% down=%.1f%% median=%.1f" % (len(tr), 100*np.mean(np.array(tr) > 0), 100*np.mean(np.array(tr) == 0), 100*np.mean(np.array(tr) < 0), np.median(tr)))
for lo, hi, lab in ((-99, -3, "≤−3"), (-3, 0, "−2..−1"), (0, 0.5, "0"), (0.5, 3, "+1..+2"), (3, 99, "≥+3")):
    sel = [x["placed"] for r in races for x in r["rows"] if x["trend"] is not None and lo <= x["trend"] < hi or (lab == "0" and x["trend"] == 0)]
    print(f"  {lab:7s} n={len(sel):5d} place={100*np.mean(sel):.1f}%")

def spearman_within(f):
    vals = []
    for r in races:
        xs = [x for x in r["rows"] if x["trend"] is not None]
        if len(xs) < 4: continue
        a = np.argsort(np.argsort([x["trend"] for x in xs])); b = np.argsort(np.argsort([f(x) for x in xs]))
        if a.std() and b.std(): vals.append(np.corrcoef(a, b)[0, 1])
    return np.median(vals)
for lab, f in (("final_rank_score", lambda x: x["score"]), ("form_score", lambda x: x["form"]), ("rating_score", lambda x: x["rscore"])):
    print("median within-race rho(trend, %s) = %+.3f" % (lab, spearman_within(f)))

# 4. 增量條件 logit
def zs(v):
    v = np.array(v, float); s = v.std()
    return (v - v.mean()) / s if s > 0 else v * 0
def design(r):
    xs = r["rows"]; zA = zs([x["score"] for x in xs])
    have = [x["trend"] is not None for x in xs]
    zt = np.zeros(len(xs))
    if sum(have) >= 2:
        zt[np.array(have)] = zs([x["trend"] for x in xs if x["trend"] is not None])
    return np.c_[zA, zt], np.array([x["placed"] for x in xs])
D = [(r["date"], *design(r)) for r in races]
def nll(beta, data, cols):
    t = 0.0
    for _, X, y in data:
        u = X[:, cols] @ beta; u = u - u.max(); lp = u - np.log(np.exp(u).sum())
        t -= (lp * y).sum() / y.sum()
    return t
train = [x for x in D if x[0] < SPLIT]; test = [x for x in D if x[0] >= SPLIT]
bA = minimize(nll, [1.0], args=(train, [0])).x; bB = minimize(nll, [1.0, 0.0], args=(train, [0, 1])).x
print("train races %d test races %d  beta A %s  beta B %s" % (len(train), len(test), bA.round(4), bB.round(4)))
def per_race(data):
    out = defaultdict(list)
    for date, X, y in data:
        la = -nll(bA, [(date, X, y)], [0]); lb = -nll(bB, [(date, X, y)], [0, 1])
        sa = X[:, [0]] @ bA; sb = X[:, [0, 1]] @ bB
        rows_a = [dict(placed=int(p), s=float(s)) for p, s in zip(y, sa)]
        rows_b = [dict(placed=int(p), s=float(s)) for p, s in zip(y, sb)]
        out[date].append((lb - la, pair_auc(rows_a, lambda x: x["s"]), pair_auc(rows_b, lambda x: x["s"]), len(y)))
    return out
pt = per_race(test)
def dll(L):
    s = n = 0
    for day in L:
        for d, _, _, k in day: s += d; n += 1
    return s / n
def dauc(L):
    wa = na = wb = nb = 0
    for day in L:
        for _, (a1, a2), (b1, b2), _ in day: wa += a1; na += a2; wb += b1; nb += b2
    return wb / nb - wa / na
print("test ΔLL/race %+.5f" % dll(pt.values()), boot(pt, dll, rng).round(5))
print("test ΔAUC     %+.5f" % dauc(pt.values()), boot(pt, dauc, rng).round(5))

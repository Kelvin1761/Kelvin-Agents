"""EXP-20261116-16 tennis total games model. See PROTOCOL.md (locked before running)."""
import json, math, re, sqlite3, sys
from collections import defaultdict
from datetime import date, timedelta
import numpy as np

DB = sys.argv[1]
sys.path.insert(0, sys.argv[2])  # tennis-wong-choi/src
from tennis_wc.pricing.props import tier_of

SPLIT = "2026-09-01"
SEED = 20260826
c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)


def total_games(sets):
    tot = 0
    for i, (a, b) in enumerate(sets):
        hi, lo = max(a, b), min(a, b)
        if hi > 7:
            if i == len(sets) - 1 and len(sets) == 3:
                tot += 1
                continue
            return None
        if hi < 6 or (hi == 6 and lo > 4) or (hi == 7 and lo not in (5, 6)):
            return None
        tot += a + b
    return tot


res = defaultdict(set)
for mid, sj in c.execute("SELECT match_id, score_json FROM match_results WHERE score_json IS NOT NULL"):
    try:
        s = json.loads(sj)
    except Exception:
        continue
    sets = tuple((x["player_a_games"], x["player_b_games"]) for x in (s.get("sets") or []))
    if not sets or max(s.get("player_a_sets") or 0, s.get("player_b_sets") or 0) != 2 or len(sets) > 3:
        continue
    res[mid].add(sets)
meta = {r[0]: r[1:] for r in c.execute("""
  SELECT m.id, m.match_date, m.player_a_id, m.player_b_id, m.tour, m.start_time_utc,
    (SELECT t.name FROM tournaments t WHERE t.id=m.tournament_id),
    (SELECT tl.level FROM tournament_levels tl WHERE tl.tournament_id=m.tournament_id ORDER BY tl.id DESC LIMIT 1),
    (SELECT tl.surface FROM tournament_levels tl WHERE tl.tournament_id=m.tournament_id AND tl.surface IS NOT NULL ORDER BY tl.id DESC LIMIT 1)
  FROM matches m WHERE COALESCE(m.fixture_status,'')!='DISPUTED' AND m.match_date >= '2026-01-01'""")}
matches = []
for mid, ss in res.items():
    if len(ss) != 1 or mid not in meta:
        continue
    tg = total_games(next(iter(ss)))
    if tg is None:
        continue
    d, a, b, tour, st, tn, lvl, surf = meta[mid]
    matches.append(dict(id=mid, date=d, a=a, b=b, tour=tour if tour in ("ATP", "WTA") else "OTHER",
                        tier=tier_of(tn, lvl) if tier_of(tn, lvl) in ("TOUR", "CHALLENGER", "ITF") else "OTHER",
                        surf=(surf or "unknown").lower() if (surf or "").lower() in ("hard", "clay", "grass") else "unknown",
                        start=st, y=tg))
print(f"matches with clean Bo3 score: {len(matches)}")

# ---- as-of serve features
def player_stats(pid, d):
    lo = (date.fromisoformat(d) - timedelta(days=365)).isoformat()
    rows = c.execute("""SELECT match_date, opponent_id, hold_rate, break_rate, service_games_played
        FROM player_match_history WHERE player_id=? AND history_status='ACTIVE' AND hold_rate IS NOT NULL
        AND match_date < ? AND match_date >= ? ORDER BY id""", (pid, d, lo)).fetchall()
    seen = {}
    for md, opp, h, br, sg in rows:
        seen[(md, opp)] = (h, br if br is not None else None, sg or 10.0)
    return list(seen.values())

TOUR_MEAN = {}
def shrunk(vals, mean, k=30.0):
    num = sum(v * w for v, w in vals); den = sum(w for _, w in vals)
    return (num + k * mean) / (den + k)

dev_hold = defaultdict(list); dev_brk = defaultdict(list)
cache = {}
for m in matches:
    for p in (m["a"], m["b"]):
        cache[(p, m["date"])] = st = player_stats(p, m["date"])
        if m["date"] < SPLIT:
            for h, br, sg in st:
                dev_hold[m["tour"]].append(h)
                if br is not None: dev_brk[m["tour"]].append(br)
gh = np.mean(sum(dev_hold.values(), [])); gb = np.mean(sum(dev_brk.values(), []))
for t in ("ATP", "WTA", "OTHER"):
    TOUR_MEAN[t] = (np.mean(dev_hold[t]) if len(dev_hold[t]) > 200 else gh, np.mean(dev_brk[t]) if len(dev_brk[t]) > 200 else gb)
print("dev tour means (hold, break):", {k: (round(v[0], 3), round(v[1], 3)) for k, v in TOUR_MEAN.items()})

def elo(pid, d):
    r = c.execute("SELECT rating FROM player_elo_history_v2 WHERE player_id=? AND surface='' AND as_of_date < ? ORDER BY as_of_date DESC LIMIT 1", (pid, d)).fetchone()
    return r[0] if r else 1500.0

for m in matches:
    hm, bm = TOUR_MEAN[m["tour"]]
    for side in ("a", "b"):
        st = cache[(m[side], m["date"])]
        m[f"h{side}"] = shrunk([(h, sg) for h, _, sg in st], hm)
        m[f"k{side}"] = shrunk([(br, sg) for _, br, sg in st if br is not None], bm)
        m[f"n{side}"] = len(st)
    ra, rb = elo(m["a"], m["date"]), elo(m["b"], m["date"])
    m["q"] = abs(1 / (1 + 10 ** ((rb - ra) / 400)) - 0.5)

CATS = [("tour", ["WTA", "OTHER"]), ("tier", ["CHALLENGER", "ITF", "OTHER"]), ("surf", ["clay", "grass", "unknown"])]
def X(m, model):
    x = [1.0] + [1.0 if m[k] == v else 0.0 for k, vs in CATS for v in vs]
    if model in ("B1", "M"):
        x += [m["q"], m["q"] ** 2]
    if model == "M":
        H = m["ha"] + m["hb"]; K = m["ka"] + m["kb"]
        x += [H, K, H * (1 - 2 * m["q"]), 1.0 if min(m["na"], m["nb"]) >= 5 else 0.0]
    return x

dev = [m for m in matches if m["date"] < SPLIT]; hold = [m for m in matches if m["date"] >= SPLIT]
print(f"dev {len(dev)} ({min(m['date'] for m in dev)}..{max(m['date'] for m in dev)}), holdout {len(hold)} ({min(m['date'] for m in hold)}..{max(m['date'] for m in hold)})")
print("coverage both >=5 stats matches: dev %.1f%%, holdout %.1f%%" % (100*np.mean([min(m['na'], m['nb']) >= 5 for m in dev]), 100*np.mean([min(m['na'], m['nb']) >= 5 for m in hold])))
fits = {}
for model in ("B0", "B1", "M"):
    A = np.array([X(m, model) for m in dev]); y = np.array([m["y"] for m in dev])
    w, *_ = np.linalg.lstsq(A, y, rcond=None)
    sig = float(np.std(y - A @ w))
    fits[model] = (w, sig)
    print(f"{model}: dev RMSE {sig:.3f}  coef {np.round(w, 2).tolist()}")
for m in matches:
    for model, (w, sig) in fits.items():
        m["mu_" + model] = float(np.dot(X(m, model), w))

rng = np.random.default_rng(SEED)
yh = np.array([m["y"] for m in hold])
err = {k: (np.array([m["mu_" + k] for m in hold]) - yh) for k in fits}
for k in fits:
    print(f"holdout RMSE {k}: {np.sqrt(np.mean(err[k]**2)):.3f}  MAE {np.mean(np.abs(err[k])):.3f}")
d2 = err["M"] ** 2 - err["B1"] ** 2
st = [d2[s].mean() for s in (rng.integers(0, len(d2), len(d2)) for _ in range(4000))]
print(f"holdout ΔMSE (M - B1): {d2.mean():+.3f}  95% CI [{np.percentile(st,2.5):+.3f}, {np.percentile(st,97.5):+.3f}]")
cov = np.array([min(m['na'], m['nb']) >= 5 for m in hold])
if cov.sum() > 50:
    dc = d2[cov]; st = [dc[s].mean() for s in (rng.integers(0, len(dc), len(dc)) for _ in range(4000))]
    print(f"  (descriptive) covered subset n={cov.sum()}: ΔMSE {dc.mean():+.3f} [{np.percentile(st,2.5):+.3f}, {np.percentile(st,97.5):+.3f}]")

# ---- market check: Sportsbet two-way Match Total Games
byid = {m["id"]: m for m in matches}
first = {}
for mid, sel, line, odds, f in c.execute("""SELECT match_id, selection_name, line, odds, fetched_at FROM market_odds_snapshots
    WHERE bookmaker='Sportsbet' AND market_name='Match Total Games' ORDER BY id"""):
    m = byid.get(mid)
    if m is None or line is None or not m["start"] or not f < m["start"].replace("+00:00", "Z"):
        continue
    side = "over" if sel.lower().startswith("over") else "under" if sel.lower().startswith("under") else None
    if side and (mid, line, side) not in first:
        first[(mid, line, side)] = odds
mk = []
for (mid, line, side), oo in first.items():
    if side != "over" or (mid, line, "under") not in first:
        continue
    ou = first[(mid, line, "under")]
    if oo <= 1 or ou <= 1 or byid[mid]["y"] == line:
        continue
    io, iu = 1 / oo, 1 / ou
    mk.append(dict(m=byid[mid], line=line, oo=oo, ou=ou, pf=io / (io + iu)))
def phi(z): return 0.5 * (1 + math.erf(z / math.sqrt(2)))
def auc(s, y):
    o = np.argsort(s); r = np.empty(len(s)); r[o] = np.arange(1, len(s) + 1); n1 = y.sum(); n0 = len(y) - n1
    return (r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)
def boot_auc(s, y):
    st = []
    for _ in range(2000):
        i = rng.integers(0, len(y), len(y))
        if 0 < y[i].sum() < len(i): st.append(auc(s[i], y[i]))
    return np.percentile(st, [2.5, 97.5])
for lab, sel in (("dev", lambda r: r["m"]["date"] < SPLIT), ("holdout", lambda r: r["m"]["date"] >= SPLIT)):
    rs = [r for r in mk if sel(r)]
    # one line per match: the line closest to the market's 50/50
    best = {}
    for r in rs:
        k = r["m"]["id"]
        if k not in best or abs(r["pf"] - 0.5) < abs(best[k]["pf"] - 0.5): best[k] = r
    rs = list(best.values())
    if len(rs) < 30:
        print(f"\nmarket {lab}: {len(rs)} matches — too few"); continue
    y = np.array([r["m"]["y"] > r["line"] for r in rs]).astype(float)
    pf = np.array([r["pf"] for r in rs])
    print(f"\nmarket {lab}: {len(rs)} matches; Sportsbet over hit {y.mean():.3f} vs fair {pf.mean():.3f}")
    for model in ("B1", "M"):
        w, sig = fits[model]
        pm = np.array([1 - phi((r["line"] - r["m"]["mu_" + model]) / sig) for r in rs])
        a_m, a_g = auc(pm, y), auc(pm - pf, y)
        lo, hi = boot_auc(pm - pf, y)
        pl, pl5 = [], []
        for p, r, yy in zip(pm, rs, y):
            evo, evu = r["oo"] * p - 1, r["ou"] * (1 - p) - 1
            ev, win, o = (evo, yy == 1, r["oo"]) if evo >= evu else (evu, yy == 0, r["ou"])
            if ev > 0: pl.append(o - 1 if win else -1.0)
            if ev > 0.05: pl5.append(o - 1 if win else -1.0)
        def ci(v):
            v = np.array(v); s = [v[rng.integers(0, len(v), len(v))].mean() for _ in range(4000)]
            return v.mean(), *np.percentile(s, [2.5, 97.5])
        txt = f"  {model}: AUC model {a_m:.3f} | market {auc(pf, y):.3f} | gap AUC {a_g:.3f} [{lo:.3f}, {hi:.3f}]"
        if pl:
            r0 = ci(pl); txt += f" | EV>0 {len(pl)} bets ROI {r0[0]*100:+.1f}% [{r0[1]*100:+.1f}, {r0[2]*100:+.1f}]"
        if pl5:
            r5 = ci(pl5); txt += f" | EV>5% {len(pl5)} bets ROI {r5[0]*100:+.1f}% [{r5[1]*100:+.1f}, {r5[2]*100:+.1f}]"
        print(txt)

"""EXP-20261103-13 evaluation, exactly as pre-registered in the protocol.

Inputs: replay JSONL (legacy candidates + B2 picks), archived sidecar legs (C and S_v4
probabilities), ledger settlements. One run, prints every arm.

Harness details fixed before results (not in the protocol table, recorded here):
* K arms enumerate every 2-4 leg combination of the 15 highest-probability eligible legs
  per game (all combinations would be identical in practice: the joint-prob maximiser
  never reaches below the top 15).
* Eligible = player milestone over leg with a settlement, not day-to-day, not bench-risk
  (the same availability facts B2 uses), price > 1.
* A combo with any void leg is dropped from that arm's count.

usage: python3 evaluate.py <replay_dir> <analysis_root> <ledger_dir>
"""
import itertools
import json
import math
import random
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression

replay_dir, root, ledger = (Path(a) for a in sys.argv[1:4])
DEV_END = "2026-10-28"
HOLDOUT = {"2026-10-29", "2026-11-01", "2026-11-02", "2026-11-03"}
if "--dev-only" in sys.argv:  # harness debugging; never prints a holdout number
    HOLDOUT = set()
STAT = {"pts": "PTS", "reb": "REB", "ast": "AST", "fg3m": "FG3M", "3PM": "FG3M"}
SEED, DRAWS = 20261103, 2000

# --- settlements -----------------------------------------------------------
y = {}
for f in ledger.glob("*.jsonl"):
    for line in f.open():
        r = json.loads(line)
        if r.get("row_type") == "settlement" and r.get("side", "over") == "over":
            y[(r["target_date"], r["game_tag"], r["player"], STAT[r["market"]], float(r["line"]))] = r["outcome"]

# --- archived probabilities ---------------------------------------------------
probs = {}
for sc in root.glob("* NBA Analysis/Game_*_Full_Analysis.md.market_legs.json"):
    day = sc.parent.name.split()[0]
    tag = sc.name[len("Game_"):-len("_Full_Analysis.md.market_legs.json")]
    for leg in json.loads(sc.read_text())["legs"]:
        if leg["market"] in STAT:
            probs[(day, tag, leg["player"], STAT[leg["market"]], float(leg["line"]))] = (
                leg.get("p_final"), leg.get("season_rate_v4_prob_S"))

# S recomputed with nba_engine.model from each day's ESPN game data (bit-identical to the
# archived S_v4 where both exist, parity_model.py); the archive only has S from 10-26.
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / ".agents/skills/nba"))
from nba_engine import model  # noqa: E402
from nba_identity import player_name_key  # noqa: E402
_gd = {}
def s_new(day, tag, team, player, stat, line):
    if (day, tag) not in _gd:
        f = root / f"{day} NBA Analysis" / f"nba_game_data_{tag}.json"
        _gd[(day, tag)] = json.loads(f.read_text()) if f.exists() else None
    gd = _gd[(day, tag)]
    if not gd:
        return None
    p = next((p for p in gd["players"].get(team, []) if player_name_key(p["name"]) == player_name_key(player)), None)
    if p is None:
        return None
    return model.s_prob((p.get("gamelog") or {}).get("season_log"), stat, line,
                        (gd.get("opponent_context") or {}).get(team), gd["meta"].get("roster_season"), team)

# --- legacy candidates + B2 -------------------------------------------------
rows, b2 = [], defaultdict(list)
for f in replay_dir.glob("*.jsonl"):
    for line in f.open():
        r = json.loads(line)
        if r.get("market_type") != "PLAYER_MILESTONE":
            continue
        key = (r["day"], r["game"], r["player"], STAT.get(r["category"], r["category"]), float(r["line_val"]))
        c, _ = probs.get(key, (None, None))
        s = s_new(r["day"], r["game"], r["team"], r["player"], key[3], key[4])
        r.update(key=key, y=y.get(key), C=c, S=s, M=1 / r["odds"])
        rows.append(r)
        if r["b2_pick"]:
            b2[(r["day"], r["game"])].append(r)
games = sorted({(r["day"], r["game"]) for r in rows})
print(f"rows={len(rows)} settled={sum(r['y'] in ('hit','miss') for r in rows)} games={len(games)} "
      f"with C={sum(r['C'] is not None for r in rows)} with S={sum(r['S'] is not None for r in rows)}")

def is_holdout(day):
    return day in HOLDOUT

scored = [r for r in rows if r["y"] in ("hit", "miss") and r["C"] is not None and r["S"] is not None]
for r in scored:
    r["Y"] = 1 if r["y"] == "hit" else 0

# --- MS: fit on dev only -----------------------------------------------------
def lg(p):
    p = min(max(p, 0.02), 0.98)
    return math.log(p / (1 - p))

stats = ["PTS", "REB", "AST", "FG3M"]
def design(r):
    return [1.0 * (r["key"][3] == s) for s in stats] + [lg(r["M"]), lg(r["S"])]

dev = [r for r in scored if r["day"] <= DEV_END]
fit = LogisticRegression(penalty=None, fit_intercept=False, max_iter=2000).fit(
    np.array([design(r) for r in dev]), np.array([r["Y"] for r in dev]))
print("MS coef (a_PTS,a_REB,a_AST,a_FG3M,beta_M,gamma_S):", np.round(fit.coef_[0], 4).tolist())
for r in rows:
    r["MS"] = (float(fit.predict_proba(np.array([design(r)]))[0, 1])
               if r["S"] is not None else None)

# --- probability metrics --------------------------------------------------
def ll(p, yv):
    p = min(max(p, 1e-4), 1 - 1e-4)
    return -(yv * math.log(p) + (1 - yv) * math.log(1 - p))

def by_day_boot(items, fn, days):
    rng = random.Random(SEED)
    out = []
    groups = defaultdict(list)
    for it in items:
        groups[it["day"]].append(it)
    for _ in range(DRAWS):
        sample = [it for d in (rng.choice(days) for _ in days) for it in groups[d]]
        out.append(fn(sample))
    out.sort()
    return out[int(0.025 * DRAWS)], out[int(0.975 * DRAWS) - 1]

print("\n## Probability (leg level)")
for split, sel in (("dev", lambda d: d <= DEV_END), ("holdout", is_holdout)):
    part = [r for r in scored if sel(r["day"])]
    if not part:
        continue
    days = sorted({r["day"] for r in part})
    base = sum(ll(r["C"], r["Y"]) for r in part) / len(part)
    print(f"{split}: n={len(part)} days={len(days)}")
    for arm in ("M", "C", "S", "MS"):
        loss = sum(ll(r[arm], r["Y"]) for r in part) / len(part)
        brier = sum((r[arm] - r["Y"]) ** 2 for r in part) / len(part)
        hi = [r for r in part if r[arm] >= 0.7]
        zone = (sum(r["Y"] for r in hi) / len(hi) - sum(r[arm] for r in hi) / len(hi)) if hi else float("nan")
        lo, up = by_day_boot(part, lambda s, a=arm: (sum(ll(r[a], r["Y"]) - ll(r["C"], r["Y"]) for r in s) / len(s)), days)
        print(f"  {arm:3s} logloss={loss:.4f} brier={brier:.4f} d_vs_C={loss-base:+.4f} [{lo:+.4f},{up:+.4f}] "
              f"p>=0.7: n={len(hi)} actual-pred={zone:+.3f}")

# --- selection ---------------------------------------------------------------
def allowed(combo):
    players = [r["player"] for r in combo]
    if len(set(players)) != len(players):
        return False
    teams = defaultdict(int)
    pts = defaultdict(int)
    for r in combo:
        teams[r["team"]] += 1
        pts[r["team"]] += r["key"][3] == "PTS"
    return max(teams.values()) <= 3 and max(pts.values()) <= 2

def price(combo):
    return math.prod(r["odds"] for r in combo)

def pick(game_rows, arm, value_check=False):
    pool = [r for r in game_rows if r[arm] is not None and r["y"] in ("hit", "miss", "void")
            and not r.get("day_to_day") and not r.get("bench_minutes_risk") and r["odds"] > 1
            and (not value_check or r[arm] >= r["M"])]
    pool = sorted(pool, key=lambda r: -r[arm])[:15]
    best, best_p = None, -1
    for n in (2, 3, 4):
        for combo in itertools.combinations(pool, n):
            if 2.0 <= price(combo) <= 4.0 and allowed(combo):
                p = math.prod(r[arm] for r in combo)
                if p > best_p:
                    best, best_p = list(combo), p
    return best

by_game = defaultdict(list)
for r in rows:
    by_game[(r["day"], r["game"])].append(r)

def outcome(combo):
    if not combo or any(r["y"] not in ("hit", "miss") for r in combo):
        return None
    return all(r["y"] == "hit" for r in combo)

arms = {"B2": lambda g: b2.get(g) or None,
        "K-C": lambda g: pick(by_game[g], "C"),
        "K-S": lambda g: pick(by_game[g], "S", value_check=True),
        "K-MS": lambda g: pick(by_game[g], "MS")}
print("\n## Selection (one combo per game, product-of-legs price)")
results = {}
for name, fn in arms.items():
    for g in games:
        combo = fn(g)
        results[(name, g)] = (outcome(combo), price(combo) if combo else None, combo)

def summary(name, sel):
    rows_ = [(g, *results[(name, g)][:2]) for g in games if sel(g[0]) and results[(name, g)][0] is not None]
    n = len(rows_)
    hits = sum(o for _, o, _ in rows_)
    profit = sum((p - 1) if o else -1 for _, o, p in rows_)
    return n, hits, profit

for split, sel in (("dev", lambda d: d <= DEV_END), ("holdout", is_holdout)):
    print(f"{split}:")
    for name in arms:
        n, hits, profit = summary(name, sel)
        print(f"  {name:5s} combos={n:3d} hit={hits:3d} ({hits / n if n else float('nan'):.1%}) "
              f"proxy ROI={profit / n if n else float('nan'):+.1%}")
    hold_days = sorted({g[0] for g in games if sel(g[0])})
    for name in ("K-C", "K-S", "K-MS"):
        def diff(sample_days, name=name):
            def rate(arm):
                xs = [results[(arm, g)][0] for d in sample_days for g in games
                      if g[0] == d and results[(arm, g)][0] is not None]
                return sum(xs) / len(xs) if xs else 0.0
            return rate(name) - rate("B2")
        rng = random.Random(SEED)
        ds = sorted(diff([rng.choice(hold_days) for _ in hold_days]) for _ in range(DRAWS))
        print(f"  {name} - B2 hit rate: {diff(hold_days):+.1%} [{ds[int(.025*DRAWS)]:+.1%}, {ds[int(.975*DRAWS)-1]:+.1%}]")

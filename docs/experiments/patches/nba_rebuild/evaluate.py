"""EXP-20261103-15 evaluation, exactly as pre-registered in the protocol.

Inputs: replay JSONL (legacy candidates + B2 picks), archived sidecar legs (C and S_v4
probabilities), ledger settlements. One run, prints every arm.

Harness details fixed before results (not in the protocol table, recorded here):
* K arms use nba_engine.select.best_combo -- the live selector's exact branch-and-bound
  search over every eligible leg (amendment 3: the first harness cut the pool to the top
  15 by probability, which made the 2.0 floor unreachable; bug, fixed before holdout).
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

# S from as-of rebuilt ESPN inputs (protocol amendment 1): each player's newest season_log
# cut to games before the game's US day; opponent table from the 11-03 ESPN team bundle,
# whose opponent_context() filters by the same cutoff day.
NBA = Path(__file__).resolve().parents[4] / ".agents/skills/nba"
sys.path[:0] = [str(NBA), str(NBA / "nba_data_extractor/scripts")]
from datetime import date, datetime  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402
from nba_engine import model  # noqa: E402
from nba_identity import player_name_key  # noqa: E402
import nba_team_context  # noqa: E402

BUNDLE = json.loads((root / "2026-11-03 NBA Analysis" / "NBA_Team_Context.json").read_text())
LOGS = {}   # (team, name key) -> newest season_log carrying per-game teams
for f in root.glob("* NBA Analysis/nba_game_data_*.json"):
    for team, ps in json.loads(f.read_text())["players"].items():
        for p in ps:
            log = (p.get("gamelog") or {}).get("season_log") or {}
            if not log.get("dates") or not log.get("teams"):
                continue
            k = (team, player_name_key(p["name"]))
            if k not in LOGS or (log["dates"][0], len(log["dates"])) > (LOGS[k]["dates"][0], len(LOGS[k]["dates"])):
                LOGS[k] = log
CUTOFF, OPP = {}, {}
def game_context(day, tag):
    if (day, tag) not in CUTOFF:
        sb = json.loads((root / f"{day} NBA Analysis" / f"Sportsbet_Odds_{tag}.json").read_text())
        start = datetime.fromisoformat(str(sb["event_start_time"]).replace("Z", "+00:00"))
        CUTOFF[(day, tag)] = start.astimezone(ZoneInfo("America/New_York")).date()
    return CUTOFF[(day, tag)]

def truncated(log, cutoff):
    keep = [i for i, d in enumerate(log["dates"]) if date.fromisoformat(d) < cutoff]
    out = {k: ([v[i] for i in keep] if isinstance(v, list) and len(v) == len(log["dates"]) else v)
           for k, v in log.items()}
    assert all(date.fromisoformat(d) < cutoff for d in out["dates"])
    return out

def s_new(day, tag, team, player, stat, line):
    log = LOGS.get((team, player_name_key(player)))
    if log is None:
        return None
    cutoff = game_context(day, tag)
    a, h = tag.split("_")
    opp = h if team == a else a
    if (opp, cutoff) not in OPP:
        OPP[(opp, cutoff)] = nba_team_context.opponent_context(BUNDLE, opp, cutoff)
    return model.s_prob(truncated(log, cutoff), stat, line, OPP[(opp, cutoff)], "2026-27", team)

# --- legacy candidates + B2 -------------------------------------------------
rows, b2 = [], defaultdict(list)
for f in replay_dir.glob("*.jsonl"):
    for line in f.open():
        r = json.loads(line)
        if r.get("market_type") != "PLAYER_MILESTONE":
            continue
        key = (r["day"], r["game"], r["player"], STAT.get(r["category"], r["category"]), float(r["line_val"]))
        c, _ = probs.get(key, (None, None))
        s_rebuilt = s_new(r["day"], r["game"], r["team"], r["player"], key[3], key[4])
        s_arch = probs.get(key, (None, None))[1]
        s = s_arch if s_arch is not None else s_rebuilt   # amendment 2
        r["S_rebuilt"], r["S_archived"] = s_rebuilt, s_arch
        r.update(key=key, y=y.get(key), C=c, S=s, M=1 / r["odds"])
        rows.append(r)
        if r["b2_pick"]:
            b2[(r["day"], r["game"])].append(r)
games = sorted({(r["day"], r["game"]) for r in rows})
_d = sorted(abs(r["S_rebuilt"] - r["S_archived"]) for r in rows
            if r["S_rebuilt"] is not None and r["S_archived"] is not None)
if _d:
    print(f"S rebuild vs archived S_v4: legs={len(_d)} median|diff|={_d[len(_d)//2]:.4f} "
          f"p95={_d[int(.95*len(_d))]:.4f} max={_d[-1]:.4f} exact(<1e-4)={sum(x < 1e-4 for x in _d)/len(_d):.1%}")
print(f"S source: archived={sum(r['S_archived'] is not None for r in rows)} "
      f"rebuilt-only={sum(r['S_archived'] is None and r['S_rebuilt'] is not None for r in rows)} "
      f"none={sum(r['S'] is None for r in rows)}")
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from joint_search import Policy, best_combo  # noqa: E402  (was nba_engine/select.py at 6f1871f8)
POLICY = Policy()

def pick(game_rows, arm, value_check=False):
    pool = [r for r in game_rows if r[arm] is not None and r["y"] in ("hit", "miss", "void")
            and not r.get("day_to_day") and not r.get("bench_minutes_risk") and r["odds"] > 1
            and (not value_check or r[arm] >= r["M"])]
    combo, _ = best_combo(pool, lambda r: r[arm], lambda r: r["odds"], lambda r: r["player"],
                          lambda r: r["team"], lambda r: r["key"][3] == "PTS", POLICY)
    return combo or None

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

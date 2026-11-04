"""EXP-20261104-13: teammate absence shift (out today vs recently) -- model term (H1) and bets (H2).

usage: python3 analyse.py <repo_root> <analysis_root> <ledger_dir>
Runs once; prints dev and holdout for every pre-registered measure.
"""
import json
import math
import random
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

repo, root, ledger = (Path(a) for a in sys.argv[1:4])
sys.path.insert(0, str(repo / ".agents/skills/nba"))
from nba_availability import classify_injury_status  # noqa: E402
from nba_engine.legs import MARKET, build_legs  # noqa: E402
from nba_identity import player_name_key as key  # noqa: E402
from nba_schedule import canonical_team_abbr as canon  # noqa: E402

DEV_END = "2026-10-28"
HOLDOUT = {"2026-10-29", "2026-11-01", "2026-11-02", "2026-11-03"}
STATS = ("PTS", "REB", "AST", "FG3M")
ROTATION_MIN = 20.0
RECENT_TEAM_GAMES = 5
SEED, DRAWS = 20261104, 2000

# outcomes
y = {}
for f in ledger.glob("*.jsonl"):
    for line in f.open():
        r = json.loads(line)
        if r.get("row_type") == "settlement" and r.get("side", "over") == "over" and r["outcome"] in ("hit", "miss"):
            y[(r["target_date"], r["game_tag"], key(r["player"]), r["market"], float(r["line"]))] = int(r["outcome"] == "hit")

# newest season log per (team, player): rebuilt as-of by truncation (EXP-20261103-15 amendment 1)
LOGS = {}
for f in root.glob("* NBA Analysis/nba_game_data_*.json"):
    for team, ps in json.loads(f.read_text())["players"].items():
        for p in ps:
            log = (p.get("gamelog") or {}).get("season_log") or {}
            if log.get("dates"):
                k = (canon(team), key(p["name"]))
                if k not in LOGS or (log["dates"][0], len(log["dates"])) > (LOGS[k]["dates"][0], len(LOGS[k]["dates"])):
                    LOGS[k] = log

bundle = json.loads((root / "2026-11-03 NBA Analysis" / "NBA_Team_Context.json").read_text())
TEAM_GAMES = defaultdict(list)   # team -> [(date, {stat: value})]
for r in bundle["tables"]["Regular Season"]["rows"]:
    TEAM_GAMES[canon(r["TEAM_ABBREVIATION"])].append((date.fromisoformat(r["GAME_DATE"][:10]), {s: float(r[s]) for s in STATS}))


def played(log, cutoff):
    """Dates (< cutoff) the player appeared, newest first, with per-game stats."""
    out = []
    for i, d in enumerate(log["dates"]):
        dd = date.fromisoformat(d)
        if dd < cutoff and float(log["MIN"][i]) > 0:
            out.append((dd, {s: float(log[s][i]) for s in (*STATS, "MIN")}))
    return out


def shift_for(team, player, cutoff, pkg):
    team_games = sorted((g for g in TEAM_GAMES[team] if g[0] < cutoff), key=lambda g: g[0], reverse=True)
    if not team_games:
        return None
    recent_dates = [g[0] for g in team_games[:RECENT_TEAM_GAMES]]
    team_mean = {s: sum(g[1][s] for g in team_games[:10]) / len(team_games[:10]) for s in STATS}
    injuries = {key(n): classify_injury_status(st) for n, st in ((pkg.get("injuries") or {}).get(team) or {}).items()}
    shift = {s: 0.0 for s in STATS}
    for mate in (pkg.get("players") or {}).get(team, []):
        mk = key(mate.get("name", ""))
        if mk == player:
            continue
        mins = [float(m) for m in (mate.get("gamelog") or {}).get("MIN") or []]
        if not mins or sum(mins) / len(mins) < ROTATION_MIN:
            continue
        log = LOGS.get((team, mk))
        if not log:
            continue
        games = played(log, cutoff)
        if not games:
            continue
        on = {d for d, _ in games}
        recent_absent = sum(d not in on for d in recent_dates) / len(recent_dates)
        today = 1.0 if injuries.get(mk) == "out" else 0.0
        last10 = games[:10]
        for s in STATS:
            share = (sum(g[s] for _, g in last10) / len(last10)) / team_mean[s] if team_mean[s] else 0.0
            shift[s] += share * (today - recent_absent)
    return shift


rows = []
for day_dir in sorted(root.glob("2026-1* NBA Analysis")):
    day = day_dir.name.split()[0]
    for gd in sorted(day_dir.glob("nba_game_data_*.json")):
        tag = gd.stem.replace("nba_game_data_", "")
        sb = day_dir / f"Sportsbet_Odds_{tag}.json"
        if not sb.exists():
            continue
        odds, pkg = json.loads(sb.read_text()), json.loads(gd.read_text())
        start = datetime.fromisoformat(str(odds["event_start_time"]).replace("Z", "+00:00"))
        cutoff = start.astimezone(ZoneInfo("America/New_York")).date()
        legs, _ = build_legs(odds, pkg)
        cache = {}
        for l in legs:
            k = (day, tag, key(l.player), MARKET[l.stat], l.line)
            if k not in y or l.p_final is None:
                continue
            team = canon(l.team)
            if team not in cache:
                cache[team] = {}
            pk = key(l.player)
            if pk not in cache[team]:
                cache[team][pk] = shift_for(team, pk, cutoff, pkg)
            sh = cache[team][pk]
            if sh is None:
                continue
            rows.append({"day": day, "stat": l.stat, "p": l.p_final, "price": l.price, "y": y[k], "shift": sh[l.stat]})

print(f"legs: {len(rows)} (dev {sum(r['day'] <= DEV_END for r in rows)}, holdout {sum(r['day'] in HOLDOUT for r in rows)})")
for lo, hi, name in ((0.10, 9, "shift>=+0.10"), (-9, -0.10, "shift<=-0.10"), (-0.10, 0.10, "|shift|<0.10")):
    print(f"  {name}: {sum(lo <= r['shift'] < hi if hi < 9 else r['shift'] >= lo for r in rows)}")

# --- H1: fit delta_s on dev with logit(p_final) as offset -----------------------
def lg(p):
    p = min(max(p, 1e-4), 1 - 1e-4)
    return math.log(p / (1 - p))

def X(r):
    return np.array([r["shift"] * (r["stat"] == s) for s in STATS])

dev = [r for r in rows if r["day"] <= DEV_END]
Xd = np.array([X(r) for r in dev]); od = np.array([lg(r["p"]) for r in dev]); yd = np.array([r["y"] for r in dev])
delta = np.zeros(len(STATS))
for _ in range(50):
    z = od + Xd @ delta
    p = 1 / (1 + np.exp(-z))
    g = Xd.T @ (yd - p)
    H = (Xd * (p * (1 - p))[:, None]).T @ Xd + 1e-6 * np.eye(len(STATS))
    step = np.linalg.solve(H, g)
    delta += step
    if np.abs(step).max() < 1e-9:
        break
print("\nH1 delta per stat (dev fit):", dict(zip(STATS, np.round(delta, 3))))

def cand(r):
    return 1 / (1 + math.exp(-(lg(r["p"]) + float(X(r) @ delta))))

def ll(p, yv):
    p = min(max(p, 1e-4), 1 - 1e-4)
    return -(yv * math.log(p) + (1 - yv) * math.log(1 - p))

def dll(part):
    return sum(ll(cand(r), r["y"]) - ll(r["p"], r["y"]) for r in part) / len(part)

def boot(part, fn):
    days = sorted({r["day"] for r in part})
    by = defaultdict(list)
    for r in part:
        by[r["day"]].append(r)
    rng = random.Random(SEED)
    vals = sorted(fn([r for d in (rng.choice(days) for _ in days) for r in by[d]]) for _ in range(DRAWS))
    return vals[int(.025 * DRAWS)], vals[int(.975 * DRAWS) - 1]

for name, sel in (("dev", lambda d: d <= DEV_END), ("holdout", lambda d: d in HOLDOUT)):
    part = [r for r in rows if sel(r["day"])]
    lo, hi = boot(part, dll)
    base = sum(ll(r["p"], r["y"]) for r in part) / len(part)
    print(f"{name}: n={len(part)} base logloss {base:.4f}  delta(cand-base) {dll(part):+.5f} [{lo:+.5f}, {hi:+.5f}]")
    for gname, gsel in (("shift>=+0.10", lambda s: s >= 0.10), ("shift<=-0.10", lambda s: s <= -0.10)):
        g = [r for r in part if gsel(r["shift"])]
        if g:
            glo, ghi = boot(g, dll) if len({r['day'] for r in g}) > 1 else (float("nan"), float("nan"))
            print(f"    {gname}: n={len(g)} delta {dll(g):+.5f} [{glo:+.5f}, {ghi:+.5f}]  "
                  f"base calib (actual - p) {sum(r['y'] - r['p'] for r in g) / len(g):+.3f}")

# --- H2: bets -------------------------------------------------------------------
def roi(part):
    return sum(r["y"] * r["price"] - 1 for r in part) / len(part) if part else float("nan")

print("\nH2 flat ROI at Sportsbet price (calib = actual - 1/price)")
for name, sel in (("dev", lambda d: d <= DEV_END), ("holdout", lambda d: d in HOLDOUT)):
    part = [r for r in rows if sel(r["day"])]
    groups = {"absorber (shift>=+0.10)": [r for r in part if r["shift"] >= 0.10],
              "returner (shift<=-0.10)": [r for r in part if r["shift"] <= -0.10],
              "control": [r for r in part if -0.10 < r["shift"] < 0.10]}
    ctrl = groups["control"]
    for gname, g in groups.items():
        if not g:
            print(f"  {name} {gname}: n=0"); continue
        calib = sum(r["y"] - 1 / r["price"] for r in g) / len(g)
        lo, hi = boot(g, roi) if len({r['day'] for r in g}) > 1 else (float("nan"), float("nan"))
        extra = ""
        if gname != "control":
            gid = {id(r) for r in g}
            def diff(s):
                a = [r for r in s if id(r) in gid]; c = [r for r in s if id(r) not in gid]
                return (roi(a) if a else 0.0) - roi(c)
            dlo, dhi = boot(g + ctrl, diff)
            extra = f" | minus control {roi(g) - roi(ctrl):+.3f} [{dlo:+.3f}, {dhi:+.3f}]"
        print(f"  {name} {gname}: n={len(g)} ROI {roi(g):+.3f} [{lo:+.3f}, {hi:+.3f}] calib {calib:+.3f}{extra}")

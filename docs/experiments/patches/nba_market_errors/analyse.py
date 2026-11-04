"""EXP-20261104-12: market mispricing by segment (H1) and late injury news (H2).

usage: python3 analyse.py <ledger_dir> <analysis_root> <repo_root>
Runs once, prints every pre-registered segment for dev and holdout.
"""
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

ledger, root, repo = (Path(a) for a in sys.argv[1:4])
sys.path.insert(0, str(repo / ".agents/skills/nba"))
from nba_identity import player_name_key as key  # noqa: E402

DEV_END = "2026-10-28"
SEED, DRAWS = 20261104, 2000

rows = defaultdict(list)
for f in sorted(ledger.glob("*.jsonl")):
    for line in f.open():
        r = json.loads(line)
        rows[r.get("row_type")].append(r)

leg_id = lambda r: (r["target_date"], r["game_tag"], key(r["player"]), r["market"], float(r["line"]))  # noqa: E731

# --- outcome ------------------------------------------------------------------
y = {}
for r in rows["settlement"]:
    if r.get("side", "over") == "over" and r["outcome"] in ("hit", "miss"):
        y[leg_id(r)] = 1 if r["outcome"] == "hit" else 0

# --- the 21:00 publication price: first production snapshot per game --------------
first_prod = {}
for r in rows["model_obs"]:
    if r.get("snapshot_role") != "production" or r.get("post_tip"):
        continue
    g = (r["target_date"], r["game_tag"])
    if g not in first_prod or r["snapshot_created_at"] < first_prod[g]:
        first_prod[g] = r["snapshot_created_at"]
pub = {}
for r in rows["model_obs"]:
    g = (r["target_date"], r["game_tag"])
    if r.get("snapshot_role") == "production" and r["snapshot_created_at"] == first_prod.get(g) \
            and r.get("side", "over") == "over" and r.get("price_at_model"):
        pub[leg_id(r)] = r

close = {}
for r in rows["price_obs"]:
    if r.get("post_tip") or r.get("side", "over") != "over":
        continue
    k = leg_id(r)
    if k not in close or r["captured_at"] > close[k][0]:
        close[k] = (r["captured_at"], float(r["price"]))

# --- player role from the archived game package -----------------------------------
_pkg = {}
def player_info(day, tag, team, player):
    if (day, tag) not in _pkg:
        f = root / f"{day} NBA Analysis" / f"nba_game_data_{tag}.json"
        _pkg[(day, tag)] = json.loads(f.read_text()) if f.exists() else None
    pkg = _pkg[(day, tag)]
    if not pkg:
        return None
    p = next((p for p in (pkg.get("players") or {}).get(team, []) if key(p.get("name", "")) == player), None)
    if not p:
        return None
    gl = p.get("gamelog") or {}
    mins = [float(m) for m in gl.get("MIN") or []]
    teams = {str(m).split()[0] for m in gl.get("l10_matchups") or [] if str(m).split()}
    return {"minutes": sum(mins) / len(mins) if mins else None,
            "games": gl.get("games_played") or len(gl.get("dates") or gl.get("PTS") or []),
            "moved": bool(teams - {team})}

legs = []
for k, m in pub.items():
    if k not in y:
        continue
    day, tag, player, market, line = k
    team = m.get("team")
    info = player_info(day, tag, team, player) or {}
    price = float(m["price_at_model"])
    legs.append({"day": day, "game": tag, "team": team, "player": player, "market": market, "line": line,
                 "y": y[k], "price": price, "close": close.get(k, (None, None))[1],
                 "p_s": m.get("season_rate_v4_prob_S"), "home": tag.split("_")[1] == team, **info})
print(f"legs with publication price + result: {len(legs)} (dev {sum(l['day'] <= DEV_END for l in legs)}, "
      f"holdout {sum(l['day'] > DEV_END for l in legs)}); with S: {sum(l['p_s'] is not None for l in legs)}")

# --- metrics ------------------------------------------------------------------
def roi(ls, price="price"):
    ls = [l for l in ls if l[price]]
    return sum(l["y"] * l[price] - 1 for l in ls) / len(ls) if ls else float("nan")

def calib(ls):
    return (sum(l["y"] for l in ls) - sum(1 / l["price"] for l in ls)) / len(ls) if ls else float("nan")

def boot(ls, fn):
    days = sorted({l["day"] for l in ls})
    by = defaultdict(list)
    for l in ls:
        by[l["day"]].append(l)
    rng = random.Random(SEED)
    vals = sorted(fn([l for d in (rng.choice(days) for _ in days) for l in by[d]]) for _ in range(DRAWS))
    return vals[int(.025 * DRAWS)], vals[int(.975 * DRAWS) - 1]

def band(p, cuts, labels):
    for c, lab in zip(cuts, labels):
        if p < c:
            return lab
    return labels[-1]

STAT = {"pts": "PTS", "reb": "REB", "ast": "AST", "fg3m": "3PM"}
families = {
    "A 項目": lambda l: STAT.get(l["market"], l["market"]),
    "B 發佈價": lambda l: band(l["price"], [1.3, 1.6, 2.2, 4, 10], ["<1.30", "1.30-1.60", "1.60-2.20", "2.20-4.00", "4-10", ">=10"]),
    "C 分鐘": lambda l: None if l.get("minutes") is None else band(l["minutes"], [20, 28, 34], ["<20", "20-28", "28-34", ">=34"]),
    "D 往績": lambda l: None if l.get("games") is None else ("少樣本<15" if l["games"] < 15 else "轉隊" if l.get("moved") else "其他"),
    "E 主客": lambda l: "主" if l["home"] else "客",
    "F S-市場": lambda l: None if l["p_s"] is None else band(100 * (l["p_s"] - 1 / l["price"]), [-10, -3, 3, 10], ["<=-10", "-10..-3", "-3..3", "3..10", ">=10"]),
}

print("\n## H1 segments (flat ROI at 21:00 price; calib = actual - 1/price)")
candidates = []
for fam, fn in families.items():
    print(f"\n{fam}")
    groups = defaultdict(list)
    for l in legs:
        g = fn(l)
        if g is not None:
            groups[g].append(l)
    for g in sorted(groups):
        dev = [l for l in groups[g] if l["day"] <= DEV_END]
        hold = [l for l in groups[g] if l["day"] > DEV_END]
        line = f"  {g:12s} dev n={len(dev):5d} ROI {roi(dev):+.3f} calib {calib(dev):+.3f} | hold n={len(hold):5d} ROI {roi(hold):+.3f} calib {calib(hold):+.3f}"
        if dev and roi(dev) > 0 and len(dev) >= 150:
            candidates.append((fam, g, hold))
            line += "  <- candidate"
        print(line)

print(f"\nholdout tests for {len(candidates)} candidate(s), Holm over {len(candidates)}:")
for i, (fam, g, hold) in enumerate(candidates):
    lo, hi = boot(hold, roi) if hold else (float("nan"), float("nan"))
    print(f"  {fam} {g}: holdout ROI {roi(hold):+.3f} [{lo:+.3f}, {hi:+.3f}] n={len(hold)}")
if not candidates:
    print("  none")

print("\nall legs: dev ROI %+.3f, holdout ROI %+.3f; close-price ROI dev %+.3f holdout %+.3f" % (
    roi([l for l in legs if l['day'] <= DEV_END]), roi([l for l in legs if l['day'] > DEV_END]),
    roi([l for l in legs if l['day'] <= DEV_END], 'close'), roi([l for l in legs if l['day'] > DEV_END], 'close')))

# --- H2: late scratches after the 21:00 publication -------------------------------
def level(r):
    lv = {r.get("espn_level"), r.get("official_level")}
    return "out" if "out" in lv else "dtd" if "dtd" in lv else "ok"

status = defaultdict(dict)   # (day, game) -> snapshot_created_at -> {(team, player): level}
roles = {}
for r in rows["availability_obs"]:
    if r.get("post_tip"):
        continue
    g = (r["target_date"], r["game_tag"])
    status[g].setdefault(r["snapshot_created_at"], {})[(r["team"], key(r["player"]))] = level(r)
    roles[(g, r["snapshot_created_at"])] = r.get("snapshot_role")

events = []   # (day, game, team, player)
for g, snaps in status.items():
    prod_at = first_prod.get(g)
    if not prod_at:
        continue
    before = snaps.get(prod_at, {})
    later = {who: lv for at in sorted(s for s in snaps if s > prod_at) for who, lv in snaps[at].items()}
    for (team, player), lv in later.items():
        if lv == "out" and before.get((team, player), "ok") != "out":
            info = player_info(g[0], g[1], team, player) or {}
            if (info.get("minutes") or 0) >= 20:
                events.append((g[0], g[1], team, player))
print(f"\n## H2 late scratches after 21:00 (rotation players, L10 >= 20 min): {len(events)}")
for e in events:
    print("  ", e)
hit = {(d, g, t) for d, g, t, _ in events}
scratched = {(d, g, p) for d, g, _, p in events}
affected = [l for l in legs if (l["day"], l["game"], l["team"]) in hit and (l["day"], l["game"], l["player"]) not in scratched]
others = [l for l in legs if (l["day"], l["game"], l["team"]) not in hit]
for name, part in (("dev", lambda d: d <= DEV_END), ("holdout", lambda d: d > DEV_END), ("all", lambda d: True)):
    a = [l for l in affected if part(l["day"])]
    o = [l for l in others if part(l["day"])]
    if not a:
        print(f"  {name}: no affected legs")
        continue
    moved = [l["close"] / l["price"] - 1 for l in a if l["close"]]
    a_set = {id(l) for l in a}
    def diff(s):
        aa = [l for l in s if id(l) in a_set]
        oo = [l for l in s if id(l) not in a_set]
        return (roi(aa) if aa else 0.0) - roi(oo)
    lo, hi = boot(a + o, diff)
    print(f"  {name}: affected n={len(a)} ROI@21:00 {roi(a):+.3f} calib {calib(a):+.3f} | others n={len(o)} ROI {roi(o):+.3f}"
          f" | diff {roi(a) - roi(o):+.3f} [{lo:+.3f}, {hi:+.3f}] | price 21:00->close median {sorted(moved)[len(moved)//2] if moved else float('nan'):+.3f}"
          f" | ROI@close {roi(a, 'close'):+.3f}")

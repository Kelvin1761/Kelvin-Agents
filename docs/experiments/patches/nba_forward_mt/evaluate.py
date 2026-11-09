"""EXP-20261109-04: two pre-registered NBA forward tests (frozen before any forward data exists).

  M  minutes risk  — are 21:00 legs with a pre-game minutes-risk flag over-estimated by p_final?
  T  late receivers — after a rotation player is first seen Out *after* 21:00, are the
                      teammates who absorb his shots / assists under-priced at the next refresh?

usage:
  python3 evaluate.py status   [--ledger DIR] [--analysis DIR]   -> JSON progress, no outcomes shown
  python3 evaluate.py evaluate [--ledger DIR] [--analysis DIR] [--out FILE] [--force]

`status` only counts rows (it never prints hit rates). `evaluate` refuses to run before a
test's checkpoint and refuses to overwrite a frozen result unless --force (which must be
justified in the experiment record). Protocol: docs/experiments/EXP-20261109-04-*.md.
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / ".agents/skills/nba"))
from nba_identity import player_name_key as key  # noqa: E402

EXPERIMENT = "EXP-20261109-04"
START = "2026-11-10"          # first forward target_date; nothing earlier is ever read
SEED, DRAWS = 20261109, 2000
MARKETS = ("pts", "reb", "ast", "fg3m")

# --- M: frozen definitions ------------------------------------------------------------
M_P_MIN, M_PRICE_MAX = 0.60, 2.00
M_MIN_GAMES, M_MIN_MINUTES = 5, 20.0
M_BLOWOUT_SPREAD = 10.0
M_MINUTES_SD = 6.0
M_CHECK_DAYS, M_CHECK_FLAGGED = 21, 800
M_PASS_DELTA = -0.03

# --- T: frozen definitions ------------------------------------------------------------
T_MIN_GAMES, T_MIN_MINUTES = 5, 24.0
T_RECEIVERS = 2
T_TARGET_PRICE = 1.90
T_NEWS_SLACK = timedelta(minutes=10)
T_CHECK_EVENTS, T_CHECK_LEGS = 60, 200
T_PASS_DELTA = 0.05
OUT_LEVELS = {"out"}
INJURY_OUT = {"out", "suspension", "suspended", "doubtful"}


def ts(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def default_ledger() -> Path:
    return Path.home() / "WongChoiData" / "NBA_Market_Eval" / "ledger"


def default_analysis() -> Path:
    # Same default as run_nba_daily_schedule.sh (the scheduler's local primary).
    import os
    env = os.environ.get("WONGCHOI_NBA_DATA_ROOT", "").strip()
    return Path(env).expanduser() if env else Path.home() / "WongChoiData" / "Wong Choi NBA Analysis"


# --- loading ---------------------------------------------------------------------------
def load(ledger: Path) -> dict[str, list[dict]]:
    rows: dict[str, list[dict]] = defaultdict(list)
    for f in sorted(ledger.glob("*.jsonl")):
        if f.stem < START:
            continue
        for line in f.open(encoding="utf-8"):
            r = json.loads(line)
            if (r.get("target_date") or "") >= START:
                rows[r.get("row_type")].append(r)
    return rows


def leg_id(r: dict) -> tuple:
    return (r["target_date"], r["game_tag"], key(r["player"]), r["market"], float(r["line"]))


def outcomes(rows) -> dict:
    y = {}
    for r in rows["settlement"]:
        if r.get("side", "over") == "over" and r.get("outcome") in ("hit", "miss"):
            y[leg_id(r)] = int(r["y"])
    return y


def first_production(rows) -> dict:
    """(date, tag) -> (snapshot_created_at, snapshot_id) of the first production snapshot."""
    first: dict = {}
    for r in rows["model_obs"]:
        if r.get("snapshot_role") != "production" or r.get("post_tip"):
            continue
        g = (r["target_date"], r["game_tag"])
        if g not in first or r["snapshot_created_at"] < first[g][0]:
            first[g] = (r["snapshot_created_at"], r.get("snapshot_id"))
    return first


_pkg: dict = {}


def snapshot_files(analysis: Path, day: str, snap: str, tag: str):
    """The 21:00 snapshot's own game package and Sportsbet odds (never a later refresh)."""
    k = (day, snap, tag)
    if k not in _pkg:
        _pkg[k] = (None, None)
        for folder in sorted(analysis.glob(f"{day} NBA Analysis*")):
            d = folder / "_prediction_snapshots" / str(snap)
            g, o = d / f"nba_game_data_{tag}.json", d / f"Sportsbet_Odds_{tag}.json"
            if g.is_file():
                _pkg[k] = (json.loads(g.read_text(encoding="utf-8")),
                           json.loads(o.read_text(encoding="utf-8")) if o.is_file() else None)
                break
    return _pkg[k]


def player_rows(pkg: dict) -> dict:
    """name_key -> {team, minutes[], fga[], ast[], status, dates[]} from the package."""
    out = {}
    for team, players in (pkg.get("players") or {}).items():
        for p in players or []:
            gl = p.get("gamelog") or {}
            out[key(p.get("name") or gl.get("name") or "")] = {
                "team": team,
                "minutes": [float(x) for x in (gl.get("MIN") or []) if x is not None],
                "fga": [float(x) for x in (gl.get("FGA") or []) if x is not None],
                "ast": [float(x) for x in (gl.get("AST") or []) if x is not None],
                "dates": list(gl.get("l10_dates") or []),
                "status": (p.get("status") or "").strip(),
            }
    return out


def injuries(pkg: dict) -> dict:
    """name_key -> lowercased status, from the snapshot's injury table."""
    out = {}
    for team, table in (pkg.get("injuries") or {}).items():
        for name, status in (table or {}).items():
            out[key(name)] = str(status or "").strip().lower()
    return out


def mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def boot(items: list[dict], fn, seed=SEED, draws=DRAWS):
    """Percentile CI, resampling whole games."""
    games = defaultdict(list)
    for it in items:
        games[it["game"]].append(it)
    keys = sorted(games)
    rnd = random.Random(seed)
    vals = []
    for _ in range(draws):
        sample = [x for k in (rnd.choice(keys) for _ in keys) for x in games[k]]
        v = fn(sample)
        if v is not None:
            vals.append(v)
    vals.sort()
    if not vals:
        return None, None
    return vals[int(0.025 * len(vals))], vals[min(len(vals) - 1, int(0.975 * len(vals)))]


# --- M ---------------------------------------------------------------------------------
def spread(odds: dict | None):
    try:
        return abs(float(str((odds or {}).get("game_lines", {}).get("spread_away")).replace("+", "")))
    except (TypeError, ValueError):
        return None


def us_game_date(tip_off: str | None, target_date: str) -> date:
    if tip_off:
        return (ts(tip_off) - timedelta(hours=5)).date()
    return date.fromisoformat(target_date) - timedelta(days=1)


def previous_game_date(dates: list[str]):
    for text in dates:
        try:
            return datetime.strptime(text.strip().title(), "%b %d, %Y").date()
        except ValueError:
            continue
    return None


def m_legs(rows, analysis: Path, y: dict) -> tuple[list[dict], dict]:
    first = first_production(rows)
    legs, missing = [], defaultdict(int)
    for r in rows["model_obs"]:
        g = (r["target_date"], r["game_tag"])
        if g not in first or r.get("snapshot_created_at") != first[g][0]:
            continue
        if r.get("side", "over") != "over" or r.get("market") not in MARKETS:
            continue
        p, price = r.get("p_final"), r.get("price_at_model")
        if p is None or not price or not (p >= M_P_MIN and price < M_PRICE_MAX):
            continue
        lid = leg_id(r)
        if lid not in y:
            missing["unsettled"] += 1
            continue
        pkg, odds = snapshot_files(analysis, g[0], first[g][1], g[1])
        if pkg is None:
            missing["snapshot_missing"] += 1
            continue
        pl = player_rows(pkg).get(lid[2])
        if not pl or len(pl["minutes"]) < M_MIN_GAMES or mean(pl["minutes"]) < M_MIN_MINUTES:
            missing["not_rotation"] += 1
            continue
        inj = injuries(pkg).get(lid[2], "")
        prev = previous_game_date(pl["dates"])
        sp = spread(odds)
        flags = {
            "blowout": sp is not None and sp >= M_BLOWOUT_SPREAD,
            "volatile_minutes": statistics.pstdev(pl["minutes"]) >= M_MINUTES_SD,
            "status": bool(inj) and inj not in INJURY_OUT
                      or (pl["status"] not in ("", "Active") and pl["status"].lower() not in INJURY_OUT),
            "back_to_back": prev is not None
                            and prev == us_game_date(r.get("tip_off"), g[0]) - timedelta(days=1),
        }
        legs.append({"game": g, "day": g[0], "p": float(p), "price": float(price), "y": y[lid],
                     "picked": bool(r.get("picked")), "flags": flags, "flagged": any(flags.values())})
    return legs, dict(missing)


def m_status(rows, analysis, y) -> dict:
    legs, missing = m_legs(rows, analysis, y)
    days = len({l["day"] for l in legs})
    flagged = sum(l["flagged"] for l in legs)
    return {"days": days, "legs": len(legs), "flagged_legs": flagged,
            "checkpoint": {"days": M_CHECK_DAYS, "flagged_legs": M_CHECK_FLAGGED},
            "ready": days >= M_CHECK_DAYS and flagged >= M_CHECK_FLAGGED, "excluded": missing}


def resid(ls):
    return mean([l["y"] - l["p"] for l in ls]) if ls else None


def roi(ls):
    return mean([l["y"] * l["price"] - 1 for l in ls]) if ls else None


def m_evaluate(rows, analysis, y) -> dict:
    legs, missing = m_legs(rows, analysis, y)

    def delta(sample):
        a, b = [l for l in sample if l["flagged"]], [l for l in sample if not l["flagged"]]
        return resid(a) - resid(b) if a and b else None

    lo, hi = boot(legs, delta)
    d = delta(legs)
    out = {"n_legs": len(legs), "n_flagged": sum(l["flagged"] for l in legs),
           "primary_delta_resid": d, "ci95": [lo, hi],
           "pass": d is not None and hi is not None and d <= M_PASS_DELTA and hi < 0,
           "flagged": {"resid": resid([l for l in legs if l["flagged"]]),
                       "roi": roi([l for l in legs if l["flagged"]])},
           "unflagged": {"resid": resid([l for l in legs if not l["flagged"]]),
                         "roi": roi([l for l in legs if not l["flagged"]])},
           "by_flag_descriptive": {}, "picked_descriptive": {}, "excluded": missing}
    for f in ("blowout", "volatile_minutes", "status", "back_to_back"):
        s = [l for l in legs if l["flags"][f]]
        out["by_flag_descriptive"][f] = {"n": len(s), "resid": resid(s), "roi": roi(s)}
    pk = [l for l in legs if l["picked"]]
    out["picked_descriptive"] = {
        "flagged": {"n": sum(l["flagged"] for l in pk), "resid": resid([l for l in pk if l["flagged"]])},
        "unflagged": {"n": sum(not l["flagged"] for l in pk), "resid": resid([l for l in pk if not l["flagged"]])}}
    return out


# --- T ---------------------------------------------------------------------------------
def prices_by_player(rows) -> dict:
    """(date, tag, name_key, market) -> [(captured_at, line, price)] pre-tip overs."""
    out = defaultdict(list)
    for r in rows["price_obs"]:
        if r.get("post_tip") or r.get("side", "over") != "over" or r.get("market") not in ("pts", "ast"):
            continue
        try:
            out[(r["target_date"], r["game_tag"], key(r["player"]), r["market"])].append(
                (ts(r["captured_at"]), float(r["line"]), float(r["price"])))
        except (TypeError, ValueError, KeyError):
            continue
    return out


def pick_line(obs, y, base, after=None):
    """First pre-tip price per line (after `after` if given, else the last one); choose the
    line whose price is closest to 1.90 (ties: lower line). Must be settled."""
    per_line = {}
    for at, line, price in sorted(obs):
        if after is not None:
            if at >= after and line not in per_line:
                per_line[line] = price
        else:
            per_line[line] = price
    best = None
    for line, price in sorted(per_line.items()):
        lid = base + (line,)
        if lid not in y:
            continue
        gap = abs(price - T_TARGET_PRICE)
        if best is None or gap < best[0] - 1e-12:
            best = (gap, line, price, y[lid])
    return None if best is None else {"line": best[1], "price": best[2], "y": best[3]}


def receivers(players: dict, team: str, exclude: set) -> dict:
    pool = [(k, v) for k, v in players.items()
            if v["team"] == team and k not in exclude
            and len(v["minutes"]) >= T_MIN_GAMES and mean(v["minutes"]) >= T_MIN_MINUTES]
    by_fga = sorted(pool, key=lambda kv: (-mean(kv[1]["fga"]), kv[0]))[:T_RECEIVERS]
    by_ast = sorted(pool, key=lambda kv: (-mean(kv[1]["ast"]), kv[0]))[:T_RECEIVERS]
    return {"pts": [k for k, _ in by_fga], "ast": [k for k, _ in by_ast]}


def t_legs(rows, analysis, y):
    first = first_production(rows)
    prices = prices_by_player(rows)
    outs = defaultdict(dict)   # (date, tag) -> name_key -> first pre-tip Out time
    for r in rows["availability_obs"]:
        if r.get("post_tip"):
            continue
        if (r.get("espn_level") or "").lower() in OUT_LEVELS or (r.get("official_level") or "").lower() in OUT_LEVELS:
            # NOT r["name_key"]: the ledger writes "asanewell", player_name_key gives "asa newell".
            g, k = (r["target_date"], r["game_tag"]), key(r["player"])
            at = ts(r["recorded_at"])
            if k not in outs[g] or at < outs[g][k]:
                outs[g][k] = at
    events, ev_legs, ctl_legs, missing = [], [], [], defaultdict(int)
    for g, (created, snap) in sorted(first.items()):
        pkg, _ = snapshot_files(analysis, g[0], snap, g[1])
        if pkg is None:
            missing["snapshot_missing"] += 1
            continue
        players, inj = player_rows(pkg), injuries(pkg)
        created_at = ts(created)
        out_at_snapshot = {k for k, s in inj.items() if s in INJURY_OUT} | \
                          {k for k, at in outs[g].items() if at <= created_at}
        teams = sorted({v["team"] for v in players.values()})
        for team in teams:
            late = sorted(((at, k) for k, at in outs[g].items()
                           if at > created_at and k not in out_at_snapshot
                           and players.get(k, {}).get("team") == team
                           and len(players[k]["minutes"]) >= T_MIN_GAMES
                           and mean(players[k]["minutes"]) >= T_MIN_MINUTES))
            if late:
                news_at, who = late[0]
                gone = out_at_snapshot | {k for k, at in outs[g].items() if at <= news_at}
                rec = receivers(players, team, gone)
                events.append({"game": g, "team": team, "player": who, "news_at": news_at.isoformat()})
                for market, names in rec.items():
                    for k in names:
                        leg = pick_line(prices.get(g + (k, market), []), y, g + (k, market),
                                        after=news_at - T_NEWS_SLACK)
                        if leg:
                            ev_legs.append({"game": g, "market": market, **leg})
                        else:
                            missing["event_leg_unpriced"] += 1
            else:
                rec = receivers(players, team, out_at_snapshot | set(outs[g]))
                for market, names in rec.items():
                    for k in names:
                        leg = pick_line(prices.get(g + (k, market), []), y, g + (k, market))
                        if leg:
                            ctl_legs.append({"game": g, "market": market, **leg})
    return events, ev_legs, ctl_legs, dict(missing)


def cal(ls):
    return mean([l["y"] - 1 / l["price"] for l in ls]) if ls else None


def t_status(rows, analysis, y) -> dict:
    events, ev, ctl, missing = t_legs(rows, analysis, y)
    return {"events": len(events), "event_legs": len(ev), "control_legs": len(ctl),
            "checkpoint": {"events": T_CHECK_EVENTS, "event_legs": T_CHECK_LEGS},
            "ready": len(events) >= T_CHECK_EVENTS and len(ev) >= T_CHECK_LEGS, "excluded": missing}


def t_evaluate(rows, analysis, y) -> dict:
    events, ev, ctl, missing = t_legs(rows, analysis, y)
    items = [dict(l, arm="event") for l in ev] + [dict(l, arm="control") for l in ctl]

    def delta(sample):
        a = [l for l in sample if l["arm"] == "event"]
        b = [l for l in sample if l["arm"] == "control"]
        return cal(a) - cal(b) if a and b else None

    lo, hi = boot(items, delta)
    rlo, rhi = boot([l for l in items if l["arm"] == "event"], roi)
    d, r = delta(items), roi(ev)
    return {"events": len(events), "event_legs": len(ev), "control_legs": len(ctl),
            "primary_delta_cal": d, "ci95": [lo, hi],
            "event_roi": r, "event_roi_ci95": [rlo, rhi],
            "pass": d is not None and lo is not None and d >= T_PASS_DELTA and lo > 0 and (r or 0) > 0,
            "by_market_descriptive": {m: {"event_n": sum(l["market"] == m for l in ev),
                                          "event_cal": cal([l for l in ev if l["market"] == m]),
                                          "control_cal": cal([l for l in ctl if l["market"] == m])}
                                      for m in ("pts", "ast")},
            "excluded": missing}


TESTS = {"M": (m_status, m_evaluate), "T": (t_status, t_evaluate)}


def status(ledger: Path, analysis: Path) -> dict:
    rows = load(ledger)
    y = outcomes(rows)
    return {name: fns[0](rows, analysis, y) for name, fns in TESTS.items()}


def evaluate(ledger: Path, analysis: Path, out_dir: Path, *, force: bool = False,
             only: str | None = None) -> dict:
    rows = load(ledger)
    y = outcomes(rows)
    results = {}
    for name, (st, ev) in TESTS.items():
        if only and name != only:
            continue
        path = out_dir / f"{EXPERIMENT}-{name}-result.json"
        if path.is_file() and not force:
            results[name] = json.loads(path.read_text(encoding="utf-8"))
            continue
        progress = st(rows, analysis, y)
        if not progress["ready"]:
            results[name] = {"status": "not_ready", "progress": progress}
            continue
        result = {"experiment": EXPERIMENT, "test": name, "evaluated_at": datetime.now(timezone.utc).isoformat(),
                  "start": START, "progress": progress, **ev(rows, analysis, y)}
        out_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        results[name] = result
    return results


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("status", "evaluate"))
    ap.add_argument("--ledger", type=Path, default=None)
    ap.add_argument("--analysis", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    ledger = a.ledger or default_ledger()
    analysis = a.analysis or default_analysis()
    if a.mode == "status":
        print(json.dumps(status(ledger, analysis), ensure_ascii=False, indent=1, default=str))
    else:
        out = a.out or ledger.parent / "reports"
        print(json.dumps(evaluate(ledger, analysis, out, force=a.force), ensure_ascii=False, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Parity: nba_engine.legs against the legacy candidate pool (replay JSONL).

usage: python3 parity_legs.py <repo_root> <analysis_root> <replay.jsonl ...>
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

repo, root = Path(sys.argv[1]), Path(sys.argv[2])
sys.path[:0] = [str(repo / ".agents/skills/nba")]
from nba_engine.legs import LABEL, build_legs  # noqa: E402

old = defaultdict(dict)
for f in sys.argv[3:]:
    for line in open(f):
        r = json.loads(line)
        if r.get("market_type") == "PLAYER_MILESTONE":
            old[(r["day"], r["game"])][(r["player"], r["category"], float(r["line_val"]))] = r

c = Counter()
for (day, tag), rows in sorted(old.items()):
    d = root / f"{day} NBA Analysis"
    odds = json.loads((d / f"Sportsbet_Odds_{tag}.json").read_text())
    pkg = json.loads((d / f"nba_game_data_{tag}.json").read_text())
    legs, _ = build_legs(odds, pkg)
    new = {(l.player, l.label, l.line): l for l in legs if not (l.stat == "FG3M" and "volatile_3pm" in l.flags)}
    c["old"] += len(rows)
    c["new"] += len(new)
    c["only_old"] += len(rows.keys() - new.keys())
    c["only_new"] += len(new.keys() - rows.keys())
    for k in rows.keys() & new.keys():
        o, n = rows[k], new[k]
        checks = {
            "hit_l10": abs(o["hit_l10"] - round(100 * n.hit_l10, 1)) < 0.06,
            "hit_l5": abs(o["hit_l5"] - round(100 * n.hit_l5, 1)) < 0.06,
            "avg": abs(o["avg"] - n.avg) < 0.006,
            "cov": abs(o["cov"] - n.cov) < 0.0006,
            "l3_avg": abs(o["l3_avg"] - n.l3_avg) < 0.006,
            "C": n.p_c is not None and abs(o["estimated_prob"] - round(100 * n.p_c, 1)) < 0.06,
            "dtd": bool(o["day_to_day"]) == (n.availability == "dtd"),
            "bench": bool(o["bench_minutes_risk"]) == ("bench_minutes" in n.flags),
            "early": bool(o["early_season_guard"]) == bool({"l10_mostly_previous_season", "new_team"} & set(n.flags)),
        }
        for name, ok in checks.items():
            c[f"bad_{name}"] += not ok
        if not all(checks.values()) and c["printed"] < 5:
            c["printed"] += 1
            print("MISMATCH", day, tag, k, {n_: v for n_, v in checks.items() if not v})
print(dict(c))

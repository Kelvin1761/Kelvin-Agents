"""Parity: nba_engine.banker.select_b2 against the legacy B2 picks (replay JSONL).

usage: python3 parity_b2.py <repo_root> <analysis_root> <replay.jsonl ...>
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

repo, root = Path(sys.argv[1]), Path(sys.argv[2])
sys.path[:0] = [str(repo / ".agents/skills/nba")]
from nba_engine.banker import select_b2  # noqa: E402
from nba_engine.legs import build_legs  # noqa: E402

old, rules = defaultdict(set), {}
for f in sys.argv[3:]:
    for line in open(f):
        r = json.loads(line)
        rules[(r["day"], r["game"])] = r["rule"]
        if r["b2_pick"]:
            old[(r["day"], r["game"])].add((r["player"], r["category"], float(r["line_val"])))
c = Counter()
for (day, tag), rule in sorted(rules.items()):
    d = root / f"{day} NBA Analysis"
    package = json.loads((d / f"nba_game_data_{tag}.json").read_text())
    legs, _ = build_legs(json.loads((d / f"Sportsbet_Odds_{tag}.json").read_text()), package)
    combo, new_rule = select_b2(legs, (package.get("meta") or {}).get("season_phase"))
    new = {(l.player, l.label, l.line) for l in combo}
    same = new == old[(day, tag)]
    c["same" if same else "different"] += 1
    if not same:
        print(day, tag, "old", rule, sorted(old[(day, tag)]), "\n            new", new_rule, sorted(new))
print(dict(c))

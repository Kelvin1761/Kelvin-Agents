"""EXP-20261104-07: nba_game_data_<TAG>.json field-for-field, old extractor vs simplified one.

Run both extractors back-to-back per game (same ESPN cache, minutes apart), then:
  for tag in ...; do
    python3 <old>/nba_extractor.py --date 20261105 --game $tag --output base/nba_game_data_$tag.json
    python3 <new>/nba_extractor.py --date 20261105 --game $tag --output new/nba_game_data_$tag.json
  done
  python3 <this> <dir containing base/ and new/>
Prints every differing / removed / added field path (team tags folded to <T>) with counts.
"""
import json, sys, collections
from pathlib import Path
S = Path(sys.argv[1])
diffs = collections.Counter(); ex = {}
def walk(a, b, p):
    if isinstance(a, dict) and isinstance(b, dict):
        for k in set(a) | set(b):
            q = p + "/" + k
            if k not in b: diffs[("removed", gen(q))] += 1; continue
            if k not in a: diffs[("added", gen(q))] += 1; continue
            walk(a[k], b[k], q)
    elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        for i, (x, y) in enumerate(zip(a, b)): walk(x, y, p + "[]")
    elif a != b:
        diffs[("changed", gen(p))] += 1; ex.setdefault(gen(p), (str(a)[:80], str(b)[:80]))
import re
def gen(p): return re.sub(r"/(players|team_stats|team_dvp|injuries|key_defenders|usage_redistribution|correlation_warnings|opponent_context|team_recent|rosters)/[A-Z]{2,4}", r"/\1/<T>", p)
games = 0
for f in sorted((S / "base").glob("nba_game_data_*.json")):
    g = S / "new" / f.name
    if not g.exists(): continue
    games += 1
    walk(json.loads(f.read_text()), json.loads(g.read_text()), "")
print(games, "games")
for k, v in sorted(diffs.items(), key=str): print(v, k, ex.get(k[1], ""))

"""EXP-20261127-40 secondary (report only): replay featured O/U picks from the 21:00 snapshot with p_final vs MS2 (frozen EXP-20261111-05 coefs)."""
import json, math, sys, glob, os, re
from types import SimpleNamespace
from pathlib import Path
REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / ".agents/skills/nba"))
sys.path.insert(0, str(REPO / "docs/experiments/patches/nba_s2_forward"))
from nba_engine import featured
import evaluate as ev
ROOT = Path.home() / "WongChoiData/Wong Choi NBA Analysis"
LEDGER = Path.home() / "WongChoiData/NBA_Market_Eval/ledger"
STATK = {"pts": "PTS", "reb": "REB", "ast": "AST", "fg3m": "FG3M"}

def settle(day):
    res = {}
    p = LEDGER / f"{day}.jsonl"
    if not p.exists(): return res
    for line in p.open():
        if '"settlement"' not in line: continue
        r = json.loads(line)
        if r.get("y") is None or r.get("line") is None: continue
        res.setdefault((r["game_tag"], r["player"], r["market"], float(r["line"])), int(r["y"]))
    return res

out = {"pub": [], "ms2": []}
match_pub = [0, 0]; days = 0
for d in sorted(ROOT.glob("2026-11-* NBA Analysis")):
    day = d.name[:10]
    if day < "2026-11-12" or day > "2026-11-26": continue
    snaps = sorted((d / "_prediction_snapshots").glob("*"))
    prev = day.replace("-", "")
    # 21:00 run on the evening before (Sydney): name starts with target-1 and hour 20-22
    cand = [s for s in snaps if re.match(r"\d{8}-(20|21|22)", s.name) and s.name[:8] < prev]
    if not cand: print("no 21:00 snapshot", day); continue
    snap = cand[0]; days += 1
    res = settle(day)
    picks = {"pub": [], "ms2": []}
    for side in glob.glob(str(snap / "*.market_legs.json")):
        sc = json.load(open(side)); tag = Path(side).name.split("_Full")[0].replace("Game_", "")
        oddsf = snap / f"Sportsbet_Odds_{tag}.json"
        if not oddsf.exists(): continue
        odds = json.load(open(oddsf))
        for arm in ("pub", "ms2"):
            legs = []
            for l in sc["legs"]:
                p = l.get("p_final")
                if arm == "ms2" and p is not None and l.get("p_s2") is not None and l.get("price") and l["price"] > 1 and l["market"] in STATK:
                    p = ev.blend("MS2", STATK[l["market"]], float(l["price"]), float(l["p_s2"]))
                legs.append(SimpleNamespace(player=l["player"], stat=STATK.get(l["market"]), line=float(l["line"]),
                                            p_final=p, availability=l.get("availability"), team=l.get("team")))
            pk = featured.game_pick(odds, legs)
            if pk: pk["game_tag"] = tag; picks[arm].append(pk)
        if sc.get("featured") is not None:
            pub_live = sc["featured"][0] if sc["featured"] else None
            rep = next((p for p in picks["pub"] if p["game_tag"] == tag), None)
            match_pub[1] += 1
            if (pub_live and rep and (pub_live["player"], pub_live["ou_line"], pub_live["side"]) == (rep["player"], rep["ou_line"], rep["side"])) or (not pub_live and not rep):
                match_pub[0] += 1
    for arm in picks:
        for pk in featured.daily_top(picks[arm]):
            key = (pk["game_tag"], pk["player"], pk["market"], float(pk["milestone_line"]))
            y = res.get(key)
            if y is None: continue
            win = (y == 1) if pk["side"] == "over" else (y == 0)
            out[arm].append({"day": day, "key": "|".join(map(str, key)) + "|" + pk["side"], "win": win,
                             "pnl": (pk["price"] - 1) if win else -1.0})
print("days", days, "replay p_final == live sidecar featured:", match_pub)
for arm, rows in out.items():
    n = len(rows); w = sum(r["win"] for r in rows); pnl = sum(r["pnl"] for r in rows)
    print(arm, "n", n, "win", w, "ROI%", round(100 * pnl / n, 2) if n else None, "pnl", round(pnl, 2))
a = {r["key"] for r in out["pub"]}; b = {r["key"] for r in out["ms2"]}
print("shared", len(a & b), "only_pub", len(a - b), "only_ms2", len(b - a))
for nm, s, arm in (("only_pub", a - b, "pub"), ("only_ms2", b - a, "ms2"), ("shared", a & b, "pub")):
    rows = [r for r in out[arm] if r["key"] in s]
    if rows: print(nm, len(rows), "win", sum(r["win"] for r in rows), "pnl", round(sum(r["pnl"] for r in rows), 2))

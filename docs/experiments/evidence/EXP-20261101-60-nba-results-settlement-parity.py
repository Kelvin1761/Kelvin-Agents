"""EXP-20261101-60 R1 gate: ESPN-only Results Brief vs every stored Results Brief.

usage: python3 EXP-20261101-60-nba-results-settlement-parity.py <analysis root> <scratch dir>

For every "<Sydney date> NBA Analysis/Results_Brief_<US date>.json": re-fetch the
US date with the ESPN-only fetch_nba_results into <scratch>/<US date>/, then
settle that day's ledger legs (model_obs + sgm_obs, settlement rows dropped)
twice into throw-away ledgers -- once per brief -- and compare per leg.
"""
import collections
import json
import subprocess
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

repo = Path(__file__).resolve().parents[3]
analysis, scratch = Path(sys.argv[1]), Path(sys.argv[2])
sys.path.insert(0, str(repo / ".agents/skills/nba/nba_daily_auto"))
import nba_market_ledger as L  # noqa: E402

FETCH = repo / ".agents/skills/nba/nba_reflector/scripts/fetch_nba_results.py"
ledger = L.ledger_root()
report = {"dates": {}, "totals": collections.Counter(), "differences": []}


def settle(sydney, brief, rows):
    with tempfile.TemporaryDirectory() as tmp:
        L.append_rows(Path(tmp), sydney, rows)
        L.settle(sydney, brief, root=Path(tmp))
        return {(r["game_tag"], r["player"], r["market"], float(r["line"]), r.get("side") or "over"):
                (r.get("outcome"), r.get("actual"), r.get("y"))
                for r in L.read_rows(Path(tmp), sydney) if r.get("row_type") == "settlement"}


for stored in sorted(analysis.glob("* NBA Analysis/Results_Brief_*.json")):
    if stored.name.endswith("_Verified.json"):
        continue
    us = stored.stem.split("_")[-1]
    sydney = (date.fromisoformat(us) + timedelta(days=1)).isoformat()
    out = scratch / us
    out.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run([sys.executable, str(FETCH), "--date", us, "--dir", str(out)],
                          capture_output=True, text=True)
    fresh = out / stored.name
    old, new = json.loads(stored.read_text()), (json.loads(fresh.read_text()) if fresh.is_file() else {"games": []})
    final = lambda b: sum(str(g.get("status", "")).startswith("Final") for g in b.get("games", []))
    scores = lambda b: {(g["away"]["team"], g["home"]["team"]): (g["away"].get("score"), g["home"].get("score"))
                        for g in b.get("games", []) if str(g.get("status", "")).startswith("Final")}
    s_old, s_new = scores(old), scores(new)
    rows = [r for r in L.read_rows(ledger, sydney) if r.get("row_type") in ("model_obs", "sgm_obs")]
    a = settle(sydney, stored, rows) if rows else {}
    b = settle(sydney, fresh, rows) if rows and fresh.is_file() else {}
    same = sum(a.get(k) == b.get(k) for k in a)
    diffs = [(sydney, *k, a.get(k), b.get(k)) for k in sorted(set(a) | set(b), key=str) if a.get(k) != b.get(k)]
    report["differences"] += diffs
    report["dates"][us] = {
        "fetch_rc": proc.returncode,
        "stored_source": sorted({str(g.get("game_id", ""))[:5] for g in old.get("games", [])}),
        "finals_stored": final(old), "finals_espn": final(new),
        "final_scores_equal": sum(s_old.get(k) == v for k, v in s_new.items()), "final_scores_compared": len(s_new),
        "legs_settled_stored": len(a), "legs_settled_espn": len(b), "legs_identical": same, "legs_different": len(diffs)}
    for k in ("legs_settled_stored", "legs_settled_espn", "legs_identical", "legs_different"):
        report["totals"][k] += report["dates"][us][k]
report["totals"] = dict(report["totals"])
(scratch / "settlement_parity.json").write_text(json.dumps(report, indent=1, default=str))
print(json.dumps({"dates": report["dates"], "totals": report["totals"]}, indent=1))
print("differences (first 40):")
for d in report["differences"][:40]:
    print(" ", d)

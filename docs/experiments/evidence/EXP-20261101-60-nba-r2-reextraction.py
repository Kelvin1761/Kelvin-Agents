"""EXP-20261101-60 R2 gate: same-day re-extraction, before (main, nba.com code paths
present but standing down) vs after (ESPN only, ESPN ids).

usage: python3 EXP-20261101-60-nba-r2-reextraction.py <repo> <before dir> <after dir> GAME [GAME ...]

Players are matched by name key (player_id changes namespace on purpose). For every
matched player the model inputs are compared field by field; the live C layer
p_final is recomputed for every standard Sportsbet milestone at a fixed price grid
(the slate had no props priced yet; C reads only stat, price and L10 hit rate, so
any price grid exposes every input difference).
"""
import collections
import json
import sys
from pathlib import Path

repo, before_dir, after_dir, games = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4:]
sys.path.insert(0, str(repo / ".agents/skills/nba"))
sys.path.insert(0, str(repo / ".agents/skills/nba/nba_wong_choi/scripts"))
import nba_prob_layer  # noqa: E402
from nba_identity import player_name_key  # noqa: E402

LINES = {"PTS": [10, 15, 20, 25, 30, 35, 40], "REB": [3, 5, 7, 9, 11, 13, 15],
         "AST": [2, 4, 6, 8, 10, 12], "FG3M": [1, 2, 3, 4, 5, 6]}
PRICES = [1.4, 1.9, 2.8, 4.5]
MODEL_FIELDS = ("gamelog", "splits", "advanced", "h2h", "prop_analytics", "fatigue", "position", "status", "age",
                "splits_season")
VOLATILE = {"source", "snapshot_age_days", "on_court_source"}


def strip(value):
    if isinstance(value, dict):
        return {k: strip(v) for k, v in value.items() if k not in VOLATILE}
    if isinstance(value, list):
        return [strip(v) for v in value]
    return value


def c_layer(gamelog):
    out = {}
    for stat, lines in LINES.items():
        values = (gamelog or {}).get(stat) or []
        for line in lines:
            hit = round(sum(v >= line for v in values[:10]) / len(values[:10]) * 100, 0) if values else None
            for price in PRICES:
                out[(stat, line, price)] = nba_prob_layer.calibrated_prob(stat, price, hit)
    return out


report = {"games": {}, "totals": collections.Counter(), "field_diffs": collections.Counter(), "examples": []}
for game in games:
    before = json.loads((before_dir / f"nba_game_data_{game}.json").read_text())
    after = json.loads((after_dir / f"nba_game_data_{game}.json").read_text())
    entry = {"teams": {}}
    for team in before["players"]:
        b = {player_name_key(p["name"]): p for p in before["players"][team]}
        a = {player_name_key(p["name"]): p for p in after["players"].get(team, [])}
        shared = sorted(set(b) & set(a))
        diffs = collections.Counter()
        c_changed = c_total = 0
        for key in shared:
            for field in MODEL_FIELDS:
                if strip(b[key].get(field)) != strip(a[key].get(field)):
                    diffs[field] += 1
                    if len(report["examples"]) < 12:
                        report["examples"].append((game, b[key]["name"], field))
            pb, pa = c_layer(b[key].get("gamelog")), c_layer(a[key].get("gamelog"))
            c_total += len(pb)
            c_changed += sum(pb[k] != pa[k] for k in pb)
        entry["teams"][team] = {
            "players_before": len(b), "players_after": len(a), "matched": len(shared),
            "only_before": sorted(b[k]["name"] for k in set(b) - set(a)),
            "only_after": sorted(a[k]["name"] for k in set(a) - set(b)),
            "field_diffs": dict(diffs), "c_cells": c_total, "c_changed": c_changed,
            "player_id_source_after": sorted({str(p.get("player_id_source")) for p in a.values()}),
        }
        report["field_diffs"].update(diffs)
        for k in ("matched", "c_cells", "c_changed"):
            report["totals"][k] += entry["teams"][team][k]
        report["totals"]["only_before"] += len(entry["teams"][team]["only_before"])
        report["totals"]["only_after"] += len(entry["teams"][team]["only_after"])
    team_level = {}
    for field in ("team_stats", "injuries", "usage_redistribution", "correlation_warnings", "opponent_context",
                  "team_recent", "key_defenders", "team_dvp"):
        team_level[field] = strip(before.get(field)) == strip(after.get(field))
    entry["team_level_equal"] = team_level
    entry["meta_before"] = {k: before["meta"].get(k) for k in ("stat_source", "fallback_used", "statistics_contract")}
    entry["meta_after"] = {k: after["meta"].get(k) for k in ("stat_source", "fallback_used", "statistics_contract")}
    entry["official_injuries_key_after"] = "official_injuries" in after
    opp = lambda pkg: collections.Counter(  # noqa: E731
        f"{name}:{src.get('status')}" for team in pkg["players"].values() for p in team
        for name, src in ((p.get("opportunity_features") or {}).get("sources") or {}).items())
    entry["opportunity_status_before"], entry["opportunity_status_after"] = dict(opp(before)), dict(opp(after))
    report["games"][game] = entry
report["totals"] = dict(report["totals"])
report["field_diffs"] = dict(report["field_diffs"])
print(json.dumps(report, indent=1, ensure_ascii=False, default=str))

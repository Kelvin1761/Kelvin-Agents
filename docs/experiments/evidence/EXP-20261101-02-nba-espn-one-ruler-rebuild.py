"""EXP-20261101-02: rebuild the verified training corpus on the ESPN ruler.

usage:
  WC_NBA_ESPN_HTTP_RESPONSES_DIR=<ext>/espn_responses WC_NBA_STAT_SOURCE=espn \
    python3 EXP-20261101-02-nba-espn-one-ruler-rebuild.py <repo> <corpus root> <out dir>

For every case of the strict priced manifest (49 events, 2026-04..06):
* baseline: the original nba.com package through today's feature builder
  (v3 contract: no defender_pm), ``stat_source`` derived = 'nbacom';
* candidate: the same package with every statistic replaced by the live ESPN
  path -- the extractor's own ``fetch_player_gamelog`` / ``fetch_player_splits``
  / ``compute_fatigue_adjustment`` with stats.nba.com stood down, league tables
  from ESPN box scores, player OFF/DEF from play-by-play lineups, positions on
  ESPN's G/F/C scale -- ``stat_source`` = 'espn'.
Point-in-time: every ESPN input is a closed US day before the event's US day
(history_date_to), the same window the original nba.com calls used. Odds,
roster, injury statuses and capture provenance are the original ones.
Labels are joined from the verified v2 dataset; rows present in only one arm
are counted, never imputed.
"""
import copy, csv, glob, json, os, statistics, sys
from datetime import date, datetime
from pathlib import Path

repo, corpus, out = map(Path, sys.argv[1:4])
assert os.environ.get("WC_NBA_STAT_SOURCE") == "espn", "stand nba.com down"
assert os.environ.get("WC_NBA_ESPN_HTTP_RESPONSES_DIR"), "historical responses live on the external disk"
NBA = repo / ".agents/skills/nba"
for p in (NBA, NBA / "nba_data_extractor/scripts", repo / ".agents/scripts/nba_ml", repo):
    sys.path.insert(0, str(p))
import nba_api_breaker, nba_espn_league as L, nba_espn_lineups as P, nba_espn_http as H
import nba_extractor as X
from nba_identity import player_name_key
from build_nba_ml_dataset import extract_game_data
from nba_ml_features import FEATURE_COLS, FEATURE_CONTRACT
from nba_ml_pit import sha
nba_api_breaker.install()
X.API_SLEEP = 0   # nba.com pacing; ESPN spacing lives in nba_espn_http and repeats hit the cache

manifest = json.loads((corpus / "strict_priced_manifest.json").read_text())
v2 = list(csv.DictReader(open(corpus / "verified_dataset_v2/dataset.csv")))
labels = {(r["game_group"], r["player_key"], r["stat_category"], float(r["line_value"])): r
          for r in v2 if r["hit"] != ""}
provenance = {r["source_game_path"]: json.loads(r["source_provenance"]) for r in v2}

SEASON = "2025-26"
index = L.nba_name_index()
tables = {}


def league(date_to):
    """ESPN team/player tables for one history_date_to (regular season, as nba.com)."""
    if date_to not in tables:
        games = L.season_games(SEASON, date_to)
        team = L.team_advanced(games)
        adv = L.player_advanced(games, index)
        lineups = P.season_lineups(SEASON, date_to)
        L.fill_on_court_ratings(adv, P.player_ratings(lineups, index))
        tables[date_to] = (team, adv, len(games), len(lineups))
    return tables[date_to]


# ESPN ids and positions from every 2025-26 game ESPN served (incl. playoffs).
espn_ids, positions = {}, {}
for path in glob.glob(str(P.cache_root() / "*.json")):
    game = json.loads(Path(path).read_text())
    for pid, row in game.get("players", {}).items():
        espn_ids.setdefault((row["team"], player_name_key(row["name"])), pid)
        positions[pid] = row.get("position", "")
by_name = {}
for (team, key), pid in espn_ids.items():
    by_name.setdefault(key, set()).add(pid)

out.mkdir(parents=True, exist_ok=False)
(out / "espn_packages").mkdir()
rows_nb, rows_es, coverage = [], [], []
advanced_pairs = {}   # (date_to, nba id) -> (nba.com advanced, ESPN advanced): full-season parity
for case in manifest["cases"]:
    game_path, odds_path = Path(case["game"]), Path(case["odds"])
    assert sha(game_path) == case["game_sha256"] and sha(odds_path) == case["odds_sha256"]
    original = json.loads(game_path.read_text())
    meta = original["meta"]
    date_to = X.history_date_to(meta["date"])
    team_tbl, adv_tbl, n_box, n_pbp = league(date_to)
    package = copy.deepcopy(original)
    package["team_stats"] = team_tbl
    package["key_defenders"], package["team_dvp"] = {}, {}
    seen = matched = 0
    for team, players in package["players"].items():
        for player in players:
            seen += 1
            key = player_name_key(player["name"])
            pid = int(player["player_id"])
            espn = espn_ids.get((X.canonical_team_abbr(team), key))
            if espn is None and len(by_name.get(key, ())) == 1:
                espn = next(iter(by_name[key]))
            for field in ("gamelog", "splits", "fatigue", "prop_analytics", "h2h", "opportunity_features"):
                player.pop(field, None)
            player["advanced"] = adv_tbl.get(pid, {})
            original_adv = next((p.get("advanced") for p in original["players"][team]
                                 if p.get("player_id") == player["player_id"]), None)
            if original_adv and player["advanced"]:
                advanced_pairs[(date_to, pid)] = (original_adv, player["advanced"])
            player["position"] = positions.get(espn, "") if espn else ""
            if espn is None:
                continue
            X.ESPN_IDS[pid] = espn
            gamelog = X.fetch_player_gamelog(pid, player["name"], season=SEASON, as_of=meta["date"])
            splits = X.fetch_player_splits(pid, player["name"], season=SEASON, as_of=meta["date"])
            player["gamelog"], player["splits"] = gamelog, splits
            fatigue = X.compute_fatigue_adjustment(splits, gamelog, meta["date"])
            if fatigue:
                player["fatigue"] = fatigue
            matched += bool(gamelog)
    package["meta"]["data_sources"] = {
        "team_stats": {"rows": len(team_tbl), "source": L.SOURCE, "espn_games": n_box},
        "player_advanced": {"rows": len(adv_tbl), "source": L.SOURCE, "espn_pbp_games": n_pbp}}
    package["meta"]["stat_source"] = X.stat_source(package)
    package["meta"]["espn_rebuild"] = {"experiment": "EXP-20261101-02", "history_date_to": date_to,
                                       "original_sha256": case["game_sha256"],
                                       "built_at": datetime.now().isoformat(timespec="seconds")}
    target = out / "espn_packages" / case["case_id"] / game_path.name
    target.parent.mkdir()
    target.write_text(json.dumps(package, ensure_ascii=False))
    prov = provenance.get(str(game_path.resolve())) or provenance.get(str(game_path))
    base = extract_game_data(game_path, odds_path=odds_path, provenance=prov)
    cand = extract_game_data(target, odds_path=odds_path, provenance=prov)
    coverage.append({"case": case["case_id"], "players": seen, "espn_gamelog": matched,
                     "stat_source": package["meta"]["stat_source"],
                     "baseline_rows": len(base), "espn_rows": len(cand)})
    rows_nb += base
    rows_es += cand
    print(case["case_id"], coverage[-1], H.summary(), flush=True)


def keyed(rows):
    return {(r["game_group"], r["player_key"], r["stat_category"], float(r["line_value"])): r
            for r in rows if r["population"] == "priced_milestone"}


nb, es = keyed(rows_nb), keyed(rows_es)
both = sorted(set(nb) & set(es) & set(labels))
fields = ["feature_contract", "stat_source", "population", "game_date", "game_group", "game_tag", "player",
          "player_key", "team", "opponent", "position", "stat_category", *FEATURE_COLS, "market_price",
          "n_history", "pit_status", "actual_value", "hit"]
for name, rows in (("nbacom", nb), ("espn", es)):
    with open(out / f"dataset_{name}.csv", "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for key in both:
            writer.writerow({**rows[key], "actual_value": labels[key]["actual_value"], "hit": labels[key]["hit"]})

# Feature parity, nba.com vs ESPN, on the paired rows.
parity = {}
for feature in FEATURE_COLS:
    pairs = [(float(nb[k][feature]), float(es[k][feature])) for k in both
             if nb[k][feature] is not None and es[k][feature] is not None]
    missing = sum(1 for k in both if (nb[k][feature] is None) != (es[k][feature] is None))
    diffs = sorted(abs(a - b) for a, b in pairs)
    parity[feature] = {"n": len(pairs), "coverage_flip": missing,
                       "identical": round(sum(d < 1e-9 for d in diffs) / len(diffs), 4) if diffs else None,
                       "median_abs": round(statistics.median(diffs), 3) if diffs else None,
                       "p90_abs": round(diffs[int(.9 * len(diffs))], 3) if diffs else None}
# One row per player and window (nba.com's table is frozen at the regular
# season's end through the playoffs, so most players appear once).
season_parity = {}
unique = {pid: pair for (_, pid), pair in sorted(advanced_pairs.items())}
for field in ("OFF_RATING", "DEF_RATING", "NET_RATING", "PACE", "USG_PCT", "TS_PCT", "AST_PCT"):
    d = [b[field] - a[field] for a, b in unique.values()
         if a.get(field) is not None and b.get(field) is not None]
    if d:
        a_ = sorted(abs(x) for x in d)
        season_parity[field] = {"n": len(d), "median_abs": round(statistics.median(a_), 2),
                                "p90_abs": round(a_[int(.9 * len(a_))], 2), "bias": round(statistics.mean(d), 2)}
report = {"season_player_parity": season_parity, "feature_contract": FEATURE_CONTRACT, "cases": len(coverage), "paired_labeled_rows": len(both),
          "baseline_only": len(set(nb) - set(es)), "espn_only": len(set(es) - set(nb)),
          "baseline_priced": len(nb), "espn_priced": len(es), "labels": len(labels),
          "espn_tables": {k: {"box_games": v[2], "pbp_games": v[3]} for k, v in tables.items()},
          "coverage": coverage, "feature_parity": parity, "espn_http": H.summary()}
(out / "rebuild_report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False))
print(json.dumps({k: v for k, v in report.items() if k != "coverage"}, indent=1, ensure_ascii=False))

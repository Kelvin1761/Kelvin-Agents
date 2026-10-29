"""ESPN vs nba_api L10 parity through the extractor's own fetch_player_gamelog."""
import glob, json, sys, collections
from datetime import datetime
from pathlib import Path
W = str(Path(__file__).resolve().parents[3] / ".agents" / "skills" / "nba")
sys.path.insert(0, W); sys.path.insert(0, W + "/nba_data_extractor/scripts")
import nba_extractor as X
import nba_espn_stats as E
from nba_identity import player_name_key

ESPN_ID = {}
class FakeLog:
    def __init__(self, player_id, season, date_to_nullable=None, season_type_all_star="Regular Season", **_):
        d = datetime.strptime(date_to_nullable, "%m/%d/%Y").date() if date_to_nullable else None
        self.df = E.espn_gamelog_frame(ESPN_ID[player_id], season, season_type_all_star, d)
    def get_data_frames(self):
        return [self.df]
X.playergamelog.PlayerGameLog = FakeLog
X.API_SLEEP = 0
X.time.sleep = lambda s: None

STATS = ["PTS","REB","AST","STL","BLK","TOV","MIN","FGM","FGA","FG3M","FG3A","FTM","FTA"]
day = sys.argv[1]
root = f"/Users/imac/wongchoi-scheduler/{day} NBA Analysis"
cnt = collections.Counter(); diffs = []
for f in sorted(glob.glob(root + "/nba_game_data_*.json")):
    pkg = json.load(open(f)); meta = pkg["meta"]
    for team, players in pkg["players"].items():
        espn = {player_name_key(r["name"]): r["espn_id"] for r in E.espn_roster(team)}
        for p in players:
            gl = p.get("gamelog")
            if not gl or not gl.get("PTS"):
                continue
            eid = espn.get(player_name_key(p["name"]))
            if not eid:
                cnt["no_espn_id"] += 1; diffs.append(("no_espn_id", team, p["name"])); continue
            ESPN_ID[p["player_id"]] = eid
            rec = X.fetch_player_gamelog(p["player_id"], p["name"], season=meta["statistics_season"],
                                         as_of=meta["date"], include_previous=meta.get("season_phase") == "EARLY_REGULAR")
            if not rec:
                cnt["espn_none"] += 1; diffs.append(("espn_none", team, p["name"])); continue
            cnt["players"] += 1
            if rec["l10_dates"] != gl["l10_dates"]:
                cnt["dates_differ"] += 1; diffs.append(("dates", team, p["name"], gl["l10_dates"][:4], rec["l10_dates"][:4]))
                continue
            if rec["l10_matchups"] != gl["l10_matchups"]:
                cnt["matchup_differ"] += 1; diffs.append(("matchup", p["name"], gl["l10_matchups"][:3], rec["l10_matchups"][:3]))
            bad = [s for s in STATS if [float(v) for v in rec[s]] != [float(v) for v in gl[s]]]
            if bad:
                cnt["stat_differ"] += 1
                for s in bad: cnt["differ_" + s] += 1
                diffs.append(("stats", team, p["name"], bad, {s: (gl[s], rec[s]) for s in bad[:2]}))
            else:
                cnt["exact"] += 1
            if rec["games_played"] != gl["games_played"]:
                cnt["games_played_differ"] += 1
print(dict(cnt))
for d in diffs[:25]: print(d)

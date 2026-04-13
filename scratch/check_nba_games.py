import json
from nba_api.stats.endpoints import scoreboardv2
import datetime

# check for 2026-04-12 (US time corresponds to AU 04-13)
games = scoreboardv2.ScoreboardV2(game_date="2026-04-12").get_normalized_dict()
matchups = games['GameHeader']
print(f"Games found for 2026-04-12: {len(matchups)}")
for game in matchups:
    print(f"Game: {game['GAME_ID']} - {game['VISITOR_TEAM_ID']} @ {game['HOME_TEAM_ID']}")

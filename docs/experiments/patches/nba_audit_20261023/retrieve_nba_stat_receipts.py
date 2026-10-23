"""Primary NBA receipts for the fixed audit; Final stats are labels only."""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path

from nba_api.stats.endpoints import playergamelogs,leaguedashptdefend

parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);args=parser.parse_args()
if not os.path.ismount('/Volumes/Kelvin Hardisk 1'):raise SystemExit('external volume is not mounted')
root=args.root;results=root/'verified_results';results.mkdir(exist_ok=True)
path=results/'nba_playoff_final_player_logs.json'
if not path.exists():
    parameters={'season_nullable':'2025-26','season_type_nullable':'Playoffs','date_from_nullable':'04/01/2026','date_to_nullable':'06/11/2026','timeout':25}
    frame=playergamelogs.PlayerGameLogs(**parameters).get_data_frames()[0]
    path.write_text(json.dumps({'source':'NBA stats PlayerGameLogs','parameters':parameters,
        'retrieved_at':datetime.now(timezone.utc).isoformat(),'rows':json.loads(frame.to_json(orient='records'))},indent=2)+'\n')
for mode in ('PerGame','Totals'):
    path=root/f'defender_{mode}.json'
    if not path.exists():
        frame=leaguedashptdefend.LeagueDashPtDefend(defense_category='Overall',per_mode_simple=mode,season='2025-26',date_to_nullable='04/08/2026',timeout=20).get_data_frames()[0]
        path.write_text(frame.to_json(orient='records'))
print('Receipts retained; no existing response was overwritten.')

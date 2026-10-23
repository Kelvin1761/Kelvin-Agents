"""Read-only primary-source audit retrieval; results stay in external scratch."""
import os,json,time,hashlib
from pathlib import Path
from datetime import datetime,timezone
import requests
import argparse
parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);args=parser.parse_args()
root=args.root/'verified_results'
if not os.path.ismount('/Volumes/Kelvin Hardisk 1'):raise SystemExit('not mounted')
man=json.loads((root/'event_manifest.json').read_text());proof=[];s=requests.Session()
for event in man['events']:
 event_id=event['event_id'];path=root/f'summary_{event_id}.json';row={'event_id':event_id,'feature_file':event['file']}
 try:
  if not path.exists():
   url='https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event='+event_id
   response=s.get(url,timeout=20);response.raise_for_status();data=response.json()
   path.write_text(json.dumps({'source_url':url,'retrieved_at':datetime.now(timezone.utc).isoformat(),'payload':data},indent=2)+'\n')
  data=json.loads(path.read_text())['payload'];status=data['header']['competitions'][0]['status']['type']
  if data['header']['id']!=event_id or status.get('name')!='STATUS_FINAL' or not status.get('completed'):raise ValueError('not Final or event mismatch')
  teams=data.get('boxscore',{}).get('players',[])
  if len(teams)!=2 or any(not t.get('statistics') for t in teams):raise ValueError('incomplete boxscore')
  row.update(status='ok',path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),teams=[t['team']['abbreviation'] for t in teams])
 except Exception as exc:row.update(status='failed',error=type(exc).__name__,detail=str(exc)[:250])
 proof.append(row);print(event_id,row['status'],flush=True)
 (root/'boxscore_manifest.json').write_text(json.dumps({'results':proof,'state':'running'},indent=2)+'\n')
 time.sleep(.2)
(root/'boxscore_manifest.json').write_text(json.dumps({'results':proof,'state':'complete'},indent=2)+'\n')

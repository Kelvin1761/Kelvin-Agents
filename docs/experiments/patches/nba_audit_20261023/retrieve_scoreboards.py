"""Read-only primary-source audit retrieval; results stay in external scratch."""
import os,json,hashlib,time
from pathlib import Path
from datetime import datetime,timezone
from collections import defaultdict,Counter
import requests
import argparse
parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);args=parser.parse_args()
root=args.root
if not os.path.ismount('/Volumes/Kelvin Hardisk 1'):raise SystemExit('not mounted')
out=root/'verified_results';out.mkdir(exist_ok=True)
coverage=json.loads((root/'raw_temporal_coverage.json').read_text())
bydate=defaultdict(list)
for row in coverage['files']:
 if not row['flags']:bydate[row['us_game_date']].append(row)
alias={'GS':'GSW','NO':'NOP','NY':'NYK','SA':'SAS','UTAH':'UTA','WSH':'WAS'}
canon=lambda x:alias.get(x,x)
s=requests.Session();found=[];failures=[]
for date,files in sorted(bydate.items()):
 url='https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates='+date.replace('-','')+'&limit=100'
 path=out/('scoreboard_'+date+'.json')
 try:
  if path.exists():data=json.loads(path.read_text())
  else:
   response=s.get(url,timeout=15);response.raise_for_status();data=response.json()
   path.write_text(json.dumps({'source_url':url,'retrieved_at':datetime.now(timezone.utc).isoformat(),'payload':data},indent=2)+'\n')
   data=json.loads(path.read_text())
  payload=data.get('payload',data);events=payload.get('events',[])
  for row in files:
   d=json.loads(Path(row['file']).read_text());meta=d['meta'];wanted={canon(meta[side]['abbr']) for side in ('away','home')}
   matches=[e for e in events if {canon(c['team']['abbreviation']) for c in e['competitions'][0]['competitors']}==wanted]
   if len(matches)!=1:failures.append({'file':row['file'],'reason':'event_absent_or_ambiguous','n':len(matches)});continue
   e=matches[0]
   found.append({'file':row['file'],'game_date':date,'event_id':e['id'],'event_start':e['date'],'status':e['status']['type'],'source_path':str(path),'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
  print(date,'events',len(events),'matched',sum(x['game_date']==date for x in found),flush=True)
 except Exception as exc:failures.append({'date':date,'reason':type(exc).__name__,'detail':str(exc)[:200]});print(date,type(exc).__name__,flush=True)
 time.sleep(.2)
proof={'events':found,'failures':failures,'status_counts':dict(Counter(x['status']['name'] for x in found))}
(out/'event_manifest.json').write_text(json.dumps(proof,indent=2)+'\n')
print({'matched':len(found),'failures':len(failures),'statuses':proof['status_counts']},flush=True)

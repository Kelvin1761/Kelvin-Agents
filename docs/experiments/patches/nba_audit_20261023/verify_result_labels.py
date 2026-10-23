"""Read-only primary-source audit retrieval; results stay in external scratch."""
import json,os,hashlib,sys
from pathlib import Path
from collections import Counter
sys.path.insert(0,str(Path(__file__).resolve().parents[4]/'.agents/skills/nba'))
from nba_identity import player_name_key
import argparse
parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);args=parser.parse_args()
root=args.root/'verified_results'
if not os.path.ismount('/Volumes/Kelvin Hardisk 1'):raise SystemExit('not mounted')
alias={'GS':'GSW','NO':'NOP','NY':'NYK','SA':'SAS','UTAH':'UTA','WSH':'WAS'}
canon=lambda t:alias.get(t,t)
manifest=json.loads((root/'event_manifest.json').read_text());summaries={r['event_id']:r for r in json.loads((root/'boxscore_manifest.json').read_text())['results']}
pg_path=root/'nba_playoff_final_player_logs.json';nba=json.loads(pg_path.read_text())['rows'];events=[];counts=Counter()
for event in manifest['events']:
 raw=json.loads(Path(event['file']).read_text());expected={canon(raw['meta'][side]['abbr']) for side in ('away','home')}
 out={**event,'labels':[],'flags':[]};nr=[r for r in nba if r['GAME_DATE'][:10]==event['game_date'] and {r['TEAM_ABBREVIATION'],r['MATCHUP'].split()[-1]}==expected]
 if nr and len({r['GAME_ID'] for r in nr})!=1:raise ValueError('ambiguous NBA game')
 nba_labels={(canon(r['TEAM_ABBREVIATION']),player_name_key(r['PLAYER_NAME'])):{'pts':int(r['PTS']),'reb':int(r['REB']),'ast':int(r['AST']),'fg3m':int(r['FG3M'])} for r in nr}
 summary=summaries[event['event_id']]
 if summary['status']=='ok':
  data=json.loads(Path(summary['path']).read_text())['payload'];teams=data['boxscore']['players']
  if {canon(t['team']['abbreviation']) for t in teams}!=expected:raise ValueError('wrong summary teams')
  for t in teams:
   team=canon(t['team']['abbreviation']);seen=set()
   for table in t['statistics']:
    labels=table.get('names') or table['labels']
    for athlete in table.get('athletes',[]):
     name=athlete['athlete']['displayName'];key=(team,player_name_key(name))
     if key in seen:raise ValueError('duplicate athlete tables')
     seen.add(key)
     row={'player':name,'team':team,'player_key':key[1],'source_path':summary['path'],'source_sha256':summary['sha256']}
     if athlete.get('didNotPlay'):
      row['status']='void'
     else:
      stats=dict(zip(labels,athlete.get('stats',[])))
      try:
       values={k:int(stats[v].split('-')[0]) for k,v in {'pts':'PTS','reb':'REB','ast':'AST','fg3m':'3PT'}.items()}
       if any(v<0 for v in values.values()):raise ValueError('negative')
       row.update(status='played',**values)
       if key in nba_labels:
        counts['cross_checked_player_rows']+=1
        if values!=nba_labels[key]:out['flags'].append({'player':name,'reason':'source_disagreement','espn':values,'nba':nba_labels[key]})
      except (KeyError,ValueError):row['status']='unavailable'
     out['labels'].append(row)
  out['label_source']='ESPN Final summary, NBA cross-check where available'
 elif nr:
  out['label_source']='ESPN exact-event Final status plus NBA official final PlayerGameLogs'
  out['nba_game_id']=nr[0]['GAME_ID']
  for r in nr:
   team=canon(r['TEAM_ABBREVIATION']);key=player_name_key(r['PLAYER_NAME'])
   out['labels'].append({'player':r['PLAYER_NAME'],'team':team,'player_key':key,'status':'played',**nba_labels[(team,key)],'source_path':str(pg_path),'source_sha256':hashlib.sha256(pg_path.read_bytes()).hexdigest()})
 else:out['flags'].append({'reason':'no_verified_boxscore'})
 counts['events']+=1;counts['flagged_events']+=bool(out['flags']);counts.update('labels_'+r['status'] for r in out['labels'])
 events.append(out)
proof={'counts':dict(counts),'events':events}
(root/'verified_labels.json').write_text(json.dumps(proof,indent=2)+'\n');print(dict(counts));print([{'event_id':e['event_id'],'flags':e['flags']} for e in events if e['flags']])

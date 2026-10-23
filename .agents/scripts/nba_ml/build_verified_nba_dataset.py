"""Build priced v2 NBA rows from independently verified pre-tip/Final artifacts."""
from __future__ import annotations
import argparse
import csv
import json
import math
from pathlib import Path
import sys

REPO=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(REPO/'.agents/skills/nba'))
from nba_identity import player_name_key
from nba_schedule import canonical_team_abbr as canonical
from nba_ml_features import FEATURE_CONTRACT
from nba_ml_pit import sha,timestamp,game_day,capture_order
from build_nba_ml_dataset import extract_game_data


def source_players(path,event_id,day,teams):
    """Recheck label values against the hash-matched primary raw response."""
    data=json.loads(Path(path).read_text());result={}
    if 'payload' in data:
        data=data['payload'];header=data['header'];status=header['competitions'][0]['status']['type']
        if str(header['id'])!=str(event_id) or status.get('name')!='STATUS_FINAL' or not status.get('completed'):
            raise ValueError('summary event not Final')
        for group in data['boxscore']['players']:
            team=canonical(group['team']['abbreviation'])
            if team not in teams:raise ValueError('summary team mismatch')
            for table in group['statistics']:
                for entry in table.get('athletes',[]):
                    if entry.get('didNotPlay'):continue
                    values=dict(zip(table.get('names') or table['labels'],entry.get('stats',[])))
                    try:stats={key:int(values[label].split('-')[0]) for key,label in {'pts':'PTS','reb':'REB','ast':'AST','fg3m':'3PT'}.items()}
                    except (ValueError,KeyError):continue
                    identity=(team,player_name_key(entry['athlete']['displayName']))
                    if identity in result:raise ValueError('duplicate summary player')
                    result[identity]=stats
    elif data.get('source')=='NBA stats PlayerGameLogs':
        ids=set()
        for row in data['rows']:
            if row['GAME_DATE'][:10]!=day or {row['TEAM_ABBREVIATION'],row['MATCHUP'].split()[-1]}!=teams:continue
            ids.add(row['GAME_ID']);identity=(canonical(row['TEAM_ABBREVIATION']),player_name_key(row['PLAYER_NAME']))
            if identity in result:raise ValueError('duplicate NBA result player')
            result[identity]={key:int(row[label]) for key,label in {'pts':'PTS','reb':'REB','ast':'AST','fg3m':'FG3M'}.items()}
        if len(ids)!=1:raise ValueError('NBA date/team event not unique')
    else:raise ValueError('unsupported primary result provenance')
    return result


def build_verified_dataset(manifest_path,labels_path,output_dir):
    manifest_path,labels_path,output_dir=map(Path,(manifest_path,labels_path,output_dir))
    manifest=json.loads(manifest_path.read_text());labels=json.loads(labels_path.read_text())
    by_file={event['file']:event for event in labels['events']}
    if len(by_file)!=len(labels['events']):raise ValueError('duplicate label feature file')
    rows=[];coverage=[];checked_sources={};source_tables={}
    for case in manifest['cases']:
        game,odds=Path(case['game']),Path(case['odds'])
        if sha(game)!=case['game_sha256'] or sha(odds)!=case['odds_sha256']:raise ValueError('immutable feature input changed')
        event=by_file[str(game)]
        if event.get('flags'):raise ValueError('unresolved label verification flags')
        scoreboard=Path(event['source_path'])
        if sha(scoreboard)!=event['source_sha256']:raise ValueError('scoreboard hash mismatch')
        raw=json.loads(scoreboard.read_text())['payload']
        matches=[item for item in raw['events'] if str(item['id'])==str(event['event_id'])]
        if len(matches)!=1:raise ValueError('scoreboard event not unique')
        match=matches[0];status=match['status']['type']
        if status.get('name')!='STATUS_FINAL' or not status.get('completed'):raise ValueError('event not Final')
        competitors={item['homeAway']:canonical(item['team']['abbreviation']) for item in match['competitions'][0]['competitors']}
        payload=json.loads(game.read_text());meta=payload['meta'];teams=set(competitors.values())
        if any(canonical(meta[side]['abbr'])!=competitors[side] for side in ('away','home')):raise ValueError('home/away identity mismatch')
        if game_day(meta)!=event['game_date']:raise ValueError('US result/feature date mismatch')
        tip=timestamp(match['date'])
        provenance={'game_modified_at':case['drive_modified_at'],'odds_modified_at':case['odds_source']['modified_time'],
                    'kind':'independent Google Drive source metadata','input_manifest_sha256':sha(manifest_path)}
        if not tip or any(timestamp(provenance[key]) is None or timestamp(provenance[key])>=tip for key in ('game_modified_at','odds_modified_at')):
            raise ValueError('source timestamp not before verified event tip')
        features=extract_game_data(game,odds_path=odds,provenance=provenance)
        if any(row['pit_status']!='verified' for row in features):raise ValueError('unverified feature capture')
        players={}
        for label in event['labels']:
            if label['status']!='played':continue
            identity=(label['team'],label['player_key'])
            if identity in players:raise ValueError('ambiguous label identity')
            source=Path(label['source_path']);digest=label['source_sha256']
            if source not in checked_sources:
                checked_sources[source]=sha(source)
            if checked_sources[source]!=digest:raise ValueError('label source hash mismatch')
            source_key=(source,event['event_id'])
            if source_key not in source_tables:source_tables[source_key]=source_players(source,event['event_id'],event['game_date'],teams)
            parsed=source_tables[source_key]
            if identity not in parsed or any(parsed[identity][key]!=label[key] for key in ('pts','reb','ast','fg3m')):
                raise ValueError('label values disagree with primary source')
            players[identity]=label
        labeled=0
        for row in features:
            label=players.get((row['team'],row['player_key']))
            if label:
                actual=label[{'PTS':'pts','REB':'reb','AST':'ast','FG3M':'fg3m'}[row['stat_category']]]
                if isinstance(actual,bool) or not math.isfinite(actual) or actual<0:raise ValueError('invalid label count')
                row.update(actual_value=actual,hit=int(actual>=row['line_value']),result_status='Final',
                           source_result_path=label['source_path'],source_result_sha256=label['source_sha256'])
                labeled+=1
            rows.append(row)
        coverage.append({'case_id':case['case_id'],'priced_rows':len(features),'labeled_rows':labeled,
                         'void_or_missing_label_rows':len(features)-labeled,'event_id':event['event_id']})
    # Resolve duplicate captures before fitting, always taking the earliest,
    # with no use of price attractiveness, hits or validation performance.
    unique={};duplicates=0
    for row in sorted(rows,key=lambda item:(timestamp(item['captured_at']).timestamp(),item['source_game_path'])):
        key=tuple(row[name] for name in ('game_group','player_key','stat_category','line_value'))
        if key in unique:
            duplicates+=1
            if unique[key]['actual_value']!=row['actual_value']:raise ValueError('conflicting event labels')
            if capture_order(row)<capture_order(unique[key]):unique[key]=row
        else:unique[key]=row
    rows=list(unique.values())
    if not rows:raise ValueError('no priced feature rows')
    output_dir.mkdir(parents=True,exist_ok=False)
    with (output_dir/'dataset.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    report={'feature_contract':FEATURE_CONTRACT,'manifest_sha256':sha(manifest_path),'labels_sha256':sha(labels_path),
            'dataset_sha256':sha(output_dir/'dataset.csv'),'cases':coverage,'duplicate_rows_resolved_earliest':duplicates,
            'rows':len(rows),'labeled_rows':sum(row['hit'] is not None for row in rows),
            'game_dates':sorted({row['game_date'] for row in rows})}
    (output_dir/'dataset_meta.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({key:report[key] for key in ('feature_contract','rows','labeled_rows','dataset_sha256')},indent=2))
    return output_dir/'dataset.csv'


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--manifest',required=True);parser.add_argument('--labels',required=True);parser.add_argument('--output-dir',required=True)
    args=parser.parse_args();build_verified_dataset(args.manifest,args.labels,args.output_dir)


if __name__=='__main__':main()

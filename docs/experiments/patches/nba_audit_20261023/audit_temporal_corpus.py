"""Reproduce the source/time screen without reading or selecting by outcomes."""
import argparse
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

REPO=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(REPO/'.agents/scripts/nba_ml'))
from nba_ml_pit import log_day,timestamp,sha
from capture_replay import discover


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);args=parser.parse_args()
    root=args.root;inventory=json.loads((root/'source_drive_inventory.json').read_text())
    metadata={(entry['folder']['title'],f['title']):f for entry in inventory for f in entry['files']}
    coverage=Counter();rows=[];bad=[]
    for path in sorted((root/'corpus').glob('*/nba_game_data_*.json')):
        payload=json.loads(path.read_text());meta=payload.get('meta') or {};row={'file':str(path),'flags':[]};coverage['files']+=1
        tip=timestamp(meta.get('date'));captured=timestamp(meta.get('extracted_at'),legacy_sydney=True)
        if not tip or not captured:
            row['flags'].append('timestamp_unknown');coverage['timestamp_unknown']+=1;rows.append(row);continue
        day=tip.astimezone(ZoneInfo('America/Los_Angeles')).date()
        row.update(tip=tip.isoformat(),us_game_date=str(day),captured_at=captured.isoformat())
        if captured>=tip:row['flags'].append('capture_post_tip')
        source=metadata.get((path.parent.name,path.name),{});modified=timestamp(source.get('modified_time'))
        row['drive_modified_at']=source.get('modified_time')
        if not modified or modified>=tip:row['flags'].append('drive_modified_after_tip');coverage['drive_modified_after_tip']+=1
        else:coverage['drive_modified_before_tip']+=1
        for players in payload.get('players',{}).values():
            for player in players:
                coverage['players']+=1;gl=player.get('gamelog') or {};dates=gl.get('l10_dates') or []
                if not dates:coverage['logs_missing_dates']+=1;continue
                coverage['logs_with_dates']+=1;parsed=[log_day(value) for value in dates]
                if any(value is None for value in parsed):
                    row['flags'].append('history_dates_invalid');coverage['log_date_parse_failed']+=1
                elif any(value>=day for value in parsed):
                    row['flags'].append('target_or_future_logs');coverage['logs_contains_target_or_future']+=1
                    bad.append({'file':str(path),'player':player['name'],'tip':meta['date'],'latest':str(max(parsed))})
                else:coverage['logs_strictly_prior']+=1
        rows.append(row)
    temporal={'coverage':dict(coverage),'files':rows,'target_or_future_logs':bad}
    output=root/'raw_temporal_coverage_reproduced.json'
    if output.exists():raise ValueError('reproduction output already exists')
    output.write_text(json.dumps(temporal,indent=2)+'\n')
    immutable={row['file']:row for row in rows if not row['flags']}
    manifest=discover(root/'corpus');cases=[];counts=Counter()
    for case in manifest['cases']:
        if case['game'] not in immutable:continue
        counts['matched_raw']+=1;row=immutable[case['game']];path=Path(case['odds'])
        source=metadata.get((path.parent.name,path.name),{});modified=timestamp(source.get('modified_time'))
        if not modified or modified>=timestamp(row['tip']):counts['odds_not_verified_pre_tip']+=1;continue
        counts['both_sources_pretip']+=1;cases.append({**case,**row,'odds_source':source})
    (root/'strict_priced_manifest_reproduced.json').write_text(json.dumps({'cases':cases,'coverage':dict(counts),
        'dates':dict(Counter(c['us_game_date'] for c in cases)),'inventory_sha256':sha(root/'source_drive_inventory.json')},indent=2)+'\n')
    print(json.dumps({'coverage':dict(coverage),'priced':dict(counts)}))


if __name__=='__main__':main()

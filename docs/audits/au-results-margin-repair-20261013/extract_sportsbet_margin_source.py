"""Read frozen post-race cache only: dated result metadata, never scoring inputs.

Adapted from docs/audits/au-full-model-20261011/extract_dated_result_sources.py (Codex).
Usage: python3 extract_sportsbet_margin_source.py <out_dir>   (run from the scheduler worktree)
"""
import csv,hashlib,json,os,sys
from collections import Counter,defaultdict
from pathlib import Path
root=Path('/Users/imac/wongchoi-scheduler')
report=Path(sys.argv[1]); report.mkdir(parents=True, exist_ok=True)
os.environ['WC_SB_CACHE_ONLY']='1'
scripts=root/'.agents/skills/au_racing'
sys.path.insert(0,str(scripts))
from claw_sportsbet_form import BASE,SportsbetFormFetcher,parse_race,parse_runner_blocks,run_date
sys.path.insert(0,str(scripts/'au_wong_choi_auto/scripts'))
from au_racing_engine.source_alignment import normalize_horse_name
fetcher=SportsbetFormFetcher(delay=0,verbose=False)
ids_path=scripts/'data/sb_archive_meeting_ids.json'
ids=json.loads(ids_path.read_text())
fields=['Date','Track','Race','Horse','Pos','Barrier','Weight','Jockey','Trainer','Distance','Condition','Margin','Time','WinningTime']
rows,links,conflicts=[],[],[]
seen={}
stats=Counter()
for name,meta in sorted(ids.items()):
 if not ('2026-08-24'<=meta['date']<='2026-08-30' or meta['date']=='2026-10-11'): continue
 for rid in meta['races']:
  url=f"{BASE}/{meta['meetingId']}/{rid}/"
  path=fetcher._cache_path(url)
  if not path.exists(): stats['uncached_race_pages']+=1;continue
  # Read frozen file directly: no network/cache refresh and no publication-time inference.
  html=path.read_text()
  digest=hashlib.sha256(path.read_bytes()).hexdigest()
  parsed=parse_race(html)
  rno=parsed['meta'].get('race_number')
  if rno is None: stats['missing_race_number']+=1;continue
  stats['cached_race_pages']+=1
  for block in parse_runner_blocks(html):
   matches=[run for run in block.get('runs',[]) if run_date(run)==meta['date'] and str((run.get('header') or {}).get('race'))==str(rno)]
   if not matches: stats['runner_without_target_run']+=1;continue
   signatures={json.dumps(run,sort_keys=True) for run in matches}
   if len(signatures)>1:
    conflicts.append({'kind':'multiple_dated_runs','date':meta['date'],'meeting':name,'race':rno,'horse':block['name'],'source':str(path)})
    continue
   run=matches[0]; h=run.get('header') or {}
   try: pos=int(run['pos'])
   except (KeyError,ValueError,TypeError): stats['invalid_finish']+=1;continue
   if pos<1: stats['invalid_finish']+=1;continue
   track=meta['slug'].replace('_',' ').title()
   row={'Date':meta['date'],'Track':track,'Race':str(rno),'Horse':block['name'],'Pos':str(pos),'Barrier':run.get('barrier') or '', 'Weight':run.get('weight') or '', 'Jockey':(run.get('jockey') or '').strip(),'Trainer':'','Distance':h.get('dist') or '', 'Condition':(h.get('going') or '').strip(),'Margin':'0' if pos==1 else (run.get('margin') or ''),'Time':'','WinningTime':run.get('winning_time') or ''}
   key=(row['Date'],row['Track'],row['Race'],normalize_horse_name(row['Horse']))
   if key in seen:
    if seen[key]!=row: conflicts.append({'kind':'conflicting_same_identity','key':key,'first':seen[key],'second':row,'source':str(path)})
    else:stats['identical_duplicates']+=1
    continue
   seen[key]=row;rows.append(row)
   links.append({'key':key,'source_path':str(path),'source_sha256':digest,'dated_run_track':h.get('track'),'dated_run_date':run_date(run),'dated_run_race':h.get('race'),'pit_status':'POST_RACE_LABEL_METADATA_ONLY','trainer_reason':'No dated trainer in matched run; current overview not used.','Time_reason':'WinningTime is race winner time, not this runner Time.','track_join_status':'MAPPING_TRACK_WITH_RAW_RUN_TRACK_REQUIRES_ALIAS_RECONCILIATION'})
  if stats['cached_race_pages']%100==0: print(f"pages={stats['cached_race_pages']} rows={len(rows)}",flush=True)
rows.sort(key=lambda r:(r['Date'],r['Track'],int(r['Race']),normalize_horse_name(r['Horse'])))
output=report/'dated_result_source_rows.csv'
with output.open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
(report/'dated_result_source_lineage.json').write_text(json.dumps(links,indent=2))
(report/'dated_result_source_conflicts.json').write_text(json.dumps(conflicts,indent=2))
monthly=defaultdict(lambda: {'rows':0,'present':Counter()})
for row in rows:
 month=row['Date'][:7]; monthly[month]['rows']+=1
 for field in fields:
  if row[field]!='':monthly[month]['present'][field]+=1
summary={'schema':'au-dated-result-source-audit/v1','stats':dict(stats),'rows':len(rows),'races':len({(r['Date'],r['Track'],r['Race']) for r in rows}),'conflicts':len(conflicts),'monthly':dict(monthly),'csv_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'mapping_sha256':hashlib.sha256(ids_path.read_bytes()).hexdigest(),'parser_sha256':hashlib.sha256((scripts/'claw_sportsbet_form.py').read_bytes()).hexdigest(),'production_write':False,'repair_applied':False,'limitations':['Not PIT-certified scoring input; post-race labels and metadata only.','Raw source track aliases not yet reconciled against mapping track.','Trainer unavailable from dated run; no current summary backfill.','Time intentionally empty; WinningTime separate.','Cache mtime is not availability proof.','No odds or market fields extracted.']}
(report/'dated_result_source_summary.json').write_text(json.dumps(summary,indent=2))
print(json.dumps({k:summary[k] for k in ['rows','races','conflicts','stats']}),flush=True)

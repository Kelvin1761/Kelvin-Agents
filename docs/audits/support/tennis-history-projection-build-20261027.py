import json,sqlite3,hashlib,os
from pathlib import Path
source=Path('/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-bugs-20261026/bug_research_baseline.db')
output=Path('/private/tmp/tennis-feature-projection-20261027.db')
assert not output.exists()
assert os.statvfs('/private/tmp').f_bavail*os.statvfs('/private/tmp').f_frsize>10_000_000_000
baseline=json.load(open('/private/tmp/tennis-history-features-baseline.json'))
ids=baseline['ids']
s=sqlite3.connect(f'{source.as_uri()}?mode=ro',uri=True);s.row_factory=sqlite3.Row
players=sorted({r[0] for r in s.execute('SELECT player_a_id FROM matches WHERE id IN (SELECT value FROM json_each(?)) UNION SELECT player_b_id FROM matches WHERE id IN (SELECT value FROM json_each(?))',(json.dumps(ids),json.dumps(ids)))})
t=sqlite3.connect(output);t.execute('PRAGMA journal_mode=OFF');t.execute('PRAGMA temp_store=MEMORY')
tables=['player_match_history','players','matches','tournaments','tournament_levels','rankings_history',
        'player_elo_history','player_elo_history_v2','raw_api_responses','news_snapshots',
        'odds_snapshots','market_odds_snapshots','feature_snapshots']
counts={};related=set(players)
try:
 for table in tables:
  schema=s.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone()
  if not schema:continue
  t.execute(schema[0]);columns=[r['name'] for r in s.execute(f'PRAGMA table_info({table})')]
  where='';params=()
  if table=='player_match_history':
   where=' WHERE player_id IN (SELECT value FROM json_each(?)) OR opponent_id IN (SELECT value FROM json_each(?))';params=(json.dumps(players),)*2
  elif table=='rankings_history':
   where=' WHERE player_id IN (SELECT value FROM json_each(?))';params=(json.dumps(sorted(related)),)
  elif table.startswith('player_elo_history') or (table=='news_snapshots' and 'player_id' in columns):
   where=' WHERE player_id IN (SELECT value FROM json_each(?))';params=(json.dumps(players),)
  elif table in ('odds_snapshots','market_odds_snapshots','feature_snapshots'):
   where=' WHERE match_id IN (SELECT value FROM json_each(?))';params=(json.dumps(ids),)
  expressions=["'{}' AS "+c if table=='raw_api_responses' and c in ('request_params_json','response_json') else c for c in columns]
  cursor=s.execute(f'SELECT {",".join(expressions)} FROM {table}{where}',params)
  n=0
  while True:
   rows=cursor.fetchmany(500)
   if not rows:break
   t.executemany(f'INSERT INTO {table}({",".join(columns)}) VALUES ({",".join("?" for _ in columns)})',[tuple(r) for r in rows]);n+=len(rows)
   if table=='player_match_history':
    for r in rows:related.update(v for v in (r['player_id'],r['opponent_id']) if v is not None)
   if output.stat().st_size>500_000_000:raise RuntimeError('projection cap reached')
  t.commit();counts[table]=n
  print(table,n,output.stat().st_size,flush=True)
  for index in s.execute("SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name=? AND sql IS NOT NULL",(table,)):
   t.execute(index[0])
 t.commit();assert t.execute('PRAGMA quick_check').fetchone()[0]=='ok'
finally:
 t.close();s.close()
manifest={'source':str(source),'source_sha256':'2e13a17a63871cbd5e108a4c258ec1c7193d1c032752ed74025f8f02249284ac',
          'fixture_ids':ids,'player_ids':players,'rows':counts,'projection':str(output),
          'projection_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
          'limitations':['Only for the fixed fixture feature/probability probe; not a replacement evaluation corpus.',
                        'Unused raw response bodies/request JSON omitted; provenance metadata retained.',
                        'Must verify full baseline feature payload equality before candidate comparisons.']}
Path('/private/tmp/tennis-feature-projection-manifest.json').write_text(json.dumps(manifest,indent=2))

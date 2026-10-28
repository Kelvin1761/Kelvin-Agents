import sqlite3,sys,json,hashlib,inspect
from pathlib import Path
import tennis_wc.features.feature_builder as b
path=Path('/private/tmp/tennis-feature-projection-20261027.db')
connection=sqlite3.connect(f'{path.as_uri()}?mode=ro',uri=True)
connection.row_factory=sqlite3.Row
connection.execute('PRAGMA cache_size=-131072')
class ReadOnlySession:
 def execute(self,*args): return connection.execute(*args)
 def close(self): pass
 def __enter__(self): return self
 def __exit__(self,*args): return False
session=ReadOnlySession()
def ro(): return session
for name,module in list(sys.modules.items()):
 if name.startswith('tennis_wc.features.') and hasattr(module,'get_connection'):
  module.get_connection=ro
 if name.startswith('tennis_wc.features.') and hasattr(module,'utc_now'):
  module.utc_now=lambda:'2026-10-26T00:00:00Z'
with ro() as c:
 ids=[r[0] for r in c.execute('''WITH candidates AS (
 SELECT id,NTILE(12) OVER(ORDER BY match_date,id) bucket FROM matches
 WHERE match_date BETWEEN '2026-08-01' AND '2026-10-25' AND start_time_utc IS NOT NULL
 AND player_a_id!=player_b_id AND source_provider!='mock'), ranked AS (
 SELECT id,ROW_NUMBER() OVER(PARTITION BY bucket ORDER BY id) n FROM candidates)
 SELECT id FROM ranked WHERE n=1 ORDER BY id''')]
results={}
for mid in ids:
 try:
  snapshot,valid=b.assemble_match_feature_snapshot(mid)
  results[str(mid)]={'snapshot':snapshot,'validation':valid}
 except Exception as e:
  results[str(mid)]={'error':str(e)}
 print(mid,flush=True)
output={'dataset':str(path),'dataset_sha256':'b4119900e1e44eaeb5602c86ac9a56276d333c6b029cde0419f6a7682a74e9c0','source_dataset_sha256':'2e13a17a63871cbd5e108a4c258ec1c7193d1c032752ed74025f8f02249284ac','ids':ids,'source_sha256':hashlib.sha256(Path(inspect.getfile(b)).read_bytes()).hexdigest(),'results':results}
Path(sys.argv[1]).write_text(json.dumps(output,indent=2))

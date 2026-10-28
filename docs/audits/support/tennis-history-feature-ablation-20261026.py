import sqlite3,sys,json,hashlib,inspect
from pathlib import Path
import tennis_wc.features.feature_builder as b
path=Path('/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-bugs-20261026/bug_research_baseline.db')
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
from tennis_wc.modelling.probability_model import predict_match_probability
modules=[module for name,module in list(sys.modules.items()) if name.startswith('tennis_wc.features.')]
original={(id(module),key):getattr(module,key) for module in modules
          for key in ('guard_clause','guard_params','clean_history_row') if hasattr(module,key)}
outputs={}
for arm in ('guard_only','values_only','combined'):
 for module in modules:
  for key in ('guard_clause','guard_params','clean_history_row'):
   if (id(module),key) in original:
    setattr(module,key,original[(id(module),key)])
  if arm=='guard_only' and hasattr(module,'clean_history_row'):
   module.clean_history_row=dict
  if arm=='values_only':
   if hasattr(module,'guard_clause'): module.guard_clause=lambda *args:''
   if hasattr(module,'guard_params'): module.guard_params=lambda *args:()
 results={}
 for mid in ids:
  try:
   snapshot,valid=b.assemble_match_feature_snapshot(mid)
   results[str(mid)]={'snapshot':snapshot,'validation':valid,'model':predict_match_probability(snapshot)}
  except Exception as e:
   results[str(mid)]={'error':str(e)}
  print(arm,mid,flush=True)
 outputs[arm]=results
output={'dataset':str(path),'dataset_sha256':'2e13a17a63871cbd5e108a4c258ec1c7193d1c032752ed74025f8f02249284ac',
        'ids':ids,'source_files':{str(Path(inspect.getfile(module))):hashlib.sha256(Path(inspect.getfile(module)).read_bytes()).hexdigest()
                                for module in modules if hasattr(module,'__file__')},'arms':outputs}
Path(sys.argv[1]).write_text(json.dumps(output,indent=2))

import sqlite3, json, hashlib, os
from pathlib import Path
source=Path('/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-bugs-20261026/bug_research_baseline.db')
output=Path('/private/tmp/tennis-elo-source-projection-20261027.db')
assert not output.exists()
assert os.statvfs('/private/tmp').f_bavail*os.statvfs('/private/tmp').f_frsize>10_000_000_000
s=sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)
t=sqlite3.connect(output);t.execute('PRAGMA journal_mode=OFF');counts={}
for name in ('players','player_match_history'):
 t.execute(s.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone()[0])
 columns=[r[1] for r in s.execute('PRAGMA table_info('+name+')')]
 cur=s.execute('SELECT * FROM '+name);count=0
 while True:
  rows=cur.fetchmany(1000)
  if not rows:break
  t.executemany('INSERT INTO '+name+' VALUES ('+','.join('?' for _ in columns)+')',rows);count+=len(rows)
  if output.stat().st_size>500_000_000:raise RuntimeError('projection size cap exceeded')
 for row in s.execute("SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name=? AND sql IS NOT NULL",(name,)):t.execute(row[0])
 t.commit();counts[name]=count
 print(name,count,flush=True)
assert t.execute('PRAGMA quick_check').fetchone()[0]=='ok'
t.close();s.close()
manifest={'source':str(source),'source_sha256':'2e13a17a63871cbd5e108a4c258ec1c7193d1c032752ed74025f8f02249284ac','projection':str(output),'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'bytes':output.stat().st_size,'row_counts':counts,'limitations':['Only complete player/history tables; raw source bodies and unrelated tables are not copied. Not an evaluation corpus.']}
Path('/private/tmp/tennis-elo-projection-manifest.json').write_text(json.dumps(manifest,indent=2))
print(manifest,flush=True)

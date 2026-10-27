"""Lossless projection of every row in the tables used by the profit diagnostic."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3

TABLES = ('matches','predictions','odds_snapshots','match_results','result_observations',
          'tournaments','tournament_levels','players')
p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--output',required=True);p.add_argument('--manifest',required=True)
a=p.parse_args();source=Path(a.source).resolve();output=Path(a.output).resolve()
assert not output.exists()
assert os.statvfs(output.parent).f_bavail*os.statvfs(output.parent).f_frsize>10_000_000_000
s=sqlite3.connect(source.as_uri()+'?mode=ro',uri=True);s.execute('BEGIN')
t=sqlite3.connect(output);t.execute('PRAGMA journal_mode=OFF');counts={}
try:
 for name in TABLES:
  schema=s.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone()
  if schema is None:raise RuntimeError('required table missing: '+name)
  t.execute(schema[0]);cols=list(s.execute('PRAGMA table_info('+name+')'))
  cursor=s.execute('SELECT * FROM '+name);n=0
  while True:
   rows=cursor.fetchmany(500)
   if not rows:break
   t.executemany('INSERT INTO '+name+' VALUES ('+','.join('?' for _ in cols)+')',rows);n+=len(rows)
   if output.stat().st_size>500_000_000:raise RuntimeError('projection exceeds local size cap')
  assert n==s.execute('SELECT COUNT(*) FROM '+name).fetchone()[0]
  for index in s.execute("SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name=? AND sql IS NOT NULL",(name,)):t.execute(index[0])
  t.commit();counts[name]=n
 assert t.execute('PRAGMA quick_check').fetchone()[0]=='ok'
finally:
 t.close();s.close()
manifest={'source':str(source),'snapshot_at':datetime.now(timezone.utc).isoformat(),
          'tables':counts,'projection':str(output),'bytes':output.stat().st_size,
          'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
          'method':'All columns and rows in all named tables, in one source read transaction; no outcome or cohort selection.'}
Path(a.manifest).write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(manifest))

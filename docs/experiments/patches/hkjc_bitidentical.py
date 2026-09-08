#!/usr/bin/env python3
"""證明 Q1 個「獨立一節」係恆等變換：193 場逐匹馬對 ability_score，
一定要 bit-identical（memory: display-only-changes-leak-into-ranking）。"""
import os, sys, json, subprocess
from pathlib import Path
os.environ.setdefault("PYTHONDONTWRITEBYTECODE","1")
R=Path(sys.argv[1])
for p in ('.agents/skills/hkjc_racing/hkjc_reflector/scripts','.agents/scripts',
          '.agents/skills/shared_racing/scripts',
          '.agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts'):
    sys.path.insert(0,str(R/p))
import pit_backtest as pb, rescore_backtest as bt
DIRS=sorted([Path(l.strip()) for l in open('/tmp/hkjc_bt.lst') if l.strip()])
ROWS=pb.load_all_rows(); out={}
for md in DIRS:
    d=pb.meeting_date_from_dir(md)
    if not d: continue
    pb.inject_as_of(ROWS,d)
    races,_=bt.rescore_meeting(md,include_legacy=False)
    for i,race in enumerate(races):
        for s in race["scored"]:
            out[f"{md.name}|{i}|{s['hn']}"]=repr(s["ability"])
json.dump(out,open(sys.argv[2],'w')); print(f"{len(out)} runner → {sys.argv[2]}")

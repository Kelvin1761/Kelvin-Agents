#!/usr/bin/env python3
"""A/B the 走位匹配 correctness fixes (race-identity dedupe + sample shrinkage).

The digest lives in the Logic files, so the arms rebuild `draw_position_fit`
from the Facts markdown at score time. Written to BOTH the horse top level and
`_data` because `engine_core._value()` checks the top level first — writing only
`_data` gets shadowed and every arm comes out identical.
"""
import importlib.util, os, re, sys, json
from pathlib import Path
os.environ.setdefault("PYTHONDONTWRITEBYTECODE","1")
FW=Path('/Users/imac/CodexWork/wc-drawfit')
for p in ('.agents/skills/hkjc_racing/hkjc_reflector/scripts','.agents/scripts',
          '.agents/skills/shared_racing/scripts',
          '.agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts',
          '.agents/skills/hkjc_racing/hkjc_wong_choi/scripts'):
    sys.path.insert(0,str(FW/p))
import pit_backtest as pb, rescore_backtest as bt

def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec); sys.modules[name]=m; spec.loader.exec_module(m); return m
NEW=load(str(FW/'.agents/skills/hkjc_racing/hkjc_wong_choi/scripts/create_hkjc_logic_skeleton.py'),'skel_new')
OLD=load('/tmp/oldskel/a/b/c/d/e/f/old_skeleton.py','skel_old')
DED=load('/tmp/v_ded/a/b/c/d/e/f/skel.py','skel_ded')      # 只修去重 key
SHR=load('/tmp/v_shr/a/b/c/d/e/f/skel.py','skel_shr')      # 只加樣本門檻

DIRS=[Path(l.rstrip('\n')) for l in open('/tmp/hkjc_bt.lst') if l.strip()]
HDR=re.compile(r'^### 馬號\s*(\S+)\s*—', re.M)
_orig=bt.rescore_logic
MODE={'mod':None}
CUR={'meeting':None}
STAT={'touched':0,'changed':0}

def facts_digests(meeting, race, mod):
    for fp in meeting.glob('*Facts.md'):
        m=re.search(r'Race\s*(\d+)',fp.name,re.I)
        if not m or int(m.group(1))!=race: continue
        txt=fp.read_text(encoding='utf-8',errors='replace'); ms=list(HDR.finditer(txt)); out={}
        for i,hm in enumerate(ms):
            blk=txt[hm.end():ms[i+1].start() if i+1<len(ms) else len(txt)]
            b=re.search(r'檔位:\s*(\d+)',blk); barrier=int(b.group(1)) if b else 0
            hist=mod.parse_all_draw_history(blk)
            if not hist: continue
            out[hm.group(1).strip()]=mod.compute_draw_position_fit([],barrier,hist)
        return out
    return {}

def patched(logic,**kw):
    mod=MODE['mod']
    if mod is not None:
        rn=(logic.get('race_analysis') or {}).get('race_number')
        digests=facts_digests(CUR['meeting'],int(rn),mod) if rn else {}
        for num,h in (logic.get('horses') or {}).items():
            if not isinstance(h,dict): continue
            d=digests.get(str(num))
            if not d: continue
            dd=h.setdefault('_data',{})
            before=str(h.get('draw_position_fit') or dd.get('draw_position_fit') or '')
            for tgt in (h,dd): tgt['draw_position_fit']=d
            STAT['touched']+=1
            if before!=d: STAT['changed']+=1
    return _orig(logic,**kw)
bt.rescore_logic=patched

ROWS=pb.load_all_rows()
res={}
for name,mod in (('DF0 baseline',None),('DF1 舊 digest 重建',OLD),('DF2a 只修去重 key',DED),('DF2b 只加樣本門檻',SHR),('DF3 兩個一齊',NEW)):
    MODE['mod']=mod; STAT.update({'touched':0,'changed':0})
    races=[]
    for md in sorted(DIRS):
        d=pb.meeting_date_from_dir(md)
        if not d: continue
        pb.inject_as_of(ROWS,d); CUR['meeting']=md
        r,_=bt.rescore_meeting(md,include_legacy=False); races.extend(r)
    agg=bt.evaluate(races); n=agg['races'] or 1
    res[name]={m:round(100*agg[m]/n,2) for m in bt.METRICS}
    print('%-26s races=%3d touched=%4d changed=%4d  '%(name,agg['races'],STAT['touched'],STAT['changed'])
          +'  '.join('%s=%5.2f'%(m,100*agg[m]/n) for m in bt.METRICS),flush=True)
MODE['mod']=None
json.dump(res,open('/tmp/ab_drawfit.json','w'),indent=1)

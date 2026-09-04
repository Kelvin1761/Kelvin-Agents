#!/usr/bin/env python3
"""A/B the 賽績線 fixes on the PIT corpus.

Both fixes live upstream of the Logic files, so the arms rebuild
`_data.formline_table` from the Facts markdown on disk before scoring:

  FL0  baseline        — the truncated table currently stored in Logic
  FL1  row fix         — carry race context onto continuation rows (60.9% of
                         opponent rows were being dropped)
  FL2  class floor     — an opponent who later CONTESTED graded races is
                         evidence of a strong field even with no win
  FL3  FL1 + FL2
"""
import os, re, sys, json
from pathlib import Path
os.environ.setdefault("PYTHONDONTWRITEBYTECODE","1")
R=Path('/Users/imac/Antigravity-repo')
for p in ('.agents/skills/hkjc_racing/hkjc_reflector/scripts','.agents/scripts',
          '.agents/skills/shared_racing/scripts',
          '.agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts',
          '.agents/skills/hkjc_racing/hkjc_wong_choi/scripts'):
    sys.path.insert(0,str(R/p))
import pit_backtest as pb, rescore_backtest as bt
from hkjc_racing_engine import engine_core as ec

DIRS=[Path(l.rstrip('\n')) for l in open('/tmp/hkjc_bt.lst') if l.strip()]
GRADED=('一級賽','二級賽','三級賽','分級賽','第一班')
_orig_rescore=bt.rescore_logic
_orig_fl=ec.RacingEngine._formline_strength_score
MODE={'rows':False,'floor':False,'thin':False}

# ── Facts → full opponent table ────────────────────────────────────────────
_TBL=re.compile(r'🔗 \*\*賽績線:\*\*.*?\n(\|[^\n]+\n\|[-| ]+\n)(.*?)(?=\n\n|\n💡|\Z)', re.S)
_HDR=re.compile(r'^### 馬號\s*(\S+)\s*—\s*([^|\n]+)', re.M)

def facts_tables(meeting: Path, race_no: int):
    """{horse_no: [row, ...]} from that race's Facts.md, full rows."""
    out={}
    for fp in meeting.glob('*Facts.md'):
        m=re.search(r'Race\s*(\d+)', fp.name, re.I)
        if not m or int(m.group(1))!=race_no:
            continue
        txt=fp.read_text(encoding='utf-8',errors='replace')
        marks=list(_HDR.finditer(txt))
        for i,hm in enumerate(marks):
            start=hm.end(); end=marks[i+1].start() if i+1<len(marks) else len(txt)
            block=txt[start:end]
            tm=_TBL.search(block)
            if not tm: continue
            rows=[]; ctx=['','','','']
            for line in tm.group(2).strip().split('\n'):
                if not line.strip().startswith('|'): continue
                c=[x.strip() for x in line.split('|')]
                if len(c)<9: continue
                if c[1].isdigit(): ctx=[c[1],c[2],c[3],c[4]]
                elif not ctx[0]: continue
                if not c[5] or c[5]=='對手': continue
                rows.append({'race_num':ctx[0],'date':ctx[1],'race_id':ctx[2],
                             'my_finish':ctx[3],'opponents':c[5],
                             'next_class':c[6],'next_performance':c[7],'strength':c[8]})
            if rows: out[str(hm.group(1)).strip()]=rows
    return out

# ── FL2: relabel a row using the class it was contested at ────────────────
def relabel(row):
    """兩個獨立改動，可以分開開關（AGENTS.md：一齊郁就要做 ablation）。
      floor —— 對手其後**參賽**過分級賽／第一班，本身就係強陣證據（唔需要再贏）
      thin  —— 後續出賽 <3 次而冇贏冇上名 = 冇證據，唔係「弱組」（AU 版本已經係咁）
    """
    s=str(row.get('strength') or '').strip()
    nc=str(row.get('next_class') or '')
    perf=str(row.get('next_performance') or '')
    if s in ('','-'): return s
    if '超強組' in s or ('強組' in s and '中' not in s): return s   # a win already counted
    m=re.search(r'出\s*(\d+)\s*次', perf)
    runs=int(m.group(1)) if m else 0
    graded=any(g in nc for g in GRADED)
    if MODE['floor'] and graded:
        return '✅ 強組' if runs>=2 else '⚠️ 中組'
    if MODE['thin'] and runs and runs<3 and '弱組' in s:
        return '-'
    return s

def ratio_from(rows):
    sc=0.0; tot=0
    for r in rows:
        s=relabel(r) if (MODE['floor'] or MODE['thin']) else str(r.get('strength') or '').strip()
        if s in ('','-'): continue
        tot+=1
        sc += 2.0 if '超強組' in s else 1.0 if ('強組' in s and '中' not in s) else 0.5 if '中組' in s else 0.0
    return sc,tot

def rating_from(sc,tot):
    if tot==0: return '無資料'
    r=sc/tot
    return '✅✅ 極強' if r>=0.7 else '✅ 強' if r>=0.5 else '中強' if r>=0.3 else '中弱' if r>=0.15 else '❌ 弱'

# ── wire the arms in ──────────────────────────────────────────────────────
CUR={'meeting':None}
STAT={'touched':0,'changed':0,'notable':0}
def patched_rescore(logic,**kw):
    if MODE['rows'] or MODE['floor']:
        race_no=(logic.get('race_analysis') or {}).get('race_number')
        tables=facts_tables(CUR['meeting'], int(race_no)) if race_no else {}
        for num,h in (logic.get('horses') or {}).items():
            if not isinstance(h,dict): continue
            dd=h.setdefault('_data',{})
            rows=tables.get(str(num)) if MODE['rows'] else dd.get('formline_table')
            if not rows: continue
            # `_value` 先睇 horse top-level 再睇 `_data` —— 只寫 `_data` 會被
            # 上面同名嘅 key 遮住，四個 arm 就會出一模一樣嘅結果。兩邊都要寫。
            before=str(h.get('formline_strength') or dd.get('formline_strength') or '')
            label=f"{rating_from(*ratio_from(rows))} (強組比例: %.0f/%d)"%ratio_from(rows)
            for tgt in (h,dd):
                tgt['formline_table']=rows
                tgt['formline_strength']=label
            STAT['touched']+=1
            if before!=label: STAT['changed']+=1
    return _orig_rescore(logic,**kw)
bt.rescore_logic=patched_rescore

def run_arm(name, rows, floor, thin=False):
    MODE.update({'rows':rows,'floor':floor,'thin':thin})
    out=[]
    for md in sorted(DIRS):
        d=pb.meeting_date_from_dir(md)
        if not d: continue
        pb.inject_as_of(ROWS,d)
        CUR['meeting']=md
        r,_=bt.rescore_meeting(md,include_legacy=False)
        out.extend(r)
    agg=bt.evaluate(out); n=agg['races'] or 1
    print("   [debug] touched=%d changed=%d"%(STAT['touched'],STAT['changed']),flush=True)
    STAT.update({'touched':0,'changed':0})
    print("%-22s races=%3d  "%(name,agg['races'])+"  ".join("%s=%5.2f"%(m,100*agg[m]/n) for m in bt.METRICS),flush=True)
    return {m:round(100*agg[m]/n,2) for m in bt.METRICS}|{'races':agg['races']}

ROWS=pb.load_all_rows()
res={}
ARMS=[("FL0 baseline",       False, False, False),
      ("FL1 row fix",        True,  False, False),
      ("FL2a class floor",   False, True,  False),
      ("FL2b thin-evidence", False, False, True),
      ("FL3 rows+floor",     True,  True,  False),
      ("FL4 rows+thin",      True,  False, True),
      ("FL5 all three",      True,  True,  True)]
for name,rows,floor,thin in ARMS:
    res[name]=run_arm(name,rows,floor,thin)
MODE.update({'rows':False,'floor':False,'thin':False})
json.dump(res,open('/tmp/ab_formline.json','w'),indent=1)

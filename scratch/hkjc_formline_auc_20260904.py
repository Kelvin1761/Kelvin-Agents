#!/usr/bin/env python3
"""FL1 wiring check + paired-bootstrap AUC for FL3 (rows + class floor)."""
import os,re,sys,json,random,statistics as st
from pathlib import Path
os.environ.setdefault("PYTHONDONTWRITEBYTECODE","1")
R=Path('/Users/imac/Antigravity-repo')
for p in ('.agents/skills/hkjc_racing/hkjc_reflector/scripts','.agents/scripts',
          '.agents/skills/shared_racing/scripts',
          '.agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts'):
    sys.path.insert(0,str(R/p))
import pit_backtest as pb, rescore_backtest as bt
DIRS=[Path(l.rstrip('\n')) for l in open('/tmp/hkjc_bt.lst') if l.strip()]
GRADED=('一級賽','二級賽','三級賽','分級賽','第一班')
_orig=bt.rescore_logic
MODE={'rows':False,'floor':False}
CUR={'meeting':None}
_TBL=re.compile(r'🔗 \*\*賽績線:\*\*.*?\n(\|[^\n]+\n\|[-| ]+\n)(.*?)(?=\n\n|\n💡|\Z)', re.S)
_HDR=re.compile(r'^### 馬號\s*(\S+)\s*—', re.M)

def facts_tables(meeting,race):
    for fp in meeting.glob('*Facts.md'):
        m=re.search(r'Race\s*(\d+)',fp.name,re.I)
        if not m or int(m.group(1))!=race: continue
        txt=fp.read_text(encoding='utf-8',errors='replace'); marks=list(_HDR.finditer(txt)); out={}
        for i,hm in enumerate(marks):
            blk=txt[hm.end():marks[i+1].start() if i+1<len(marks) else len(txt)]
            tm=_TBL.search(blk)
            if not tm: continue
            rows=[]; ctx=['','','','']
            for line in tm.group(2).strip().split('\n'):
                c=[x.strip() for x in line.split('|')]
                if len(c)<9: continue
                if c[1].isdigit(): ctx=c[1:5]
                elif not ctx[0]: continue
                if not c[5] or c[5]=='對手': continue
                rows.append({'race_num':ctx[0],'date':ctx[1],'race_id':ctx[2],'my_finish':ctx[3],
                             'opponents':c[5],'next_class':c[6],'next_performance':c[7],'strength':c[8]})
            if rows: out[hm.group(1).strip()]=rows
        return out
    return {}

def relabel(r):
    s=str(r.get('strength') or '').strip()
    if s in ('','-'): return s
    if '超強組' in s or ('強組' in s and '中' not in s): return s
    if any(g in str(r.get('next_class') or '') for g in GRADED):
        m=re.search(r'出\s*(\d+)\s*次',str(r.get('next_performance') or ''))
        return '✅ 強組' if (m and int(m.group(1))>=2) else '⚠️ 中組'
    return s

def label(rows):
    sc=0.0;tot=0
    for r in rows:
        s=relabel(r) if MODE['floor'] else str(r.get('strength') or '').strip()
        if s in ('','-'): continue
        tot+=1
        sc+= 2.0 if '超強組' in s else 1.0 if ('強組' in s and '中' not in s) else 0.5 if '中組' in s else 0.0
    if tot==0: return '無資料'
    q=sc/tot
    tag='✅✅ 極強' if q>=0.7 else '✅ 強' if q>=0.5 else '中強' if q>=0.3 else '中弱' if q>=0.15 else '❌ 弱'
    return f"{tag} (強組比例: {sc:.0f}/{tot})"

def patched(logic,**kw):
    if MODE['rows'] or MODE['floor']:
        rn=(logic.get('race_analysis') or {}).get('race_number')
        tables=facts_tables(CUR['meeting'],int(rn)) if rn else {}
        for num,h in (logic.get('horses') or {}).items():
            if not isinstance(h,dict): continue
            dd=h.setdefault('_data',{})
            rows=tables.get(str(num)) if MODE['rows'] else dd.get('formline_table')
            if not rows: continue
            lab=label(rows)
            for tgt in (h,dd):
                tgt['formline_table']=rows; tgt['formline_strength']=lab
    return _orig(logic,**kw)
bt.rescore_logic=patched

def collect(rows,floor):
    MODE.update({'rows':rows,'floor':floor}); out={}
    for md in sorted(DIRS):
        d=pb.meeting_date_from_dir(md)
        if not d: continue
        pb.inject_as_of(ROWS,d); CUR['meeting']=md
        r,_=bt.rescore_meeting(md,include_legacy=False)
        for i,x in enumerate(r): out[(md.name,i)]=x
    return out

def auc(race):
    ap=race['actual']; top3={h for h,p in ap.items() if p<=3}
    pos=[s['ability'] for s in race['scored'] if s['hn'] in top3]
    neg=[s['ability'] for s in race['scored'] if s['hn'] in ap and s['hn'] not in top3]
    if not pos or not neg: return None
    return sum((1.0 if a>b else 0.5 if a==b else 0.0) for a in pos for b in neg)/(len(pos)*len(neg))

ROWS=pb.load_all_rows()
arms={'FL0':(False,False),'FL1 rows':(True,False),'FL3 rows+floor':(True,True)}
data={k:collect(*v) for k,v in arms.items()}
MODE.update({'rows':False,'floor':False})
keys=sorted(set.intersection(*[set(d) for d in data.values()]))
A={k:{q:auc(d[q]) for q in keys} for k,d in data.items()}
keys=[q for q in keys if all(A[k][q] is not None for k in arms)]
print('paired races: %d'%len(keys))
for k in arms: print('  %-16s within-race AUC = %.4f'%(k,st.mean(A[k][q] for q in keys)))
# wiring: did any ability score actually move under FL1?
moved=sum(1 for q in keys if sorted(s['ability'] for s in data['FL0'][q]['scored'])
                          != sorted(s['ability'] for s in data['FL1 rows'][q]['scored']))
print('\nFL1 wiring: %d/%d races have at least one ability_score changed'%(moved,len(keys)))
random.seed(20260904)
for cand in ('FL1 rows','FL3 rows+floor'):
    d=[A[cand][q]-A['FL0'][q] for q in keys]
    boots=sorted(st.mean(random.choices(d,k=len(d))) for _ in range(4000))
    lo,hi=boots[100],boots[3900]
    print('\n%s − FL0: ΔAUC %+.4f  95%% CI [%+.4f, %+.4f]  (%d/%d races moved)'%(
        cand,st.mean(d),lo,hi,sum(1 for x in d if abs(x)>1e-9),len(d)))
    print('   verdict: %s'%('IMPROVES' if lo>0 else 'WORSE' if hi<0 else 'CI spans zero — not resolvable'))

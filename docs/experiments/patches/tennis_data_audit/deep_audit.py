#!/usr/bin/python3
"""Read-only tennis source audit; dates are UTC calendar dates unless stated."""
import bisect
import csv
import io
import statistics
import urllib.request
import unicodedata
import collections
import datetime as dt
import json
import re
import sqlite3
from pathlib import Path

DB = '/Users/imac/Antigravity-repo/tennis-wong-choi/tennis_wc.db'
LOG = Path('/Users/imac/Antigravity-repo/tennis-wong-choi/data/logs/tennis_daily_schedule.log')
OUT = Path(__file__).with_name('deep_audit_out.md')
today = dt.date.today()
c = sqlite3.connect('file:' + DB + '?mode=ro', uri=True)
c.execute('PRAGMA query_only=ON')
out = ['# 網球數據完整性審計', '', '日期：%s。生產 DB 唯讀；日期以本機日曆日計。' % today, '']

def table(headers, rows):
    out.append('| ' + ' | '.join(headers) + ' |')
    out.append('| ' + ' | '.join(['---'] * len(headers)) + ' |')
    for row in rows:
        out.append('| ' + ' | '.join(str(v).replace('|', '\\|').replace('\n', ' ') for v in row) + ' |')
    out.append('')

def norm(col):
    x = 'CAST("%s" AS TEXT)' % col
    return "CASE WHEN length({0})>=8 AND substr({0},5,1) BETWEEN '0' AND '9' THEN substr({0},1,4)||'-'||substr({0},5,2)||'-'||substr({0},7,2) ELSE substr({0},1,10) END".format(x)

out += ['## 1. 來源新鮮度', '', '最新日期採用資料日期；7／30 日採用新增時間（有 created_at 時），否則使用資料日期。窗口包括今日。⚠ 表示 7 日零行但 30 日有行。', '']
rows=[]
tables=[x[0] for x in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
priority=['match_date','ranking_date','as_of_date','fetched_at','observed_at','captured_at','recorded_at','featured_at','created_at','updated_at','calculated_at','start_date','archived_at','decided_at','placed_at','first_seen_at','market_start_utc','settled_at','reported_created_at','start_time_utc']
for t in tables:
    cols=[r[1] for r in c.execute('PRAGMA table_info("'+t+'")')]
    datecol=next((x for x in priority if x in cols), None)
    if not datecol: continue
    added=next((x for x in ('created_at','observed_at','fetched_at','captured_at','recorded_at','featured_at',datecol) if x in cols),datecol)
    provider=next((x for x in ('source_provider','provider_name') if x in cols),None)
    group='COALESCE(CAST("%s" AS TEXT),\'(null)\')'%provider if provider else "'(無來源欄)'"
    nd,na=norm(datecol),norm(added)
    sql='SELECT '+group+', MAX('+nd+'), SUM(CASE WHEN '+na+'>=? AND '+na+'<=? THEN 1 ELSE 0 END), SUM(CASE WHEN '+na+'>=? AND '+na+'<=? THEN 1 ELSE 0 END) FROM "'+t+'" GROUP BY 1'
    for p,last,n7,n30 in c.execute(sql,((today-dt.timedelta(days=6)).isoformat(),today.isoformat(),(today-dt.timedelta(days=29)).isoformat(),today.isoformat())):
        try: lag=(today-dt.date.fromisoformat(last)).days
        except (TypeError,ValueError): lag='未知'
        rows.append((t,p,datecol+'/'+added,last or '無',lag,n7 or 0,n30 or 0,'⚠' if not n7 and n30 else ''))
table(['表','來源','資料日期／新增欄','最新','落後日','7日','30日','標記'],rows)

out += ['## 2. 定價母體覆蓋率', '', '每個球員取 created_at 最早快照（同時刻以 id 最小）。百分比分母為可解析快照；缺失快照及 JSON 無效另外列出。', '']
def bucket(name, level):
    n=(name or '').lower(); l=(level or '').upper()
    if 'challenger' in n or l=='CHALLENGER': return 'CHALLENGER'
    if 'itf' in n or l=='ITF' or n.startswith(('m15','m25','w15','w35','w50','w75','w100')): return 'ITF'
    if 'utr' in n: return 'UTR'
    if l.startswith(('ATP','WTA','GRAND')): return 'TOUR'
    return '未知'
def value(d,*path):
    for k in path:
        if not isinstance(d,dict): return None
        d=d.get(k)
    return d.get('value') if isinstance(d,dict) and 'value' in d else d
q='''SELECT m.id,m.match_date,m.player_a_id,m.player_b_id,m.round,t.name,tl.level,tl.surface FROM matches m LEFT JOIN tournaments t ON t.id=m.tournament_id LEFT JOIN tournament_levels tl ON tl.id=(SELECT id FROM tournament_levels x WHERE x.tournament_id=m.tournament_id AND x.tour=m.tour ORDER BY (source_provider='curated_tournament_metadata') DESC,(level!='UNKNOWN' AND level!='未確認') DESC,(surface IS NOT NULL) DESC,id DESC LIMIT 1) WHERE m.source_provider='sportsbet' AND m.match_date>=? AND m.match_date<=?'''
meta={r[0]:r for r in c.execute(q,('2026-09-01',today.isoformat()))}
stats=collections.defaultdict(collections.Counter)
fields=['rank','elo','surface_elo_distinct','hold','break','bp','history10','h2h','fatigue','surface','round']
for mid,d,a,b,rnd,name,level,surface in meta.values():
    try: day=dt.date.fromisoformat(d[:10]); week=(day-dt.timedelta(days=day.weekday())).isoformat()
    except (TypeError,ValueError): continue
    s=stats[(week,bucket(name,level))]
    for pid in (a,b):
        s['players']+=1
        row=c.execute('SELECT features_json FROM feature_snapshots WHERE match_id=? AND player_id=? ORDER BY created_at,id LIMIT 1',(mid,pid)).fetchone()
        if not row: s['missing']+=1; continue
        try:
            f=json.loads(row[0])
            if not isinstance(f,dict): raise ValueError('not object')
        except (TypeError,ValueError): s['invalid']+=1; continue
        s['n']+=1
        oe,se=value(f,'overall_elo'),value(f,'surface_elo')
        checks=[value(f,'current_rank') is not None,oe is not None, isinstance(oe,(int,float)) and isinstance(se,(int,float)) and abs(se-oe)>1e-9,value(f,'tournament_level_stats','hold_rate') is not None,value(f,'tournament_level_stats','break_rate') is not None,value(f,'pressure_stats','break_point_save_rate') is not None,(value(f,'bo_format_stats','matches') or 0)>=10,(value(f,'head_to_head','matches') or 0)>0,value(f,'fatigue','status')=='KNOWN',bool(surface and surface.upper() not in ('UNKNOWN','未確認')),bool(rnd and rnd.upper() not in ('UNKNOWN','未確認'))]
        for k,v in zip(fields,checks): s[k]+=bool(v)
rows=[]
for (week,level),s in sorted(stats.items()):
    cells=[]
    for k in fields:
        n=s['n']; pct=100*s[k]/n if n else 0
        prev=[]
        for i in range(1,5):
            w=(dt.date.fromisoformat(week)-dt.timedelta(days=7*i)).isoformat(); p=stats.get((w,level))
            if p and p['n']: prev.append(100*p[k]/p['n'])
        cells.append(('%0.1f%%'%pct if n else '無')+(' ⚠' if len(prev)==4 and sum(prev)/4-pct>15 else ''))
    rows.append([week,level,s['players'],s['n'],s['missing'],s['invalid']]+cells)
table(['週一','級別','球員場次','有效','缺快照','無效JSON']+fields,rows)

out += ['## 3. 球員往績新鮮度', '', '每個球員場次及來源取比賽日前最近一場，僅計 ACTIVE 往績；無紀錄另列，>30 日比例以有往績者為分母；非當時已知資料的回溯審計。', '']
providers=['tennisexplorer','tennismylife_history','jeff_sackmann','composite']
history=collections.defaultdict(list)
for pid,source,d in c.execute("SELECT player_id,source_provider,substr(match_date,1,10) FROM player_match_history WHERE history_status='ACTIVE' AND source_provider IN (?,?,?,?) ORDER BY player_id,source_provider,match_date",providers):
    try: history[(pid,source)].append(dt.date.fromisoformat(d).toordinal())
    except (ValueError,TypeError): pass
fresh=collections.defaultdict(list); missing=collections.Counter()
for mid,d,a,b,rnd,name,level,surface in meta.values():
    try: day=dt.date.fromisoformat(d[:10]); ordinal=day.toordinal(); week=(day-dt.timedelta(days=day.weekday())).isoformat()
    except (ValueError,TypeError): continue
    for pid in (a,b):
        for source in providers:
            key=(week,bucket(name,level),source); dates=history.get((pid,source),[]); i=bisect.bisect_left(dates,ordinal)
            if i: fresh[key].append(ordinal-dates[i-1])
            else: missing[key]+=1
table(['週一','級別','來源','有往績球員場次','無往績','中位日數','>30 日數','>30 日比例'],[(w,l,p,len(fresh[(w,l,p)]),missing[(w,l,p)],statistics.median(fresh[(w,l,p)]) if fresh[(w,l,p)] else '無',sum(x>30 for x in fresh[(w,l,p)]),('%.1f%%'%(100*sum(x>30 for x in fresh[(w,l,p)])/len(fresh[(w,l,p)]))) if fresh[(w,l,p)] else '無') for w,l,p in sorted(set(fresh)|set(missing))])
out += ['## 4. 身份衝突', '', '日誌以每行日期及類型計，同一行可屬多類；姓名只從同一類型後的錯誤片段中抽取，未列名不代表無受影響球員。', '']
counts=collections.Counter(); names=collections.defaultdict(set); patterns=['PlayerIdentityConflict','player_identity_conflict','event_identity_rejected','RankingIdentityHoldError']
if LOG.exists():
    with LOG.open(errors='replace') as f:
        for line in f:
            m=re.search(r'2026-\d\d-\d\d',line)
            if not m or m.group()<'2026-11-06': continue
            for p in patterns:
                for match in re.finditer(re.escape(p),line,re.I):
                    key=(m.group(),p); counts[key]+=1
                    segment=line[match.end():].split('"}',1)[0]
                    for pair in re.findall(r"'([^']+)'\s*->\s*'([^']+)'",segment): names[key].update(pair)
table(['日期','類型','出現次數','可抽出不同姓名數'],[(d,p,n,len(names[(d,p)])) for (d,p),n in sorted(counts.items())] or [('無匹配','—',0,0)])
holds=collections.defaultdict(lambda: [0,0,set(),0])
for provider,typ,status,body in c.execute("SELECT provider_name,entity_type,status_code,response_json FROM raw_api_responses WHERE status_code=206 OR lower(COALESCE(entity_type,'')) LIKE '%hold%'"):
    h=holds[(provider,typ,status)]; h[0]+=1
    try:
        obj=json.loads(body); held=obj.get('held',[]) if isinstance(obj,dict) else []
        if isinstance(held,list):
            h[1]+=len(held)
            for item in held:
                if isinstance(item,dict) and item.get('player_name'): h[2].add(item['player_name'])
    except (ValueError,TypeError): h[3]+=1
table(['來源','entity_type','HTTP','記錄','held 條目數','不同姓名','無效JSON'],[(p,t,s,v[0],v[1],len(v[2]),v[3]) for (p,t,s),v in sorted(holds.items(),key=lambda x:str(x[0]))])
out += ['held 條目可重複；206 包括快取及來源證據，並非全部身份擱置。', '']
ids=set(x[0] for x in c.execute('SELECT DISTINCT match_id FROM market_odds_snapshots WHERE match_id IS NOT NULL UNION SELECT DISTINCT match_id FROM odds_snapshots WHERE match_id IS NOT NULL'))
byday=collections.defaultdict(collections.Counter)
for mid,d,*_ in meta.values(): byday[d[:10]]['total']+=1; byday[d[:10]]['missing']+=mid not in ids
table(['日期','Sportsbet 場次','兩表均無 match_id','比例'],[(d,v['total'],v['missing'],'%.1f%%'%(100*v['missing']/v['total'])) for d,v in sorted(byday.items())])
out += ['以 match_id 關聯；未連結 match_id 的 event 價格未計入，因此是關聯缺失，不必然代表事件完全無價格。', '', '## 5. TML 擱置衝突', '', '同一 CSV 場次同時涉及多名衝突球員只計一次；token 重疊是機械分類，不能證實身份。', '']
entities={str(i):n for i,n in c.execute("SELECT provider_entity_id,entity_name FROM provider_entities WHERE provider_name='tennismylife_history' AND entity_type='player'")}
urls=['https://stats.tennismylife.org/data/2026_challenger.csv','https://stats.tennismylife.org/data/atp_quali/2026_atp_quali.csv']
conflicts=collections.defaultdict(set); affected=set(); errors=[]; csv_counts=[]
def tokens(s): return set(re.findall(r'[a-z0-9]+',unicodedata.normalize('NFKD',s).encode('ascii','ignore').decode().lower()))
for url in urls:
    try:
        req=urllib.request.Request(url,headers={'User-Agent':'TennisWongChoi/0.1'})
        with urllib.request.urlopen(req,timeout=30) as response: content=response.read().decode('utf-8-sig')
        records=list(csv.DictReader(io.StringIO(content))); status='即時下載'
    except Exception as e:
        errors.append((url,type(e).__name__,str(e)))
        archived=c.execute("SELECT fetched_at,response_json FROM raw_api_responses WHERE provider_name='tennismylife_history' AND endpoint=? AND status_code=200 ORDER BY fetched_at DESC,id DESC LIMIT 1",(url,)).fetchone()
        if not archived:
            csv_counts.append((url,'未知','下載失敗且無存檔')); continue
        records=json.loads(archived[1]); status='DB 存檔 '+archived[0]
    csv_counts.append((url,len(records),status))
    for idx,row in enumerate(records):
        for side in ('winner','loser'):
            pid=str(row.get(side+'_id','')).strip(); name=(row.get(side+'_name') or '').strip(); old=entities.get(pid)
            if pid and old and name and old.strip().casefold()!=name.casefold(): conflicts[(pid,old,name)].add((url,idx)); affected.add((url,idx))
table(['CSV','行數','狀態'],csv_counts)
if errors: out += ['下載錯誤：'+ '; '.join('%s：%s %s'%e for e in errors), '']
rows=[]; categories=collections.Counter()
for (pid,old,name),games in sorted(conflicts.items()):
    category='同一人改名（token 重疊）' if tokens(old)&tokens(name) else 'ID 重新分配（無 token 重疊）'; categories[category]+=1
    rows.append((pid,old,name,len(games),category))
table(['ID','DB 名','CSV 名','CSV 場數','分類'],rows or [('無可核實結果','—','—','未知','—')])
out += ['已核實衝突組合 %s；涉及不同場次 %s；分類數 %s。%s'%(len(rows),len(affected),dict(categories), '即時下載失敗；數字僅代表所列 DB 存檔。' if errors else ''), '']
out += ['## 6. 賽果同結算', '']
start=(today-dt.timedelta(days=29)).isoformat()
for label,sql in [('精選',"SELECT f.match_date,p.result_status,COUNT(*) FROM featured_picks f LEFT JOIN prop_tracker p ON p.id=f.prop_id WHERE f.match_date>=? AND f.match_date<=? GROUP BY 1,2"),('prop_tracker',"SELECT match_date,result_status,COUNT(*) FROM prop_tracker WHERE match_date>=? AND match_date<=? GROUP BY 1,2")]:
    totals=collections.defaultdict(collections.Counter)
    for d,status,n in c.execute(sql,(start,today.isoformat())):
        try: day=dt.date.fromisoformat(d[:10]); week=(day-dt.timedelta(days=day.weekday())).isoformat()
        except (TypeError,ValueError): continue
        s=totals[week]; s['total']+=n; status=(status or '無狀態').upper(); s[status]+=n
        if status=='PENDING' and (today-day).days>3: s['old']+=n
    table([label+' 週一','總數','PENDING >3日','VOID','VOID %','狀態分布'],[(w,s['total'],s['old'],s['VOID'],'%.1f%%'%(100*s['VOID']/s['total']),', '.join('%s:%s'%(k,v) for k,v in sorted(s.items()) if k not in ('total','old'))) for w,s in sorted(totals.items())])
out += ['精選以 prop_id 連接 prop_tracker，連不到列為無狀態。', '', '## 7. 總結', '', '以下按可量度的受影響定價場次，再按嚴重程度排序；快照球員缺欄只表示至少一人缺，並非因果證明。', '']
# Count affected matches directly from the same first snapshots as section 2.
affected_fields=collections.Counter()
for mid,d,a,b,rnd,name,level,surface in meta.values():
    missing_fields=set()
    for pid in (a,b):
        row=c.execute('SELECT features_json FROM feature_snapshots WHERE match_id=? AND player_id=? ORDER BY created_at,id LIMIT 1',(mid,pid)).fetchone()
        try: f=json.loads(row[0]) if row else None
        except (ValueError,TypeError): f=None
        if not isinstance(f,dict): missing_fields.add('快照缺失或無效'); continue
        if value(f,'current_rank') is None: missing_fields.add('排名缺失')
        if value(f,'tournament_level_stats','hold_rate') is None: missing_fields.add('hold 缺失')
        if value(f,'tournament_level_stats','break_rate') is None: missing_fields.add('break 缺失')
        if value(f,'fatigue','status')!='KNOWN': missing_fields.add('疲勞未知')
    if not surface or surface.upper() in ('UNKNOWN','未確認'): missing_fields.add('場地缺失')
    if not rnd or rnd.upper() in ('UNKNOWN','未確認'): missing_fields.add('輪次缺失')
    affected_fields.update(missing_fields)
issues=[(k,v,'待核實（僅觀察缺欄）') for k,v in affected_fields.items()]
issues.append(('兩張 odds 表均無 match_id',sum(v['missing'] for v in byday.values()),'待核實（可能未連結）'))
table(['問題','受影響 Sportsbet 場次','性質'],sorted(issues,key=lambda x:-x[1]))
out += ['WTA serve 未接線（EXP-20261026-04 REJECT）、Challenger 場地（EXP-20261113-50 REJECT）、wta_official_stats 於 11-06 重寫後停用：按題述記錄列為刻意；上述統計未拆解到各決策，不能直接推算各自影響場次。', '', '排名來源停更新檢查：以各來源曾出現球員為母體，其他來源較該球員在目標來源最後日期更新只代表 DB 有紀錄；不保證實際讀取通過 receipt 或時效檢查。', '']
ranking_summary=[]
for source in ('composite','wta_numeric_pdf'):
    date_expr=norm("ranking_date")
    sql="""WITH cohort AS (SELECT player_id,MAX({date}) last FROM rankings_history WHERE source_provider=? GROUP BY player_id), other AS (SELECT player_id,MAX({date}) last FROM rankings_history WHERE source_provider!=? GROUP BY player_id) SELECT count(*),sum(other.last>cohort.last),sum(other.last>=?),max(cohort.last) FROM cohort LEFT JOIN other USING(player_id)""".format(date=date_expr)
    n,newer,recent,last=c.execute(sql,(source,source,(today-dt.timedelta(days=30)).isoformat())).fetchone()
    levels=collections.Counter()
    cohort={r[0] for r in c.execute('SELECT DISTINCT player_id FROM rankings_history WHERE source_provider=?',(source,))}
    for mid,d,a,b,rnd,name,level,surface in meta.values():
        if a in cohort or b in cohort: levels[bucket(name,level)]+=1
    ranking_summary.append((source,last,n,newer or 0,recent or 0,', '.join('%s:%s'%x for x in sorted(levels.items()))))
table(['來源','最新 ranking_date','曾有排名球員','其他來源日期較新球員','其他來源近30日球員','定價場次級別（至少一人）'],ranking_summary)
out += ['其他來源按各來源最新排名日期比較（同一球員可計入多個來源）：', '']
alternatives=[]
for source in ('composite','wta_numeric_pdf'):
    sql="""WITH cohort AS (SELECT player_id,MAX({date}) last FROM rankings_history WHERE source_provider=? GROUP BY player_id), alt AS (SELECT player_id,source_provider,MAX({date}) last FROM rankings_history WHERE source_provider!=? GROUP BY player_id,source_provider) SELECT alt.source_provider,count(*),sum(alt.last>cohort.last),sum(alt.last>=?),max(alt.last) FROM cohort JOIN alt USING(player_id) GROUP BY alt.source_provider ORDER BY 3 DESC""".format(date=norm('ranking_date'))
    alternatives.extend((source,)+r for r in c.execute(sql,(source,source,(today-dt.timedelta(days=30)).isoformat())))
table(['原來源','其他來源','同一批球員','較原來源新','近30日','其他來源最新日期'],alternatives)
out += ['讀取路徑：src/tennis_wc/store/ranking_reads.py 的 RankingReader.rows/select 讀 rankings_history，包含 composite 和 wta_numeric_pdf；select 會檢查來源 receipt、日期及時效。資料庫有較新行不等於已獲選用。', '', '時間分類：排名兩來源的最新日期見上表；是否屬最近中斷須另核對抓取及退役決策。其他缺欄未憑單次覆蓋率判斷「一直沒有」或「最近斷咗」。', '']
OUT.write_text('\n'.join(out),encoding='utf-8')
print('寫入',OUT)

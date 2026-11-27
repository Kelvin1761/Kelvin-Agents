#!/usr/bin/python3
"""Read-only tennis history and rankings audit."""
import bisect, collections, datetime, html, json, random, re, sqlite3, unicodedata
from pathlib import Path
DB='/Users/imac/Antigravity-repo/tennis-wong-choi/tennis_wc.db'
LOG=Path('/Users/imac/Antigravity-repo/tennis-wong-choi/data/logs/tennis_daily_schedule.log')
OUT=Path(__file__).with_name('history_gap_out.md')
c=sqlite3.connect('file:'+DB+'?mode=ro',uri=True)
c.execute('PRAGMA query_only=ON')
def norm(s):
 s=unicodedata.normalize('NFKD',html.unescape(s or '')).encode('ascii','ignore').decode().lower()
 return re.findall(r'[a-z]+',s)
def level(name,l):
 n=(name or '').lower(); l=(l or '').upper()
 if 'challenger' in n or l=='CHALLENGER': return 'Challenger'
 if 'itf' in n or l=='ITF' or n.startswith(('m15','m25','w15','w35','w50','w75','w100')): return 'ITF'
 if 'utr' in n: return 'UTR'
 return '其他'
def table(h,rows):
 out.append('| '+' | '.join(h)+' |');out.append('| '+' | '.join(['---']*len(h))+' |')
 for r in rows: out.append('| '+' | '.join(str(x).replace('|','\\|').replace('\n',' ') for x in r)+' |')
 out.append('')
q="""SELECT m.id,m.match_date,m.player_a_id,m.player_b_id,t.name,tl.level FROM matches m LEFT JOIN tournaments t ON t.id=m.tournament_id LEFT JOIN tournament_levels tl ON tl.id=(SELECT id FROM tournament_levels x WHERE x.tournament_id=m.tournament_id AND x.tour=m.tour ORDER BY (source_provider='curated_tournament_metadata') DESC,(level!='UNKNOWN' AND level!='未確認') DESC,(surface IS NOT NULL) DESC,id DESC LIMIT 1) WHERE m.source_provider='sportsbet' AND m.match_date >= '2026-11-01' AND m.match_date < '2026-12-01'"""
# Only linked Sportsbet prices: union avoids repeated snapshots and duplicate matches.
priced=set(x[0] for x in c.execute("SELECT DISTINCT match_id FROM market_odds_snapshots WHERE match_id IS NOT NULL AND lower(source_provider)='sportsbet' UNION SELECT DISTINCT match_id FROM odds_snapshots WHERE match_id IS NOT NULL AND lower(source_provider)='sportsbet'"))
fixtures=[r for r in c.execute(q) if r[0] in priced]
names={i:(n,p) for i,n,p in c.execute('SELECT id,name,source_provider FROM players')}
history=collections.defaultdict(list)
for pid,d in c.execute("SELECT player_id,substr(match_date,1,10) FROM player_match_history WHERE source_provider='tennisexplorer' AND history_status='ACTIVE' ORDER BY player_id,match_date"):
 history[pid].append(d)
missing=collections.defaultdict(dict)
for mid,d,a,b,n,l in fixtures:
 if not '2026-11-09'<=d[:10]<='2026-11-26': continue
 lev=level(n,l)
 if lev=='其他': continue
 for pid in (a,b):
  if bisect.bisect_left(history.get(pid,[]),d[:10])==0: missing[lev].setdefault(pid,(mid,d[:10]))
rng=random.Random(20261127)
samples={lev:rng.sample(sorted(missing[lev]),min(80,len(missing[lev]))) for lev in ('ITF','UTR','Challenger')}
# Build inverted index over players, including those without history for B/C distinction.
index=collections.defaultdict(set)
for pid,(name,_) in names.items():
 for token in set(norm(name)):
  if len(token)>=2: index[token].add(pid)
def similar(pid):
 a=norm(names.get(pid,('',))[0]); candidates=set()
 for tok in a:
  if len(tok)>=2: candidates.update(index[tok])
 result=[]
 for other in candidates-{pid}:
  b=norm(names[other][0]); shared=set(a)&set(b)
  if not shared: continue
  ar=[x for x in a if x not in shared]; br=[x for x in b if x not in shared]
  if (len(a)>=2 and len(b)>=2 and (len(shared)>=2 or (ar and br and any(x[0]==y[0] and (len(x)==1 or len(y)==1 or x==y) for x in ar for y in br)))):
   result.append(other)
 return sorted(result)
# Normalise decoded raw bodies; track first matching record per candidate surname.
surnames={pid:(norm(names.get(pid,('',))[0])[-1] if norm(names.get(pid,('',))[0]) else '') for ids in samples.values() for pid in ids}
need={x for x in surnames.values() if len(x)>=2}; found={}; raw_count=0; bad=0
for rid,prov,when,body in c.execute("SELECT id,provider_name,fetched_at,response_json FROM raw_api_responses WHERE provider_name IN ('composite','tennisexplorer') AND entity_type='match_history' AND fetched_at >= '2026-09-28' AND fetched_at < '2026-11-27' AND status_code=200"):
 raw_count+=1
 try: obj=json.loads(body); text=obj.get('html','') if isinstance(obj,dict) and 'html' in obj else json.dumps(obj,ensure_ascii=False)
 except (ValueError,TypeError): bad+=1; continue
 words=set(norm(text))
 for word in need & words: found.setdefault(word,(rid,prov,when[:10]))
out=['# 網球往績缺口及 composite 排名審計','','生產資料庫唯讀；以 match_id 連上 Sportsbet 價格之 Sportsbet 場次為母體。賽日前 ACTIVE 往績，事後回溯；同一球員可出現於多級別。每級按排序後 ID、seed 20261127 抽最多 80 人。','', 'A 為機械相似候選，並非身份確認；B = 原文無姓但 DB 有相似名（無符合 A 往績），C = 原文及 DB 均無相似名；D = 原文有姓、姓名不能解析或證據不足。B/C 互斥，空白原文無法搜尋，B/C 僅代表可讀原文；原文無姓不證明賽事沒抓取；姓氏以最後一個 token 近似，倒轉／多字姓可能誤判。原文命中只代表同姓，並非同一人。', '', '原文範圍：2026-09-28 至 2026-11-26 成功抓取 composite／tennisexplorer match_history；%d 筆，無效 JSON %d 筆。'%(raw_count,bad),'']
counts={}; examples={}
for lev,ids in samples.items():
 counts[lev]=collections.Counter();examples[lev]=collections.defaultdict(list)
 for pid in ids:
  name=names.get(pid,('未知',''))[0]; sims=similar(pid); mid,day=missing[lev][pid]
  prior=[x for x in sims if bisect.bisect_left(history.get(x,[]),day)>0]
  surname=surnames[pid]
  if '/' in name:
   cat='D';evidence='雙打組合，姓名無法按單打球員可靠比對'
  elif prior:
   cat='A'; other=prior[0]; evidence='相似 ID %s %s；賽日前往績 %s'%(other,names[other][0],history[other][0])
  elif not surname or len(surname)<2 or raw_count==bad:
   cat='D';evidence='姓名或原文證據不足'
  elif surname in found:
   cat='D';evidence='原文同姓 %s：raw %s/%s/%s；身份未確認'%((surname,)+found[surname])
  elif sims:
   cat='B';other=sims[0];evidence='原文無姓 %s；相似 ID %s %s（無符合 A 往績）'%(surname,other,names[other][0])
  else:
   cat='C';evidence='原文無姓 %s；DB 無機械相似名'%surname
  counts[lev][cat]+=1; examples[lev][cat].append((pid,name,mid,day,evidence))
out+=['## 分類比例','']
table(['級別','母體不同球員','樣本','A','B','C','D'],[(l,len(missing[l]),len(samples[l]))+tuple('%d (%.1f%%)'%(counts[l][k],100*counts[l][k]/len(samples[l]) if samples[l] else 0) for k in 'ABCD') for l in samples])
for lev in samples:
 for cat in 'ABCD':
  out+=['### %s %s（最多五例）'%(lev,cat),'']
  table(['球員 ID','姓名','場次 ID','比賽日','證據'],examples[lev][cat][:5])
out+=['## 抓取範圍及排名程式','','- `tennis-wong-choi/src/tennis_wc/sources/providers/tennisexplorer_provider.py:29` 使用 results `type=all`，第 431–439 行逐日下載；程式無 ITF／UTR 篩選，參數不能證實網站實際包括全部 ITF 或 UTR。composite 歷史由 ESPN 提供（`providers/__init__.py:35-36`），不等同 TennisExplorer 頁面。','- `sources/ingest_rankings.py:65-68,174-210,230-237` 用當前 provider 抓取，按 row.raw.source 將官方及 Sackmann 排名寫成實際來源，只有其他來源才標 composite；因此 composite 標籤停止不等於抓取停止。`sources/providers/__init__.py:19,47-72` composite 優先官方、後備 Sackmann；`run.py:80-92` 每日仍呼叫。排名來源標籤由寫入路徑決定，須核對 raw receipt。','']
# Normalize mixed YYYYMMDD / YYYY-MM-DD dates before comparing.
def dateval(s):
 s=str(s or '')[:10];return s[:4]+'-'+s[4:6]+'-'+s[6:8] if len(s)>=8 and s[4:5].isdigit() else s
rank=collections.defaultdict(dict)
for pid,provider,d in c.execute("SELECT player_id,source_provider,MAX(CASE WHEN substr(ranking_date,5,1) BETWEEN '0' AND '9' THEN substr(ranking_date,1,4)||'-'||substr(ranking_date,5,2)||'-'||substr(ranking_date,7,2) ELSE substr(ranking_date,1,10) END) FROM rankings_history GROUP BY player_id,source_provider"):
 rank[pid][provider]=dateval(d)
cohort={pid for pid,rs in rank.items() if 'composite' in rs and not any(d>rs['composite'] for p,d in rs.items() if p!='composite')}
only={pid for pid in cohort if len(rank[pid])==1}
by=collections.defaultdict(lambda:[set(),0,0,set(),0])
for mid,d,a,b,n,l in fixtures:
 lev=level(n,l); hits=cohort & {a,b}
 if hits: by[lev][0].update(hits);by[lev][1]+=1;by[lev][2]+=len(hits)
 only_hits=only & {a,b}
 if only_hits: by[lev][3].update(only_hits);by[lev][4]+=1
out+=['## 排名影響','','composite 球員最後日期與各其他來源最後日期逐人比較；同日其他來源不算較新。只計 DB 有紀錄，不保證現時排名讀取符合時效或 receipt。','符合「沒有其他較新來源」：%d 人；其中完全只有 composite：%d 人。'%(len(cohort),len(only)),'']
table(['11月定價場次級別','受影響不同球員','至少一人受影響場次','受影響球員場次','只有 composite 球員','只有 composite 場次'],[(l,len(v[0]),v[1],v[2],len(v[3]),v[4]) for l,v in sorted(by.items())])
out+=['各級別球員可重複；場次按 match_id 去重，球員場次每場最多兩人。','','## 10-28 至 11-02 排名相關日誌','']
lines=[]
if LOG.exists():
 for line in LOG.open(errors='replace'):
  if re.search(r'\[2026-(?:10-(?:28|29|30|31)|11-0[12])T',line) and re.search(r'rankings_(?:atp|wta)',line,re.I) and re.search(r'error|fail|hold',line,re.I):
   lines.append(line.strip())
out+=['符合條件 %d 行；以下每天首個 WARNING，原文截取排名部分。'%len(lines),'']
seen=set()
for line in lines:
 day=line[1:11]
 if day in seen or 'WARNING:' not in line: continue
 seen.add(day);out.append('- '+line[:1500])
out+=['','排名資料日期與寫入日期不同；身份 hold 可部分寫入，單靠日誌不能推斷 composite 停止更新的根因。','']
OUT.write_text('\n'.join(out),encoding='utf-8')
print(OUT)

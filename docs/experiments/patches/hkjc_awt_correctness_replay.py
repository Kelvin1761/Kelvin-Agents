#!/usr/bin/env python3
"""Paired input-correctness replay; no target results and no weight fitting."""
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import sys

import pandas as pd

import hkjc_awt_source_trace as trace

ROOT=trace.ROOT
facts_old,_,EngineOld=trace.load_candidates()
# load_candidates returns metadata candidate; retain explicit frozen baseline engine.
EngineOld=trace.RacingEngine
facts_new=trace.load_source('awt_replay_live_facts',trace.FACTS,trace.FACTS.read_text())
engine_new=trace.load_source('hkjc_racing_engine._awt_replay_live_core',trace.ENGINE,trace.ENGINE.read_text()).RacingEngine
logic_path=ROOT/'.agents/skills/hkjc_racing/hkjc_wong_choi/scripts/create_hkjc_logic_skeleton.py'
logic=trace.load_source('awt_replay_logic',logic_path,logic_path.read_text())
OUT=ROOT/'docs/audits/hkjc-awt-source-fix-20261014';OUT.mkdir(exist_ok=True)


def core_name(value):
    return re.sub(r'\s*[（(][A-Z]\d{3}[）)]\s*$','',str(value)).strip().replace(' ','')


def brand(value):
    match=re.search(r'([A-Z]\d{3})$',str(value).strip())
    return match.group(1) if match else str(value).strip()


def profile_for(cache,horse,target):
    wanted=brand(horse.get('brand_no',''));name=core_name(horse['name'])
    possible=[]
    for key,entry in cache.items():
        data=entry.get('data',{})
        if wanted and brand(data.get('horse_id',key))==wanted and core_name(data.get('name',''))==name and not data.get('error'):
            possible.append(data)
    unique={json.dumps(p,sort_keys=True,ensure_ascii=False):p for p in possible}
    if len(unique)!=1:return None,'unresolved_or_ambiguous'
    data=deepcopy(next(iter(unique.values())))
    data['entries']=[e for e in data.get('entries',[]) if facts_old._profile_entry_datetime(e) and facts_old._profile_entry_datetime(e)<target]
    return data,'exact_id_and_name'


def transfer(original,block):
    result=deepcopy(original);data=result.setdefault('_data',{})
    summary=logic.parse_summary(block)
    if 'season_stats' in summary:
        result['season_stats']=summary['season_stats'];data['season_stats_line']=summary['season_stats']
    if 'surface_performance_shadow' in summary:
        result['surface_performance_shadow']=summary['surface_performance_shadow'];data['surface_performance_shadow']=summary['surface_performance_shadow']
    finish=logic.parse_finish_time_summary(block)
    for key,value in {'finish_time_block':finish.get('full_block','偏差趨勢未找到'),
                      'finish_time_adj':finish.get('adj_deviation',''),
                      'finish_time_adj_level':finish.get('adj_level','')}.items():data[key]=value
    return result


def run():
    f=pd.read_csv(ROOT/'scratch/hkjc_race_weight_oracle_20261013/dataset.csv',
                  usecols=['meeting','meeting_name','date','race_number','horse_number','horse_name','track','distance_num'])
    f=f[f.track=='AWT'];records=[];counts=Counter();hashes={}
    for (meeting,race),group in f.groupby(['meeting','race_number'],sort=True):
        meeting=Path(meeting);form=trace.only_path(meeting.glob(f'* Race {race} 賽績.md'),'formguide')
        lp=meeting/f'Race_{race}_Logic.json';cp=meeting/'.hkjc_cache/profile_cache.json'
        sources=[form,lp,cp]
        for path in sources:
            if path.exists():hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        original=json.loads(lp.read_text());cache=json.loads(cp.read_text()) if cp.exists() else {}
        old={h['num']:h for h in facts_old.parse_hkjc_formguide(str(form))['horses']}
        new={h['num']:h for h in facts_new.parse_hkjc_formguide(str(form))['horses']}
        context=dict(original.get('race_analysis') or {});numbers=[];old_scores=[];new_scores=[];horses=[]
        for _,row in group.iterrows():
            number=int(row.horse_number);target=pd.Timestamp(row.date).to_pydatetime()
            a=deepcopy(old[number]);b=deepcopy(new[number])
            if core_name(a['name'])!=core_name(row.horse_name):raise ValueError('identity mismatch')
            for h in (a,b):h['races']=[r for r in h['races'] if r.get('date_dt') and r['date_dt']<target]
            profile,status=profile_for(cache,a,target);counts[status]+=1
            distance=int(row.distance_num)
            # Identical profile/horse context, only original versus fixed facts code differs.
            block_a=facts_old.generate_horse_block(a,'沙田AWT',distance,'C4',profile_data=profile,race_date=str(row.date))
            block_b=facts_new.generate_horse_block(b,'沙田AWT',distance,'C4',profile_data=profile,race_date=str(row.date))
            stored=original['horses'][str(number)]
            input_a=transfer(stored,block_a);input_b=transfer(stored,block_b)
            score_a=EngineOld(input_a,context).analyze_horse();score_b=engine_new(input_b,context).analyze_horse()
            delta=float(score_b['ability_score'])-float(score_a['ability_score'])
            counts['runners']+=1;counts['ability_changed']+=abs(delta)>1e-8
            fields=[k for k in ('season_stats','surface_performance_shadow') if input_a.get(k)!=input_b.get(k)]
            fields+=['_data.'+k for k in ('finish_time_block','finish_time_adj','finish_time_adj_level') if input_a['_data'].get(k)!=input_b['_data'].get(k)]
            counts['inputs_changed']+=bool(fields)
            numbers.append(number);old_scores.append(float(score_a['ability_score']));new_scores.append(float(score_b['ability_score']))
            horses.append({'number':number,'name':str(row.horse_name),'profile_identity':status,'fields_changed':fields,
                'ability_before':score_a['ability_score'],'ability_after':score_b['ability_score'],'delta':delta,
                'input_before':{k:input_a.get(k) for k in ('season_stats','surface_performance_shadow')},
                'input_after':{k:input_b.get(k) for k in ('season_stats','surface_performance_shadow')},
                'finish_before':{k:input_a['_data'].get(k) for k in ('finish_time_block','finish_time_adj')},
                'finish_after':{k:input_b['_data'].get(k) for k in ('finish_time_block','finish_time_adj')},
                'matrix_before':score_a['matrix_scores'],'matrix_after':score_b['matrix_scores']})
        order_a=sorted(numbers,key=lambda n:(-old_scores[numbers.index(n)],n));order_b=sorted(numbers,key=lambda n:(-new_scores[numbers.index(n)],n))
        counts['races']+=1;counts['order_changed']+=order_a!=order_b;counts['top4_changed']+=order_a[:4]!=order_b[:4]
        records.append({'meeting':meeting.name,'race':int(race),'order_before':order_a,'order_after':order_b,'horses':horses})
        print('Replayed',meeting.name,race,flush=True)
    for path,digest in hashes.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=digest:raise ValueError('source changed')
    (OUT/'paired_replay.json').write_text(json.dumps({'design':{'target_outcomes_read':False,'weights_changed':False,
        'not_performance_evidence':True,'baseline':'pre-fix exact dirty checkout snapshots',
        'transfer_scope':'surface evidence, same-course stats and finish-time facts only; all other stored inputs frozen',
        'limitations':'standalone engine, no meeting SIP; profile cache PIT unproven; unresolved profiles explicitly use no-profile in both arms',
        'class_argument':'C4 identical in both arms; profile class-specific times otherwise preserved'},'counts':dict(counts),'source_sha256':hashes,'records':records},ensure_ascii=False,indent=2))
    print(dict(counts))

if __name__=='__main__':run()

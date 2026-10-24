"""Expired quotes may leave an analysis card, never an executable pick."""
from datetime import datetime,timedelta,timezone
import hashlib
import json
from pathlib import Path
import sys
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from services.nba_published_analysis import verified_published_reports

NOW=datetime.now(timezone.utc)-timedelta(hours=1)


def snapshot(tmp_path,role='production'):
    folder=tmp_path/'2026-10-25 NBA Analysis';dest=folder/'_prediction_snapshots'/'one';dest.mkdir(parents=True)
    files={
        'Game_BKN_CLE_Full_Analysis.md':'report',
        'Sportsbet_Odds_BKN_CLE.json':json.dumps({'event_start_time':(NOW+timedelta(days=1)).isoformat()}),
        'Game_BKN_CLE_Full_Analysis.md.market_legs.json':'{}',
        'nba_game_data_BKN_CLE.json':'{}',
    }
    for name,text in files.items():(dest/name).write_text(text)
    meta={'sport':'nba','target_date':'2026-10-25','append_only':True,'snapshot_role':role,
          'created_at':NOW.isoformat(),'game_tags':['BKN_CLE'],
          'files':[{'name':name,'bytes':len(text.encode()),'sha256':hashlib.sha256(text.encode()).hexdigest()} for name,text in files.items()]}
    (dest/'manifest.json').write_text(json.dumps(meta));return folder,dest,meta


def test_verified_snapshot_rechecks_entire_firewall_at_publication_time(tmp_path):
    folder,dest,_=snapshot(tmp_path);calls=[]
    def firewall(report,odds,**kwargs):calls.append((report,odds,kwargs));return True,[]
    rows=verified_published_reports(folder,'2026-10-25',firewall)
    assert len(rows)==1 and rows[0][0]=='BKN_CLE'
    assert calls==[(dest/'Game_BKN_CLE_Full_Analysis.md',dest/'Sportsbet_Odds_BKN_CLE.json',{'validation_time':NOW})]


@pytest.mark.parametrize('name',['Game_BKN_CLE_Full_Analysis.md','Sportsbet_Odds_BKN_CLE.json',
                                'Game_BKN_CLE_Full_Analysis.md.market_legs.json','nba_game_data_BKN_CLE.json'])
def test_any_artifact_tamper_invalidates_analysis_proof(tmp_path,name):
    folder,dest,_=snapshot(tmp_path);(dest/name).write_text('tampered')
    assert verified_published_reports(folder,'2026-10-25',lambda *args,**kwargs:(True,[]))==[]


@pytest.mark.parametrize('change',[{'snapshot_role':'warmup'},{'target_date':'2026-10-24'},
                                  {'created_at':(NOW+timedelta(days=2)).isoformat()},
                                  {'created_at':(NOW+timedelta(hours=25)).isoformat()},
                                  {'append_only':False}])
def test_unpublished_wrong_date_or_late_snapshots_are_not_analysis_cards(tmp_path,change):
    folder,dest,meta=snapshot(tmp_path);meta.update(change);(dest/'manifest.json').write_text(json.dumps(meta))
    assert verified_published_reports(folder,'2026-10-25',lambda *args,**kwargs:(True,[]))==[]


@pytest.mark.parametrize('passed',[False,None])
def test_snapshot_receipt_never_overrides_a_failed_firewall(tmp_path,passed):
    folder,_,_=snapshot(tmp_path)
    assert verified_published_reports(folder,'2026-10-25',lambda *args,**kwargs:(passed,['blocked']))==[]


def test_snapshot_after_tip_is_rejected_even_when_in_the_past(tmp_path):
    folder,dest,meta=snapshot(tmp_path)
    odds=dest/'Sportsbet_Odds_BKN_CLE.json'
    odds.write_text(json.dumps({'event_start_time':(NOW-timedelta(minutes=1)).isoformat()}))
    for row in meta['files']:
        if row['name']==odds.name:
            row.update(bytes=odds.stat().st_size,sha256=hashlib.sha256(odds.read_bytes()).hexdigest())
    (dest/'manifest.json').write_text(json.dumps(meta))
    assert verified_published_reports(folder,'2026-10-25',lambda *a,**kw:(True,[]))==[]


def test_blocked_game_cannot_supply_saved_analysis(tmp_path):
    folder,dest,meta=snapshot(tmp_path)
    meta['blocked_game_tags']=['BKN_CLE'];(dest/'manifest.json').write_text(json.dumps(meta))
    assert verified_published_reports(folder,'2026-10-25',lambda *a,**kw:(True,[]))==[]


def test_merge_preserves_only_readonly_analysis_when_local_source_is_missing():
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from generate_static import _merge_sports_feed
    card={'id':'nba:one','analysis_only':True,'decision':'OBSERVE','validation_status':'analysis_only'}
    old={'analysis_run_id':'nba:2026-10-25','validation_status':'blocked','analysis_cards':[card],
         'recommendations':[{'id':'never-restore','decision':'BET'}]}
    fresh={'sports':{'nba':{'analysis_run_id':'nba:unavailable','validation_status':'unavailable','recommendations':[]}}}
    merged=_merge_sports_feed({'sports':{'nba':old}},fresh,today='2026-10-24')
    assert merged['sports']['nba']['analysis_cards']==[card]
    assert merged['sports']['nba']['recommendations']==[]
    assert merged['sports']['nba']['analysis_run_id']=='nba:2026-10-25'
    expired=_merge_sports_feed({'sports':{'nba':old}},fresh,today='2026-10-26')
    assert not expired['sports']['nba'].get('analysis_cards')


def test_feed_contract_rejects_executable_analysis_cards():
    from services.multisport_exporter import validate_multisport_feed,SCHEMA_VERSION
    feed={'schema_version':SCHEMA_VERSION,'sports':{'nba':{'analysis_cards':[{'decision':'BET','analysis_only':True}]}}}
    assert 'unsafe_analysis_card:nba' in validate_multisport_feed(feed)


def test_export_recovers_proven_analysis_with_original_joint_probability(tmp_path, monkeypatch):
    from services import multisport_exporter as exporter
    folder, dest, meta = snapshot(tmp_path)
    report = dest/'Game_BKN_CLE_Full_Analysis.md'
    content = '''# NBA
**odds_source**: SPORTSBET_LIVE
Python Auto-Selection
### 🛡️ 組合 1: Banker SGM — 組合賠率 @3.5
| 🧩 1 | First Player 20+ PTS | @1.8 | 90% | 80% | +10% | +20% |
| 🧩 2 | Second Player 5+ AST | @2.0 | 80% | 70% | +10% | +20% |
未填寫項目 殘留: 0
'''
    report.write_text(content)
    odds = dest/'Sportsbet_Odds_BKN_CLE.json'
    odds.write_text(json.dumps({'target_analysis_date':'2026-10-25','game_tag':'BKN_CLE',
                               'player_props':{'PTS':{'First Player':{'line':'20+','odds':1.8}}},
                               'event_start_time':(NOW+timedelta(days=1)).isoformat()}))
    sidecar = dest/'Game_BKN_CLE_Full_Analysis.md.market_legs.json'
    sidecar.write_text(json.dumps({'report_sha256':hashlib.sha256(content.encode()).hexdigest(),
      'combos':[{'combo_id':'1','adjusted_joint_prob':0.4,'sgm_quote':{'status':'ok','decimal_odds':3.5}}]}))
    for row in meta['files']:
        path=dest/row['name']
        row.update(bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    (dest/'manifest.json').write_text(json.dumps(meta))
    def firewall(report, odds, **kwargs):
        return (kwargs.get('validation_time')==NOW, [])
    monkeypatch.setattr(exporter,'nba_publication_firewall',firewall)
    feed=exporter.export_nba_snapshot(tmp_path,target_date='2026-10-25',firewall=firewall)
    assert feed['recommendations']==[]
    assert len(feed['analysis_cards'])==1
    card=feed['analysis_cards'][0]
    assert card['analysis_only'] is True and card['decision']=='OBSERVE'
    assert card['metrics']['model_probability']==0.4
    assert card['metrics']['expected_value']==pytest.approx(0.4)
    assert card['odds_status']=='published_snapshot_price'


def test_warmup_is_available_only_to_explicit_readonly_analysis_caller(tmp_path):
    folder,_,_=snapshot(tmp_path,role='warmup')
    firewall=lambda *a,**kw:(True,[])
    assert verified_published_reports(folder,'2026-10-25',firewall)==[]
    assert len(verified_published_reports(folder,'2026-10-25',firewall,include_warmup=True))==1

"""Track formal and research publications without repricing or inventing results."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'backend'))
from services.nba_tracking import build_tracking

DAY='2026-10-25'
TAG='BOS_NYK'


def publication(root, name='first', price=2.5, probability=.6, role='production', created='2026-10-24T09:00:00+00:00',day=DAY):
    folder=root/f'{day} NBA Analysis'/'_prediction_snapshots'/name
    folder.mkdir(parents=True)
    text=f'''SPORTSBET_LIVE Python Auto-Selection
### 組合 1: 穩膽 SGM — 組合賠率 @{price}
| 🧩 1 | First Player 20+ PTS | @1.5 | 80% | 80% | +10% | +20% |
| 🧩 2 | Second Player 6+ REB | @1.5 | 80% | 80% | +10% | +20% |
未填寫項目 殘留: 0
'''
    files={f'Game_{TAG}_Full_Analysis.md':text,
           f'Sportsbet_Odds_{TAG}.json':json.dumps({'event_start_time':'2026-10-24T23:00:00+00:00'}),
           f'nba_game_data_{TAG}.json':'{}',
           f'Game_{TAG}_Full_Analysis.md.market_legs.json':json.dumps({'report_sha256':hashlib.sha256(text.encode()).hexdigest(),'combos':[{'combo_id':'1','adjusted_joint_prob':probability,'sgm_quote':{'status':'ok','decimal_odds':price},'legs':[]}]})}
    for filename,content in files.items():(folder/filename).write_text(content)
    (folder/'manifest.json').write_text(json.dumps({'sport':'nba','target_date':day,'append_only':True,'snapshot_role':role,'created_at':created,'game_tags':[TAG],'files':[{'name':k,'bytes':len(v.encode()),'sha256':hashlib.sha256(v.encode()).hexdigest()} for k,v in files.items()]}))
    return folder


def results(root, outcomes=('hit','hit')):
    directory=root/'ledger';directory.mkdir(exist_ok=True)
    rows=[{'row_type':'settlement','target_date':DAY,'game_tag':TAG,'player':player,'market':market,'line':line,'outcome':outcome,'actual':line-1 if outcome=='miss' else actual,'results_sha256':'a'*64,'settled_at':'2026-10-25T03:00:00+00:00'} for player,market,line,outcome,actual in zip(['First Player','Second Player'],['pts','reb'],[20,6],outcomes,[25,8])]
    (directory/f'{DAY}.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))


def build(root):return build_tracking([root],root,lambda *a,**kw:(True,[]))


def test_first_verified_bet_is_frozen_and_refresh_not_double_counted(tmp_path):
    publication(tmp_path,'z-first');publication(tmp_path,'a-later',price=3,created='2026-10-24T10:00:00+00:00')
    results(tmp_path)
    row=build(tmp_path)['records'][0]
    assert row['odds']==2.5 and row['profit']==1.5 and row['stake']==1
    assert row['snapshot_id']=='z-first' and len(build(tmp_path)['records'])==1


def test_partial_results_are_not_a_settled_win(tmp_path):
    publication(tmp_path);results(tmp_path,outcomes=('hit',))
    row=build(tmp_path)['records'][0]
    assert row['state']=='pending' and row['profit'] is None
    assert [l['state'] for l in row['legs']]==['won','pending']


def test_void_requires_repricing_never_assumed_refund(tmp_path):
    publication(tmp_path);results(tmp_path,('hit','void'))
    row=build(tmp_path)['records'][0]
    assert row['state']=='unpriced' and row['profit'] is None


def test_warmup_late_and_corrupt_publications_are_not_bets(tmp_path):
    publication(tmp_path,'warm',role='warmup')
    publication(tmp_path,'late',created='2026-10-25T00:00:00+00:00')
    folder=publication(tmp_path,'corrupt');(folder/f'nba_game_data_{TAG}.json').write_text('tampered')
    assert build(tmp_path)['records']==[]


def test_negative_ev_and_no_prediction_never_promoted(tmp_path):
    publication(tmp_path,probability=.2)
    assert build(tmp_path)['records']==[]
    publication(tmp_path,'eligible')
    (tmp_path/'ledger').mkdir()
    (tmp_path/'ledger'/f'{DAY}.jsonl').write_text(json.dumps({'row_type':'no_prediction','target_date':DAY,'game_tag':TAG})+'\n')
    assert build(tmp_path)['records']==[]


def test_firewall_failure_does_not_create_paper_bet(tmp_path):
    publication(tmp_path)
    assert build_tracking([tmp_path],tmp_path,lambda *a,**kw:(False,['blocked']))['records']==[]


def test_unavailable_source_cannot_claim_zero_bets(tmp_path):
    assert build(tmp_path)['status']=='unavailable'


def test_projection_merge_keeps_cold_history_but_obeys_locally_covered_dates():
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from generate_static import _merge_sports_feed
    old={'status':'valid','records':[{'id':'cold','day':'2026-10-25'}, {'id':'covered','day':'2026-10-26'}]}
    cached={'sports':{'nba':{'validation_status':'blocked','tracking':old}}}
    fresh={'sports':{'nba':{'validation_status':'blocked','tracking':{'status':'valid','covered_dates':['2026-10-26'],'records':[]}}}}
    result=_merge_sports_feed(cached,fresh)['sports']['nba']['tracking']
    assert result['records']==[{'id':'cold','day':'2026-10-25'}]
    assert result['retained_dates']==['2026-10-25']



def test_unverifiable_settlement_does_not_manufacture_profit(tmp_path):
    publication(tmp_path);results(tmp_path)
    path=tmp_path/'ledger'/f'{DAY}.jsonl'
    rows=[json.loads(line) for line in path.read_text().splitlines()]
    rows[0]['results_sha256']='missing-proof'
    rows[1]['settled_at']='2099-01-01T00:00:00Z'
    path.write_text(''.join(json.dumps(row)+'\n' for row in rows))
    row=build(tmp_path)['records'][0]
    assert row['state']=='pending' and row['profit'] is None



def test_verified_known_miss_is_loss_even_if_another_player_is_unresolved(tmp_path):
    publication(tmp_path);results(tmp_path,outcomes=('miss',))
    row=build(tmp_path)['records'][0]
    assert row['state']=='lost' and row['profit']==-1
    assert [l['state'] for l in row['legs']]==['lost','pending']


def research_publication(root, name='research', price=2.4, version='banker-ev-shadow-v1',created='2026-10-24T09:00:00+00:00'):
    folder=publication(root,name,probability=.2,created=created)
    side=folder/f'Game_{TAG}_Full_Analysis.md.market_legs.json'
    data=json.loads(side.read_text())
    data['review_candidates']=[{'candidate_id':'steady','version':version,'analysis_only':True,'decision':'OBSERVE','odds':price,'expected_value':-.2,
        'sgm_quote':{'captured_at':'2026-10-24T08:59:00+00:00'},
        'legs':[{'player':'First Player','category':'PTS','market':'pts','line':20,'side':'over'}, {'player':'Second Player','category':'REB','market':'reb','line':6,'side':'over'}]}]
    side.write_text(json.dumps(data))
    manifest=folder/'manifest.json';meta=json.loads(manifest.read_text())
    for row in meta['files']:
        if row['name']==side.name:row.update(bytes=side.stat().st_size,sha256=hashlib.sha256(side.read_bytes()).hexdigest())
    manifest.write_text(json.dumps(meta));return folder


def test_negative_ev_research_tracks_real_quote_and_first_choice_without_promotion(tmp_path,monkeypatch):
    import services.nba_latest_analysis as latest
    monkeypatch.setattr(latest,'_review_price',lambda candidate,odds:(2.4,'expired'))
    research_publication(tmp_path);publication(tmp_path,'later-formal',created='2026-10-24T10:00:00+00:00')
    results(tmp_path)
    rows=build(tmp_path)['records'];assert len(rows)==1
    row=rows[0];assert row['tracking_kind']=='research' and row['snapshot_id']=='research'
    assert row['odds']==2.4 and row['state']=='won' and row['profit']==1.4


def test_unverified_research_quote_keeps_accuracy_but_never_invents_roi(tmp_path):
    research_publication(tmp_path);results(tmp_path)
    row=build(tmp_path)['records'][0]
    assert row['tracking_kind']=='research' and row['state']=='unpriced'
    assert row['odds'] is None and row['profit'] is None
    assert all(leg['state']=='won' for leg in row['legs'])


def test_current_research_arm_takes_precedence_over_same_snapshot_legacy_formal(tmp_path,monkeypatch):
    import services.nba_latest_analysis as latest
    monkeypatch.setattr(latest,'_review_price',lambda candidate,odds:(2.4,'expired'))
    folder=research_publication(tmp_path)
    side=folder/f'Game_{TAG}_Full_Analysis.md.market_legs.json';data=json.loads(side.read_text())
    data['combos'][0]['adjusted_joint_prob']=.6;side.write_text(json.dumps(data))
    manifest=folder/'manifest.json';meta=json.loads(manifest.read_text())
    for row in meta['files']:
        if row['name']==side.name:row.update(bytes=side.stat().st_size,sha256=hashlib.sha256(side.read_bytes()).hexdigest())
    manifest.write_text(json.dumps(meta))
    records=build(tmp_path)['records'];assert len(records)==1 and records[0]['tracking_kind']=='research'


def test_tracking_inception_excludes_otherwise_valid_older_publications(tmp_path):
    publication(tmp_path,day='2026-10-24')
    data=build(tmp_path)
    assert data['inception_date']=='2026-10-25' and data['records']==[]
    publication(tmp_path,'launch-day')
    assert len(build(tmp_path)['records'])==1


def test_new_research_version_is_tracked_without_resetting_old_history(tmp_path,monkeypatch):
    import services.nba_latest_analysis as latest
    monkeypatch.setattr(latest,'_review_price',lambda candidate,odds:(2.4,'expired'))
    research_publication(tmp_path,version='banker-ev-shadow-v42')
    row=build(tmp_path)['records'][0]
    assert row['model_version']=='banker-ev-shadow-v42'
    assert row['day']=='2026-10-25'


def test_cached_pre_inception_rows_are_excluded_even_when_source_unavailable():
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from generate_static import _merge_sports_feed
    cached={'sports':{'nba':{'tracking':{'status':'valid','records':[{'id':'old','day':'2026-10-24'},{'id':'keep','day':'2026-10-25','model_version':'v1'}]}}}}
    result=_merge_sports_feed(cached,{'sports':{}})['sports']['nba']['tracking']
    assert [r['id'] for r in result['records']]==['keep']
    assert result['inception_date']=='2026-10-25'


def test_upgraded_model_does_not_replace_first_game_selection_or_original_price(tmp_path,monkeypatch):
    import services.nba_latest_analysis as latest
    monkeypatch.setattr(latest,'_review_price',lambda candidate,odds:(candidate['odds'],'expired'))
    research_publication(tmp_path,'z-first',price=2.4)
    research_publication(tmp_path,'a-upgraded',price=3.2,version='banker-ev-shadow-v2',created='2026-10-24T10:00:00+00:00')
    results(tmp_path)
    records=build(tmp_path)['records'];assert len(records)==1
    assert records[0]['odds']==2.4 and records[0]['snapshot_id']=='z-first'
    assert records[0]['model_version']=='banker-ev-shadow-v1'

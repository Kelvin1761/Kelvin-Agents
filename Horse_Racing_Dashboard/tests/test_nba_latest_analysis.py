from pathlib import Path
import sys,json,hashlib
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from services.nba_latest_analysis import build_latest_analysis


def write_game(root,tag='BKN_CLE',players=3,report=True):
    odds={'target_analysis_date':'2099-10-25','event_start_time':'2099-10-25T00:00:00Z',
          'player_props':{'PTS':{f'Player {i}':{} for i in range(players)}}}
    (root/f'Sportsbet_Odds_{tag}.json').write_text(json.dumps(odds))
    if report:
        content='Latest real game analysis';path=root/f'Game_{tag}_Full_Analysis.md';path.write_text(content)
        side={'report_sha256':hashlib.sha256(content.encode()).hexdigest(),'combos':[],
              'legs':[{'player':'Star','market':'pts','line':20,'price':2,'p_final':.45,'p_l10_base_rate':.7}],
              'review_candidates':[{'candidate_id':'steady','label':'較低倍率','analysis_only':True,'decision':'OBSERVE','legs':[{'selection':'First 10+','odds':1.5},{'selection':'Second 5+','odds':1.5}],
                                    'sgm_quote':{},'odds':99,'expected_value':50,'model_probability':.3}]}
        Path(str(path)+'.market_legs.json').write_text(json.dumps(side))


def test_zero_formal_bets_still_exports_latest_game_analysis(tmp_path):
    write_game(tmp_path)
    latest=build_latest_analysis(tmp_path,'2099-10-25',lambda *a:(True,[]))
    assert latest['coverage']['analysed_games']==1
    game=latest['games'][0]
    assert game['formal_sgm_count']==0 and game['market_count']==1
    assert game['report_markdown']=='Latest real game analysis'
    assert game['review_candidates'][0]['odds'] is None
    assert game['review_candidates'][0]['expected_value'] is None
    assert game['review_candidates'][0]['decision']=='OBSERVE'


def test_tampered_sidecar_report_binding_is_not_shown(tmp_path):
    write_game(tmp_path);(tmp_path/'Game_BKN_CLE_Full_Analysis.md').write_text('changed')
    game=build_latest_analysis(tmp_path,'2099-10-25',lambda *a:(True,[]))['games'][0]
    assert game['status']=='source_invalid' and not game['review_candidates']
    assert 'report_markdown' not in game


def test_failed_firewall_never_reveals_unverified_candidates(tmp_path):
    write_game(tmp_path)
    game=build_latest_analysis(tmp_path,'2099-10-25',lambda *a:(False,['blocked']))['games'][0]
    assert game['status']=='refresh_required' and not game['review_candidates']


def test_unopened_and_sparse_markets_have_separate_game_rows(tmp_path):
    write_game(tmp_path,'MIL_PHI',0,False);write_game(tmp_path,'MIA_CHA',2,False)
    latest=build_latest_analysis(tmp_path,'2099-10-25',lambda *a:(False,[]))
    assert latest['coverage']['pending_games']==2
    assert {r['status'] for r in latest['games']}=={'data_insufficient','waiting_player_markets'}


def test_wrong_date_is_never_presented_as_latest(tmp_path):
    write_game(tmp_path)
    assert build_latest_analysis(tmp_path,'2099-10-24',lambda *a:(True,[]))['games']==[]


def test_other_domain_deploy_preserves_analysis_without_restoring_bets():
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from generate_static import _merge_sports_feed
    latest={'event_date':'2099-10-25','games':[{'game_tag':'BKN_CLE','status':'analysed'}]}
    cached={'sports':{'nba':{'analysis_run_id':'nba:2099-10-25','validation_status':'blocked','latest_analysis':latest,'recommendations':[]}}}
    fresh={'sports':{'nba':{'analysis_run_id':'nba:unavailable','validation_status':'unavailable','recommendations':[]}}}
    result=_merge_sports_feed(cached,fresh,today='2099-10-24')['sports']['nba']
    assert result['latest_analysis']==latest and result['recommendations']==[]
    assert result['analysis_run_id']=='nba:2099-10-25'


def test_malformed_candidate_legs_are_dropped_without_losing_game(tmp_path):
    write_game(tmp_path)
    path=tmp_path/'Game_BKN_CLE_Full_Analysis.md.market_legs.json'
    side=json.loads(path.read_text());side['review_candidates'][0]['legs']='invalid';path.write_text(json.dumps(side))
    game=build_latest_analysis(tmp_path,'2099-10-25',lambda *a:(True,[]))['games'][0]
    assert game['status']=='analysed' and game['review_candidates']==[]

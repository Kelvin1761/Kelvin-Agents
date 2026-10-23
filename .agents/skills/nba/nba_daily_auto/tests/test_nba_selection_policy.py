"""Report thresholds come from the selector; relaxed Banker is explicitly tagged."""
import sys
from pathlib import Path

NBA=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(NBA));sys.path.insert(0,str(NBA/'nba_wong_choi/scripts'))
import generate_nba_reports as r
from nba_selection_policy import BANKER,BANKER_FALLBACK,VALUE,HIGH,description
from nba_sgm_quote import QuotedCombo


def candidate(name,hit,cov,odds):
    return {'market_type':r.PLAYER_MARKET,'player':name,'team':'BOS','category':'REB','line_val':3,
            'hit_l10':hit,'hit_l5':hit,'edge':20,'odds':odds,'cov':cov,'avg':8,'l3_avg':8,
            'desc':name,'season_phase':'MID_SEASON'}


def test_banker_strict_and_fallback_are_tagged_and_match_rendered_thresholds(monkeypatch):
    calls=[]
    def build(pool,**kwargs):
        calls.append((pool,kwargs));return pool[:2] if len(pool)>=2 else []
    monkeypatch.setattr(r,'_greedy_build',build)
    strict=r.select_combo_1([candidate('A',80,.65,1.2),candidate('B',80,.65,1.2)])
    assert strict.selection_rule=='banker'
    assert calls[0][1]['min_legs']==2 and calls[0][1]['max_legs']==4
    assert calls[0][1]['target_max']==3.5
    calls.clear()
    fallback=r.select_combo_1([candidate('A',70,.75,1.15),candidate('B',70,.75,1.15)])
    assert fallback.selection_rule=='banker_fallback' and len(calls)==2
    assert calls[0][0]==[] and calls[1][1]['target_max']==4.0
    quoted=QuotedCombo(fallback,{'status':'fixture'})
    text=description('1',quoted)
    assert quoted.selection_rule=='banker_fallback'
    assert 'fallback 放寬門檻' in text and '≥70%' in text and '≤0.75' in text and '2-4 Legs' in text
    assert '≥80%' not in text


def test_value_and_high_descriptions_use_actual_builder_targets(monkeypatch):
    calls=[]
    monkeypatch.setattr(r,'_greedy_build',lambda pool,**kwargs:calls.append(kwargs) or [])
    pool=[candidate('A',80,.3,1.5),candidate('B',80,.3,1.5)]
    r.select_combo_2(pool);r.select_combo_3(pool)
    assert calls[0]['target_min']==VALUE.target_min==3.0
    assert calls[1]['min_legs']==HIGH.min_legs==3 and calls[1]['max_legs']==HIGH.max_legs==5
    assert '3.0-5.0x' in description('2',[]) and '8.0-15.0x' in description('3',[])


def test_full_report_identifies_actual_c_source_and_avoids_false_safety_and_provider_claims(monkeypatch):
    monkeypatch.setenv('NBA_WC_PROB_LAYER','1')
    ext={'name':'Verified Star','advanced':{'USG_PCT':25},'gamelog':{'PTS':[20,22,18,24,26,20,23,19,21,25],'MIN':[32]*10}}
    card=r.build_player_card('Verified Star','BOS',{'lines':{'10':'1.8'}},ext,'points',engine_mode='legacy')
    for name in ('select_combo_1','select_combo_2','select_combo_3','select_combo_x_value_bomb'):
        monkeypatch.setattr(r,name,lambda _:[])
    text=r.gen_full_report({'away':{'abbr':'BOS'},'home':{'abbr':'LAL'}},{},{},{},{},[card],'fixture')
    version=card['line_analysis']['10']['probability_model_id'].split(':')[1]
    assert f'最終機率來源**: {version} 市場＋L10 校準層' in text
    assert '(Low Risk)' not in text and 'MCP Playwright' not in text and 'DOM Snapshot' not in text
    assert 'fallback ≥70%' in text and '3.0-5.0x' in text

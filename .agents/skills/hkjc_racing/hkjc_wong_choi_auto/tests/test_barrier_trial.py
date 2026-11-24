import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import pytest
from hkjc_racing_engine import barrier_trial as b

@pytest.mark.parametrize('text,value', [('SH',.1),('S/H',.1),('N',.05),('NOSE',.05),('HD',.2),('NECK',.3),('DH',0),('短馬頭位',.1),('馬頭位',.2),('頭位',.2),('鼻位',.05),('頸位',.3),('1-1/4',1.25),('4 1/4',4.25),('1/2',.5),('2l',2),('',0),('?',None)])
def test_margin(text,value):
    assert b.margin_lengths(text) == value


def test_asof():
    table = {'trials': {'A123': [['2026-01-01', 2], ['2026-01-03', 1]]}}
    assert b.last_trial('A123','2026-01-03',table) == ('2026-01-01',2)


def test_centered_and_non_debut():
    horses = {'1': {'is_debut': True, 'hkjc_horse_id': 'A123'}, '2': {}}
    result = b.adjustments(horses, '2026-01-03', {'trials': {'A123': [['2026-01-01', 2]]}})
    assert sum(x[0] for x in result.values()) == pytest.approx(0)
    assert result['2'][1] is None


def test_disabled_and_missing(monkeypatch):
    horses = {'1': {'is_debut': True, 'python_auto': {'ability_score_raw': 50}}}
    monkeypatch.setattr(b, 'ENABLED', False)
    assert b.apply(horses, {'race_date': '2026-01-01'}) == 0
    monkeypatch.setattr(b, 'ENABLED', True)
    monkeypatch.setattr(b, 'load_table', lambda: None)
    assert b.apply(horses, {'race_date': '2026-01-01'}) == 0
    assert horses['1']['python_auto'] == {'ability_score_raw': 50}


def test_parse():
    html = '<table><tr><td>第 1 組</td></tr><tr>' + ''.join(f'<td>{v}</td>' for v in ['馬 (A123)', 'a','b','c','d','1-1/4','x','1.02.34','ok']) + '</tr></table>'
    assert b.parse_trial_page(html) == [{'group':'第 1 組','rows':[{'code':'A123','margin':1.25,'time':62.34}]}]

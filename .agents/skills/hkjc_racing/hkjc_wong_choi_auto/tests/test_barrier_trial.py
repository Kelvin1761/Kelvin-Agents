import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from hkjc_racing_engine import barrier_trial as bt  # noqa: E402


@pytest.mark.parametrize("text,value", [("", 0.0), ("SH", 0.1), ("S/H", 0.1), ("N", 0.05), ("NOSE", 0.05), ("HD", 0.2),
                                        ("neck", 0.3), ("DH", 0.0), ("1-1/4L", 1.25), ("4 1/4L", 4.25), ("1/2l", 0.5),
                                        ("短馬頭位", 0.1), ("鼻位", 0.05), ("6", 6.0), ("ML", None)])
def test_margin(text, value):
    assert bt.margin_lengths(text) == value


def test_last_trial_is_strictly_before_race_date():
    table = {"trials": {"A123": [["2026-01-01", 1.0], ["2026-01-05", 2.0]]}}
    assert bt.last_trial("A123", "2026-01-05", table) == ("2026-01-01", 1.0)
    assert bt.last_trial("A123", "2026-01-06", table) == ("2026-01-05", 2.0)
    assert bt.last_trial("B999", "2026-01-06", table) is None


def test_parse_trial_page():
    html = ('<table><tr><td>第 1 組 - 沙田全天候跑道 - 1200米</td></tr>'
            '<tr><td>好馬 (A123)</td><td>j</td><td>t</td><td>07</td><td></td><td></td><td>3 3 1</td><td>1.08.84</td><td></td></tr>'
            '<tr><td>二馬 (B456)</td><td>j</td><td>t</td><td>06</td><td></td><td>SH</td><td>6 6 2</td><td>1.08.86</td><td></td></tr></table>')
    g = bt.parse_trial_page(html)
    assert len(g) == 1 and [r["code"] for r in g[0]["rows"]] == ["A123", "B456"]
    assert g[0]["rows"][0]["margin"] == 0.0 and g[0]["rows"][1]["margin"] == 0.1
    assert abs(g[0]["rows"][0]["time"] - 68.84) < 1e-9


def test_figure_day_fallback_cap_and_old_records():
    table = {'trials': {f'X{i:03}': [['2026-01-01', 0, '草地', 1000, '好', 60.0]] for i in range(30)}}
    table['trials']['A123'] = [['2026-01-01', 0, '草地', 1000, '好', 60], ['2026-01-02', 0, '草地', 1000, '黏', 65]]
    table['trials']['B123'] = [['2026-01-01', 3]]
    figures = bt.trial_figures(table)
    assert figures['A123'] == [('2026-01-01', None), ('2026-01-02', -3.0)]
    assert bt.trial_figures(table) is figures
    assert bt.last_trial_figure('A123', '2026-01-02', table) == ('2026-01-01', None, '草地', 1000)
    assert bt.last_trial_figure('B123', '2026-01-02', table) == ('2026-01-01', None, None, None)
    assert bt.last_trial_figure('A123', '2026-01-03', table)[1] == -3


def test_parse_metadata():
    html = '<table><tr><td>第 1 組 - 草地 - 1000米</td></tr><tr><td>場地狀況: 好地</td></tr><tr><td>分段時間: 23.4 24.5</td></tr></table>'
    g = bt.parse_trial_page(html)[0]
    assert (g['track'], g['dist'], g['going'], g['splits']) == ('草地', 1000, '好地', [23.4, 24.5])


def test_adjustments_center_and_disabled(monkeypatch):
    horses = {'a': {'debut_runner': True}, 'b': {}}
    monkeypatch.setattr(bt.debut_trainer, 'is_debut', lambda h: bool(h.get('debut_runner')))
    monkeypatch.setattr(bt, 'horse_code', lambda h: 'A123')
    monkeypatch.setattr(bt, 'last_trial_figure', lambda *args: ('2026-01-01', 1.0, '草地', 1000))
    result = bt.adjustments(horses, '2026-01-02', {})
    assert result['b'][1] is None
    assert sum(v[0] for v in result.values()) == pytest.approx(0)
    monkeypatch.setattr(bt, 'ENABLED', False)
    assert bt.apply(horses, {'race_date': '2026-01-02'}) == 0

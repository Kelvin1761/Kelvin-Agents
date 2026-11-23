import sys
from pathlib import Path
from unittest.mock import patch
import pandas as pd
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from hkjc_racing_engine import performance_figure as pf, tags


def test_segment():
    runs = [(1.3, 120, 1.2, '2026-01-01', '泥地', False), (1.0, 120, 1.2, '2025-12-01', '田草', False)]
    awt = runs[:1]
    assert pf.segment_gap(runs, awt, 120)['gap'] == pytest.approx(.1)      # 整體 (1.3+1.0/2)/1.5 = 1.2；泥地 1.3
    assert pf.segment_gap(runs[:1], awt, 120) is None                      # 整體少過 2 仗
    assert pf.segment_gap(runs, [], 120) is None                           # 冇分段往績
    meta = {'date': '2026-02-01', 'distance': 1200, 'race_context': {'venue': '沙田', 'track': '全天候'}}
    seg = {'awt': {'A': awt}, 'straight': {}}
    with patch.object(pf, 'figures_as_of', return_value={'A': runs}), patch.object(pf, 'segment_figures', return_value=seg):
        label = tags._segment_figure_tag({'horse_code': 'A', 'weight': 120}, meta)[0]
    assert '未入分' in label['label'] and not label['scored'] and label['tone'] == 'good'
    seg['awt']['A'] = [(1.2, 120, 1.2, '2026-01-01', '泥地', False)]
    with patch.object(pf, 'figures_as_of', return_value={'A': runs}), patch.object(pf, 'segment_figures', return_value=seg):
        assert not tags._segment_figure_tag({'horse_code': 'A', 'weight': 120}, meta)


def test_head_to_head():
    rows = []
    for day, times in [('2025-01-01', (70, 72)), ('2025-06-01', (70, 70.1)), ('2026-01-01', (70, 72)), ('2026-01-02', (70, 69))]:
        for code, t, w in [('A', times[0], 130), ('B', times[1], 120)]:
            rows.append({'race': day, 'date': day, 'code': code, 'time': t, 'w': w, 'km': 1.2})
    horses = {'1': {'horse_code': 'A', 'weight': 120, 'python_auto': {'ability_score': 70}}, '2': {'horse_code': 'B', 'horse_name': '對手', 'weight': 130, 'python_auto': {'ability_score': 80}}}
    meta = {'date': '2026-01-02', 'distance': 1000}
    with patch.object(pf, 'load_results', return_value=pd.DataFrame(rows)):
        result = tags._head_to_head_tags(horses['1'], horses, meta)
    assert len(result) == 1 and result[0]['label'].count('贏超過 1 秒') == 2
    assert '未入分' in result[0]['label'] and result[0]['scored'] is False
    rows = [r for r in rows if r['date'] == '2025-06-01']
    with patch.object(pf, 'load_results', return_value=pd.DataFrame(rows)):
        label = tags._head_to_head_tags(horses['1'], horses, meta)[0]['label']
    expected = .1 + pf.BETA_LB * 1.2 * 10 - pf.BETA_LB * -10
    assert f'贏 {expected:.2f} 秒' in label
    meta['date'] = '2026-06-02'
    with patch.object(pf, 'load_results', return_value=pd.DataFrame(rows)):
        assert not tags._head_to_head_tags(horses['1'], horses, meta)

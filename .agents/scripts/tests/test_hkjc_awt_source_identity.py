"""AWT identity must survive parsing, rendering and surface evidence reading."""
import importlib.util
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / '.agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts'))
from hkjc_racing_engine.engine_core import RacingEngine  # noqa: E402

spec = importlib.util.spec_from_file_location('awt_identity_live_facts', ROOT / '.agents/scripts/inject_hkjc_fact_anchors.py')
facts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(facts)


@pytest.mark.parametrize('target,expected', [('沙田AWT', .7), ('跑馬地草地', 2.), ('沙田草地', 4.)])
def test_reader_uses_target_surface_sample(target, expected):
    text = (f'今場={target} 63.4分 | 沙田草地 62分(有效樣本4.0/原始5) | '
            '跑馬地草地 61分(有效樣本2.0/原始3) | 沙田AWT 63.4分(有效樣本0.7/原始1)')
    result = RacingEngine({'surface_performance_shadow': text}, {})._surface_performance_shadow_component()
    assert result['effective_n'] == expected
    assert result['score'] == 63.4


def test_missing_target_row_never_borrows_other_surface_sample():
    text = '今場=沙田AWT 60分 | 沙田草地 61分(有效樣本4.0/原始5)'
    result = RacingEngine({'surface_performance_shadow': text}, {})._surface_performance_shadow_component()
    assert result['effective_n'] == 0


@pytest.mark.parametrize('rail,expected', [('AWT', '沙田AWT'), ('A', '沙田')])
def test_formguide_retains_surface_in_venue(tmp_path, rail, expected):
    path = tmp_path / '賽績.md'
    path.write_text(f'''馬號: 1
馬名: 測試馬
檔位: 1
騎師: 測試騎師
負磅: 120
排位體重: 1100
往績紀錄:
  [1] 06/05/2026 | 日數: 17 | 沙田 "{rail}" 1200 好
      檔位: 4 | 馬重: 1100 | 負磅: 120 | 騎師: 測試騎師 | 名次: 2 / 12
      能量: 91 | 分段時間: 23.00, 22.70, 23.89
      短評: 中等步速
''')
    race = facts.parse_hkjc_formguide(str(path))['horses'][0]['races'][0]
    assert race['venue'] == expected
    assert race['rail'] == rail
    result = facts.compute_surface_performance_shadow([race], '沙田AWT', 1200, '2026-06-07')
    assert result['target_runs'] == int(rail == 'AWT')
    same_day = facts.compute_surface_performance_shadow([race], '沙田AWT', 1200, '2026-05-06')
    assert same_day['target_runs'] == 0


def test_rendered_awt_and_time_standard_lookup_keep_full_surface(monkeypatch):
    race = {'venue': '沙田AWT', 'date': '06/05/2026', 'date_dt': facts.parse_date('06/05/2026'),
            'distance': 1200, 'finish': 2, 'field_size': 12, 'energy': 91,
            'sectionals': {}, 'splits': [], 'comment': ''}
    horse = {'num': 1, 'name': '測試馬', 'jockey': '測試騎師', 'weight': 120,
             'barrier': 1, 'races': [race], 'pdf_overseas_races': []}
    profile = {'entries': [{'date': '06/05/2026', 'finish_time_raw': '1.09.35', 'class_grade': '4', 'placing': 2}]}
    calls = []
    monkeypatch.setattr(facts, 'get_standard_time', lambda venue, *args: calls.append(venue) or 69.)
    text = facts.generate_horse_block(horse, '沙田AWT', 1200, 'C4', profile_data=profile, race_date='2026-06-07')
    assert '| 沙田AWT |' in text
    assert '| 沙田AW |' not in text
    assert calls and set(calls) == {'沙田AWT'}

"""starter PDF 冇嘅時候，fsc「來港前賽績記錄」要砌返同一批海外往績 rows。

Fixtures 係真 fsc PDF 嘅 pdfplumber 文字（只留 標題行＋往績詳情），同埋同一批馬喺
starter PDF 入面嘅海外往績節（`starter_overseas_excerpt.md`）。對照用嘅欄位就係
評分會讀嘅欄位：日期、名次／馬數、路程、表面、級別（G1/G2/G3 子字串）、負磅、
頭馬時間、勝負距離，另加地區／方向／場地碼。
"""
import importlib.util
import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = Path(__file__).resolve().parent / 'fixtures' / 'hkjc_fsc'

_spec = importlib.util.spec_from_file_location(
    'hkjc_overseas_formsheet_t', ROOT / '.agents/scripts/hkjc_overseas_formsheet.py')
fsc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fsc)

_fspec = importlib.util.spec_from_file_location(
    'fsc_facts_t', ROOT / '.agents/scripts/inject_hkjc_fact_anchors.py')
facts = importlib.util.module_from_spec(_fspec)
_fspec.loader.exec_module(facts)

COMPARED = ('Date', 'Region', 'Direction', 'Distance', 'Going', 'Surface', 'Placing',
            'Field_Size', 'Weight', 'Finish_Time_Raw', 'Margin')


def _fixture(brand):
    return (FIXTURES / f'fsc_{brand}.txt').read_text(encoding='utf-8')


def _engine_grade(race_type):
    """同 speed.py／jockey.py／trainer.py 一樣嘅子字串判斷。"""
    upper = str(race_type or '').upper()
    return next((g for g in ('G1', 'G2', 'G3') if g in upper or f'{g[1]}級' in upper), '')


@pytest.mark.parametrize('brand,race_date', [
    ('L193', '2026-10-14'),   # 11 仗 → 只留最近 10；一級／二級／三級
    ('K379', '2026-10-14'),   # 膠沙地 (Polytrack)
    ('L267', '2026-10-14'),   # 表列；配備斷行；大爛地
    ('J215', '2026-05-24'),   # 「1.3.02R」頭馬時間手民之誤
])
def test_fallback_rows_match_the_starter_pdf_field_for_field(brand, race_date):
    starter = facts.parse_pdf_overseas_races(FIXTURES / 'starter_overseas_excerpt.md', brand, '')
    fallback = fsc.rows_from_text(_fixture(brand), race_date)
    assert starter, 'fixture 冇 starter rows，對照冇意義'
    assert len(fallback) == len(starter)
    for got, want in zip(fallback, starter):
        assert {k: got[k] for k in COMPARED} == {k: want[k] for k in COMPARED}
        assert _engine_grade(got['Race_Type']) == _engine_grade(want['Race_Type'])
        assert got['Is_PDF_Overseas'] is True


def test_last_ten_starts_oldest_first_like_the_starter_pdf():
    rows = fsc.rows_from_text(_fixture('L193'), '2026-10-14')
    assert len(rows) == 10
    assert rows[0]['Date'] == '6/4/2024'          # 16.3.2024 嗰仗係第 11 仗，要跌走
    assert rows[-1]['Date'] == '21/4/2025'
    # form.py 按 list 次序俾權重，所以次序一定要同 PDF 一樣（舊 → 新）。
    dates = [facts.parse_date(r['Date']) for r in rows]
    assert dates == sorted(dates)


def test_grade_words_become_engine_codes():
    rows = fsc.rows_from_text(_fixture('L193'), '2026-10-14')
    grades = [_engine_grade(r['Race_Type']) for r in rows]
    assert grades.count('G1') == 1 and grades.count('G2') == 1 and grades.count('G3') == 3
    # 中文「一級」唔會中引擎嘅 "1級" 判斷 —— 唔轉就會靜靜冇咗海外加分。
    assert not any('一級' in r['Race_Type'] or '三級' in r['Race_Type'] for r in rows)
    listed = fsc.rows_from_text(_fixture('L267'), '2026-10-14')
    assert sum(r['Race_Type'].endswith(' L') for r in listed) == 4


def test_only_runs_strictly_before_the_race_date():
    rows = fsc.rows_from_text(_fixture('L193'), '2024-11-02')
    assert [r['Date'] for r in rows][-1] == '22/6/2024'   # 2.11.2024 當日嗰仗唔計
    assert len(rows) == 5


def test_bom_and_crlf_layout_parses_the_same():
    text = _fixture('L267')
    odd = '﻿' + text.replace('\n', '\r\n')
    assert fsc.rows_from_text(odd, '2026-10-14') == fsc.rows_from_text(text, '2026-10-14')


def test_horse_with_no_overseas_runs_gives_no_rows():
    text = ('未命名 (M001)\n往績詳情\n名次及 馬匹 勝負 頭馬時間\n'
            '日期 馬場 途程(米) 場地 賽事名稱/類別 級別 出馬 檔位 負磅 賠率 配備 距離 騎師\n')
    assert fsc.rows_from_text(text, '2026-11-04') == []
    assert fsc.rows_from_text('', '2026-11-04') == []


def test_unplaced_run_counts_towards_ten_but_is_dropped_like_the_pdf():
    """UR／DNF（「- / 5」）PDF 都會計入「最近 10 仗」，但 parser 唔收；fallback 一樣。"""
    blocks = fsc.split_run_blocks(_fixture('K037'))
    rows = fsc.rows_from_text(_fixture('K037'), '2026-10-14')
    assert len(rows) == len(blocks[-10:]) - 1
    assert '+LNk' in [r['Margin'] for r in rows]          # 長馬頸


@pytest.mark.parametrize('brand,margins', [
    ('K009', {'+Hd', '-SH'}),       # 馬頭／短馬頭
    ('L147', {'+DH'}),              # 平頭（名次欄有「(平頭)」）
    ('L109', {'+Nk'}),              # 馬頸；Tapeta 嘅「-標準」斷咗落續行
])
def test_margin_words_and_odd_layouts(brand, margins):
    rows = fsc.rows_from_text(_fixture(brand), '2026-11-04')
    assert margins <= {r['Margin'] for r in rows}
    assert all(r['Direction'] in {'RH', 'LH', 'St'} for r in rows)


def test_all_weather_surface_matches_starter_rule():
    row = fsc.rows_from_text(_fixture('K379'), '2026-10-14')[0]
    assert (row['Going'], row['Surface']) == ('Polytrack', 'SYNTHETIC')
    tapeta = [r for r in fsc.rows_from_text(_fixture('L109'), '2026-11-04') if r['Going'] == 'Tapeta']
    assert tapeta and all(r['Surface'] == 'SYNTHETIC' for r in tapeta)


@pytest.mark.parametrize('brand,race_date,listed', [
    ('J215', '2026-05-24', True),    # 25/26 季：J/K/L
    ('J215', '2026-09-06', False),   # 換季：J 由 PDF 消失
    ('K229', '2026-10-14', True),
    ('M001', '2026-11-04', True),
    ('H123', '2026-11-04', False),
    ('', '2026-11-04', False),
])
def test_only_the_last_three_import_seasons_are_listed(brand, race_date, listed):
    assert fsc.listed_in_starter_pdf(brand, race_date) is listed


def test_brand_padding():
    assert fsc.normalise_brand('L31') == 'L031'
    assert fsc.normalise_brand('HK_2024_K475') == 'K475'
    assert fsc.normalise_brand('-') == ''


def _no_network(url):
    raise AssertionError(f'unexpected download {url}')


def test_cached_text_is_used_without_network(tmp_path):
    (tmp_path / 'fsc_L193.txt').write_text(_fixture('L193'), encoding='utf-8')
    rows, status = fsc.fallback_overseas_rows('L193', '2026-10-14', cache_dir=tmp_path,
                                              http_get=_no_network)
    assert status == 'ok' and len(rows) == 10


def test_not_found_is_cached_for_a_week(tmp_path):
    calls = []

    def http_404(url):
        calls.append(url)
        return 404, b'nope'

    assert fsc.fetch_formsheet_text('L999', cache_dir=tmp_path, http_get=http_404) == (None, 'not_found')
    assert calls == [fsc.FSC_URL.format(brand='L999')]
    assert fsc.fetch_formsheet_text('L999', cache_dir=tmp_path, http_get=_no_network) == (None, 'not_found')
    stale = (tmp_path / 'fsc_L999.missing').stat().st_mtime + fsc.MISSING_RETRY_SECONDS + 1
    assert fsc.fetch_formsheet_text('L999', cache_dir=tmp_path, http_get=http_404, now=stale)[1] == 'not_found'
    assert len(calls) == 2


def test_network_error_is_reported_not_raised(tmp_path):
    def boom(url):
        raise TimeoutError('slow')

    rows, status = fsc.fallback_overseas_rows('L193', '2026-10-14', cache_dir=tmp_path, http_get=boom)
    assert rows == [] and status == 'error:TimeoutError'


def test_visiting_runner_and_old_import_get_no_rows(tmp_path):
    assert fsc.fallback_overseas_rows('', '2026-12-14', cache_dir=tmp_path,
                                      http_get=_no_network) == ([], 'no_brand')
    assert fsc.fallback_overseas_rows('J215', '2026-11-04', cache_dir=tmp_path,
                                      http_get=_no_network) == ([], 'not_listed')


# ───────────────────── 接駁：Facts 生成 ─────────────────────

def _meeting(tmp_path, name, brand='L193', horse='馭跑得'):
    meeting = tmp_path / name
    meeting.mkdir()
    prefix = name[5:10]
    (meeting / f'{prefix} Race 1 賽績.md').write_text(f'''馬號: 1
馬名: {horse}
烙號: {brand}
檔位: 1
騎師: 測試騎師
負磅: 120
排位體重: 1100
往績紀錄:
  [1] 06/05/2026 | 日數: 17 | 沙田 "A" 1200 好
      檔位: 4 | 馬重: 1100 | 負磅: 120 | 騎師: 測試騎師 | 名次: 2 / 12
      能量: 91 | 分段時間: 23.00, 22.70, 23.89
      短評: 中等步速
''', encoding='utf-8')
    return meeting, prefix


@pytest.fixture
def fsc_cache(tmp_path, monkeypatch):
    cache = tmp_path / 'cache'
    cache.mkdir()
    for brand in ('L193', 'L267'):
        (cache / f'fsc_{brand}.txt').write_text(_fixture(brand), encoding='utf-8')
    monkeypatch.setenv('WC_HKJC_FSC_CACHE_DIR', str(cache))
    monkeypatch.delenv('WC_HKJC_FSC_FALLBACK', raising=False)
    return cache


def test_starter_pdf_stays_primary_when_present(tmp_path, fsc_cache):
    meeting, prefix = _meeting(tmp_path, '2026-11-04_HappyValley')
    (meeting / f'{prefix} 全日出賽馬匹資料 (PDF).md').write_text(
        (FIXTURES / 'starter_overseas_excerpt.md').read_text(encoding='utf-8'), encoding='utf-8')
    data = facts.parse_hkjc_formguide(str(meeting / f'{prefix} Race 1 賽績.md'), as_of_date='2026-11-04')
    assert data['overseas_source']['mode'] == 'starter_pdf'
    rows = data['horses'][0]['pdf_overseas_races']
    assert rows and all('Source' not in r for r in rows)


def test_missing_pdf_falls_back_to_fsc_with_the_same_rows(tmp_path, fsc_cache):
    meeting, prefix = _meeting(tmp_path, '2026-11-04_HappyValley')
    data = facts.parse_hkjc_formguide(str(meeting / f'{prefix} Race 1 賽績.md'), as_of_date='2026-11-04')
    assert data['overseas_source']['mode'] == 'fsc_fallback'
    rows = data['horses'][0]['pdf_overseas_races']
    starter = facts.parse_pdf_overseas_races(FIXTURES / 'starter_overseas_excerpt.md', 'L193', '')
    assert [{k: r[k] for k in COMPARED} for r in rows] == [{k: r[k] for k in COMPARED} for r in starter]
    assert data['overseas_source']['horses'] == [
        {'num': 1, 'name': '馭跑得', 'brand_no': 'L193', 'status': 'ok', 'rows': 10}]


def test_pdf_without_overseas_section_also_falls_back(tmp_path, fsc_cache):
    meeting, prefix = _meeting(tmp_path, '2026-11-04_HappyValley')
    (meeting / f'{prefix} 全日出賽馬匹資料 (PDF).md').write_text('=== 截斷咗 ===\n', encoding='utf-8')
    data = facts.parse_hkjc_formguide(str(meeting / f'{prefix} Race 1 賽績.md'), as_of_date='2026-11-04')
    assert data['overseas_source']['mode'] == 'fsc_fallback'
    assert len(data['horses'][0]['pdf_overseas_races']) == 10


def test_old_meetings_keep_their_original_inputs(tmp_path, fsc_cache, monkeypatch):
    """`FSC_FALLBACK_SINCE` 之前嘅賽日重跑 Facts 唔可以無端端多咗海外往績。"""
    meeting, prefix = _meeting(tmp_path, '2026-05-17_ShaTin')
    fg = str(meeting / f'{prefix} Race 1 賽績.md')
    data = facts.parse_hkjc_formguide(fg, as_of_date='2026-05-17')
    assert data['overseas_source']['mode'] == 'none'
    assert data['horses'][0]['pdf_overseas_races'] == []
    monkeypatch.setenv('WC_HKJC_FSC_FALLBACK', 'force')
    assert facts.parse_hkjc_formguide(fg, as_of_date='2026-10-14')['overseas_source']['mode'] == 'fsc_fallback'
    monkeypatch.setenv('WC_HKJC_FSC_FALLBACK', '0')
    assert facts.parse_hkjc_formguide(fg, as_of_date='2026-11-04')['overseas_source']['mode'] == 'none'


def test_sidecar_is_written_on_fallback_and_cleared_when_pdf_returns(tmp_path):
    source = {'mode': 'fsc_fallback', 'starter_pdf': '',
              'horses': [{'num': 1, 'name': 'x', 'brand_no': 'L193', 'status': 'ok', 'rows': 10},
                         {'num': 2, 'name': 'y', 'brand_no': '', 'status': 'no_brand', 'rows': 0}]}
    path = facts.record_overseas_source(source, tmp_path, 3, race_date='2026-11-04')
    assert path.name == 'Overseas_Fallback_R3.json'
    payload = json.loads(path.read_text(encoding='utf-8'))
    assert payload['status_counts'] == {'ok': 1, 'no_brand': 1}
    assert facts.record_overseas_source({'mode': 'starter_pdf'}, tmp_path, 3) is None
    assert not path.exists()
    # 舊場次重跑：唔寫警告檔。
    assert facts.record_overseas_source({'mode': 'none'}, tmp_path, 3, race_date='2026-05-17') is None
    assert not os.path.exists(path)

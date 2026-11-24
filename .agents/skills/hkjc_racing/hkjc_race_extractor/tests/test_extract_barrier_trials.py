import datetime as dt
import importlib.util
import json
from pathlib import Path
import sys

scripts = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(scripts))
spec = importlib.util.spec_from_file_location('extract_barrier_trials', scripts / 'extract_barrier_trials.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_incremental_empty_atomic(tmp_path, monkeypatch):
    path = tmp_path / 'trials.json'
    path.write_text(json.dumps({'trials':{}, 'scraped':['2026-01-01'], 'empty':[]}))
    calls = []
    monkeypatch.setattr(m, 'fetch_url', lambda url, **kw: calls.append(url) or '<html></html>')
    monkeypatch.setattr(m.time, 'sleep', lambda _: None)
    replaces = []
    replace = m.os.replace
    monkeypatch.setattr(m.os, 'replace', lambda a,b: (replaces.append((a,b)), replace(a,b)))
    m.update(path, today=dt.date(2026,1,3))
    result = json.loads(path.read_text())
    days = [(dt.date(2025,12,27) + dt.timedelta(days=i)).strftime('%Y/%m/%d') for i in range(8)]
    assert calls == [m.URL.format(d) for d in days]          # 最近 7 日重抓 + 新日子
    assert '2026-01-02' in result['empty'] and '2026-01-03' in result['empty']
    assert len(replaces) == len(days) and all(Path(x[0]).parent == path.parent for x in replaces)


PAGE = ('<table><tr><td>第 1 組</td></tr>'
        '<tr><td>好馬(A123)</td><td>x</td><td>x</td><td>x</td><td>x</td><td>SH</td><td>x</td><td>0.59.10</td><td>x</td></tr></table>')


def test_recent_empty_day_is_rechecked(tmp_path, monkeypatch):
    path = tmp_path / 'trials.json'
    path.write_text(json.dumps({'trials': {}, 'scraped': ['2026-01-09', '2026-01-10'], 'empty': ['2026-01-10']}))
    monkeypatch.setattr(m, 'fetch_url', lambda url, **kw: PAGE if url.endswith('2026/01/10') else '<html></html>')
    monkeypatch.setattr(m.time, 'sleep', lambda _: None)
    m.update(path, today=dt.date(2026, 1, 11))
    result = json.loads(path.read_text())
    assert '2026-01-10' not in result['empty']
    assert result['trials']['A123'] == [['2026-01-10', 0.1, '', None, '', 59.1]]


def test_v2_deduplicates_time_and_caps_margin():
    table = {'trials': {'A123': [['2026-01-01', 2]]}, 'scraped': [], 'empty': []}
    html = PAGE.replace('第 1 組', '第 1 組 - 草地 - 1000米').replace('SH', '20')
    m.add_day(table, '2026-01-02', html)
    m.add_day(table, '2026-01-02', html)
    assert table['schema'] == 2
    assert table['trials']['A123'] == [['2026-01-01', 2], ['2026-01-02', 15, '草地', 1000, '', 59.1]]

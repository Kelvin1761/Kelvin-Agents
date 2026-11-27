import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, REPO / path)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


def test_profit_and_legacy_fixture(tmp_path, monkeypatch):
    ev = module('mp_test', 'docs/experiments/patches/nba_ms2_profit/evaluate.py')
    f = module('featured_test', 'docs/experiments/patches/nba_featured/evaluate.py')
    root, ledger = tmp_path / 'analysis', tmp_path / 'ledger'
    ledger.mkdir()
    for day, prev in [('2026-11-28', '20261127'), ('2026-11-29', '20261128')]:
        snap = root / f'{day} NBA Analysis' / '_prediction_snapshots' / f'{prev}-210000'
        snap.mkdir(parents=True)
        (snap / 'manifest.json').write_text(json.dumps({'snapshot_role': 'production', 'target_date': day, 'completeness': 'complete', 'created_at': day + 'T00:00:00+00:00'}))
        pick = {'player': 'A', 'market': 'pts', 'milestone_line': 10, 'ou_line': 9.5, 'side': 'over', 'price': 2.0, 'edge': .2}
        leg = {'player': 'A', 'market': 'pts', 'line': 10, 'availability': 'ok', 'p_final': .7, 'p_legacy': .7}
        (snap / 'Game_X_Full_Analysis.market_legs.json').write_text(json.dumps({'legs': [leg], 'featured_legacy': [pick]}))
        (snap / 'Sportsbet_Odds_X.json').write_text(json.dumps({'player_props_two_way': {'points': {'A': {'9.5': {'over': 2, 'under': 2}}}}}))
        (ledger / f'{day}.jsonl').write_text(json.dumps({'row_type': 'settlement', 'game_tag': 'X', 'player': 'A', 'market': 'pts', 'line': 10, 'y': 1, 'outcome': 'hit'})+'\n')
    monkeypatch.setattr(ev, 'START', '2026-11-28')
    days = ev.load(ledger, root)
    assert ev.status(days=days)['MP']['ready'] is False
    monkeypatch.setattr(ev, 'CHECKPOINT', {'days': 2, 'bets': 2})
    result = ev.evaluate(ledger, root, tmp_path / 'out')['MP']
    assert result['verdict'] == 'no_difference'
    assert result['n_bets'] == 2
    monkeypatch.setattr(f, 'LEGACY_FROM', '2026-11-28')
    rows = f.legacy_records(ledger, root)
    assert len(rows) == 2 and all(r['state'] == 'won' for r in rows)


def test_snapshot_manifest_and_missing_legacy(tmp_path):
    ev = module('mp_snapshot_test', 'docs/experiments/patches/nba_ms2_profit/evaluate.py')
    day = '2026-11-29'
    folder = tmp_path / f'{day} NBA Analysis' / '_prediction_snapshots'
    for name, role, at in [('early_name', 'warmup', '01'), ('later_name', 'production', '02'),
                            ('first_production', 'production', '00')]:
        snap = folder / name
        snap.mkdir(parents=True)
        (snap / 'manifest.json').write_text(json.dumps({'target_date': day, 'snapshot_role': role,
            'completeness': 'complete', 'created_at': f'{day}T{at}:00:00+00:00'}))
        (snap / 'Game_X_Full_Analysis.market_legs.json').write_text(json.dumps({'legs': [{'p_final': .6}]}))
    assert ev.snapshot(folder.parent, day).name == 'first_production'
    state = ev.status(tmp_path / 'ledger', tmp_path)['MP']
    assert state['days'] == 0 and state['skipped'][0]['day'] == day


def test_partial_settlement_and_frozen_result(tmp_path, monkeypatch):
    ev = module('mp_partial_test', 'docs/experiments/patches/nba_ms2_profit/evaluate.py')
    root, ledger = tmp_path / 'analysis', tmp_path / 'ledger'
    ledger.mkdir()
    for day in ('2026-11-29', '2026-11-30'):
        snap = root / f'{day} NBA Analysis' / '_prediction_snapshots' / 'production'
        snap.mkdir(parents=True)
        (snap / 'manifest.json').write_text(json.dumps({'target_date': day, 'snapshot_role': 'production',
            'completeness': 'complete', 'created_at': day + 'T00:00:00+00:00'}))
        leg = {'player': 'A', 'market': 'pts', 'line': 10, 'availability': 'ok', 'p_final': .7, 'p_legacy': .7}
        pick = {'player': 'A', 'market': 'pts', 'milestone_line': 10, 'ou_line': 9.5, 'side': 'over', 'price': 2., 'edge': .2}
        (snap / 'Game_X_Full_Analysis.market_legs.json').write_text(json.dumps({'legs': [leg], 'featured': [pick], 'featured_legacy': [pick]}))
        (snap / 'Sportsbet_Odds_X.json').write_text(json.dumps({'player_props_two_way': {'points': {'A': {'9.5': {'over': 2, 'under': 2}}}}}))
    row = {'row_type': 'settlement', 'game_tag': 'X', 'player': 'A', 'market': 'pts', 'line': 10, 'y': 1}
    (ledger / '2026-11-30.jsonl').write_text(json.dumps(row) + '\n')
    state = ev.status(ledger, root)['MP']
    assert state['days'] == 0 and state['pending'] == ['2026-11-29']
    monkeypatch.setattr(ev, 'CHECKPOINT', {'days': 1, 'bets': 1})
    (ledger / '2026-11-29.jsonl').write_text(json.dumps(row) + '\n')
    frozen = ev.evaluate(ledger, root, tmp_path / 'out')
    row['y'] = 0
    (ledger / '2026-11-29.jsonl').write_text(json.dumps(row) + '\n')
    assert ev.evaluate(ledger, root, tmp_path / 'out') == frozen
    assert ev.evaluate(ledger, root, tmp_path / 'out', force=True) != frozen


def test_roots_partial_and_legacy(tmp_path, monkeypatch):
    ev = module('mp_roots', 'docs/experiments/patches/nba_ms2_profit/evaluate.py')
    f = module('f_roots', 'docs/experiments/patches/nba_featured/evaluate.py')
    from services import nba_tracking
    a, b, ledger = tmp_path / 'runtime', tmp_path / 'archive', tmp_path / 'ledger'
    ledger.mkdir()
    day = '2026-11-29'
    snap = a / f'{day} NBA Analysis suffix' / '_prediction_snapshots' / 'partial'
    snap.mkdir(parents=True)
    (b / f'{day} NBA Analysis').mkdir(parents=True)
    later = b / f'{day} NBA Analysis' / '_prediction_snapshots' / 'complete'
    later.mkdir(parents=True)
    (later / 'manifest.json').write_text(json.dumps({'target_date': day, 'snapshot_role': 'production', 'completeness': 'complete', 'created_at': day + 'T01:00:00+00:00'}))
    (snap / 'manifest.json').write_text(json.dumps({'target_date': day, 'snapshot_role': 'production', 'completeness': 'partial', 'created_at': day + 'T00:00:00+00:00'}))
    pick = {'player': 'A', 'market': 'pts', 'milestone_line': 10, 'ou_line': 9.5, 'side': 'over', 'price': 2., 'edge': .2}
    leg = {'player': 'A', 'market': 'pts', 'line': 10, 'availability': 'ok', 'p_final': .7, 'p_legacy': .7}
    (snap / 'Game_X_Full_Analysis.market_legs.json').write_text(json.dumps({'legs': [leg], 'featured_legacy': [pick]}))
    (snap / 'Sportsbet_Odds_X.json').write_text(json.dumps({'player_props_two_way': {'points': {'A': {'9.5': {'over': 2, 'under': 2}}}}}))
    (ledger / f'{day}.jsonl').write_text(json.dumps({'row_type': 'settlement', 'game_tag': 'X', 'player': 'A', 'market': 'pts', 'line': 10, 'y': 1}) + '\n')
    monkeypatch.setattr(nba_tracking, '_tracking_roots', lambda repo: [a, b])
    assert ev.load(ledger, b)[0]['day'] == day
    assert len(f.legacy_records(ledger, b)) == 1
    assert ev.load(ledger, tmp_path / 'isolated') == []


def test_missing_snapshot_grace_empty_and_window(tmp_path, monkeypatch):
    from datetime import date, timedelta
    ev = module('mp_window', 'docs/experiments/patches/nba_ms2_profit/evaluate.py')
    today = date.today()
    recent = today.isoformat()
    old = (today - timedelta(days=5)).isoformat()
    monkeypatch.setattr(ev, 'START', old)
    (tmp_path / f'{old} NBA Analysis').mkdir()
    (tmp_path / f'{recent} NBA Analysis').mkdir()
    state = ev.status(tmp_path / 'ledger', tmp_path)['MP']
    assert state['skipped'] == [{'day': old, 'reason': 'missing production snapshot'}]
    assert state['pending'] == [recent]
    snap = tmp_path / f'{old} NBA Analysis' / '_prediction_snapshots' / 'one'
    snap.mkdir(parents=True)
    (snap / 'manifest.json').write_text(json.dumps({'target_date': old, 'snapshot_role': 'production', 'completeness': 'complete', 'created_at': old + 'T00:00:00+00:00'}))
    (snap / 'Game_X_Full_Analysis.market_legs.json').write_text(json.dumps({'legs': []}))
    (snap / 'Sportsbet_Odds_X.json').write_text('{}')
    assert ev.status(tmp_path / 'ledger', tmp_path)['MP']['skipped'][0]['reason'] == 'no bets'
    monkeypatch.setattr(ev, 'CHECKPOINT', {'days': 2, 'bets': 2})
    days = [{'day': str(i), 'live': [{'pnl': 1, 'stat': 'pts'}], 'shadow': [{'pnl': 1, 'stat': 'pts'}], 'card_live': [], 'card_shadow': [], 'losses': []} for i in range(3)]
    state = ev.progress(days)
    assert (state['days'], state['bets'], state['available_days'], state['available_bets']) == (2, 2, 3, 3)
    assert ev.judge(days)['days'] == state['days']

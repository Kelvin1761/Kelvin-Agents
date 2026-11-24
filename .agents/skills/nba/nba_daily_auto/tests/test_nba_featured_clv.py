import json
import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import nba_featured_clv as clv

NOW = datetime(2026, 11, 25, tzinfo=timezone.utc)
PICK = {'game_tag': 'A_B', 'player': 'Player', 'market': 'pts', 'ou_line': 20.5,
        'side': 'over', 'p_fair': 0.5, 'start_time_utc': '2026-11-24T12:00:00Z'}


def row(**kw):
    return dict(row_type='ou_two_way', game_tag='A_B', player='Player', market='pts', ou_line=20.5,
                side='over', price=1.8, complement_price=2.2, captured_at='2026-11-24T11:00:00Z',
                tip_off='2026-11-24T12:00:00Z', **kw)


def test_quotes_and_cache(tmp_path):
    ledger = tmp_path / 'ledger'; ledger.mkdir()
    path = ledger / '2026-11-24.jsonl'
    bad = {**row(), 'price': 3, 'post_tip': True, 'captured_at': '2026-11-24T11:59:00Z'}
    path.write_text('{"ou_two_way" broken\n' + '\n'.join(map(json.dumps, [row(), bad])))
    q = clv.day_quotes(path)
    assert len(q) == 1 and next(iter(q.values()))[1:] == [1.8, 2.2]
    first = clv.quotes(ledger, ['2026-11-24'], tmp_path / 'cache')
    assert clv.quotes(ledger, ['2026-11-24'], tmp_path / 'cache') == first
    assert json.loads(json.dumps(first)) == first


def test_clv_statuses():
    q = {json.dumps(['A_B', 'Player', 'pts', 20.5]): ['2026-11-24T11:00:00+00:00', 1.8, 2.2]}
    assert clv.clv_for(PICK, q, NOW)['pp'] > 0
    assert clv.clv_for({**PICK, 'side': 'under'}, q, NOW)['pp'] < 0
    assert clv.clv_for(PICK, q, datetime(2026, 11, 24, tzinfo=timezone.utc)) == {'status': 'pending'}
    assert clv.clv_for(PICK, {}, NOW) == {'status': 'unavailable'}
    moved = {json.dumps(['A_B', 'Player', 'pts', 21.5]): next(iter(q.values()))}
    assert clv.clv_for({**PICK, 'side': 'under'}, moved, NOW)['our_way']
    assert not clv.clv_for(PICK, moved, NOW)['our_way']


def test_a_line_pulled_after_publication_is_not_a_zero_clv():
    """Its last pre-tip quote is the 21:00 one; that is not a close (Claude 2026-11-24)."""
    import json as _json
    key = _json.dumps(["A_B", "P", "ast", 5.5])
    other = _json.dumps(["A_B", "P", "ast", 6.5])
    day_q = {key: ["2026-11-20T09:59:00+00:00", 1.9, 1.9], other: ["2026-11-20T20:00:00+00:00", 1.9, 1.9]}
    pick = {"game_tag": "A_B", "player": "P", "market": "ast", "ou_line": 5.5, "side": "under", "p_fair": 0.5,
            "start_time_utc": "2026-11-21T00:00:00+00:00", "published_at": "2026-11-20T10:03:00+00:00"}
    out = clv.clv_for(pick, day_q, "2026-11-21T03:00:00+00:00")
    assert out["status"] == "line_moved" and out["close_line"] == 6.5 and out["our_way"] is True

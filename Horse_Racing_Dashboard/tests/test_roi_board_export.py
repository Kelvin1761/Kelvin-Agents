"""Portfolio page: the unified ROI board is copied into the snapshot, never recomputed."""
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from services.roi_board_export import export_roi_board


def test_export_copies_board_days_and_marks_domains_without_days(tmp_path):
    ledger = tmp_path / 'roi_board.json'
    ledger.write_text(json.dumps({'domains': {
        'au': {'day': '2026-11-06', 'since': '2026-08-12',
               'cumulative': {'bets': 3, 'hits': 1, 'stake': 3.0, 'pnl': -0.5},
               'days': {'2026-11-06': {'bets': 2, 'hits': 1, 'stake': 2.0, 'pnl': 0.5},
                        '2026-11-05': {'bets': 1, 'hits': 0, 'pnl': -1.0}}},
        'tennis': {'day': '2026-11-04', 'cumulative': {'bets': 4, 'hits': 2, 'stake': 4.0, 'pnl': 0.2}},
    }}), encoding='utf-8')
    board = export_roi_board(ledger)
    assert board['status'] == 'valid'
    assert list(board['domains']) == ['au', 'nba', 'tennis']
    au = board['domains']['au']
    assert list(au['days']) == ['2026-11-05', '2026-11-06']
    # A row without stake is flat 1u per bet, as on the board itself.
    assert au['days']['2026-11-05'] == {'bets': 1, 'hits': 0, 'stake': 1.0, 'pnl': -1.0}
    assert au['has_days'] is True and au['since'] == '2026-08-12'
    assert board['domains']['tennis']['has_days'] is False
    assert board['domains']['tennis']['cumulative']['bets'] == 4
    assert board['domains']['nba']['days'] == {}


def test_export_raises_on_unreadable_board(tmp_path):
    with pytest.raises(OSError):
        export_roi_board(tmp_path / 'missing.json')
    bad = tmp_path / 'bad.json'
    bad.write_text('{"nope": 1}', encoding='utf-8')
    with pytest.raises(ValueError):
        export_roi_board(bad)

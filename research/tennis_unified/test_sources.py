import hashlib

import pytest

from research.tennis_unified.sources import qualify_metadata, verified_bytes


def test_transfer_rejects_wrong_revision_or_truncated_data():
    raw = b'match_id,player\r\n1,A\r\n'
    sha = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
    verified_bytes(raw, len(raw), sha)
    with pytest.raises(ValueError, match='size mismatch'):
        verified_bytes(raw[:-1], len(raw), sha)
    with pytest.raises(ValueError, match='SHA mismatch'):
        verified_bytes(raw.replace(b'A', b'B'), len(raw), sha)


def test_shifted_csv_fields_are_held_not_repaired_or_counted_as_dates():
    good = {'match_id': '20260101-M-test', 'Date': '20260101', 'Surface': 'Hard',
            'Best of': '3', 'Player 1': 'A', 'Player 2': 'B'}
    shifted = {**good, 'Date': 'RR', 'Surface': 'Eva Asderaki-Moore', None: ['extra']}
    valid, held = qualify_metadata([good, shifted])
    assert valid == [good]
    assert held[0]['csv_line'] == 3
    assert set(held[0]['reasons']) == {'column_count_mismatch', 'invalid_event_date', 'invalid_surface'}
    assert held[0]['raw_values']['Date'] == 'RR'

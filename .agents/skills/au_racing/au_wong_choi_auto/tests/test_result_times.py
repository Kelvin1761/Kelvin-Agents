import csv
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import au_result_times as t


def test_derive_and_format():
    assert t.derive_time(70, '—', 1200, 1) == 70
    assert t.derive_time(70, '1.25L', 1200, 2) == pytest.approx(70 + 1.25 * 2.8 * 70 / 1200)
    assert t.derive_time(70, '0', 1200, 2) == 70
    for margin in ('—', 'DH', '', 'NaN'):
        assert t.derive_time(70, margin, 1200, 2) is None
    assert t.derive_time(70, 'DH', 1200, 1) == 70
    assert t.derive_time(70, 0, 0, 1) is None
    assert t.derive_time(70, 0, '1200.5', 1) is None
    assert t.derive_time(10, 0, 1200, 1) is None
    assert t.derive_time(200, 0, 1200, 1) is None
    assert t.format_time(84.27) == '01:24.270'


def test_sources_conflicts_and_venue(tmp_path):
    assert t.load_official_times(tmp_path / 'missing') == {}
    key = t.identity('2026-10-08', 'Sunshine Coast', 5, 'Example')
    bundle = tmp_path / 'bundle.json'
    bundle.write_text(json.dumps({'events': [{'key': ['sunshinecoast', '2026-10-08', 5, 1200], 'rows': [{'horse': 'Example', 'time': 71.2}]}]}))
    official = t.load_official_times(bundle)
    assert official[key] == 71.2
    assert t.resolve_time(key, 1, '0', 1200, official, {key[:3]: 70}) == ('01:11.200', 'official')
    form = tmp_path / 'Race_1_Formguide.md'
    form.write_text('Sunshine Coast R5 2026-10-08 1200m cond:Good WinningTime:1:10.570\nSunshine Coast R5 2026-10-08 1200m cond:Good WinningTime:1:10.700\n')
    assert key[:3] not in t.load_winning_times(tmp_path)
    bundle.write_text(json.dumps({'events': [{'key': ['sunshinecoast', '2026-10-08', 5, 1200], 'rows': [{'horse': 'Example', 'time': 71.2}, {'horse': 'Example', 'time': 71.3}]}]}))
    assert key not in t.load_official_times(bundle)


def test_fill_dry_run_and_atomic_apply(tmp_path):
    fields = ['Horse', 'Time', 'Date', 'Track', 'Race', 'Pos', 'Margin', 'Distance']
    csv_path = tmp_path / 'results.csv'
    with csv_path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows([dict(zip(fields, ['Example', '', '2026-10-08', 'Sunshine Coast', '5', '1', '—', '1200'])), dict(zip(fields, ['Other', '01:09.000', '2026-10-08', 'Sunshine Coast', '5', '2', '1L', '1200']))])
    original = csv_path.read_bytes()
    (tmp_path / 'Race_Formguide.md').write_text('Sunshine Coast R5 2026-10-08 1200m cond:Good WinningTime:1:10.570\n')
    assert t.fill_times(csv_path, tmp_path, tmp_path / 'missing') == 1
    assert csv_path.read_bytes() == original
    assert not list(tmp_path.glob('*.bak_*'))
    assert t.fill_times(csv_path, tmp_path, tmp_path / 'missing', True) == 1
    assert list(tmp_path.glob('*.bak_*'))[0].read_bytes() == original
    assert csv_path.read_bytes().startswith(b'\xef\xbb\xbf')
    with csv_path.open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == fields
        rows = list(reader)
    assert [r['Time'] for r in rows] == ['01:10.570', '01:09.000']


def test_formguide_margin_fallback_needs_matching_position(tmp_path):
    (tmp_path / 'R1 Formguide.md').write_text(
        '[3] Fast Horse (4)\n'
        'Ipswich R5 2026-10-08 1200m cond:Good margin:2.00L starters:9 finish:3/9 WinningTime:1:10.000\n',
        encoding='utf-8')
    winning, runners = t.load_form_runs(tmp_path)
    key = t.identity('2026-10-08', 'Ipswich', '5', 'Fast Horse')
    assert runners[key] == ('3', '2.00', '1200')
    expected = t.format_time(70 + 2 * t.METRES_PER_LENGTH * 70 / 1200)
    assert t.resolve_time(key, '3', '—', '', {}, winning, runners) == (expected, 'estimated')
    assert t.resolve_time(key, '4', '—', '', {}, winning, runners) == ('', None)


def test_unparsed_header_resets_identity_and_plain_seconds(tmp_path):
    (tmp_path / 'R2 Formguide.md').write_text(
        '[1] First Horse (4)\n'
        'Ipswich R5 2026-10-08 1000m cond:Good margin:1.00L starters:9 finish:2/9 WinningTime:58.10 PF[x]\n'
        '[2] Odd Header\n'
        'Ipswich R6 2026-10-08 1000m cond:Good margin:3.00L starters:9 finish:5/9 WinningTime:58.50\n'
        '[3] Unknown (?)\n'
        'Ipswich R7 2026-10-08 1000m cond:Good margin:3.00L starters:9 finish:5/9 WinningTime:58.70\n',
        encoding='utf-8')
    winning, runners = t.load_form_runs(tmp_path)
    assert winning[('2026-10-08', t.normalize_venue_name('Ipswich'), '5')] == 58.1
    assert t.identity('2026-10-08', 'Ipswich', '6', 'First Horse') not in runners
    assert t.identity('2026-10-08', 'Ipswich', '6', 'Odd Header') in runners
    assert t.identity('2026-10-08', 'Ipswich', '7', 'Unknown') in runners


def test_position_zero_or_text_rejected():
    assert t.derive_time('1:10.0', '1.0L', '1200', '0') is None
    assert t.derive_time('1:10.0', '1.0L', '1200', 'FF') is None
    assert t.derive_time('1:10.0', '—', '1200', '1') == 70.0


def test_malformed_winning_time_and_distance_mismatch(tmp_path):
    assert t.parse_winning_time('1:75.3') is None
    assert t.parse_winning_time('1:2:3') is None
    assert t.parse_winning_time('58.1') == 58.1
    (tmp_path / 'R3 Formguide.md').write_text(
        '[3] Fast Horse (4)\n'
        'Ipswich R5 2026-10-08 1200m cond:Good margin:2.00L starters:9 finish:3/9 WinningTime:1:10.000\n',
        encoding='utf-8')
    winning, runners = t.load_form_runs(tmp_path)
    key = t.identity('2026-10-08', 'Ipswich', '5', 'Fast Horse')
    assert t.resolve_time(key, '3', '—', '1400', {}, winning, runners) == ('', None)

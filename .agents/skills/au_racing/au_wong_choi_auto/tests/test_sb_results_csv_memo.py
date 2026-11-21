"""Per-meeting memo in sb_results_csv: reuse only when nothing that feeds the parse changed.

The memo exists to stop the nightly ingest re-parsing ~5,100 cached races (~15 CPU
minutes) to add zero rows. Its only acceptable behaviour is "same CSV bytes as no
memo"; these tests pin the invalidation rules that guarantee it.
"""
from pathlib import Path
import os
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import sb_results_csv


class DirFetcher:
    def __init__(self, root):
        self.root = root

    def _cache_path(self, url):
        return self.root / (url.strip('/').replace('/', '_') + '.html')


def _setup(tmp_path):
    cache = tmp_path / 'cache'
    cache.mkdir()
    ids = {'2026-08-07 Coffs': {'date': '2026-08-07', 'slug': 'coffs_harbour',
                                'meetingId': 'm1', 'races': ['r1', 'r2']}}
    fetcher = DirFetcher(cache)
    for rid in ('r1', 'r2'):
        p = fetcher._cache_path(f"{sb_results_csv_base()}/m1/{rid}/")
        p.write_text('page ' + rid)
    return ids, fetcher


def sb_results_csv_base():
    from claw_sportsbet_form import BASE
    return BASE


def _run(tmp_path, ids, fetcher, calls, memo=True):
    out = tmp_path / 'out.csv'

    def fake_rows(meta, _fetcher, warn=sb_results_csv._warn_stderr):
        calls.append(meta['meetingId'])
        warn('⚠️ result venue mismatch: example; row skipped')
        return [{'Date': meta['date'], 'Track': 'Coffs Harbour', 'Race': 6, 'Horse': 'Example',
                 'Pos': 1, 'Distance': '1200', 'Barrier': '3', 'Weight': '58.5', 'Jockey': 'D Rider',
                 'Trainer': '', 'Margin': '0', 'Time': '', 'SP': 2.4, 'Condition': 'Soft 5'}]

    argv = ['sb_results_csv.py', '--out', str(out), '--mapping', str(tmp_path / 'ids.json')]
    if memo:
        argv += ['--memo', str(tmp_path / 'memo.json')]
    with patch.object(sys, 'argv', argv), \
            patch('claw_sportsbet_form.SportsbetFormFetcher', return_value=fetcher), \
            patch('sb_backfill_archive.load_meeting_ids', return_value=ids), \
            patch.object(sb_results_csv, 'rows_for_meeting', side_effect=fake_rows):
        assert sb_results_csv.main() == 0
    return out.read_bytes()


def test_warm_memo_skips_parse_and_output_is_byte_identical(tmp_path, capsys):
    ids, fetcher = _setup(tmp_path)
    calls = []
    plain = _run(tmp_path, ids, fetcher, calls, memo=False)
    cold = _run(tmp_path, ids, fetcher, calls)
    warm = _run(tmp_path, ids, fetcher, calls)
    assert calls == ['m1', 'm1']          # no-memo + cold parsed; warm reused
    assert plain == cold == warm
    # warnings are replayed so the run log stays the same
    assert capsys.readouterr().err.count('venue mismatch') == 3


def test_changed_cache_file_forces_reparse(tmp_path):
    ids, fetcher = _setup(tmp_path)
    calls = []
    _run(tmp_path, ids, fetcher, calls)
    page = fetcher._cache_path(f"{sb_results_csv_base()}/m1/r2/")
    page.write_text('refetched page with more bytes')
    _run(tmp_path, ids, fetcher, calls)
    assert calls == ['m1', 'm1']


def test_touched_cache_file_same_size_forces_reparse(tmp_path):
    ids, fetcher = _setup(tmp_path)
    calls = []
    _run(tmp_path, ids, fetcher, calls)
    page = fetcher._cache_path(f"{sb_results_csv_base()}/m1/r1/")
    st = page.stat()
    os.utime(page, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))
    _run(tmp_path, ids, fetcher, calls)
    assert calls == ['m1', 'm1']


def test_new_race_page_appearing_forces_reparse(tmp_path):
    ids, fetcher = _setup(tmp_path)
    ids['2026-08-07 Coffs']['races'].append('r3')   # r3 not cached yet
    calls = []
    _run(tmp_path, ids, fetcher, calls)
    fetcher._cache_path(f"{sb_results_csv_base()}/m1/r3/").write_text('late page')
    _run(tmp_path, ids, fetcher, calls)
    assert calls == ['m1', 'm1']


def test_code_change_invalidates_whole_memo(tmp_path):
    ids, fetcher = _setup(tmp_path)
    calls = []
    _run(tmp_path, ids, fetcher, calls)
    with patch.object(sb_results_csv, 'code_fingerprint', return_value='different-parser'):
        _run(tmp_path, ids, fetcher, calls)
    assert calls == ['m1', 'm1']


def test_corrupt_memo_is_ignored(tmp_path):
    ids, fetcher = _setup(tmp_path)
    calls = []
    (tmp_path / 'memo.json').write_text('{not json')
    _run(tmp_path, ids, fetcher, calls)
    assert calls == ['m1']


def test_fingerprint_covers_parser_module():
    here = Path(sb_results_csv.__file__).resolve().parent
    assert (here / 'claw_sportsbet_form.py').exists()
    with patch.object(Path, 'read_bytes', return_value=b'x'):
        a = sb_results_csv.code_fingerprint()
    assert a != sb_results_csv.code_fingerprint()

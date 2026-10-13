"""`Race_Results_Reflector.md` must not take a runner's finish at ANOTHER venue.

2026-10-13: an emergency acceptor (Master Zous) ran Goulburn R5 the same day as
Newcastle R5. Its dated form line (same date, same race number) was written into
the Newcastle reflector as a second "3rd". `sb_results_csv` already checked the
venue; `sb_results` did not.
"""
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import sb_results  # noqa: E402


class FrozenFetcher:
    def __init__(self, *args, **kwargs):
        pass

    def _cache_path(self, _url):
        return Path(__file__)

    def get(self, _url):
        return 'frozen fixture'


def run(track, pos):
    return {'header': {'date': '06/10/2026', 'race': '5', 'track': track},
            'pos': str(pos), 'margin': None if pos == 1 else '1.0', 'sp': '3.00'}


def collect(blocks):
    ids = {'k': {'date': '2026-10-06', 'slug': 'newcastle', 'meetingId': 'm', 'races': ['r']}}
    parsed = {'meta': {'race_number': 5}, 'overview': {}}
    with patch.object(sb_results, 'SportsbetFormFetcher', FrozenFetcher), \
            patch.object(sb_results, 'parse_race', return_value=parsed), \
            patch.object(sb_results, 'parse_runner_blocks', return_value=blocks):
        return sb_results.collect('k', ids)


def test_other_venue_same_date_and_race_is_skipped(capsys):
    races, _ = collect([{'name': 'Lawless Lucy', 'runs': [run('Newcastle', 1)]},
                        {'name': 'Master Zous', 'runs': [run('Goulburn', 3)]}])
    assert [r[2] for r in races[5]] == ['Lawless Lucy']
    assert 'result venue mismatch' in capsys.readouterr().err


def test_debut_header_counts_as_this_venue():
    races, _ = collect([{'name': 'Debutant', 'runs': [run('First Start Newcastle', 2)]}])
    assert [r[2] for r in races[5]] == ['Debutant']

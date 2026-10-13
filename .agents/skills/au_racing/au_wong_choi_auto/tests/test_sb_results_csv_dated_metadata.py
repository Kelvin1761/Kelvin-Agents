"""Dated result metadata and cross-entry venue protection; no performance claims."""
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import sb_results_csv


class FrozenFetcher:
    def __init__(self, path):
        self.path = path

    def _cache_path(self, _url):
        return self.path

    def get(self, _url):
        return 'frozen fixture'


def result_rows(tmp_path, runs):
    path = tmp_path / 'cached.html'
    path.write_text('frozen fixture')
    meta = {'date': '2026-08-07', 'slug': 'coffs_harbour', 'meetingId': 'm', 'races': ['r']}
    parsed = {'meta': {'race_number': 6, 'track_condition': 'Soft 5'},
              'overview': {'1': {'name': 'Example', 'trainer': 'Future Trainer', 'barrier': 99}}}
    with patch('claw_sportsbet_form.parse_race', return_value=parsed), patch(
            'claw_sportsbet_form.parse_runner_blocks', return_value=[{'name': 'Example', 'runs': runs}]):
        return sb_results_csv.rows_for_meeting(meta, FrozenFetcher(path))


def dated_run(**kwargs):
    run = {'header': {'date': '07/08/2026', 'race': '6', 'track': 'Coffs Harbour', 'dist': '1200'},
           'pos': '1', 'barrier': '12', 'weight': '58.5', 'jockey': ' D Rider ',
           'margin': '5.75', 'winning_time': '1:11.50'}
    run.update(kwargs)
    return run


def test_full_schema_uses_dated_metadata(tmp_path):
    rows = result_rows(tmp_path, [dated_run()])
    assert len(rows) == 1
    row = rows[0]
    assert set(row) == set(sb_results_csv.FIELDS)
    assert (row['Barrier'], row['Weight'], row['Jockey'], row['Distance']) == ('12', '58.5', 'D Rider', '1200')
    assert row['Margin'] == '0'
    assert row['Trainer'] == row['Time'] == ''
    assert row['Condition'] == 'Soft 5'


def test_same_date_race_at_other_venue_is_rejected(tmp_path, capsys):
    run = dated_run(header={'date': '07/08/2026', 'race': '6', 'track': 'Ipswich', 'dist': '1200'})
    assert result_rows(tmp_path, [run]) == []
    assert 'result venue mismatch' in capsys.readouterr().err


def test_other_date_or_race_not_used(tmp_path):
    for header in [{'date': '06/08/2026', 'race': '6', 'track': 'Coffs Harbour'},
                   {'date': '07/08/2026', 'race': '5', 'track': 'Coffs Harbour'}]:
        assert result_rows(tmp_path, [dated_run(header=header)]) == []


def test_missing_venue_does_not_match(tmp_path):
    assert result_rows(tmp_path, [dated_run(header={'date': '07/08/2026', 'race': '6'})]) == []


def test_loser_margin_and_original_draw_preserved(tmp_path):
    row = result_rows(tmp_path, [dated_run(pos='8', margin='2.25')])[0]
    assert row['Margin'] == '2.25'
    assert row['Barrier'] == '12'


def test_course_layouts_do_not_collapse():
    assert sb_results_csv.track_key('Sandown Hillside') != sb_results_csv.track_key('Sandown Lakeside')


def test_debut_header_prefix_is_same_venue(tmp_path):
    """首戰馬往績標題係「First Start Coffs Harbour」—— 2026-10-13 之前被當錯場跳走。"""
    run = dated_run(header={'date': '07/08/2026', 'race': '6', 'track': 'First Start Coffs Harbour', 'dist': '1200'})
    assert len(result_rows(tmp_path, [run])) == 1


def test_barrier_trial_header_still_rejected(tmp_path):
    run = dated_run(header={'date': '07/08/2026', 'race': '6', 'track': 'Barrier Trial Coffs Harbour', 'dist': '1200'})
    assert result_rows(tmp_path, [run]) == []

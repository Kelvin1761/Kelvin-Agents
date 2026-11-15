"""Preserve current-main metadata repair through held native row readers."""
import csv
import io
import json

import pytest
from test_sectional_source_binding import ROOT
from test_same_course_source_binding import write_database


def repair_case(root):
    write_database(root)
    path=root/'comprehensive_stats/24_25/race_results_24_25.csv'
    rows=list(csv.DictReader(io.StringIO(path.read_text())))
    for row in rows: row.update(Course='合成賽事名稱',Going='第四班 - 1200米')
    stream=io.StringIO(); writer=csv.DictWriter(stream,fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows); path.write_text(stream.getvalue())
    day=root/'hkjc results 2024 25/2024-11-01'; day.mkdir(parents=True)
    page={'1':{'race_no':1,'sectional_times':[['第四班 - 1200米','場地狀況 :','好地'],['合成讓賽','賽道 :','草地 - "C" 賽道']], 'results':[]}}
    (day/'full_day_results.json').write_text(json.dumps(page))
    return path,day/'full_day_results.json'


def test_held_reader_preserves_main_repair_at_or_before_csv_cutoff(tmp_path):
    from hkjc_racing_engine import completed_sources as source
    root=tmp_path/'database'; repair_case(root)
    result=source.read_bound_rows(source.CompletedRowsSource(root,source.observe_catalog_sha256(root)))
    row=result[result['Date'].eq('2024-11-01')].iloc[0]
    assert row['Course']=='草地 - "C" 賽道' and row['Going']=='好地'


def test_native_repair_track_fallback_and_absence_are_preserved(tmp_path):
    from hkjc_racing_engine import completed_sources as source
    root=tmp_path/'database'; _,page=repair_case(root)
    page.write_text(json.dumps({'1':{'race_no':1,'track':'草地 - "B" 賽道','going':'黏地','results':[]}}))
    result=source.read_bound_rows(source.CompletedRowsSource(root,source.observe_catalog_sha256(root)))
    row=result[result['Date'].eq('2024-11-01')].iloc[0]
    assert row['Course']=='草地 - "B" 賽道' and row['Going']=='黏地'
    page.unlink()
    binding=source.CompletedRowsSource(root,source.observe_catalog_sha256(root))
    missing=source.read_bound_rows(binding)
    assert missing[missing['Date'].eq('2024-11-01')].iloc[0]['Course']=='合成賽事名稱'
    page.write_text('{}')
    with pytest.raises(ValueError,match='hash differs'): source.read_bound_rows(binding)


@pytest.mark.parametrize('fault',['changed','removed','malformed','unavailable'])
def test_repair_required_daily_input_is_bound_even_before_append_cutoff(tmp_path,monkeypatch,fault):
    from hkjc_racing_engine import completed_sources as source
    root=tmp_path/'database'; _,page=repair_case(root)
    binding=source.CompletedRowsSource(root,source.observe_catalog_sha256(root))
    if fault=='changed': page.write_text(page.read_text().replace('好地','黏地'))
    elif fault=='removed': page.unlink()
    elif fault=='malformed': page.write_text('{bad')
    elif fault=='unavailable':
        original=source.is_materialized_file
        monkeypatch.setattr(source,'is_materialized_file',lambda path:False if path==page else original(path))
    with pytest.raises((ValueError,OSError)): source.read_bound_rows(binding)

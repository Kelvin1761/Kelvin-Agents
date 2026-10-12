import csv
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from au_results_ingest import FIELDNAMES, build_fill_map, fill_missing


def source(root, venue, weight, suffix=''):
    meeting = root / f'2026-08-15 {venue} Race 1-2{suffix}'
    meeting.mkdir(parents=True)
    (meeting / 'Race_Results_Reflector.md').write_text(f'# {venue} Race Results — 2026-08-15\n')
    data = {'race_analysis': {'race_number': 1, 'distance': 1200, 'going': 'Good 4'},
            'horses': {'1': {'horse_name': 'Alpha', 'barrier': 2, 'weight': weight}}}
    (meeting / 'Race_1_Logic.json').write_text(json.dumps(data))
    return meeting


def write_csv(path, rows):
    with path.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path):
    with path.open(newline='') as f:
        return list(csv.DictReader(f))


def row(track, **values):
    return {'Date': '2026-08-15', 'Track': track, 'Race': '1', 'Horse': 'Alpha',
            'Pos': '1', **values}


def test_fill_identity_includes_venue(tmp_path):
    source(tmp_path, 'Ipswich', 55)
    source(tmp_path, 'Coffs Harbour', 59)
    data = build_fill_map(tmp_path)
    assert data[('2026-08-15', 'ipswich', '1', 'alpha')]['Weight'] == '55'
    assert data[('2026-08-15', 'coffsharbour', '1', 'alpha')]['Weight'] == '59'


def test_conflicting_same_identity_not_first_file_wins(tmp_path):
    source(tmp_path, 'Ipswich', 55)
    source(tmp_path, 'Ipswich', 59, ' duplicate')
    data = build_fill_map(tmp_path)
    assert data.get(('2026-08-15', 'ipswich', '1', 'alpha'), {}).get('Weight', '') == ''


def test_no_trackless_join(tmp_path):
    source(tmp_path, 'Ipswich', 55)
    path = tmp_path / 'results.csv'
    write_csv(path, [row('Coffs Harbour', Weight='')])
    assert fill_missing(path, tmp_path, True) == 0
    assert read_csv(path)[0]['Weight'] == ''


def test_fill_preserves_existing_barriers_and_all_nonblank_values(tmp_path):
    source(tmp_path, 'Ipswich', 55)
    path = tmp_path / 'results.csv'
    original = [row('Ipswich', Barrier='9', Weight='56.0', Distance='1200.0', Condition='Good 4')]
    write_csv(path, original)
    before = path.read_bytes()
    assert fill_missing(path, tmp_path, True) == 0
    assert path.read_bytes() == before


def test_logic_normalized_barrier_is_not_raw_draw_fill(tmp_path):
    source(tmp_path, 'Ipswich', 55)
    path = tmp_path / 'results.csv'
    write_csv(path, [row('Ipswich', Barrier='', Weight='')])
    assert fill_missing(path, tmp_path, True) == 0
    actual = read_csv(path)[0]
    assert actual['Barrier'] == ''  # stored Logic may already be densified
    assert actual['Weight'] == '55'


def test_dry_run_does_not_write_or_backup(tmp_path):
    source(tmp_path, 'Ipswich', 55)
    path = tmp_path / 'results.csv'
    write_csv(path, [row('Ipswich', Weight='')])
    before = path.read_bytes()
    assert fill_missing(path, tmp_path, False) == 0
    assert path.read_bytes() == before
    assert not list(tmp_path.glob('results.csv.bak_*'))


def test_apply_backup_and_idempotence(tmp_path):
    source(tmp_path, 'Ipswich', 55)
    path = tmp_path / 'results.csv'
    write_csv(path, [row('Ipswich', Weight='')])
    before = path.read_bytes()
    assert fill_missing(path, tmp_path, True) == 0
    assert next(tmp_path.glob('results.csv.bak_*')).read_bytes() == before
    after = path.read_bytes()
    assert fill_missing(path, tmp_path, True) == 0
    assert path.read_bytes() == after


def test_unknown_venue_not_inferred_from_unrelated_folder(tmp_path):
    m = source(tmp_path, 'Ipswich', 55)
    (m / 'Race_Results_Reflector.md').unlink()
    # Folder naming alone is not independent venue certification.
    assert build_fill_map(tmp_path) == {}


def test_report_retains_conflicts_and_extra_columns(tmp_path):
    source(tmp_path, 'Ipswich', 55)
    path = tmp_path / 'results.csv'
    with path.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES + ['source_note'])
        writer.writeheader()
        writer.writerow(row('Ipswich', Weight='59', Condition='', source_note='original'))
    report = tmp_path / 'report.json'
    assert fill_missing(path, tmp_path, True, report) == 0
    actual = read_csv(path)[0]
    assert actual['Weight'] == '59' and actual['source_note'] == 'original'
    audit = json.loads(report.read_text())
    assert any(x['column'] == 'Weight' for x in audit['conflicts'])
    assert audit['rows_before'] == audit['rows_after'] == 1


def test_report_cannot_overwrite_input_even_when_fills_available(tmp_path):
    import pytest
    source(tmp_path, 'Ipswich', 55)
    path = tmp_path / 'results.csv'
    write_csv(path, [row('Ipswich', Weight='')])
    before = path.read_bytes()
    with pytest.raises(ValueError, match='must not overwrite'):
        fill_missing(path, tmp_path, True, path)
    assert path.read_bytes() == before


def test_invalid_source_weight_not_filled(tmp_path):
    source(tmp_path, 'Ipswich', -55)
    assert build_fill_map(tmp_path).get(('2026-08-15', 'ipswich', '1', 'alpha'), {}).get('Weight', '') == ''


def test_logic_venue_contradiction_quarantines_meeting(tmp_path):
    meeting = source(tmp_path, 'Ipswich', 55)
    path = meeting / 'Race_1_Logic.json'
    data = json.loads(path.read_text())
    data['race_analysis']['meeting_intelligence'] = {'venue': 'Coffs Harbour'}
    path.write_text(json.dumps(data))
    assert build_fill_map(tmp_path) == {}


def dated_bundle(tmp_path):
    import hashlib
    page = tmp_path / 'dated-source.html'
    page.write_text('dated result fixture')
    source_csv = tmp_path / 'dated-results.csv'
    source_row = row('Ipswich', Barrier='12', Weight='58', Margin='0', Jockey='J Smith')
    write_csv(source_csv, [source_row])
    lineage = tmp_path / 'lineage.json'
    lineage.write_text(json.dumps([{'key': ['2026-08-15', 'Ipswich', '1', 'alpha'],
        'dated_run_date': '2026-08-15', 'dated_run_track': 'Ipswich', 'dated_run_race': '1',
        'source_path': str(page), 'source_sha256': hashlib.sha256(page.read_bytes()).hexdigest()}]))
    return source_csv, lineage, page


def test_dated_source_path_dry_run_apply_and_idempotence(tmp_path):
    source_csv, lineage, _ = dated_bundle(tmp_path)
    path = tmp_path / 'results.csv'
    write_csv(path, [row('Ipswich', Barrier='', Weight='', Jockey='', Margin='—')])
    before = path.read_bytes()
    report = tmp_path / 'report.json'
    kwargs = {'source_csv': source_csv, 'lineage_path': lineage}
    assert fill_missing(path, tmp_path, False, report, **kwargs) == 0
    assert path.read_bytes() == before
    assert fill_missing(path, tmp_path, True, report, **kwargs) == 0
    actual = read_csv(path)[0]
    assert actual['Barrier'] == '12' and actual['Jockey'] == 'J Smith'
    assert actual['Trainer'] == actual['Time'] == actual['SP'] == ''
    audit = json.loads(report.read_text())
    assert audit['source_method'] == 'dated_source_csv_with_hash_bound_lineage'
    assert len(audit['source_input_hashes']) == 3
    after = path.read_bytes()
    assert fill_missing(path, tmp_path, True, report, **kwargs) == 0
    assert path.read_bytes() == after


def test_dated_page_hash_change_rejected_before_apply(tmp_path):
    import pytest
    source_csv, lineage, page = dated_bundle(tmp_path)
    path = tmp_path / 'results.csv'
    write_csv(path, [row('Ipswich', Weight='')])
    before = path.read_bytes()
    page.write_text('replaced')
    with pytest.raises(ValueError, match='source hash changed'):
        fill_missing(path, tmp_path, True, source_csv=source_csv, lineage_path=lineage)
    assert path.read_bytes() == before
    assert not list(tmp_path.glob('results.csv.bak_*'))


def test_unbound_source_csv_rejected(tmp_path):
    import pytest
    source_csv, _, _ = dated_bundle(tmp_path)
    path = tmp_path / 'results.csv'
    write_csv(path, [row('Ipswich', Weight='')])
    with pytest.raises(ValueError, match='provided together'):
        fill_missing(path, tmp_path, True, source_csv=source_csv)


def test_dated_report_cannot_overwrite_lineage(tmp_path):
    import pytest
    source_csv, lineage, _ = dated_bundle(tmp_path)
    path = tmp_path / 'results.csv'
    write_csv(path, [row('Ipswich', Weight='')])
    before = path.read_bytes()
    with pytest.raises(ValueError, match='overwrite an input'):
        fill_missing(path, tmp_path, True, lineage, source_csv=source_csv, lineage_path=lineage)
    assert path.read_bytes() == before

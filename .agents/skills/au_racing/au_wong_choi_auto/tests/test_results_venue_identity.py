"""Result identities must retain venue layouts and never guess an alias."""
from pathlib import Path
import sys
import pytest
ROOT=Path(__file__).resolve().parents[5]
AUTO=Path(__file__).resolve().parents[1]/'scripts'
REFLECTOR=ROOT/'.agents/skills/au_racing/au_reflector/scripts'
sys.path.insert(0,str(AUTO));sys.path.insert(0,str(REFLECTOR))
import au_archive_calibrator as archive
import au_ml_matrix_diagnostics as reflector

@pytest.mark.parametrize('reader',[archive,reflector])
def test_layouts_remain_distinct(reader):
    assert reader.normalize_track_name('Sandown Hillside') != reader.normalize_track_name('Sandown Lakeside')
    assert reader.normalize_track_name('Caulfield Heath') != reader.normalize_track_name('Caulfield')

@pytest.mark.parametrize('reader',[archive,reflector])
@pytest.mark.parametrize('target',['','Sandown','Unrelated'])
def test_no_generic_empty_or_unrelated_fallback(reader,target):
    rows=[{'track':'Sandown Hillside','track_slug':reader.normalize_track_name('Sandown Hillside')},
          {'track':'Sandown Lakeside','track_slug':reader.normalize_track_name('Sandown Lakeside')}]
    assert reader.choose_track_rows(rows,target)==[]

@pytest.mark.parametrize('reader',[archive,reflector])
def test_exact_layout_selects_only_that_layout(reader):
    rows=[{'track':'Sandown Hillside','track_slug':reader.normalize_track_name('Sandown Hillside')},
          {'track':'Sandown Lakeside','track_slug':reader.normalize_track_name('Sandown Lakeside')}]
    assert reader.choose_track_rows(rows,'Sandown Hillside')==[rows[0]]

@pytest.mark.parametrize('reader',[archive,reflector])
def test_raw_venue_takes_precedence_over_legacy_collapsed_slug(reader):
    rows=[{'track':'Caulfield Heath','track_slug':'caulfield'}]
    assert reader.choose_track_rows(rows,'Caulfield')==[]
    assert reader.choose_track_rows(rows,'Caulfield Heath')==rows

@pytest.mark.parametrize('reader',[archive,reflector])
def test_only_nonsemantic_meeting_decoration_removed(reader):
    assert reader.normalize_track_name('2026-08-15 Sandown Hillside Race 2-9') == 'sandownhillside'
    assert reader.normalize_track_name('Rosehill Gardens') != reader.normalize_track_name('Rosehill')

@pytest.mark.parametrize('reader',[archive,reflector])
def test_slug_only_exact_fixture_remains_supported(reader):
    row={'track_slug':'eaglefarm'}
    assert reader.choose_track_rows([row],'Eagle Farm')==[row]
    assert reader.choose_track_rows([row],'Farm')==[]

import sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'Horse_Racing_Dashboard/backend'))
from services.parser_au import _parse_au_race_header  # noqa: E402

@pytest.mark.parametrize('race_class',['LAWN PRIDE AUSTRALIA MAIDEN','BM72 Handicap','Group 2 / 3YO Fillies','Listed'])
def test_modern_panorama_class_is_third_component(race_class):
    info=_parse_au_race_header(f'| 賽事格局 | Race 1 / 1300m / {race_class} |\n')
    assert info['race_class']==race_class
    assert info['distance']=='1300m'
    assert info['race_number']==1

def test_empty_modern_class_does_not_guess_from_horse_history():
    info=_parse_au_race_header('| 賽事格局 | Race 1 / 1300m /  |\nHistoric Class: Maiden\n')
    assert info.get('race_class') is None

def test_legacy_class_distance_venue_table_still_works():
    info=_parse_au_race_header('| 賽事格局 | BM72 讓磅賽 / 1300m / Rosehill Gardens / Soft 6 |\n')
    assert info['race_class']=='BM72'
    assert info['distance']=='1300m'


def test_unknown_modern_distance_does_not_use_historical_distance():
    info=_parse_au_race_header("| 賽事格局 | Race 1 / — / Maiden |\nPrevious race 1400m\n")
    assert info["distance"] is None
    assert info["race_class"]=="Maiden"

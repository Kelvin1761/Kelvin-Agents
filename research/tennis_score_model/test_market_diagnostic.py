import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import market_diagnostic as d


def test_name_keys_match_without_winner_information():
    assert d.source_name('Jannik Sinner') == d.sheet_name('Sinner J.')
    assert d.source_name('Roberto Bautista Agut') == d.sheet_name('Bautista Agut R.')
    assert d.source_name('Iga Swiatek') == d.sheet_name('Swiatek I.')


def test_incomplete_name_is_not_fuzzy_matched():
    assert d.source_name('Sinner') is None
    assert d.sheet_name('Sinner') is None

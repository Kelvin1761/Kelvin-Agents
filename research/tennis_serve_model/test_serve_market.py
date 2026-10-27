import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import serve_market as m


def test_no_positive_expectation_means_no_bet():
    assert m.profit(.5,1.9,1.9,1)==(0.,False)


def test_canonical_side_mapping_preserves_profit():
    a=m.profit(.6,2.,2.,1)
    b=m.profit(.4,2.,2.,0)
    assert a==b==(1.,True)


def test_losing_value_pick_is_minus_one():
    assert m.profit(.6,2.,2.,0)==(-1.,True)

"""Race class label → tier (EXP-20261016-05 correctness fix)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from au_racing_engine.engine_core import race_class_tier  # noqa: E402


@pytest.mark.parametrize("label, tier", [
    ("Group 1", 1), ("G1 Cox Plate", 1), ("Group 3 Handicap", 2), ("G2", 2),
    ("Listed", 3), ("LR", 3), ("Open Handicap", 3),
    ("BM56", 7), ("Hygain Edge BM62 Handicap", 7), ("BM70", 6), ("BM78", 5), ("BM90", 4),
    ("LENNOX HOTEL BENCHMARK 66 HANDICAP", 6), ("RDO EQUIPMENT TAREE BENCHMARK 82 HANDICAP", 5),
    ("0 - 56", 7), ("RTG 66+", 6), ("GRAD HCP 60+", 7),
    ("Class 1 Handicap", 7), ("CL3", 6), ("HIGHWAY-C3", 6), ("Class 5", 5),
    ("MDN-SW", 8), ("3Y MDN-SW", 8), ("Maiden Plate", 8), ("CB MDN PLT", 8),
])
def test_recognised_labels(label, tier):
    assert race_class_tier(label) == (tier, True)


@pytest.mark.parametrize("label", [
    # sponsor words used to be read as class by substring tests
    "Designer Coolrooms Maiden Plate",       # "lr" inside "coolrooms" was Listed
])
def test_sponsor_words_are_not_class(label):
    assert race_class_tier(label) == (8, True)


@pytest.mark.parametrize("label", ["", "HCP", "2Y HCP", "TAB HANDICAP", "2YO SWP", None])
def test_labels_without_class_information_stay_unknown(label):
    assert race_class_tier(label) == (7, False)

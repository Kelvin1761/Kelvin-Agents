import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from hkjc_racing_engine import barrier_trial as bt  # noqa: E402


@pytest.mark.parametrize("text,value", [("", 0.0), ("SH", 0.1), ("S/H", 0.1), ("N", 0.05), ("NOSE", 0.05), ("HD", 0.2),
                                        ("neck", 0.3), ("DH", 0.0), ("1-1/4L", 1.25), ("4 1/4L", 4.25), ("1/2l", 0.5),
                                        ("短馬頭位", 0.1), ("鼻位", 0.05), ("6", 6.0), ("ML", None)])
def test_margin(text, value):
    assert bt.margin_lengths(text) == value


def test_last_trial_is_strictly_before_race_date():
    table = {"trials": {"A123": [["2026-01-01", 1.0], ["2026-01-05", 2.0]]}}
    assert bt.last_trial("A123", "2026-01-05", table) == ("2026-01-01", 1.0)
    assert bt.last_trial("A123", "2026-01-06", table) == ("2026-01-05", 2.0)
    assert bt.last_trial("B999", "2026-01-06", table) is None


def test_parse_trial_page():
    html = ('<table><tr><td>第 1 組 - 沙田全天候跑道 - 1200米</td></tr>'
            '<tr><td>好馬 (A123)</td><td>j</td><td>t</td><td>07</td><td></td><td></td><td>3 3 1</td><td>1.08.84</td><td></td></tr>'
            '<tr><td>二馬 (B456)</td><td>j</td><td>t</td><td>06</td><td></td><td>SH</td><td>6 6 2</td><td>1.08.86</td><td></td></tr></table>')
    g = bt.parse_trial_page(html)
    assert len(g) == 1 and [r["code"] for r in g[0]["rows"]] == ["A123", "B456"]
    assert g[0]["rows"][0]["margin"] == 0.0 and g[0]["rows"][1]["margin"] == 0.1
    assert abs(g[0]["rows"][0]["time"] - 68.84) < 1e-9

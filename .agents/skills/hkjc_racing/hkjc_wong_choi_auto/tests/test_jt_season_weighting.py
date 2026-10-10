"""J/T ratings decay by season *age*, never by a hard-coded season label.

2026-10-10 (EXP-20261010-01): the old code treated only "24_25" as the old
season. After the 2026/27 rollover, 25/26 and 26/27 were both weighted ×1.0 and
24/25 was still included, so the documented "current season counts more" design
silently stopped working.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
SCRIPTS = ROOT / ".agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts"
sys.path.insert(0, str(SCRIPTS))

from hkjc_racing_engine import live_priors  # noqa: E402


def test_season_tag_turns_over_in_august():
    assert live_priors.season_tag_for_date("2026-07-15") == "25_26"
    assert live_priors.season_tag_for_date("2026-09-06") == "26_27"
    assert live_priors.season_tag_for_date(date(2027, 1, 1)) == "26_27"
    assert live_priors.season_tag_for_date("2099-12-31") == "99_00"


def test_weights_follow_age_not_label():
    w = live_priors.season_weight
    # 2025/26 season: same as the original design.
    assert w("trainer", "25_26", "25_26") == 1.0
    assert w("trainer", "24_25", "25_26") == 0.3
    # 2026/27 season: the previous season is now 25/26, and 24/25 drops out.
    assert w("trainer", "26_27", "26_27") == 1.0
    assert w("trainer", "25_26", "26_27") == 0.3
    assert w("trainer", "24_25", "26_27") == 0.0
    assert w("jockey", "25_26", "26_27") == 1.0
    assert w("jockey", "24_25", "26_27") == 0.0
    # Future seasons never count.
    assert w("jockey", "27_28", "26_27") == 0.0


def test_no_hard_coded_season_label_remains():
    source = (SCRIPTS / "hkjc_racing_engine/live_priors.py").read_text(encoding="utf-8")
    assert '== "24_25"' not in source
    assert "_w24" not in source


def test_pit_replay_follows_production_weighting():
    sys.path.insert(0, str(ROOT / ".agents/skills/hkjc_racing/hkjc_reflector/scripts"))
    import pit_backtest

    weigh = pit_backtest._season_weight_fn("trainer", "26_27")
    assert (weigh("26_27"), weigh("25_26"), weigh("24_25")) == (1.0, 0.3, 0.0)
    assert pit_backtest._season_tag("2026-09-06") == "26_27"

"""EXP-20261101-30 forward 監察：重算一定要同引擎 `_pf_aggregates` 一致。

監察靠「重算近期加權分 == 儲存分」嚟分辨邊啲場係上線版引擎評分；
重算同引擎一旦分岔，所有場都會被當成舊引擎而靜靜咁永遠唔夠數。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts"))

from au_l600_recency_forward import DECAY, horse_values  # noqa: E402
from au_racing_engine.engine_core import L600_RECENCY_DECAY, _pf_aggregates  # noqa: E402


def _runs():
    return [
        {"l600_delta": 0.4, "margin": 1.0, "run_date": "2026-05-01"},
        {"l600_delta": -0.2, "margin": None, "run_date": "2026-09-01"},
        {"l600_delta": 1.1, "margin": 3.5, "run_date": "2026-07-01"},
    ]


class ForwardReplicaTests(unittest.TestCase):
    def test_decay_matches_engine_constant(self) -> None:
        self.assertEqual(DECAY, L600_RECENCY_DECAY)

    def test_recompute_matches_engine_aggregates(self) -> None:
        runs = _runs()
        agg = _pf_aggregates(runs, "sportsbet_race_context")   # 會喺 runs 寫入 own_l600_delta
        own, race = horse_values(runs, DECAY)
        self.assertEqual(own, agg["own_l600_delta_avg"])
        self.assertEqual(race, agg["l600_delta_avg"])

    def test_decay_one_is_the_old_equal_weight_mean(self) -> None:
        runs = _runs()
        _pf_aggregates(runs, "sportsbet_race_context")
        _own, race = horse_values(runs, 1.0)
        self.assertEqual(race, round((0.4 - 0.2 + 1.1) / 3, 3))


if __name__ == "__main__":
    unittest.main()

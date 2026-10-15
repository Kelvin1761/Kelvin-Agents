"""Joint pace fit isolation, geometry and causal-claim guards."""

import unittest
from copy import deepcopy
import numpy as np

from au_joint_pace_capacity_20261015 import capacity_lookup, design, fit_within_horse
from test_au_contextual_gps_speed_20261015 import events


class JointPaceTests(unittest.TestCase):
    def test_pressure_effort_and_interaction_are_separate(self):
        np.testing.assert_array_equal(design(2, -1), [2, 4, -1, 1, -2])
        np.testing.assert_array_equal(design(10, -20), [3, 9, -3, 9, -9])

    def test_no_repeats_cannot_fit_correction(self):
        beta, n = fit_within_horse([(str(i), design(i / 100, 0), i) for i in range(150)])
        np.testing.assert_array_equal(beta, np.zeros(5))
        self.assertEqual(n, 0)

    def test_within_horse_intercept_does_not_become_pace_effect(self):
        data = [(str(i % 20), design((i % 9 - 4) / 2, (i % 7 - 3) / 2), float(i % 11)) for i in range(300)]
        shifted = [(identity, x, y + 100 * int(identity)) for identity, x, y in data]
        beta, n = fit_within_horse(data)
        other, m = fit_within_horse(shifted)
        self.assertEqual((n, m), (300, 300))
        np.testing.assert_allclose(beta, other, atol=1e-10)

    def test_adding_same_day_or_future_does_not_change_features(self):
        history = events()
        for event in history:
            for row in event["rows"]:
                row["phases"] = {
                    "E800": {
                        "start": 0,
                        "end": event["distance"] - 800,
                        "length": event["distance"] - 800,
                        "time": row["early"],
                    }
                }
        original, state = capacity_lookup(history, history, "2026-08-01", "E800")
        future = deepcopy(history[0])
        future["date"] = "2026-08-01"
        future["rows"][0]["time"] = 999999
        changed, other = capacity_lookup(history + [future], history + [future], "2026-08-01", "E800")
        self.assertEqual(original, changed)
        self.assertEqual(state, other)
        self.assertGreater(state["repeat_observations"], 100)


if __name__ == "__main__":
    unittest.main()

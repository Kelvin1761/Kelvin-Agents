"""devig.py：教科書數值、round-trip、14 匹馬、place target_sum=3、無效輸入。

racing 嗰份（shared_racing/scripts/devig.py）有對應測試；兩份 math 要一致。
最尾加咗 tennis 專用嘅 2-way／over-under ladder helper 測試。
"""
from __future__ import annotations

import math
import unittest

from tennis_wc.betting import devig as dv

FIELD_14 = [2.4, 4.0, 6.0, 7.5, 9.0, 11.0, 13.0, 15.0, 19.0, 26.0, 34.0, 51.0, 81.0, 101.0]
TRUE_14 = [0.30, 0.17, 0.12, 0.09, 0.07, 0.06, 0.05, 0.04, 0.03, 0.025, 0.02, 0.015,
           0.008, 0.002]


def _odds_from(implied: list[float]) -> list[float]:
    return [1.0 / x for x in implied]


class ShinTests(unittest.TestCase):
    def test_published_mberk_example(self) -> None:
        # mberk/shin README：[2.6, 2.4, 4.3] → z ≈ 0.01694251，p[0] ≈ 0.3729941
        r = dv.shin([2.6, 2.4, 4.3])
        self.assertAlmostEqual(r.param, 0.01694251, places=7)
        self.assertAlmostEqual(r.probabilities[0], 0.3729941, places=6)
        self.assertEqual(r.param_name, "z")

    def test_matches_mberk_fixed_point_iteration(self) -> None:
        pi = [1.0 / o for o in FIELD_14]
        total = sum(pi)
        z = 0.0
        for _ in range(2000):
            z = (sum(math.sqrt(z * z + 4 * (1 - z) * x * x / total) for x in pi) - 2) / (len(pi) - 2)
        self.assertAlmostEqual(dv.shin(FIELD_14).param, z, places=9)

    def test_two_way_closed_form(self) -> None:
        odds = [1.5, 2.6]
        pi = [1 / o for o in odds]
        s, d = sum(pi), pi[0] - pi[1]
        z = ((s - 1) * (d * d - s)) / (s * (d * d - 1))
        self.assertAlmostEqual(dv.shin(odds).param, z, places=9)

    def test_round_trip_from_known_z(self) -> None:
        for z in (0.01, 0.05, 0.12):
            s = sum(math.sqrt(z * p + (1 - z) * p * p) for p in TRUE_14)
            implied = [s * math.sqrt(z * p + (1 - z) * p * p) for p in TRUE_14]
            r = dv.shin(_odds_from(implied))
            self.assertAlmostEqual(r.param, z, places=8)
            for got, want in zip(r.probabilities, TRUE_14):
                self.assertAlmostEqual(got, want, places=8)

    def test_rejects_place_target_and_underround(self) -> None:
        with self.assertRaises(ValueError):
            dv.shin(FIELD_14, target_sum=3)
        with self.assertRaises(dv.UnderroundError):
            dv.shin([2.1, 2.1], allow_underround=True)

    def test_fair_book_gives_zero_z(self) -> None:
        r = dv.shin([2.0, 4.0, 4.0])
        self.assertEqual(r.param, 0.0)
        self.assertEqual(r.probabilities, (0.5, 0.25, 0.25))


class PowerTests(unittest.TestCase):
    def test_round_trip_from_known_k(self) -> None:
        for k in (1.05, 1.2, 1.5):
            implied = [p ** (1 / k) for p in TRUE_14]
            r = dv.power(_odds_from(implied))
            self.assertAlmostEqual(r.param, k, places=8)
            for got, want in zip(r.probabilities, TRUE_14):
                self.assertAlmostEqual(got, want, places=8)

    def test_place_market_target_three(self) -> None:
        place_true = [0.75, 0.55, 0.45, 0.35, 0.28, 0.2, 0.15, 0.1, 0.07, 0.05, 0.02,
                      0.015, 0.01, 0.005]
        self.assertAlmostEqual(sum(place_true), 3.0)
        k = 1.15
        r = dv.power(_odds_from([p ** (1 / k) for p in place_true]), target_sum=3)
        self.assertAlmostEqual(r.param, k, places=8)
        self.assertAlmostEqual(sum(r.probabilities), 3.0, places=9)
        for got, want in zip(r.probabilities, place_true):
            self.assertAlmostEqual(got, want, places=8)

    def test_moves_margin_onto_longshots(self) -> None:
        prop = dv.proportional(FIELD_14).probabilities
        pw = dv.power(FIELD_14).probabilities
        self.assertGreater(pw[0], prop[0])
        self.assertLess(pw[-1], prop[-1])


class OddsRatioTests(unittest.TestCase):
    def test_round_trip_from_known_c(self) -> None:
        for c in (1.1, 1.4, 2.0):
            implied = [c * p / (1 - p + c * p) for p in TRUE_14]
            r = dv.odds_ratio(_odds_from(implied))
            self.assertAlmostEqual(r.param, c, places=8)
            for got, want in zip(r.probabilities, TRUE_14):
                self.assertAlmostEqual(got, want, places=8)

    def test_place_target(self) -> None:
        place_odds = [1.15, 1.4, 1.7, 2.1, 2.6, 3.2, 4.0, 5.0, 6.5, 8.5, 11.0, 15.0, 21.0, 26.0]
        r = dv.odds_ratio(place_odds, target_sum=3)
        self.assertAlmostEqual(sum(r.probabilities), 3.0, places=9)
        self.assertTrue(all(0 < p < 1 for p in r.probabilities))


class AdditiveProportionalTests(unittest.TestCase):
    def test_additive_round_trip(self) -> None:
        margin = 0.01
        implied = [p + margin for p in TRUE_14]
        for got, want in zip(dv.additive(_odds_from(implied)).probabilities, TRUE_14):
            self.assertAlmostEqual(got, want, places=12)

    def test_additive_clips_negative_longshots(self) -> None:
        r = dv.additive(FIELD_14 + [201.0, 501.0])
        self.assertGreater(r.clipped, 0)
        self.assertTrue(all(p >= 0 for p in r.probabilities))
        self.assertAlmostEqual(sum(r.probabilities), 1.0, places=12)

    def test_proportional_round_trip(self) -> None:
        implied = [p * 1.18 for p in TRUE_14]
        for got, want in zip(dv.proportional(_odds_from(implied)).probabilities, TRUE_14):
            self.assertAlmostEqual(got, want, places=12)

    def test_proportional_place_caps_at_one(self) -> None:
        odds = [1.05, 1.3, 2.5, 4.0, 6.0, 9.0, 13.0, 21.0]
        r = dv.proportional(odds, target_sum=3, allow_underround=True)
        self.assertGreater(r.clipped, 0)
        self.assertTrue(all(0 <= p <= 1 for p in r.probabilities))
        self.assertAlmostEqual(sum(r.probabilities), 3.0, places=12)
        r = dv.additive(odds, target_sum=3, allow_underround=True)
        self.assertTrue(all(0 <= p <= 1 for p in r.probabilities))
        self.assertAlmostEqual(sum(r.probabilities), 3.0, places=12)


class CommonPropertyTests(unittest.TestCase):
    def test_all_methods_sum_to_one_and_preserve_order(self) -> None:
        for method in dv.METHODS:
            with self.subTest(method=method):
                r = dv.devig(FIELD_14, method)
                self.assertEqual(len(r.probabilities), 14)
                self.assertAlmostEqual(sum(r.probabilities), 1.0, places=9)
                self.assertEqual(list(r.probabilities), sorted(r.probabilities, reverse=True))
                self.assertAlmostEqual(r.overround, sum(1 / o for o in FIELD_14))

    def test_two_way_all_methods(self) -> None:
        for method in dv.METHODS:
            with self.subTest(method=method):
                r = dv.devig([1.8, 2.0], method)
                self.assertAlmostEqual(sum(r.probabilities), 1.0, places=9)
                self.assertGreater(r.probabilities[0], r.probabilities[1])

    def test_symmetric_two_way_is_half(self) -> None:
        for method in dv.METHODS:
            r = dv.devig([1.9, 1.9], method)
            for p in r.probabilities:
                self.assertAlmostEqual(p, 0.5, places=9)

    def test_fair_book_is_identity(self) -> None:
        odds = [2.0, 4.0, 4.0]
        for method in dv.METHODS:
            r = dv.devig(odds, method)
            for got, want in zip(r.probabilities, (0.5, 0.25, 0.25)):
                self.assertAlmostEqual(got, want, places=9)

    def test_fair_odds(self) -> None:
        r = dv.proportional([1.9, 1.9])
        self.assertAlmostEqual(r.fair_odds[0], 2.0)


class InvalidInputTests(unittest.TestCase):
    def test_invalid_odds_raise(self) -> None:
        for bad in (None, 1.0, 0.5, -3, float("nan"), float("inf"), "x", True):
            with self.subTest(bad=bad):
                with self.assertRaises(dv.InvalidOddsError):
                    dv.devig([2.0, 3.0, bad], "power")

    def test_numeric_strings_accepted(self) -> None:
        self.assertAlmostEqual(sum(dv.proportional(["2.0", "2.0"]).probabilities), 1.0)

    def test_too_few_outcomes(self) -> None:
        with self.assertRaises(dv.InvalidOddsError):
            dv.proportional([1.5])
        with self.assertRaises(dv.InvalidOddsError):
            dv.devig([1.5, None], "proportional", on_invalid="exclude")

    def test_exclude_mode(self) -> None:
        r = dv.devig([2.2, None, 3.0, 1.0, 4.0], "shin", on_invalid="exclude")
        self.assertEqual(r.excluded, (1, 3))
        self.assertIsNone(r.probabilities[1])
        self.assertIsNone(r.probabilities[3])
        ref = dv.shin([2.2, 3.0, 4.0])
        self.assertEqual([r.probabilities[i] for i in (0, 2, 4)], list(ref.probabilities))
        self.assertIsNone(r.fair_odds[1])

    def test_underround_raises_by_default(self) -> None:
        arb = [2.2, 2.2]
        for method in dv.METHODS:
            with self.subTest(method=method):
                with self.assertRaises(dv.UnderroundError):
                    dv.devig(arb, method)

    def test_underround_allowed_except_shin(self) -> None:
        arb = [2.1, 2.4]
        self.assertLess(dv.power(arb, allow_underround=True).param, 1.0)
        self.assertLess(dv.odds_ratio(arb, allow_underround=True).param, 1.0)
        for method in ("proportional", "additive", "power", "odds_ratio"):
            r = dv.devig(arb, method, allow_underround=True)
            self.assertAlmostEqual(sum(r.probabilities), 1.0, places=9)

    def test_bad_target_and_method(self) -> None:
        with self.assertRaises(ValueError):
            dv.power([2.0, 3.0], target_sum=2)
        with self.assertRaises(ValueError):
            dv.power([2.0, 3.0], target_sum=0)
        with self.assertRaises(ValueError):
            dv.devig([2.0, 3.0], "logit")
        with self.assertRaises(ValueError):
            dv.devig([2.0, 3.0], "power", on_invalid="skip")


class TennisHelperTests(unittest.TestCase):
    def test_two_way_matches_existing_proportional(self) -> None:
        from tennis_wc.features.market import remove_vig_two_way
        pa, pb = dv.devig_two_way(1.55, 2.45)
        ra, rb = remove_vig_two_way(1 / 1.55, 1 / 2.45)
        self.assertAlmostEqual(pa, ra, places=12)
        self.assertAlmostEqual(pb, rb, places=12)

    def test_power_two_way_shades_underdog(self) -> None:
        pa, pb = dv.devig_two_way(1.30, 3.40, "power")
        prop_a, _ = dv.devig_two_way(1.30, 3.40)
        self.assertAlmostEqual(pa + pb, 1.0, places=9)
        self.assertGreater(pa, prop_a)

    def test_matches_measure_market_coherence_power(self) -> None:
        # scripts/measure_market_coherence.py:power_devig 嘅同一條式
        raw = [1 / o for o in (1.9, 3.6, 5.5, 9.0)]
        lo, hi = 0.5, 3.0
        for _ in range(120):
            k = (lo + hi) / 2
            if sum(r ** k for r in raw) > 1.0:
                lo = k
            else:
                hi = k
        k = (lo + hi) / 2
        r = dv.power([1.9, 3.6, 5.5, 9.0])
        self.assertAlmostEqual(r.param, k, places=9)

    def test_ace_ladder_pairs(self) -> None:
        ladder = [(1.25, 3.75), (1.83, 1.95), (2.9, 1.38)]
        out = dv.devig_pairs(ladder, "shin")
        self.assertEqual(len(out), 3)
        for pair in out:
            self.assertAlmostEqual(sum(pair), 1.0, places=9)
        overs = [pair[0] for pair in out]
        self.assertEqual(overs, sorted(overs, reverse=True))

    def test_ace_ladder_invalid_pair(self) -> None:
        ladder = [(1.83, 1.95), (None, 1.4), (2.2, 2.2)]
        with self.assertRaises(dv.InvalidOddsError):
            dv.devig_pairs(ladder)
        out = dv.devig_pairs(ladder, on_invalid="exclude")
        self.assertIsNotNone(out[0])
        self.assertIsNone(out[1])
        self.assertIsNone(out[2])  # 套利對


if __name__ == "__main__":
    unittest.main()

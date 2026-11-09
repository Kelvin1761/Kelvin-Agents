"""負磅分由「馬匹健康」搬入「級數優勢」（2026-11-05）係 rank-neutral 嘅搬位。

搬之前：級數 = round(0.75·班次 + 0.25·負磅, 2) × 0.1428
        健康 = round(0.611·風險 + 0.389·負磅, 2) × 0.0404（初出馬 0.05 / 0.30）
2026-11-09 重建拆走咗逐位還原嘅 shim：兩項加權和只差兩個維度各自 round 到
2 位小數嘅誤差（≤ 0.004 原始分，初出馬權重大所以誤差較大），每個 leaf 嘅總權重仍然完全一樣。
"""
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from hkjc_racing_engine import dimensions
from hkjc_racing_engine.matrix_mapper import map_features_to_matrix_scores
from hkjc_racing_engine.scoring import DEBUT_MATRIX_WEIGHTS, MATRIX_WEIGHTS, clip_score

OLD = {False: (0.1428, 0.0404), True: (0.05, 0.30)}


def legacy_pair(features, debut):
    w_class, w_health = OLD[debut]
    c, wt, r = (clip_score(features.get(k, 60.0)) for k in ("class_score", "weight_score", "risk_score"))
    old_class = round(clip_score(0.75 * c + 0.25 * wt), 2)
    old_health = round(clip_score(0.611 * r + 0.389 * wt), 2)
    return w_class * old_class + w_health * old_health


class WeightMergeRankNeutralTests(unittest.TestCase):
    def test_class_plus_health_contribution_is_unchanged(self):
        rng = random.Random(20261105)
        for debut in (False, True):
            weights = DEBUT_MATRIX_WEIGHTS if debut else MATRIX_WEIGHTS
            for _ in range(3000):
                features = {
                    "class_score": round(rng.uniform(30, 95), 2),
                    "weight_score": round(rng.uniform(30, 95), 2),
                    "risk_score": round(rng.uniform(30, 95), 2),
                }
                m = map_features_to_matrix_scores(features, debut=debut)
                new = weights["class_advantage"] * m["class_advantage"] + weights["horse_health"] * m["horse_health"]
                self.assertAlmostEqual(new, legacy_pair(features, debut), delta=0.004)

    def test_weight_score_only_lives_in_class_advantage(self):
        formulas = dimensions.formulas()
        self.assertEqual(formulas["horse_health"], (("risk_score", 1.0),))
        self.assertIn("weight_score", dict(formulas["class_advantage"]))
        self.assertIn("weight_score", dict(dimensions.debut_formulas()["class_advantage"]))

    def test_total_weight_on_each_leaf_is_preserved(self):
        for debut in (False, True):
            weights = DEBUT_MATRIX_WEIGHTS if debut else MATRIX_WEIGHTS
            formulas = dimensions.debut_formulas() if debut else dimensions.formulas()
            w_class, w_health = OLD[debut]
            total = {}
            for key in ("class_advantage", "horse_health"):
                for leaf, share in formulas[key]:
                    total[leaf] = total.get(leaf, 0.0) + weights[key] * share
            self.assertAlmostEqual(total["class_score"], w_class * 0.75, places=12)
            self.assertAlmostEqual(total["weight_score"], w_class * 0.25 + w_health * 0.389, places=12)
            self.assertAlmostEqual(total["risk_score"], w_health * 0.611, places=12)

    def test_distance_adjustment_keeps_the_pre_merge_class_weight(self):
        # 同程舊調整（+0.43 / −0.17）係經舊級數優勢計出嚟，唔准跟住新權重變。
        from hkjc_racing_engine import scoring
        self.assertAlmostEqual(scoring.DISTANCE_SUITABILITY_RAW["same_distance_placed"], 4.0 * 0.75 * 0.1428)
        self.assertAlmostEqual(scoring.DISTANCE_SUITABILITY_RAW["same_distance_unplaced"], -1.55 * 0.75 * 0.1428)


if __name__ == "__main__":
    unittest.main()

"""EXP-20261029-30 arm B: weight_score buckets on the official-rating gap to the
field's top-rated runner, instead of the weight proxy.

HK handicaps: top weight 133, declared weight ≈ 133 − rating gap, floor-compressed.
Current thresholds ≥132 / ≤120 ⇔ gap ≤ 1 / gap ≥ 13. Missing rating → arm A
(declared weight). Fixed values, nothing fitted."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
ARM_NAME = "weight_rating_gap"


def apply():
    from hkjc_weight_input_common import bucket, install_racecard_context
    from hkjc_racing_engine.engine_core import RacingEngine
    from hkjc_racing_engine.scoring import clip_score

    install_racecard_context()
    original = RacingEngine._weight_score

    def patched(self, features):
        gap = self._value("exp30_rating_gap")
        if gap not in (None, ""):
            g = float(gap)
            score = bucket(g >= 13, g <= 1)
            return clip_score(score), f"官方評分距全場最高{g:.0f}分，負磅分{score:.0f}分。", "rating_gap"
        declared = self._value("exp30_declared_weight")
        if declared in (None, ""):
            return original(self, features)
        d = float(declared)
        score = bucket(d <= 120, d >= 132)
        return clip_score(score), f"宣佈負磅{d:.0f}磅，負磅分{score:.0f}分。", "declared_weight"

    RacingEngine._weight_score = patched

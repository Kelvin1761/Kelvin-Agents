"""EXP-20261029-30 arm A: weight_score buckets on the DECLARED weight.

The leaf claims to read the handicapper's opinion; the apprentice claim is the
jockey's allowance, not the handicapper's. Same thresholds (≤120 / ≥132)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
ARM_NAME = "weight_declared"


def apply():
    from hkjc_weight_input_common import bucket, install_racecard_context
    from hkjc_racing_engine.engine_core import RacingEngine
    from hkjc_racing_engine.scoring import clip_score

    install_racecard_context()
    original = RacingEngine._weight_score

    def patched(self, features):
        declared = self._value("exp30_declared_weight")
        if declared in (None, ""):
            return original(self, features)
        d = float(declared)
        score = bucket(d <= 120, d >= 132)
        return clip_score(score), f"宣佈負磅{d:.0f}磅，負磅分{score:.0f}分。", "declared_weight"

    RacingEngine._weight_score = patched

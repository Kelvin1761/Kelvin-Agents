"""EXP-20261112-02 arm B（兩邊，主 arm）：今仗 ≥130 磅嘅馬，官方評分分改為 —— 喺呢個磅數上過名 70、
未上過名 64（唔理評分差距）。<130 磅同冇往績嘅馬唔郁。固定值，冇擬合。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
ARM_NAME = "proven_weight_two_sided"


def apply():
    from hkjc_proven_weight_common import install
    from hkjc_racing_engine import scoring
    from hkjc_racing_engine.engine_core import RacingEngine

    install()
    original = RacingEngine._weight_score

    def patched(self, features):
        score, note, src = original(self, features)
        w = scoring.WEIGHT_MICRO_WEIGHTS
        if self._value("exp1112_heavy") is True and self._value("exp1112_proven") in (True, False):
            if self._value("exp1112_proven"):
                return w.get("heavy_weight_base", 70.0), note + "（重磅而且喺今仗磅數上過名）", src
            return w.get("base", 64.0), note + "（重磅但未喺今仗磅數上過名）", src
        return score, note, src

    RacingEngine._weight_score = patched

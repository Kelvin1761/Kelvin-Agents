"""EXP-20261112-02 arm A（只扣一邊）：官方評分分攞到頂級 70 分嘅馬，如果今仗 ≥130 磅而未喺呢個磅數
上過名，退返中性 64。其餘唔郁。固定值，冇擬合。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
ARM_NAME = "proven_weight_gate"


def apply():
    from hkjc_proven_weight_common import install
    from hkjc_racing_engine import scoring
    from hkjc_racing_engine.engine_core import RacingEngine

    install()
    original = RacingEngine._weight_score

    def patched(self, features):
        score, note, src = original(self, features)
        w = scoring.WEIGHT_MICRO_WEIGHTS
        if (self._value("exp1112_heavy") is True and self._value("exp1112_proven") is False
                and score >= w.get("heavy_weight_base", 70.0)):
            return w.get("base", 64.0), note + "（未喺今仗磅數上過名，退返中性）", src
        return score, note, src

    RacingEngine._weight_score = patched

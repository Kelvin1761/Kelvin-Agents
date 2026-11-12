"""EXP-20261112-20：剷走段速分「L400 趨勢」+3／+0.58／−1／−4（訊號檢查：上升 − 衰退 −0.38pp [−3.88,+3.27]；
唔同路程場地嘅原始末段直接比）。Fixed."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
ARM_NAME = "l400_trend_removed"


def apply():
    from hkjc_speed_factor_strip import install
    install("L400 趨勢")

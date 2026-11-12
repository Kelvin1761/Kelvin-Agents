"""EXP-20261112-19 A：剷走段速分「路程配合」±1.5（訊號檢查：97% 有往績馬一律 +1.5，相對模型 +0.02pp；「未跑過」分支語料 0 匹）。Fixed."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
ARM_NAME = "route_fit_removed"


def apply():
    from hkjc_speed_factor_strip import install
    install("路程配合")

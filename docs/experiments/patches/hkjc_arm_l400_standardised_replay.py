"""回放包裝：`hkjc_arm_l400_standardised`（EXP-20261105-03）喺歷史回放語料行。

原 arm 由 `wongchoi_paths.HK_RACING` 讀賽日 Logic 計 cell 平均（只用目標賽日之前）；回放要讀回放根目錄，
否則 2026 年之前冇觀測、arm 等於冇郁。呢度只係將資料根指去 `WC_REPLAY_ROOT`，再叫原 arm；arm 本身唔改。
"""
import importlib.util
import os
from pathlib import Path

ARM_NAME = "l400_standardised"


def apply():
    import wongchoi_paths
    wongchoi_paths.HK_RACING = Path(os.environ["WC_REPLAY_ROOT"])
    spec = importlib.util.spec_from_file_location("l400_std", Path(__file__).with_name("hkjc_arm_l400_standardised.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.apply()

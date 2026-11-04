"""EXP-20261105-03：同一個 process 套用幾個 arm。`WC_ARMS=form_linear,l400_standardised`。"""
import importlib.util
import os
from pathlib import Path

ARM_NAME = "combo"


def apply():
    names = [n.strip() for n in os.environ.get("WC_ARMS", "").split(",") if n.strip()]
    if not names:
        raise SystemExit("WC_ARMS 冇設定")
    for name in names:
        path = Path(__file__).with_name(f"hkjc_arm_{name}.py")
        spec = importlib.util.spec_from_file_location(f"hkjc_arm_{name}", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.apply()

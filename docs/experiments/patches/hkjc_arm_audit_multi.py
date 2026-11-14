"""研究計劃第 2b 步：將 dev 揀出嘅一整批審計組一齊關（holdout 一次確認一整批，計劃 §2b）。

WC_AUDIT_GROUPS = 逗號分隔嘅組名（同 hkjc_arm_audit.py）；逐組叫原 arm 嘅 apply()。
"""
import importlib.util
import os
from pathlib import Path

GROUPS = [g for g in os.environ.get("WC_AUDIT_GROUPS", "").split(",") if g]
ARM_NAME = "audit_multi_" + "+".join(GROUPS)


def apply():
    if not GROUPS:
        raise RuntimeError("WC_AUDIT_GROUPS 冇設")
    for g in GROUPS:
        os.environ["WC_AUDIT_GROUP"] = g
        spec = importlib.util.spec_from_file_location(f"audit_{g}", Path(__file__).with_name("hkjc_arm_audit.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.apply()

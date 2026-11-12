"""EXP-20261112-25 arm：外層權重換成由賽果庫（2026-04-01 之前）估出嚟再搬落引擎嘅版本（hkjc_weight_transfer.py）。
WC_EXP_TRANSFER_JSON = transfer.json；WC_EXP_TRANSFER_MODE = T100 或 T50。只改非初出馬權重（MATRIX_WEIGHTS）。Fixed."""
import json
import os

MODE = os.environ["WC_EXP_TRANSFER_MODE"]
ARM_NAME = f"weight_transfer_{MODE}"


def apply():
    from hkjc_racing_engine import scoring

    new = json.load(open(os.environ["WC_EXP_TRANSFER_JSON"]))[MODE]
    for key, value in new.items():
        scoring.MATRIX_WEIGHTS[key] = float(value)     # 同一個 dict，engine／orchestrator 一齊見到

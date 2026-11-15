"""Kelvin 2026-11-16「SIP 似係舊版遺留，可唔可以用新模型正式計分、唔用 SIP」—— 剷走 SIP-C。

SIP-C：原始分 64–68、負磅 ≤ 場內中位數、檔位 ≤5、（速度 ≥68 或 近績同穩定性 ≥55）→ 原始分 +1.0。
佢針對嘅輕磅同好檔，而家已經由負磅分（評分差距、L400／FT 逐仗負磅換算）同檔位分（＋檔位殘差曲線 shadow）各自入維度。
arm = SIP-C 唔加分（其他不變）。判法：docs/model-evaluation-contract.md「HKJC 歷史回放尺 v4」。
"""
ARM_NAME = "no_sip_c"


def apply():
    import hkjc_auto_orchestrator as orch
    orch._apply_sip_enhancements = lambda horses: None

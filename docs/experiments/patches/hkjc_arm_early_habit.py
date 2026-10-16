"""EXP-20261016-15: 前置習慣（近仗第一沿途位）加入 段速表現 —— 預先登記固定值。

訊號：`_data.position_window` 最近 3 仗（有效第一沿途位）入面，第一沿途位 ≤ 3 嘅比例 s。
少過 2 仗 → 唔加減。delta = K × (s − 1/3)，加落 speed_score（clip 0–100）。
K 由環境變數 `WC_EARLY_HABIT_K` 傳入，只准用預先登記嘅 3 / 6 / 9。

注意：engine_core 用 `from speed import SpeedScorer`（top-level module），
所以一定要 patch `engine_core.SpeedScorer`，patch package 路徑會冇接通。
"""
import os
import re

K = float(os.environ["WC_EARLY_HABIT_K"])
assert K in (3.0, 6.0, 9.0), K
ARM_NAME = f"early_habit_k{int(K)}"
FIRST_CALL = re.compile(r"沿途位=(\d+)-")


def early_habit(data):
    firsts = [int(x) for x in FIRST_CALL.findall(str(data.get("position_window") or ""))][:3]
    if len(firsts) < 2:
        return None
    return sum(f <= 3 for f in firsts) / len(firsts), len(firsts)


def apply():
    from hkjc_racing_engine import engine_core
    from hkjc_racing_engine.scoring import clip_score

    cls = engine_core.SpeedScorer
    original = cls.compute

    def compute(self):
        score, note = original(self)
        habit = early_habit(self._data())
        if habit is None:
            return score, note
        share, runs = habit
        delta = K * (share - 1.0 / 3.0)
        self.detail = list(getattr(self, "detail", []) or []) + [{
            "factor": "前置習慣", "value": f"近{runs}仗 {round(share * runs)} 次頭3",
            "delta": round(delta, 2), "why": "近仗第一沿途位"}]
        return clip_score(score + delta), note

    cls.compute = compute

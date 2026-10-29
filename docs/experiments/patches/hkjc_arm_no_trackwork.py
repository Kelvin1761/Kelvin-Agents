"""Arm: remove every trackwork influence on the ranking (EXP-20261029-02).

晨操 enters the composite two ways: the 晨操狀態 dimension (trackwork_trend_score,
outer weight ~1%) and, for debut runners only, 備戰分 via _prep_score inside the
consistency leaf. Both go to neutral 60. Display is untouched.
"""
ARM_NAME = "no_trackwork"


def apply():
    from hkjc_racing_engine import engine_core

    cls = next(c for c in vars(engine_core).values()
               if isinstance(c, type) and hasattr(c, "_trackwork_trend_score"))
    cls._trackwork_trend_score = lambda self: (60.0, "晨操唔入分（arm）", "trackwork_digest")
    cls._prep_score = lambda self: 60.0

"""EXP-20261111-07 arm: class_score −4 when the horse is 升班 (today's class above last start).

Class move comes from the racecard's own `recent_6_detail` via
`Explanations._class_move_note()` — pre-race information only. Fixed value, nothing fitted.
"""
ARM_NAME = "class_up_penalty"
PENALTY = -4.0


def apply():
    from hkjc_racing_engine.engine_core import RacingEngine
    from hkjc_racing_engine.scoring import clip_score

    original = RacingEngine._class_score

    def patched(self, features):
        score, note, tag = original(self, features)
        if self._is_debut():
            return score, note, tag
        move = self._class_move_note()
        if "（升班）" in move:
            return clip_score(score + PENALTY), f"{note}、升班{PENALTY:+.0f}", tag
        return score, note, tag

    RacingEngine._class_score = patched

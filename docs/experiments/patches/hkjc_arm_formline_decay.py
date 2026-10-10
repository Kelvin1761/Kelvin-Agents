"""Arm: decay old form-line evidence by layoff (EXP-20261010-08, pre-registered).

form_line score moves towards neutral 60 by 0.5 ** (days_since_last / 180):
a 180-day layoff keeps half of the form-line evidence. Half-life fixed a priori,
not fitted. Motivation: 佳登 (10-07 HV R3) ranked 1st on 賽績線 96 from races
140+ days earlier and finished last.
"""
ARM_NAME = "formline_decay_hl180"


def apply():
    from hkjc_racing_engine import engine_core

    original = engine_core.RacingEngine._formline_strength_score

    def decayed(self, *args, **kwargs):
        score, note, source = original(self, *args, **kwargs)
        days = self._days_since_last()
        if isinstance(days, (int, float)) and days > 0:
            keep = 0.5 ** (float(days) / 180.0)
            score = 60.0 + (float(score) - 60.0) * keep
        return score, note, source

    engine_core.RacingEngine._formline_strength_score = decayed

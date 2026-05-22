#!/usr/bin/env python3
"""
racing_engine/scoring.py — Core Scoring Framework
"""

from abc import ABC, abstractmethod
import re


FEATURE_KEYS = (
    "form_score",
    "speed_score",
    "class_score",
    "jockey_score",
    "trainer_score",
    "draw_score",
    "distance_score",
    "track_going_score",
    "weight_score",
    "consistency_score",
    "risk_score",
    "confidence_score",
)

MATRIX_WEIGHTS = {
    "sectional": 0.20,
    "trainer_signal": 0.18,
    "stability": 0.12,
    "race_shape": 0.28,
    "class_advantage": 0.08,
    "horse_health": 0.09,
    "form_line": 0.05,
}

GRADE_THRESHOLDS = (
    (96, "S+"),
    (92, "S"),
    (88, "S-"),
    (84, "A+"),
    (80, "A"),
    (76, "A-"),
    (72, "B+"),
    (68, "B"),
    (64, "B-"),
    (60, "C+"),
    (56, "C"),
    (52, "C-"),
    (48, "D"),
    (0, "E"),
)


class BaseScorer(ABC):
    def __init__(self, horse_data, race_context):
        self.horse_data = horse_data
        self.race_context = race_context
        self.score = 60.0  # Neutral base
        self.reason = ""

    @abstractmethod
    def compute(self):
        """Must return (score, reason)"""
        pass


def clip_score(value, default=60.0):
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = default
    return max(0.0, min(100.0, score))


def compute_grade(ability_score):
    score = clip_score(ability_score, 0)
    for threshold, grade in GRADE_THRESHOLDS:
        if score >= threshold:
            return grade
    return "E"


def parse_float(value):
    if isinstance(value, (int, float)):
        return float(value)
    if not value:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", str(value))
    return float(match.group(0)) if match else None


def parse_numbers(value):
    if not value:
        return []
    return [float(item) for item in re.findall(r"-?\d+(?:\.\d+)?", str(value))]


def parse_record(value):
    if not value:
        return None
    text = str(value)
    match = re.search(r"\((\d+)-(\d+)-(\d+)-(\d+)\)", text)
    if not match:
        return None
    wins, seconds, thirds, starts = (int(part) for part in match.groups())
    return {
        "wins": wins,
        "seconds": seconds,
        "thirds": thirds,
        "starts": starts,
        "places": wins + seconds + thirds,
    }


def score_from_finish(rank):
    try:
        rank = int(rank)
    except (TypeError, ValueError):
        return None
    if rank <= 1:
        return 92
    if rank == 2:
        return 82
    if rank == 3:
        return 74
    if rank <= 5:
        return 62
    if rank <= 8:
        return 48
    return 38


def score_band(score):
    score = clip_score(score)
    if score >= 85:
        return "✅✅"
    if score >= 70:
        return "✅"
    if score >= 55:
        return "➖"
    if score >= 40:
        return "❌"
    return "❌❌"

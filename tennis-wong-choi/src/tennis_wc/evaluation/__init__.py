"""Evaluation corpus definition -- what a judgement is allowed to be measured on."""
from tennis_wc.evaluation.corpus import (
    POINT_IN_TIME,
    POST_START,
    UNVERIFIABLE,
    classify_point_in_time,
    corpus_summary,
    point_in_time_clause,
)

__all__ = [
    "POINT_IN_TIME",
    "POST_START",
    "UNVERIFIABLE",
    "classify_point_in_time",
    "corpus_summary",
    "point_in_time_clause",
]

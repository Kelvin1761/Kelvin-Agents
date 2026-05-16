from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class SportsbetCompetitionMeta:
    tour: str
    tournament_name: str
    level: str
    surface: str | None
    indoor_outdoor: str | None
    is_mvp_supported: bool
    reason: str | None = None


CONFIRMED_COMPETITIONS = {
    "ATP Rome": SportsbetCompetitionMeta("ATP", "ATP Rome Masters", "ATP_1000", "clay", "outdoor", True),
    "WTA Rome": SportsbetCompetitionMeta("WTA", "WTA 1000 Rome", "WTA_1000", "clay", "outdoor", True),
}

ROUND_PATTERNS = (
    (re.compile(r"\b(?:round of|r)\s*128\b", re.IGNORECASE), "R128"),
    (re.compile(r"\b(?:round of|r)\s*64\b", re.IGNORECASE), "R64"),
    (re.compile(r"\b(?:round of|r)\s*32\b", re.IGNORECASE), "R32"),
    (re.compile(r"\b(?:round of|r)\s*16\b", re.IGNORECASE), "R16"),
    (re.compile(r"\bquarter(?:-| )?finals?\b|\bqf\b", re.IGNORECASE), "QF"),
    (re.compile(r"\bsemi(?:-| )?finals?\b|\bsf\b", re.IGNORECASE), "SF"),
    (re.compile(r"\bfinals?\b", re.IGNORECASE), "F"),
    (re.compile(r"\bqual(?:ifying|ifier)?\b", re.IGNORECASE), "Q"),
)


def sportsbet_competition_meta(competition: str | None, match_date: str | None = None) -> SportsbetCompetitionMeta:
    if not competition:
        return SportsbetCompetitionMeta("UNKNOWN", "UNKNOWN", "UNKNOWN", None, None, False, "missing_competition")
    if competition in CONFIRMED_COMPETITIONS:
        return CONFIRMED_COMPETITIONS[competition]

    lowered = competition.lower()
    if "doubles" in lowered:
        reason = "doubles_outside_mvp_scope"
    elif "challenger" in lowered:
        reason = "challenger_outside_mvp_scope"
    elif "itf" in lowered or "futures" in lowered:
        reason = "itf_outside_mvp_scope"
    elif "utr" in lowered:
        reason = "utr_outside_mvp_scope"
    else:
        reason = "competition_metadata_not_confirmed"

    tour = "WTA" if lowered.startswith(("wta", "ladies")) else "ATP" if lowered.startswith(("atp", "mens")) else "UNKNOWN"
    
    # Try heuristic fallback if match_date is provided
    level = "UNKNOWN"
    surface = None
    if match_date:
        from tennis_wc.providers.metadata_utils import infer_tournament_metadata
        meta = infer_tournament_metadata(competition, match_date)
        level = meta["level"]
        surface = meta["surface"]

    return SportsbetCompetitionMeta(tour, competition, level, surface, None, False, reason)


def sportsbet_slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def sportsbet_round_label(*values: str | None) -> str:
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        for pattern, label in ROUND_PATTERNS:
            if pattern.search(text):
                return label
    return "UNKNOWN"

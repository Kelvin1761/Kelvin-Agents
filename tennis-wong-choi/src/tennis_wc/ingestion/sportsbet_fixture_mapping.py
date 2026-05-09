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


def sportsbet_competition_meta(competition: str | None) -> SportsbetCompetitionMeta:
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
    return SportsbetCompetitionMeta(tour, competition, "UNKNOWN", None, None, False, reason)


def sportsbet_slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")

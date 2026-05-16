from __future__ import annotations

TOURNAMENT_METADATA = {
    "Internazionali BNL d'Italia": {"level": "1000", "surface": "Clay"},
    "Mutua Madrid Open": {"level": "1000", "surface": "Clay"},
    "Roland Garros": {"level": "Grand Slam", "surface": "Clay"},
    "French Open": {"level": "Grand Slam", "surface": "Clay"},
    "Wimbledon": {"level": "Grand Slam", "surface": "Grass"},
    "Australian Open": {"level": "Grand Slam", "surface": "Hard"},
    "US Open": {"level": "Grand Slam", "surface": "Hard"},
    "Monte-Carlo": {"level": "1000", "surface": "Clay"},
    "BNP Paribas Open": {"level": "1000", "surface": "Hard"},
    "Indian Wells": {"level": "1000", "surface": "Hard"},
    "Miami Open": {"level": "1000", "surface": "Hard"},
    "National Bank Open": {"level": "1000", "surface": "Hard"},
    "Canadian Open": {"level": "1000", "surface": "Hard"},
    "Cincinnati": {"level": "1000", "surface": "Hard"},
    "Western & Southern Open": {"level": "1000", "surface": "Hard"},
    "Shanghai Masters": {"level": "1000", "surface": "Hard"},
    "Rolex Paris Masters": {"level": "1000", "surface": "Hard"},
    "Paris Masters": {"level": "1000", "surface": "Hard"},
    "Rome": {"level": "1000", "surface": "Clay"},
    "Madrid": {"level": "1000", "surface": "Clay"},
}

def infer_tournament_metadata(name: str, match_date: str) -> dict:
    """
    Infers tournament level and surface based on name and date.
    Returns a dict with 'level' and 'surface'.
    """
    # 1. Check exact mapping
    name_lower = name.lower()
    for t_name, meta in TOURNAMENT_METADATA.items():
        if t_name.lower() in name_lower:
            return meta.copy()

    # 2. Heuristic Level
    level = "UNKNOWN"
    if "masters" in name_lower or "1000" in name_lower:
        level = "1000"
    elif "500" in name_lower:
        level = "500"
    elif "250" in name_lower:
        level = "250"
    elif "challenger" in name_lower:
        level = "Challenger"
    elif "itf" in name_lower:
        level = "ITF"
    elif "grand slam" in name_lower:
        level = "Grand Slam"

    # 3. Heuristic Surface (Month based)
    # Extract month from match_date (YYYY-MM-DD)
    try:
        month = int(match_date.split("-")[1])
        if 4 <= month <= 5:
            surface = "Clay" # April-May is mostly clay season
        elif month == 6 or (month == 7 and "wimbledon" in name_lower):
            surface = "Grass" # June is grass season
        else:
            surface = "Hard" # Default to hard
    except:
        surface = "Hard"

    return {"level": level, "surface": surface}

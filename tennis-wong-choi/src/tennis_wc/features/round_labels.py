from __future__ import annotations

ROUND_MAP = {
    "final": "F",
    "atp 500 final": "F",
    "semi final": "SF",
    "semifinal": "SF",
    "semifinals": "SF",
    "quarter final": "QF",
    "quarterfinal": "QF",
    "quarterfinals": "QF",
    "round of 16": "R16",
    "r16": "R16",
    "round of 32": "R32",
    "r32": "R32",
    "round of 64": "R64",
    "r64": "R64",
    "round of 128": "R128",
    "r128": "R128",
    "qualifying": "QUALIFYING",
}


def normalise_round(raw_round: str) -> str:
    """
    Convert API round names to standard values.
    """
    token = str(raw_round or "").strip()
    if token.upper() in set(ROUND_MAP.values()):
        return token.upper()
    return ROUND_MAP.get(token.lower(), "UNKNOWN")

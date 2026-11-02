"""Cross-provider full-name identity normalization; never match surnames alone."""
from __future__ import annotations

import re
import unicodedata

SUFFIXES = ("jr", "sr", "ii", "iii", "iv", "v")


def player_name_key(name: str) -> str:
    text = unicodedata.normalize('NFKD', str(name)).casefold()
    text = ''.join(char for char in text if not unicodedata.combining(char))
    text = text.replace('’', "'").replace('‘', "'").replace('.', '')
    return ' '.join(text.split())


def availability_name_key(name) -> str:
    """Compact key for injury lists ('First Last' or 'Last,First'), suffixes dropped.

    Moved here from the retired official.nba.com report parser (EXP-20261101-60)
    so the ledger's ``availability_obs.name_key`` keeps the same values. A
    suffix glued to a surname ("JacksonJr.") is only cut right after a
    lowercase letter, so a surname that merely ends in 'v' or 'ii' is kept.
    """
    text = unicodedata.normalize("NFKD", str(name or ""))
    text = "".join(c for c in text if not unicodedata.combining(c))
    if "," in text:
        last, first = text.split(",", 1)
        last = re.sub(r"(?<=[a-z])(Jr\.?|Sr\.?|III|II|IV|V)$", "", last.strip())
        text = f"{first} {last}"
    tokens = re.sub(r"[^a-z0-9 ]", "", text.casefold()).split()
    while len(tokens) > 1 and tokens[-1] in SUFFIXES:
        tokens.pop()
    return "".join(tokens)

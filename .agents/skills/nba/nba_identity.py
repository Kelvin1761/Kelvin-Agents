"""Cross-provider full-name identity normalization; never match surnames alone."""
from __future__ import annotations

import unicodedata


def player_name_key(name: str) -> str:
    text = unicodedata.normalize('NFKD', str(name)).casefold()
    text = ''.join(char for char in text if not unicodedata.combining(char))
    text = text.replace('’', "'").replace('‘', "'").replace('.', '')
    return ' '.join(text.split())

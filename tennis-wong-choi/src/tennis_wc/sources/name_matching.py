from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher


def normalise_player_name(name: str | None) -> str:
    raw = str(name or "").strip().lower()
    if "," in raw:
        parts = [part.strip() for part in raw.split(",", 1)]
        if all(parts):
            raw = f"{parts[1]} {parts[0]}"
    ascii_name = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode("ascii")
    ascii_name = re.sub(r"[^a-z0-9\s.-]", " ", ascii_name)
    # A hyphen is orthography, not identity: the feeds disagree with each other
    # about `Parrizas-Diaz` / `Parrizas Diaz`, `Chan-Yeong Oh` / `Chan Yeong Oh`,
    # `Garcia-Patron Canals` / `Garcia Patron Canals`, and each spelling created
    # its own player row with its own (missing) ranking. Keeping it split the
    # same person in two and the duplicate-name merge could never see them as
    # duplicates.
    ascii_name = ascii_name.replace("-", " ")
    ascii_name = ascii_name.replace(".", " ")
    ascii_name = re.sub(r"\s+", " ", ascii_name).strip()
    return _surname_initial_to_given_first(ascii_name)


def _surname_initial_to_given_first(name: str) -> str:
    """Rewrite the "Glushkova D." scoreboard convention as "d glushkova".

    Result boards for the lower tiers print surname first with the given name
    abbreviated, which puts the surname in the FIRST token and breaks every
    comparison below (they all read the last token as the surname).  Only a
    trailing single-letter token triggers this; real surnames are never one
    letter, and "Last, First" is already handled above.
    """
    tokens = name.split()
    if len(tokens) >= 2 and len(tokens[-1]) == 1:
        return " ".join([tokens[-1], *tokens[:-1]])
    return name


def same_player_name(left: str | None, right: str | None) -> bool:
    return player_name_score(left, right) >= 0.92


def player_name_score(left: str | None, right: str | None) -> float:
    left_norm = normalise_player_name(left)
    right_norm = normalise_player_name(right)
    if not left_norm or not right_norm:
        return 0.0
    if left_norm == right_norm:
        return 1.0

    left_tokens = left_norm.split()
    right_tokens = right_norm.split()
    if set(left_tokens) == set(right_tokens):
        return 0.98

    if _last_name(left_tokens) == _last_name(right_tokens):
        if _first_initial(left_tokens) and _first_initial(left_tokens) == _first_initial(right_tokens):
            return 0.95
        if _first_name(left_tokens) and _first_name(right_tokens):
            first_ratio = SequenceMatcher(None, _first_name(left_tokens), _first_name(right_tokens)).ratio()
            if first_ratio >= 0.86:
                return 0.93

    ratio = SequenceMatcher(None, left_norm, right_norm).ratio()
    if ratio >= 0.92:
        return ratio
    return 0.0


def match_pair_score(
    result_player: str | None,
    result_opponent: str | None,
    match_player_a: str | None,
    match_player_b: str | None,
) -> tuple[float, str | None]:
    direct_a = player_name_score(result_player, match_player_a)
    direct_b = player_name_score(result_opponent, match_player_b)
    swapped_a = player_name_score(result_player, match_player_b)
    swapped_b = player_name_score(result_opponent, match_player_a)
    direct = direct_a + direct_b
    swapped = swapped_a + swapped_b
    if direct >= 1.84 and direct >= swapped:
        return direct, "direct"
    if swapped >= 1.84:
        return swapped, "swapped"
    return 0.0, None


def _first_name(tokens: list[str]) -> str:
    return tokens[0] if tokens else ""


def _first_initial(tokens: list[str]) -> str:
    first = _first_name(tokens)
    return first[0] if first else ""


def _last_name(tokens: list[str]) -> str:
    return tokens[-1] if tokens else ""

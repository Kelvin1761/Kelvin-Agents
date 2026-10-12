"""AU result venue identity; no global aliases or cross-layout fallback."""
from __future__ import annotations
import re


def normalize_venue_name(value: object) -> str:
    """Remove case/punctuation and meeting decoration, preserving venue tokens.

    Heath, Hillside, Lakeside, Gardens, Synthetic, Acton and Scarpside remain
    part of identity. A shortened name requires a separately audited binding;
    it cannot be guessed from a substring or the other venues in a result pool.
    """
    text = str(value or "").strip().casefold()
    text = re.sub(r"^\d{4}-\d{2}-\d{2}[ _]+", "", text)
    text = re.sub(r"[ _]+race[ _]+\d+(?:-\d+)?$", "", text)
    return re.sub(r"[^a-z0-9]+", "", text)


def select_venue_rows(rows, venue: object):
    target = normalize_venue_name(venue)
    if not target:
        return []
    return [row for row in rows
            if normalize_venue_name(row.get("track") or row.get("track_slug")) == target]

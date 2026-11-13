"""ATP Challenger surface from the season calendar on Wikipedia.

Why: Sportsbet names a Challenger as "ATP Challenger 100 Taipei" and no wired
source gave its court. Measured 2026-11-13: 0 of 215 Challenger fixtures
priced since 2026-08-20 had a surface, and 57 of the first 70 精選 were
Challengers. Without a surface `surface_elo` silently equals the overall
rating, so the surface component double-counts overall Elo.

Source: the "<year> ATP Challenger Tour" article, read through the MediaWiki
API (a plain, documented endpoint). Every week lists each event as
``[[City]], Country <br/> Hard (i) – Challenger 100 – ...``. The calendar is
published before the week is played, so a court read from it was knowable
before the match (no look-ahead). The ATP site's own calendar JSON was tried
first and refused repeat requests, so it is not used.

Matching is deliberately strict: the city's tokens must all appear in the
Sportsbet competition name, the Sydney match date must fall in that event's
week (qualifying starts two days early; Sydney runs a day ahead), and every
matching entry must agree on the surface. Anything else resolves to None.
"""
from __future__ import annotations

import json
import re
import unicodedata
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, timedelta

PROVIDER = "wikipedia_atp_challenger_calendar"
_API = "https://en.wikipedia.org/w/api.php"
_USER_AGENT = "tennis-wc-metadata/1.0 (tournament surface lookup)"

_MONTHS = {m: i for i, m in enumerate(
    ("january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"), start=1)}
_SURFACES = {"hard": "Hard", "clay": "Clay", "grass": "Grass", "carpet": "Carpet"}
# Words in a Sportsbet Challenger name that are not part of the place.
_CIRCUIT_WORDS = {"atp", "challenger", "q", "qualifying", "qualifiers", "qualifier",
                  "men", "mens", "singles", "open", "the"}


@dataclass(frozen=True)
class ChallengerEvent:
    week_start: date
    name: str
    city: str
    surface: str
    indoor: bool
    category: str | None


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).lower()


def _tokens(text: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", _fold(text)) if t]


def _link_text(markup: str) -> str:
    """``[[Target|Shown]]`` -> Shown; ``[[Target]]`` -> Target."""
    return re.sub(r"\[\[([^\]|]*\|)?([^\]]*)\]\]", r"\2", markup)


_WEEK = re.compile(r"\|\s*(?:rowspan=\d+\s*\|)?\s*([A-Z][a-z]+)\s+(\d{1,2})\s*\|\|")
_EVENT = re.compile(
    r"\[\[[^\]]*\]\]\s*<br\s*/?>\s*(?P<place>.+?)\s*<br\s*/?>\s*"
    r"(?P<surface>Hard|Clay|Grass|Carpet)\s*(?P<indoor>\(i\))?\s*[–-]\s*Challenger\s*(?P<cat>\d+)?",
    re.IGNORECASE,
)


def parse_calendar(wikitext: str, year: int) -> list[ChallengerEvent]:
    """Every singles Challenger event with its week, city and court."""
    events: list[ChallengerEvent] = []
    week: date | None = None
    for line in wikitext.splitlines():
        found = _WEEK.match(line)
        if found and found.group(1).lower() in _MONTHS:
            try:
                week = date(year, _MONTHS[found.group(1).lower()], int(found.group(2)))
            except ValueError:
                week = None
        if week is None:
            continue
        for event in _EVENT.finditer(line):
            place = _link_text(event.group("place"))
            city = place.split(",")[0].strip()
            name_match = re.search(r"\[\[[^\]|]*\|?([^\]]*)\]\]\s*<br", line[:event.start() + 200])
            name = _link_text(name_match.group(0)[:-3]) if name_match else city
            if not city:
                continue
            events.append(ChallengerEvent(
                week_start=week, name=name.strip(), city=city,
                surface=_SURFACES[event.group("surface").lower()],
                indoor=bool(event.group("indoor")), category=event.group("cat"),
            ))
    return events


def resolve(events: list[ChallengerEvent], competition: str | None,
            match_date: str | None) -> ChallengerEvent | None:
    """The one event this Sportsbet competition on this Sydney date belongs to."""
    if not competition or not match_date or "doubles" in competition.lower():
        return None
    if "challenger" not in competition.lower():
        return None
    try:
        day = date.fromisoformat(match_date)
    except ValueError:
        return None
    comp = set(_tokens(competition)) - _CIRCUIT_WORDS
    category = next((t for t in _tokens(competition) if t.isdigit()), None)
    # The place as Sportsbet wrote it: "Santa Cruz" for "Santa Cruz de la
    # Sierra", "Mouilleron" for "Mouilleron-le-Captif". Country suffixes like
    # "COL" are three letters and dropped.
    place = {t for t in comp if not t.isdigit() and len(t) > 3}
    hits = []
    for event in events:
        city = set(_tokens(event.city)) - _CIRCUIT_WORDS
        if not city or not (city <= comp or (place and place <= city)):
            continue
        # Qualifying starts on the Saturday before the Monday the week is
        # named after; the final is Sunday local, Monday in Sydney.
        if not (event.week_start - timedelta(days=3) <= day <= event.week_start + timedelta(days=8)):
            continue
        if category and event.category and category != event.category:
            continue
        hits.append(event)
    if not hits or len({(e.surface, e.indoor) for e in hits}) != 1:
        return None
    return hits[0]


def fetch_wikitext(year: int, *, opener=None) -> str:
    query = urllib.parse.urlencode({
        "action": "parse", "page": f"{year} ATP Challenger Tour", "prop": "wikitext",
        "format": "json", "formatversion": "2",
    })
    request = urllib.request.Request(f"{_API}?{query}", headers={"User-Agent": _USER_AGENT})
    with (opener or urllib.request.urlopen)(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    text = (payload.get("parse") or {}).get("wikitext")
    if not isinstance(text, str) or "Challenger" not in text:
        raise ValueError(f"no Challenger calendar in the {year} article")
    return text


def load_events(year: int, *, fetch=fetch_wikitext) -> tuple[list[ChallengerEvent], int | None, str | None]:
    """Fresh calendar (stored as a raw response), else the last stored copy.

    Returns (events, raw_response_id, error). A fetch failure never blocks the
    run: it falls back to the last stored article, and with none it returns no
    events, which leaves surfaces exactly as they were before this source.
    """
    from tennis_wc.sources.raw_response_store import store_raw_response
    from tennis_wc.store.db import get_connection

    import os

    error = None
    try:
        if fetch is fetch_wikitext and os.environ.get("TENNIS_CHALLENGER_CALENDAR_OFFLINE") == "1":
            raise RuntimeError("calendar fetch disabled (TENNIS_CHALLENGER_CALENDAR_OFFLINE=1)")
        text = fetch(year)
        raw_id = store_raw_response(PROVIDER, "/w/api.php?action=parse", {"year": year},
                                    {"wikitext": text}, 200, "tournament_calendar", str(year))
        return parse_calendar(text, year), raw_id, None
    except Exception as exc:  # noqa: BLE001 - fall back to the stored copy
        error = f"{type(exc).__name__}: {exc}"
    with get_connection() as conn:
        row = conn.execute(
            """SELECT id, response_json FROM raw_api_responses
               WHERE provider_name = ? AND entity_external_id = ? AND status_code = 200
               ORDER BY id DESC LIMIT 1""", (PROVIDER, str(year))).fetchone()
    if not row:
        return [], None, error
    try:
        text = json.loads(row["response_json"])["wikitext"]
    except (TypeError, ValueError, KeyError):
        return [], None, error
    return parse_calendar(text, year), int(row["id"]), error

"""Lower-tier result feed (ITF / UTR / Challenger) from TennisExplorer.

Why this exists: props are priced on the Sportsbet board, which is ~85% ITF and
UTR, but every result source already wired up covers main tour only.  ESPN
returns three events on a typical day (ATP/WTA main draws), TennisMyLife
publishes ATP / ATP-quali / Challenger / WTA and no ITF at all, and Sportsbet's
own results section lists fixtures with no winner and no scoreline (its resulted
event API 404s).  Measured 2026-08-09 over 2026-07-20..08-07: ITF 0/1972 props
settled, UTR 0/175, Challenger 58/312, ATP-WTA 61/83.

This provider closes that gap.  It returns the full scoreline, not just the
winner, because every games/sets/first-set settler reads per-set games out of
``match_results.score_json``.

Parsing is deliberately strict.  A row is returned only when both player names,
the set tally and the per-set games all parse; anything ambiguous is dropped and
counted in ``skipped`` so a silent format change shows up as a coverage number
rather than as quietly missing results.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, datetime, timezone
from html.parser import HTMLParser
import re
import hashlib
from urllib.parse import parse_qs, urljoin, urlsplit

RESULTS_URL = "https://www.tennisexplorer.com/results/?type=all&year={year}&month={month:02d}&day={day:02d}"
# A finished best-of-three needs two won sets, best-of-five needs three.  A
# winner short of that did not finish the match on court.
_SETS_TO_WIN = {3: 2, 5: 3}


@dataclass(frozen=True)
class ResultsPage:
    """A successfully fetched decoded response, before result parsing."""
    match_date: str
    requested_url: str
    fetched_at: str
    html: str

    @property
    def decoded_html_sha256(self) -> str:
        return hashlib.sha256(self.html.encode('utf-8')).hexdigest()


@dataclass
class ParsedResult:
    tournament_name: str
    player_a_name: str
    player_b_name: str
    player_a_sets: int
    player_b_sets: int
    sets: list[dict] = field(default_factory=list)
    retired: bool = False
    row_id: str = ""
    tour: str | None = None
    draw_kind: str | None = None
    tournament_source_url: str | None = None
    player_a_source_ref: str | None = None
    player_b_source_ref: str | None = None
    classification_warnings: tuple[str, ...] = ()
    tour_source_kind: str | None = None
    tournament_source_label: str | None = None
    match_source_ref: str | None = None

    @property
    def winner_name(self) -> str:
        return (
            self.player_a_name if self.player_a_sets > self.player_b_sets
            else self.player_b_name
        )

    @property
    def loser_name(self) -> str:
        return (
            self.player_b_name if self.player_a_sets > self.player_b_sets
            else self.player_a_name
        )

    def score_payload(self) -> dict:
        payload = {
            "player_a_sets": self.player_a_sets,
            "player_b_sets": self.player_b_sets,
            "total_sets": self.player_a_sets + self.player_b_sets,
            "player_a_games": (
                sum(item["player_a_games"] for item in self.sets) if self.sets else None
            ),
            "player_b_games": (
                sum(item["player_b_games"] for item in self.sets) if self.sets else None
            ),
            "sets": list(self.sets),
            "source": "tennisexplorer_results",
        }
        if self.retired:
            payload["retired"] = True
        return payload


@dataclass(frozen=True)
class _RowSource:
    tournament_links: tuple[str, ...]
    side_links: tuple[str, ...]
    tour_icons: tuple[str, ...] = ()
    tournament_label: str = ""
    match_links: tuple[str, ...] = ()


class _ResultsTableParser(HTMLParser):
    """Collect (row id, row class, [(cell class, cell text)]) for every <tr>."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[tuple[str, str, list[tuple[str, str]]]] = []
        self._row_id = ""
        self._row_class = ""
        self._cells: list[tuple[str, str]] = []
        self._cell_class: str | None = None
        self._cell_text: list[str] = []
        self.row_sources: list[_RowSource] = []
        self._tournament_links: tuple[str, ...] = ()
        self._row_links: list[str] = []
        self._row_tournament_links: tuple[str, ...] = ()
        self._tournament_icons: tuple[str, ...] = ()
        self._tournament_label = ""
        self._row_icons: list[str] = []
        self._row_tournament_icons: tuple[str, ...] = ()
        self._row_tournament_label = ""
        self._row_match_links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        values = dict(attrs)
        if tag == "tr":
            self._row_id = values.get("id") or ""
            self._row_class = values.get("class") or ""
            self._cells = []
            self._row_links = []
            self._row_tournament_links = self._tournament_links
            self._row_icons = []
            self._row_tournament_icons = self._tournament_icons
            self._row_tournament_label = self._tournament_label
            self._row_match_links = []
        elif tag == "td":
            self._cell_class = values.get("class") or ""
            self._cell_text = []
        elif tag == "a":
            href = values.get("href") or ""
            if "t-name" in (self._cell_class or "").split():
                self._row_links.append(href)
            if "match-detail" in href:
                try:
                    path = urlsplit(urljoin("https://www.tennisexplorer.com", href)).path
                except ValueError:
                    path = ""
                if path.rstrip("/") == "/match-detail":
                    self._row_match_links.append(href)
        elif (tag == "span" and {"head", "flags"}.issubset(self._row_class.split())
              and "t-name" in (self._cell_class or "").split()):
            self._row_icons.extend(css for css in (values.get("class") or "").split()
                                   if css.startswith("type-"))

    def handle_data(self, data: str) -> None:
        if self._cell_class is not None:
            self._cell_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self._cell_class is not None:
            text = re.sub(r"\s+", " ", "".join(self._cell_text)).strip()
            self._cells.append((self._cell_class, text))
            self._cell_class = None
            self._cell_text = []
        elif tag == "tr":
            self.rows.append((self._row_id, self._row_class, self._cells))
            links = tuple(dict.fromkeys(self._row_links))
            if {"head", "flags"}.issubset(self._row_class.split()):
                # A header without links must clear the previous context.
                self._tournament_links = links
                self._tournament_icons = tuple(dict.fromkeys(self._row_icons))
                self._tournament_label = _player_name(self._cells)
            self.row_sources.append(_RowSource(self._row_tournament_links, links,
                                               self._row_tournament_icons,
                                               self._row_tournament_label,
                                               tuple(dict.fromkeys(self._row_match_links))))
            self._row_id = ""
            self._row_class = ""
            self._cells = []


def _source_url(href: str) -> str | None:
    try:
        url = urljoin("https://www.tennisexplorer.com", href)
        parsed = urlsplit(url)
    except ValueError:
        return None
    if (parsed.scheme != "https" or parsed.netloc != "www.tennisexplorer.com"
            or parsed.fragment or not href):
        return None
    return url


_ICON_TOURS = {"type-men2": "ATP", "type-men4": "ATP",
               "type-women2": "WTA", "type-women4": "WTA"}


def _classify_result(first: _RowSource, second: _RowSource) -> dict:
    """Use only the current header; an icon never manufactures a missing URL."""
    warnings = []
    tour = draw = declared_draw = tournament_url = source_kind = None
    label = first.tournament_label
    if (first.tournament_links != second.tournament_links
            or first.tour_icons != second.tour_icons
            or label != second.tournament_label):
        warnings.append("conflicting_tournament_sources")
    else:
        if not label:
            warnings.append("missing_current_tournament_label")
        icon_tours = {_ICON_TOURS[css] for css in first.tour_icons if css in _ICON_TOURS}
        unknown_icons = any(css not in _ICON_TOURS for css in first.tour_icons)
        if unknown_icons:
            warnings.append("unsupported_tour_icon")
        if len(icon_tours) > 1:
            warnings.append("conflicting_tour_sources")
        icon_tour = next(iter(icon_tours)) if len(icon_tours) == 1 else None
        if len(first.tournament_links) > 1:
            warnings.append("ambiguous_tournament_source")
        elif first.tournament_links:
            tournament_url = _source_url(first.tournament_links[0])
            parsed = urlsplit(tournament_url or "")
            parts = parsed.path.strip("/").split("/")
            if (len(parts) == 3 and len(parts[1]) == 4 and parts[1].isdigit()
                    and parts[2] in {"atp-men", "wta-women"}):
                url_tour = "ATP" if parts[2] == "atp-men" else "WTA"
                if (icon_tour and icon_tour != url_tour) or len(icon_tours) > 1:
                    warnings.append("conflicting_tour_sources")
                else:
                    tour = url_tour
                    source_kind = "tournament_url+header_icon" if icon_tour else "tournament_url"
                query = parse_qs(parsed.query, keep_blank_values=True)
                if not query:
                    declared_draw = "SINGLES"
                elif query == {"type": ["double"]}:
                    declared_draw = "DOUBLES"
                else:
                    warnings.append("unsupported_draw_query")
            else:
                warnings.append("unsupported_tournament_source")
        elif icon_tour and not unknown_icons:
            tour = icon_tour
            source_kind = "header_icon"
        else:
            warnings.append("missing_tour_source")
    refs, side_kinds = [], []
    for side in (first, second):
        ref = _source_url(side.side_links[0]) if len(side.side_links) == 1 else None
        parsed = urlsplit(ref or "")
        parts = parsed.path.strip("/").split("/")
        kind = None
        if ref and not parsed.query:
            if len(parts) == 2 and parts[0] == "player":
                kind = "SINGLES"
            elif len(parts) == 3 and parts[0] == "doubles-team":
                kind = "DOUBLES"
        if kind is None:
            warnings.append("unknown_side_source_kind")
            ref = None
        refs.append(ref)
        side_kinds.append(kind)
    if side_kinds[0] is not None and side_kinds[0] == side_kinds[1]:
        draw = side_kinds[0]
    else:
        warnings.append("side_source_kind_mismatch")
    if declared_draw and declared_draw != draw:
        warnings.append("header_side_draw_conflict")
    if refs[0] is not None and refs[0] == refs[1]:
        warnings.append("same_source_actor_on_both_sides")
    match_refs = set()
    for href in first.match_links + second.match_links:
        url = _source_url(href)
        parsed = urlsplit(url or "")
        values = parse_qs(parsed.query, keep_blank_values=True).get("id", [])
        if (not url or len(values) != 1 or not values[0].isascii()
                or not values[0].isdigit() or len(values[0]) > 20 or int(values[0]) <= 0):
            warnings.append("invalid_match_source")
        else:
            match_refs.add("https://www.tennisexplorer.com/match-detail/?id="
                           + str(int(values[0])))
    if len(match_refs) > 1:
        warnings.append("conflicting_match_sources")
    return dict(tour=tour, draw_kind=draw, tournament_source_url=tournament_url,
                player_a_source_ref=refs[0], player_b_source_ref=refs[1],
                tour_source_kind=source_kind, tournament_source_label=label or None,
                match_source_ref=next(iter(match_refs)) if len(match_refs) == 1 else None,
                classification_warnings=tuple(dict.fromkeys(warnings)))


def _cell_values(cells: list[tuple[str, str]], wanted: str) -> list[str]:
    return [text for css, text in cells if css.split() and css.split()[0] == wanted]


def _player_name(cells: list[tuple[str, str]]) -> str:
    for css, text in cells:
        if "t-name" in css:
            # Seeding and qualifier markers ride along in the same cell.
            return re.sub(r"\s*\((?:[^)]*)\)\s*$", "", text).strip()
    return ""


def _int_or_none(text: str):
    text = (text or "").strip()
    return int(text) if re.fullmatch(r"\d+", text) else None


def _games_or_none(text: str):
    """Games won in a set, with the tiebreak score peeled off.

    A tiebreak set is printed as ``7`` against ``65`` -- six games and five
    points in the breaker, run together because the points are a superscript in
    the page.  Read literally, 65 beats 7 and the set is credited to the player
    who lost it, which on 2026-08-06 affected 88 of 370 matches.  Only a leading
    6 or 7 can carry a breaker score, so anything else stays unparsed rather
    than being guessed at.
    """
    value = _int_or_none(text)
    if value is None or value <= 20:
        return value
    digits = str(value)
    if digits[0] in {"6", "7"}:
        return int(digits[0])
    return None


def parse_results_page(html: str) -> tuple[list[ParsedResult], int]:
    """Return (results, skipped_row_count) for one TennisExplorer results page."""
    parser = _ResultsTableParser()
    parser.feed(html)
    tournament = ""
    pending: dict[str, tuple[str, list[tuple[str, str]], _RowSource]] = {}
    results: list[ParsedResult] = []
    skipped = 0
    for (row_id, row_class, cells), source in zip(parser.rows, parser.row_sources):
        if "head" in row_class.split() and "flags" in row_class.split():
            tournament = _player_name(cells) or tournament
            continue
        if not row_id.startswith("r"):
            continue
        if row_id.endswith("b"):
            first = pending.pop(row_id[:-1], None)
            if first is None:
                skipped += 1
                continue
            first_tournament, first_cells, first_source = first
            parsed = _build_result(first_tournament, first_cells, cells, row_id[:-1])
            if parsed is None:
                skipped += 1
            else:
                results.append(replace(parsed, **_classify_result(first_source, source)))
        else:
            pending[row_id] = (tournament, cells, source)
    # Any first row never followed by its partner is an unparsed match.
    skipped += len(pending)
    return results, skipped


def _build_result(
    tournament: str,
    a_cells: list[tuple[str, str]],
    b_cells: list[tuple[str, str]],
    row_id: str,
) -> ParsedResult | None:
    player_a = _player_name(a_cells)
    player_b = _player_name(b_cells)
    if not player_a or not player_b or not tournament:
        return None
    a_sets = _int_or_none(next(iter(_cell_values(a_cells, "result")), ""))
    b_sets = _int_or_none(next(iter(_cell_values(b_cells, "result")), ""))
    if a_sets is None or b_sets is None or a_sets == b_sets:
        return None
    a_games = [_games_or_none(value) for value in _cell_values(a_cells, "score")]
    b_games = [_games_or_none(value) for value in _cell_values(b_cells, "score")]
    sets = [
        {"player_a_games": a, "player_b_games": b}
        for a, b in zip(a_games, b_games)
        if a is not None and b is not None
    ]
    best_of = 5 if max(a_sets, b_sets) >= 3 else 3
    retired = max(a_sets, b_sets) < _SETS_TO_WIN[best_of]
    if not sets:
        # A set tally with no per-set grid is a walkover or a retirement before
        # the first set finished.  Returning it as retired lets the props VOID;
        # dropping it would leave them PENDING for ever, which is the failure
        # this provider exists to end.  Callers must only ingest COMPLETED
        # dates, or an in-progress match would look like a retirement.
        return ParsedResult(
            tournament_name=tournament,
            player_a_name=player_a,
            player_b_name=player_b,
            player_a_sets=a_sets,
            player_b_sets=b_sets,
            sets=[],
            retired=True,
            row_id=row_id,
        )
    # The per-set grid must agree with the set tally, otherwise we are reading a
    # layout we do not understand and must not settle anything on it.
    counted_a = sum(1 for item in sets if item["player_a_games"] > item["player_b_games"])
    counted_b = sum(1 for item in sets if item["player_b_games"] > item["player_a_games"])
    if (counted_a, counted_b) != (a_sets, b_sets):
        return None
    return ParsedResult(
        tournament_name=tournament,
        player_a_name=player_a,
        player_b_name=player_b,
        player_a_sets=a_sets,
        player_b_sets=b_sets,
        sets=sets,
        retired=retired,
        row_id=row_id,
    )


class TennisExplorerResultsProvider:
    provider_name = "tennisexplorer"

    def healthcheck(self) -> bool:
        try:
            return bool(self.fetch_results_for_date(date.today().isoformat())[0])
        except Exception:
            return False

    def fetch_results_for_date(self, match_date: str) -> tuple[list[ParsedResult], int]:
        return parse_results_page(self.fetch_results_page_for_date(match_date).html)

    def fetch_results_page_for_date(self, match_date: str) -> ResultsPage:
        day = date.fromisoformat(match_date)
        url = RESULTS_URL.format(year=day.year, month=day.month, day=day.day)
        html = self._fetch_html(url)
        fetched_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')
        return ResultsPage(day.isoformat(), url, fetched_at, html)

    def _fetch_html(self, url: str) -> str:
        # Same impersonation the Sportsbet scrape needs; plain urlopen gets
        # served a bot-check page often enough to look like "no results today".
        from curl_cffi import requests

        response = requests.get(url, impersonate="chrome", timeout=30)
        if response.status_code != 200:
            raise RuntimeError(
                f"tennisexplorer results returned HTTP {response.status_code} for {url}"
            )
        return response.text

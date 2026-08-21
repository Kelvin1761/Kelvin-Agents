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

from dataclasses import dataclass, field
from datetime import date
from html.parser import HTMLParser
import re

RESULTS_URL = "https://www.tennisexplorer.com/results/?type=all&year={year}&month={month:02d}&day={day:02d}"
# A finished best-of-three needs two won sets, best-of-five needs three.  A
# winner short of that did not finish the match on court.
_SETS_TO_WIN = {3: 2, 5: 3}


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

    def handle_starttag(self, tag: str, attrs: list) -> None:
        values = dict(attrs)
        if tag == "tr":
            self._row_id = values.get("id") or ""
            self._row_class = values.get("class") or ""
            self._cells = []
        elif tag == "td":
            self._cell_class = values.get("class") or ""
            self._cell_text = []

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
            self._row_id = ""
            self._row_class = ""
            self._cells = []


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
    pending: dict[str, tuple[str, list[tuple[str, str]]]] = {}
    results: list[ParsedResult] = []
    skipped = 0
    for row_id, row_class, cells in parser.rows:
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
            first_tournament, first_cells = first
            parsed = _build_result(first_tournament, first_cells, cells, row_id[:-1])
            if parsed is None:
                skipped += 1
            else:
                results.append(parsed)
        else:
            pending[row_id] = (tournament, cells)
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
        day = date.fromisoformat(match_date)
        url = RESULTS_URL.format(year=day.year, month=day.month, day=day.day)
        return parse_results_page(self._fetch_html(url))

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

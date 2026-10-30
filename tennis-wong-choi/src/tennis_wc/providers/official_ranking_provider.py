from __future__ import annotations

import json
import hashlib
import base64
import logging
import re
from datetime import date, datetime, timezone
from html import unescape
from io import BytesIO
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from tennis_wc.providers.tennis_provider_base import TennisProvider
from tennis_wc.ranking_dates import RankingDateError, normalise_ranking_date, validate_ranking_rows
from tennis_wc.config import get_settings

logger = logging.getLogger(__name__)


# One runaway guard for every parse path, replacing four separate hard-coded
# `if len(rows) >= 500: break` lines -- one in each of the ATP UTS, WTA API, WTA
# PDF and WTA HTML parsers.
#
# Those four were the ones that mattered. Lifting the two REQUEST caps changed
# nothing on its own: the ATP payload arrived with all 2,161 rows and the parser
# still returned 500, which is why the truncation warning added alongside them
# was worth more than the caps it was meant to watch. Seven stacked 500s in
# total, counting the two request limits and `ingest_rankings`'
# CACHED_RANKING_ROW_LIMIT.
#
# 5,000 is a guard against a malformed payload, not a view about how deep the
# ladder goes: ATP holds 2,161 ranked players and WTA 1,572, so a real feed
# never reaches it -- and if one ever does, the warning says so instead of the
# rows quietly vanishing.
MAX_RANKING_ROWS = 5000


class OfficialRankingFetchError(RuntimeError):
    pass


class OfficialRankingProvider(TennisProvider):
    provider_name = "official_rankings"

    ATP_UTS_RANKINGS_URL = "https://www.ultimatetennisstatistics.com/rankingsTableTable"
    ATP_UTS_DATE_URL = "https://www.ultimatetennisstatistics.com/rankingsDate?rankType=RANK"
    ATP_NUMERIC_PDF_URL = "https://www.protennislive.com/posting/ramr/singles_entry_numerical.pdf"
    WTA_RANKED_PLAYERS_API_URL = "https://api.wtatennis.com/tennis/players/ranked"
    WTA_NUMERIC_PDF_URL = "https://wtafiles.wtatennis.com/pdf/rankings/Singles_Numeric.pdf"
    WTA_RANKINGS_URL = "https://www.wtatennis.com/rankings/singles"

    def __init__(self):
        self.ranking_source_evidence = []
        self.ranking_source_failures = []

    def _capture_text(self, url, **kwargs):
        try:
            text = self._fetch_text(url, **kwargs)
        except Exception as exc:
            self.ranking_source_evidence.append({"url": url, "received_at": datetime.now(timezone.utc).isoformat(),
                                                  "error": f"{type(exc).__name__}: {exc}"})
            raise
        self.ranking_source_evidence.append({
            "url": url, "received_at": datetime.now(timezone.utc).isoformat(),
            "decoded_utf8_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "text": text,
        })
        return text

    def healthcheck(self) -> bool:
        return True

    def fetch_rankings(self, tour: str, date_str: str | None = None) -> list[dict]:
        self.ranking_source_evidence = []
        self.ranking_source_failures = []
        tour = tour.upper()
        if tour == "ATP":
            sources = [("atp_official_numeric_pdf", self._fetch_atp_numeric_pdf),
                       ("ultimate_tennis_statistics", self._fetch_atp_uts)]
        elif tour == "WTA":
            sources = [("wta_ranked_players_api", self._fetch_wta_api),
                       ("wta_numeric_pdf", self._fetch_wta_numeric_pdf), ("wta_rankings_html", self._fetch_wta_html)]
        else:
            raise OfficialRankingFetchError(f"Unsupported official ranking tour: {tour}")
        for name, fetch in sources:
            rows = None
            try:
                rows = fetch(date_str)
                if not rows:
                    raise OfficialRankingFetchError("empty ranking source")
                return validate_ranking_rows(rows, date_str, max_age_hours=get_settings().data_max_staleness_hours_rankings)
            except (OfficialRankingFetchError, RankingDateError, OSError) as exc:
                self.ranking_source_failures.append({"source": name, "error": str(exc), "rows": rows})
                logger.info("Ranking source %s unavailable: %s", name, exc)
        raise OfficialRankingFetchError(f"All official {tour} ranking sources rejected: " +
                                         "; ".join(f"{x['source']}: {x['error']}" for x in self.ranking_source_failures))

    def _capture_pdf(self, url):
        try:
            data = self._fetch_bytes(url, timeout=30)
        except Exception as exc:
            self.ranking_source_evidence.append({"url": url, "received_at": datetime.now(timezone.utc).isoformat(),
                                                  "error": f"{type(exc).__name__}: {exc}"})
            raise
        self.ranking_source_evidence.append({"url": url, "received_at": datetime.now(timezone.utc).isoformat(),
            "sha256": hashlib.sha256(data).hexdigest(), "content_base64": base64.b64encode(data).decode("ascii")})
        return data

    def _fetch_atp_numeric_pdf(self, date_str):
        try:
            import pdfplumber
        except ImportError as exc:
            raise OfficialRankingFetchError("pdfplumber is required for the ATP official PDF") from exc
        data = self._capture_pdf(self.ATP_NUMERIC_PDF_URL)
        try:
            with pdfplumber.open(BytesIO(data)) as pdf:
                pages = [p.extract_text(x_tolerance=1, y_tolerance=3) or "" for p in pdf.pages]
        except Exception as exc:
            raise OfficialRankingFetchError(f"Invalid ATP official PDF: {exc}") from exc
        rows = _parse_atp_numeric_pdf_pages(pages, date_str)
        for row in rows:
            row["raw"]["source_pdf_sha256"] = hashlib.sha256(data).hexdigest()
        return rows

    # The whole ladder, not the first page of it. 2026-08-27: this asked for
    # 500 rows while the endpoint held 2,161 (deepest rank 2,162), and the WTA
    # path stopped at five pages of 100 while its feed ran to 1,517. Ranked
    # players went 1,000 fetched against ~3,733 available.
    #
    # That cap was not cosmetic. `current_rank` is one of only four inputs in
    # the feature set that is not a re-slice of past results, and ITF -- 85% of
    # the board we price -- sits between rank 400 and 1,500. So the model was
    # priced with no rank on 57% of players and no Elo on 35%, and on the 49.5%
    # of fixtures where all its independent inputs ARE present it draws level
    # with the market (Delta log-loss +0.0161, CI [-0.0063, +0.0379]) instead of
    # losing by +0.0639. The cap was half the deficit.
    ATP_ROW_COUNT = 4000
    WTA_PAGE_SIZE = 100
    WTA_MAX_PAGES = 40

    def _fetch_atp_uts(self, date_str: str | None) -> list[dict]:
        try:
            date_text = self._capture_text(self.ATP_UTS_DATE_URL, timeout=30, accept="application/json")
            source_date = normalise_ranking_date(json.loads(date_text))
        except (ValueError, TypeError, OSError) as exc:
            raise OfficialRankingFetchError("ATP UTS source date request failed") from exc
        if source_date is None:
            raise OfficialRankingFetchError("ATP UTS endpoint did not expose a valid source ranking date")
        params = {
            "current": "1",
            "rowCount": str(self.ATP_ROW_COUNT),
            "sort[rank]": "asc",
            "searchPhrase": "",
            "rankType": "RANK",
            "season": "",
            # UTS current is the Bootgrid page number. Pin the data date using
            # its documented dd-MM-yyyy parameter, independently of card date.
            "date": datetime.strptime(source_date, "%Y-%m-%d").strftime("%d-%m-%Y"),
            "_": "1",
        }
        try:
            text = self._capture_text(
                f"{self.ATP_UTS_RANKINGS_URL}?{urlencode(params)}",
                timeout=30,
                accept="application/json,text/javascript,*/*;q=0.8",
                extra_headers={"X-Requested-With": "XMLHttpRequest"},
            )
        except Exception as exc:
            raise OfficialRankingFetchError("ATP UTS rankings request failed") from exc
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise OfficialRankingFetchError("ATP UTS rankings endpoint returned invalid JSON") from exc
        rows = _parse_atp_uts_rankings(payload, date_str, source_date=source_date)
        for row in rows:
            row["raw"].update(source_date_url=self.ATP_UTS_DATE_URL,
                              source_date_sha256=hashlib.sha256(date_text.encode()).hexdigest())
        if not rows:
            raise OfficialRankingFetchError("ATP UTS rankings endpoint returned no parseable rows")
        # The endpoint reports its own total, so a truncated answer is
        # detectable rather than something to discover eighteen months later in
        # a coverage audit. Logged, not raised: a partial ladder is still worth
        # far more than yesterday's.
        available = _int_or_none((payload or {}).get("total"))
        if available and len(rows) < available * 0.95:
            logger.warning(
                "ATP rankings truncated: parsed %d of %d available (rowCount=%d). "
                "Raise ATP_ROW_COUNT or add paging.",
                len(rows), available, self.ATP_ROW_COUNT,
            )
        return rows

    def _fetch_wta_api(self, date_str: str | None) -> list[dict]:
        payload: list[dict] = []
        # Paged until the feed returns a short page. WTA_MAX_PAGES is a
        # runaway guard, not the intended stop: the real feed ends at page 15
        # (1,572 players, deepest rank 1,517), and a fixed range(5) silently
        # threw away two thirds of it.
        page_size = self.WTA_PAGE_SIZE
        for page in range(self.WTA_MAX_PAGES):
            params = {
                "page": str(page),
                "pageSize": str(page_size),
                "type": "rankSingles",
                "sort": "asc",
                "metric": "SINGLES",
                "at": _normalise_date(date_str) or date.today().isoformat(),
                "name": "",
                "nationality": "",
            }
            try:
                text = self._capture_text(
                    f"{self.WTA_RANKED_PLAYERS_API_URL}?{urlencode(params)}",
                    timeout=30,
                    accept="application/json,*/*;q=0.8",
                    extra_headers={
                        "account": "wta",
                        "Origin": "https://www.wtatennis.com",
                        "Referer": self.WTA_RANKINGS_URL,
                    },
                )
            except Exception as exc:
                raise OfficialRankingFetchError("WTA ranked players API request failed") from exc
            try:
                page_payload = json.loads(text)
            except json.JSONDecodeError as exc:
                raise OfficialRankingFetchError("WTA ranked players API returned invalid JSON") from exc
            if not isinstance(page_payload, list) or not page_payload:
                break
            payload.extend(page_payload)
            if len(page_payload) < page_size:
                break
        else:
            logger.warning(
                "WTA rankings hit the %d-page guard with a full last page; the "
                "feed is deeper than expected and is being truncated.",
                self.WTA_MAX_PAGES,
            )
        rows = _parse_wta_api_rankings(payload, date_str)
        if not rows:
            raise OfficialRankingFetchError("WTA ranked players API returned no parseable rows")
        return rows

    def _fetch_wta_numeric_pdf(self, date_str: str | None) -> list[dict]:
        try:
            import pdfplumber
        except Exception as exc:
            raise OfficialRankingFetchError("pdfplumber is required to parse WTA official rankings PDF") from exc

        data = self._capture_pdf(self.WTA_NUMERIC_PDF_URL)
        try:
            with pdfplumber.open(BytesIO(data)) as pdf:
                text = "\n".join(page.extract_text(x_tolerance=1, y_tolerance=3) or "" for page in pdf.pages)
        except Exception as exc:
            raise OfficialRankingFetchError(f"Invalid WTA official PDF: {exc}") from exc
        rows = _parse_wta_numeric_pdf_text(text, date_str)
        if not rows:
            raise OfficialRankingFetchError("WTA official rankings PDF returned no parseable rows")
        return rows

    def _fetch_wta_html(self, date_str: str | None) -> list[dict]:
        try:
            text = self._capture_text(self.WTA_RANKINGS_URL, timeout=30, accept="text/html,*/*;q=0.8")
        except Exception as exc:
            raise OfficialRankingFetchError("WTA official rankings page request failed") from exc
        rows = _parse_wta_rankings_html(text, date_str)
        if not rows:
            raise OfficialRankingFetchError("WTA official rankings page returned no parseable rows")
        return rows

    def _fetch_bytes(self, url: str, timeout: int) -> bytes:
        request = Request(
            url,
            headers={
                "User-Agent": "Antigravity/0.1 ranking-provider",
                "Accept": "application/pdf,text/html;q=0.8,*/*;q=0.5",
            },
        )
        with urlopen(request, timeout=timeout) as response:
            data = response.read(8 * 1024 * 1024 + 1)
        if len(data) > 8 * 1024 * 1024:
            raise OfficialRankingFetchError("ranking PDF exceeds the 8MiB source limit")
        return data

    def _fetch_text(
        self,
        url: str,
        timeout: int,
        accept: str,
        extra_headers: dict[str, str] | None = None,
    ) -> str:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) tennis-wong-choi/0.1",
            "Accept": accept,
            "Accept-Language": "en-US,en;q=0.9",
        }
        if extra_headers:
            headers.update(extra_headers)
        request = Request(url, headers=headers)
        with urlopen(request, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="replace")

    def fetch_upcoming_matches(self, date_str: str) -> list[dict]:
        return []

    def fetch_historical_matches(self, start_date: str, end_date: str) -> list[dict]:
        return []

    def fetch_match_stats(self, match_id: str) -> dict:
        return {}

    def fetch_player_profile(self, player_id: str) -> dict:
        return {}

    def fetch_player_stats(self, player_id: str) -> dict:
        return {}

    def fetch_tournaments(self, start_date: str, end_date: str) -> list[dict]:
        return []


def _parse_atp_numeric_pdf_pages(pages, requested_date=None):
    """Complete numerical singles publication; page/date/row loss rejects it."""
    if not pages:
        raise OfficialRankingFetchError("empty ATP PDF")
    rows, dates = [], set()
    for number, text in enumerate(pages, 1):
        footers = re.findall(r"Page\s+(\d+)\s+of\s+(\d+)", text)
        if footers != [(str(number), str(len(pages)))]:
            raise OfficialRankingFetchError("ATP PDF page coverage/order is incomplete")
        if not re.search(r"Rankings/\s*Numerical Order/\s*Complete/\s*Singles", text):
            raise OfficialRankingFetchError("ATP PDF is not the complete singles numerical publication")
        headers = re.findall(r"Rankings Date:\s*([A-Za-z]+\s+\d{1,2},\s*\d{4})", text)
        if len(headers) != 1:
            raise OfficialRankingFetchError("ATP PDF must expose one ranking date on every page")
        effective = _parse_display_date(headers[0], "%b %d, %Y")
        if effective is None:
            raise OfficialRankingFetchError("invalid ATP PDF ranking date")
        dates.add(effective)
        if len(dates) != 1:
            raise OfficialRankingFetchError("ATP PDF contains conflicting ranking dates")
        page_rows = 0
        for line in text.splitlines():
            if not re.match(r"^\s*\d+(?:T)?\s+", line):
                continue
            match = re.fullmatch(r"\s*(\d+)(T)?\s+(.+?)\s+((?:[0-9,]+\s+){6}[0-9,]+)\s*", line)
            if not match:
                raise OfficialRankingFetchError(f"Unparsed ATP ranking row on page {number}: {line}")
            rank = int(match.group(1))
            label = match.group(3).strip()
            country = re.search(r"\s+\(([A-Z]{3})\)$", label)
            name = label[:country.start()].strip() if country else label
            if name.count(",") != 1:
                raise OfficialRankingFetchError("ATP PDF player name is not surname-first")
            values = [int(v.replace(",", "")) for v in match.group(4).split()]
            if values[0] != sum(values[1:4]):
                raise OfficialRankingFetchError("ATP PDF points columns are inconsistent")
            player = _normalise_wta_name(name)
            rows.append({"player_id": f"atp_pdf:{_name_key(player)}", "name": player, "player_name": player,
                         "tour": "ATP", "ranking_date": effective, "rank": rank, "ranking_points": values[0],
                         "raw": {"source": "atp_official_numeric_pdf", "source_ranking_date": effective,
                                 "source_url": OfficialRankingProvider.ATP_NUMERIC_PDF_URL,
                                 "nationality": country.group(1) if country else None,
                                 "tied": bool(match.group(2)), "page": number, "line": line}})
            page_rows += 1
        if not page_rows:
            raise OfficialRankingFetchError(f"ATP PDF page {number} has no ranking rows")
    if len(rows) > MAX_RANKING_ROWS:
        raise OfficialRankingFetchError("ATP PDF exceeds the row safety limit; refusing truncation")
    previous = None
    for ordinal, row in enumerate(rows, 1):
        if row["rank"] != previous and row["rank"] != ordinal:
            raise OfficialRankingFetchError("ATP PDF rank sequence indicates missing/reordered rows")
        if previous is not None and row["rank"] < previous:
            raise OfficialRankingFetchError("ATP PDF rank order is invalid")
        previous = row["rank"]
    requested = normalise_ranking_date(requested_date)
    if requested and rows[0]["ranking_date"] > requested:
        raise OfficialRankingFetchError("ATP PDF source ranking date is after requested date")
    return rows


def _parse_wta_numeric_pdf_text(text: str, requested_date: str | None = None) -> list[dict]:
    ranking_date = _extract_ranking_date(text)
    if not ranking_date:
        raise OfficialRankingFetchError("WTA official rankings PDF did not expose an As of date")
    if _normalise_date(requested_date) and ranking_date > _normalise_date(requested_date):
        raise OfficialRankingFetchError(
            f"WTA official rankings date {ranking_date} is after requested date {requested_date}"
        )

    rows: list[dict] = []
    for line in text.splitlines():
        row = _parse_wta_numeric_line(line, ranking_date)
        if row:
            rows.append(row)
        if len(rows) >= MAX_RANKING_ROWS:
            logger.warning(
                "ranking parse hit the %d-row guard; the feed is deeper than "
                "expected and is being truncated.", MAX_RANKING_ROWS)
            break
    return rows


def _parse_atp_uts_rankings(payload: dict, requested_date: str | None = None, *, source_date=None) -> list[dict]:
    ranking_date = normalise_ranking_date(source_date)
    if ranking_date is None:
        raise OfficialRankingFetchError("ATP UTS rankings require an independently observed source date")
    requested = normalise_ranking_date(requested_date)
    if requested and ranking_date > requested:
        raise OfficialRankingFetchError("ATP UTS source ranking date is after requested date")
    rows: list[dict] = []
    for row in payload.get("rows") or []:
        rank = _int_or_none(row.get("rank"))
        points = _int_or_none(row.get("points"))
        name = _strip_html(str(row.get("name") or "")).strip()
        if not rank or not name:
            continue
        external_id = row.get("playerId") or _name_key(name)
        country = row.get("country") if isinstance(row.get("country"), dict) else {}
        rows.append(
            {
                "player_id": f"uts:{external_id}",
                "name": name,
                "player_name": name,
                "tour": "ATP",
                "ranking_date": ranking_date,
                "rank": rank,
                "ranking_points": points,
                "raw": {
                    "source": "ultimate_tennis_statistics",
                    "source_ranking_date": ranking_date,
                    "player_id": row.get("playerId"),
                    "country": country.get("id") or country.get("name"),
                },
            }
        )
        if len(rows) >= MAX_RANKING_ROWS:
            logger.warning(
                "ranking parse hit the %d-row guard; the feed is deeper than "
                "expected and is being truncated.", MAX_RANKING_ROWS)
            break
    return rows


def _parse_wta_api_rankings(payload: list | dict, requested_date: str | None = None) -> list[dict]:
    ranking_rows = payload if isinstance(payload, list) else payload.get("rows") or payload.get("items") or []
    requested = _normalise_date(requested_date)
    rows: list[dict] = []
    for row in ranking_rows:
        if not isinstance(row, dict):
            continue
        player = row.get("player") if isinstance(row.get("player"), dict) else {}
        player_name = player.get("fullName") or " ".join(
            part for part in [player.get("firstName"), player.get("lastName")] if part
        )
        player_name = _strip_html(str(player_name or "")).strip()
        rank = _int_or_none(row.get("ranking"))
        points = _int_or_none(row.get("points"))
        if not rank or not player_name:
            continue
        ranking_date = _normalise_ranked_at(row.get("rankedAt"))
        if not ranking_date:
            raise OfficialRankingFetchError("WTA ranked player is missing a valid rankedAt source date")
        if requested and ranking_date > requested:
            raise OfficialRankingFetchError(
                f"WTA official rankings date {ranking_date} is after requested date {requested_date}"
            )
        external_id = player.get("id") or _name_key(player_name)
        rows.append(
            {
                "player_id": f"wta:{external_id}",
                "name": player_name,
                "player_name": player_name,
                "tour": "WTA",
                "ranking_date": ranking_date,
                "rank": rank,
                "ranking_points": points,
                "raw": {
                    "source": "wta_ranked_players_api",
                    "source_ranking_date": ranking_date,
                    "ranked_at": row.get("rankedAt"),
                    "player_id": player.get("id"),
                    "country": player.get("countryCode"),
                    "tournaments_played": _int_or_none(row.get("tournamentsPlayed")),
                    "movement": _int_or_none(row.get("movement")),
                },
            }
        )
        if len(rows) >= MAX_RANKING_ROWS:
            logger.warning(
                "ranking parse hit the %d-row guard; the feed is deeper than "
                "expected and is being truncated.", MAX_RANKING_ROWS)
            break
    return rows


def _parse_wta_rankings_html(text: str, requested_date: str | None = None) -> list[dict]:
    ranking_date = _extract_wta_html_date(text)
    if not ranking_date:
        raise OfficialRankingFetchError("WTA HTML did not expose a source ranking date")
    requested = _normalise_date(requested_date)
    if requested and ranking_date > requested:
        raise OfficialRankingFetchError(
            f"WTA official rankings date {ranking_date} is after requested date {requested_date}"
        )

    rows: list[dict] = []
    for match in re.finditer(r'<tr\b[^>]*class=["\'][^"\']*player-row[^"\']*["\'][^>]*>.*?</tr>', text, re.I | re.S):
        row_html = match.group(0)
        name = _html_attr(row_html, "data-player-name")
        player_id = _html_attr(row_html, "data-player-id")
        rank_match = re.search(
            r'<span\b[^>]*class=["\'][^"\']*player-row__rank[^"\']*["\'][^>]*>(.*?)</span>',
            row_html,
            re.I | re.S,
        )
        points_match = re.search(
            r'<td\b[^>]*class=["\'][^"\']*player-row__cell--points[^"\']*["\'][^>]*>(.*?)</td>',
            row_html,
            re.I | re.S,
        )
        rank = _int_or_none(_strip_html(rank_match.group(1)) if rank_match else None)
        points = _int_or_none(_strip_html(points_match.group(1)) if points_match else None)
        if not name:
            name_match = re.search(
                r'<span\b[^>]*class=["\'][^"\']*player-row__name[^"\']*["\'][^>]*>(.*?)</span>',
                row_html,
                re.I | re.S,
            )
            name = _strip_html(name_match.group(1)) if name_match else None
        if not rank or not name:
            continue
        player_name = " ".join(unescape(name).split())
        rows.append(
            {
                "player_id": f"wta:{player_id or _name_key(player_name)}",
                "name": player_name,
                "player_name": player_name,
                "tour": "WTA",
                "ranking_date": ranking_date,
                "rank": rank,
                "ranking_points": points,
                "raw": {
                    "source": "wta_rankings_html",
                    "source_ranking_date": ranking_date,
                    "player_id": player_id,
                },
            }
        )
        if len(rows) >= MAX_RANKING_ROWS:
            logger.warning(
                "ranking parse hit the %d-row guard; the feed is deeper than "
                "expected and is being truncated.", MAX_RANKING_ROWS)
            break
    return rows


def _parse_wta_numeric_line(line: str, ranking_date: str) -> dict | None:
    match = re.match(
        r"^\s*(?P<rank>\d{1,4})\s+\([^)]+\)\s+"
        r"(?P<name>.+?)\s+"
        r"(?:(?P<nationality>[A-Z]{3})\s+)?"
        r"(?P<points>[0-9,]+)\s+"
        r"(?P<tournaments>\d+)(?:\s|$)",
        line,
    )
    if not match:
        return None
    rank = _int_or_none(match.group("rank"))
    points = _int_or_none(match.group("points"))
    if rank is None or points is None:
        return None
    raw_name = match.group("name").strip()
    player_name = _normalise_wta_name(raw_name)
    return {
        "player_id": f"wta:{_name_key(player_name)}",
        "name": player_name,
        "player_name": player_name,
        "tour": "WTA",
        "ranking_date": ranking_date,
        "rank": rank,
        "ranking_points": points,
        "raw": {
            "source": "wta_numeric_pdf",
            "source_ranking_date": ranking_date,
            "line": line,
            "nationality": match.group("nationality"),
            "tournaments": _int_or_none(match.group("tournaments")),
        },
    }


def _extract_ranking_date(text: str) -> str | None:
    match = re.search(r"As of:\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})", text)
    if not match:
        match = re.search(r"For:\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})", text)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%d %B %Y").date().isoformat()
    except ValueError:
        return None


def _extract_wta_html_date(text: str) -> str | None:
    for pattern in (
        r"Rankings\s+as\s+of\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})",
        r"Updated\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})",
        r"As\s+of\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})",
    ):
        match = re.search(pattern, text, re.I)
        if not match:
            continue
        parsed = _parse_display_date(match.group(1), "%B %d, %Y")
        if parsed:
            return parsed
    return None


def _normalise_wta_name(value: str) -> str:
    if "," in value:
        last, first = [part.strip() for part in value.split(",", 1)]
        value = f"{first} {last}"
    return " ".join(part.capitalize() for part in value.split())


def _name_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _html_attr(fragment: str, attr: str) -> str | None:
    match = re.search(rf"\b{re.escape(attr)}\s*=\s*['\"]([^'\"]+)['\"]", fragment, re.I)
    if not match:
        return None
    return unescape(match.group(1)).strip()


def _strip_html(value: str) -> str:
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", value)).split())


def _parse_display_date(value: str, fmt: str) -> str | None:
    try:
        return datetime.strptime(value.strip(), fmt).date().isoformat()
    except ValueError:
        return None


def _normalise_ranked_at(value) -> str | None:
    if not value:
        return None
    value = str(value).strip()
    if "T" in value:
        value = value.split("T", 1)[0]
    return normalise_ranking_date(value)


def _normalise_date(value: str | None) -> str | None:
    if not value:
        return None
    value = str(value).strip()
    if len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:8]}"
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        return value


def _int_or_none(value) -> int | None:
    if value in {None, ""}:
        return None
    try:
        return int(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None

"""Read ranking dates and original source identity without rewriting history."""
from __future__ import annotations

from datetime import date
from functools import lru_cache
import base64
import hashlib
import json

from tennis_wc.database.payload_archive import PayloadArchiveError, read_payload
from tennis_wc.config import get_settings
from tennis_wc.ranking_dates import normalise_ranking_date, uts_source_date_issue


# These old normalized feeds are the confirmed requested-date fabrication path.
# Other historical ranking providers retain their existing interpretation.
DATELESS_FEED_PROVIDERS = {"composite", "official_rankings", "ultimate_tennis_statistics"}
PUBLISHED_RANKING_SOURCES = {"atp_official_numeric_pdf", "wta_ranked_players_api", "wta_numeric_pdf",
                             "wta_rankings_html", "sackmann_ranking", "ultimate_tennis_statistics"}
MAX_RANKING_RECEIPT_BYTES = 4 * 1024 * 1024
MAX_SOURCE_CAPTURE_BYTES = 16 * 1024 * 1024
ATP_PDF_URL = "https://www.protennislive.com/posting/ramr/singles_entry_numerical.pdf"
DATE_SQL = """CASE WHEN length(ranking_date)=8 AND ranking_date NOT GLOB '*[^0-9]*'
    THEN substr(ranking_date,1,4)||'-'||substr(ranking_date,5,2)||'-'||substr(ranking_date,7,2)
    ELSE ranking_date END"""


@lru_cache(maxsize=8)
def _uts_source_date(body):
    """Bounded by bytes and entries; never retain SQLite connections in a cache."""
    try:
        payload = json.loads(body)
    except (ValueError, TypeError):
        return "ranking_source_receipt_invalid", None
    if not isinstance(payload, list):
        return None, None
    dates = set()
    found = False
    for item in payload:
        if not isinstance(item, dict):
            continue
        raw = item.get("raw") or {}
        if not isinstance(raw, dict):
            raw = {}
        if raw.get("source") != "ultimate_tennis_statistics" and not str(item.get("player_id", "")).startswith("uts:"):
            continue
        found = True
        issue = uts_source_date_issue(item)
        if issue:
            return issue, None
        effective = normalise_ranking_date(raw.get("source_ranking_date"))
        dates.add(effective)
    if found and len(dates) != 1:
        return "ranking_source_date_inconsistent", None
    return None, next(iter(dates)) if dates else None


@lru_cache(maxsize=8)
def _published_receipt(body, source):
    try:
        rows = json.loads(body)
        if not isinstance(rows, list) or not rows:
            raise ValueError("empty receipt")
        dates, captures = set(), set()
        for row in rows:
            raw = row["raw"]
            effective = normalise_ranking_date(row["ranking_date"])
            if raw.get("source") != source or not effective or normalise_ranking_date(raw.get("source_ranking_date")) != effective:
                raise ValueError("source or date mismatch")
            dates.add(effective)
            if source == "atp_official_numeric_pdf":
                if raw.get("source_url") != ATP_PDF_URL:
                    raise ValueError("unexpected PDF source")
                captures.add((int(raw["source_capture_raw_id"]), raw["source_pdf_sha256"]))
        if len(dates) != 1 or (source == "atp_official_numeric_pdf" and len(captures) != 1):
            raise ValueError("inconsistent receipt")
        return None, next(iter(dates)), next(iter(captures)) if captures else None
    except (ValueError, TypeError, KeyError):
        return "ranking_source_receipt_invalid", None, None


@lru_cache(maxsize=8)
def _pdf_capture_valid(body, expected_sha):
    try:
        captures = json.loads(body)["captures"]
        for capture in captures:
            if capture.get("url") == ATP_PDF_URL and capture.get("sha256") == expected_sha:
                data = base64.b64decode(capture["content_base64"], validate=True)
                return hashlib.sha256(data).hexdigest() == expected_sha
    except (ValueError, TypeError, KeyError):
        pass
    return False


class RankingReader:
    def __init__(self, conn):
        self.conn = conn
        self.receipts = {}

    def receipt_issue(self, raw_id, source_provider, effective=None):
        if source_provider not in DATELESS_FEED_PROVIDERS and source_provider not in PUBLISHED_RANKING_SOURCES:
            return None
        key = (raw_id, source_provider)
        if key not in self.receipts:
            size = self.conn.execute("SELECT length(CAST(response_json AS BLOB)) FROM raw_api_responses WHERE id=?", (raw_id,)).fetchone()
            if size is None:
                self.receipts[key] = ("ranking_source_receipt_missing", None)
            elif size[0] is None or size[0] > MAX_RANKING_RECEIPT_BYTES:
                self.receipts[key] = ("ranking_source_receipt_too_large", None)
            else:
                row = self.conn.execute("SELECT response_json FROM raw_api_responses WHERE id=?", (raw_id,)).fetchone()
                try:
                    body = read_payload(self.conn, "raw_response", raw_id, row[0], max_bytes=MAX_RANKING_RECEIPT_BYTES)
                    if len(body.encode("utf-8")) > MAX_RANKING_RECEIPT_BYTES:
                        self.receipts[key] = ("ranking_source_receipt_too_large", None)
                    else:
                        if source_provider in PUBLISHED_RANKING_SOURCES and source_provider != "ultimate_tennis_statistics":
                            issue, observed, capture = _published_receipt(body, source_provider)
                            if not issue and capture:
                                capture_id, sha = capture
                                size = self.conn.execute("SELECT length(CAST(response_json AS BLOB)) FROM raw_api_responses WHERE id=?", (capture_id,)).fetchone()
                                if not size or size[0] is None or size[0] > MAX_SOURCE_CAPTURE_BYTES:
                                    issue = "ranking_source_capture_missing_or_too_large"
                                else:
                                    record = self.conn.execute("SELECT response_json FROM raw_api_responses WHERE id=?", (capture_id,)).fetchone()
                                    capture_body = read_payload(self.conn, "raw_response", capture_id, record[0], max_bytes=MAX_SOURCE_CAPTURE_BYTES)
                                    if len(capture_body.encode("utf-8")) > MAX_SOURCE_CAPTURE_BYTES or not _pdf_capture_valid(capture_body, sha):
                                        issue = "ranking_source_capture_invalid"
                            self.receipts[key] = (issue, observed)
                        else:
                            self.receipts[key] = _uts_source_date(body)
                except PayloadArchiveError:
                    self.receipts[key] = ("ranking_source_receipt_invalid", None)
        issue, observed = self.receipts[key]
        if issue:
            return issue
        if observed is not None and effective is not None and effective != observed:
            return "ranking_source_date_mismatch"
        return None

    def rows(self, *, player_id=None, tour=None, cutoff=None, inclusive=False):
        where, params = ["rank IS NOT NULL"], []
        if player_id is not None:
            where.append("player_id=?"); params.append(player_id)
        if tour is not None:
            where.append("tour=?"); params.append(tour.upper())
        if cutoff is not None:
            cutoff = normalise_ranking_date(cutoff)
            if cutoff is None:
                raise ValueError("invalid ranking cutoff")
            where.append(f"({DATE_SQL}) {'<=' if inclusive else '<'} ?"); params.append(cutoff)
        return self.conn.execute(
            f"SELECT * FROM rankings_history WHERE {' AND '.join(where)} ORDER BY ({DATE_SQL}) DESC,id DESC", params)

    def select(self, player_id, cutoff, *, inclusive=False):
        if player_id is None:
            return {"rank": None, "warnings": ["missing_ranking_player_id"]}
        warnings = set()
        fallback = None
        max_age = get_settings().data_max_staleness_hours_rankings
        for row in self.rows(player_id=player_id, cutoff=cutoff, inclusive=inclusive):
            effective = normalise_ranking_date(row["ranking_date"])
            if effective is None:
                warnings.add("ranking_date_invalid"); continue
            age = (date.fromisoformat(normalise_ranking_date(cutoff))-date.fromisoformat(effective)).days*24
            if fallback is not None and age > max_age:
                break
            issue = self.receipt_issue(row["raw_response_id"], row["source_provider"], effective)
            if issue:
                warnings.add(issue); continue
            info = {**dict(row), "ranking_date": effective}
            if fallback is None:
                fallback = info
            # A tournament entry-rank reference can be dated after the weekly
            # publication. It must not override a fresh actual ranking list.
            if row["source_provider"] in PUBLISHED_RANKING_SOURCES and age <= max_age:
                return {**info, "warnings": sorted(warnings)}
            if age > max_age:
                break
        if fallback is not None:
            return {**fallback, "warnings": sorted(warnings)}
        return {"rank": None, "warnings": sorted(warnings)}

    def current_fallback_allowed(self, player_id, player):
        # Any dated history, including a rejected or future-only row, must not
        # be bypassed by the mutable copy of that same number on players.
        if self.conn.execute("SELECT 1 FROM rankings_history WHERE player_id=? LIMIT 1", (player_id,)).fetchone():
            return False
        return self.player_issue(player) is None

    def player_issue(self, player):
        meta = self.conn.execute("SELECT provider_name FROM raw_api_responses WHERE id=?",
                                 (player["raw_response_id"],)).fetchone()
        provider = meta[0] if meta else player["source_provider"]
        return self.receipt_issue(player["raw_response_id"], provider)

    def unverified_seed(self, player, seed_for_rank):
        if player["overall_elo"] is None or not self.player_issue(player):
            return False
        source_ranks = [r[0] for r in self.conn.execute(
            "SELECT rank FROM rankings_history WHERE player_id=? AND raw_response_id=?",
            (player["id"], player["raw_response_id"]))]
        source_ranks.append(player["current_rank"])
        seeds = [seed_for_rank(rank) for rank in source_ranks]
        return any(seed is not None and abs(float(player["overall_elo"])-seed) < 1e-9 for seed in seeds)


def cached_rankings(conn, tour, cutoff, *, max_age_hours, today: date):
    reader = RankingReader(conn)
    normalized = normalise_ranking_date(cutoff) if cutoff is not None else today.isoformat()
    if normalized is None:
        raise ValueError("invalid ranking cutoff")
    reference = min(normalized, today.isoformat())
    selected = {}
    for row in reader.rows(tour=tour, cutoff=reference, inclusive=True):
        pid = row["player_id"]
        effective = normalise_ranking_date(row["ranking_date"])
        if effective is None or (date.fromisoformat(reference)-date.fromisoformat(effective)).days*24 > max_age_hours:
            continue
        if reader.receipt_issue(row["raw_response_id"], row["source_provider"], effective):
            continue
        if pid in selected:
            if (selected[pid]["source_provider"] in PUBLISHED_RANKING_SOURCES
                    or row["source_provider"] not in PUBLISHED_RANKING_SOURCES):
                continue
        selected[pid] = {**dict(row), "ranking_date": effective}
    return list(selected.values())

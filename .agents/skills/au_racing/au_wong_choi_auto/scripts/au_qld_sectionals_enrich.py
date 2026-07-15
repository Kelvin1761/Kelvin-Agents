#!/usr/bin/env python3
"""Download Racing Queensland's free official race-day sectional CSVs.

This is intentionally a separate shadow-data collector from the trial/jump-out
collector.  Racing Queensland publishes these post-race files on its public
sectionals page.  The files contain genuine race sectional / position-map
evidence, whereas a trial's L600 is a heat-level readiness signal only.

The collector discovers links from the official index rather than inventing a
filename.  That makes the date/track routing auditable and avoids silently
using the wrong file when Racing Queensland changes its track naming.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import json
import re
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urljoin, urlparse

from au_official_free_data import (  # shared source-routing policy
    OUT_DIR,
    QLD_VENUES,
    USER_AGENT,
    VENUE_ALIASES,
    _fetch_text,
    normalise_venue,
)


INDEX_URL = "https://www.racingqueensland.com.au/industry/thoroughbred/thoroughbred-sectionals"
RAW_DIR = OUT_DIR / "qld_sectionals"
MANIFEST_PATH = OUT_DIR / "qld_race_sectionals.jsonl"
ERRORS_PATH = OUT_DIR / "qld_race_sectional_errors.jsonl"
TERMINAL_ERRORS = {"not_qld", "sectional_not_listed"}


def _meeting_identity(directory: Path) -> tuple[str, str] | None:
    match = re.match(r"(\d{4}-\d{2}-\d{2})\s+(.+?)\s+Race\b", directory.name, flags=re.I)
    if not match:
        return None
    return match.group(1), match.group(2).strip()


def _safe_key(day: str, venue: str) -> str:
    return hashlib.sha1(f"{day}|{normalise_venue(venue)}".encode("utf-8")).hexdigest()[:20]


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    output = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            output.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return output


def _append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _sectional_links(index_html: str) -> list[tuple[str, str, str]]:
    """Return ``(yyyymmdd, track-token, absolute-csv-url)`` from the index."""
    links: list[tuple[str, str, str]] = []
    for href in re.findall(r'''href\s*=\s*["']([^"']+)["']''', index_html, flags=re.I):
        decoded = html.unescape(unquote(href))
        match = re.search(r"/Sectional/(\d{8})_([^/?]+?)_T\.csv", decoded, flags=re.I)
        if not match:
            continue
        absolute = urljoin(INDEX_URL, decoded)
        parsed = urlparse(absolute)
        if parsed.netloc.lower() != "www.racingqueensland.com.au":
            continue
        links.append((match.group(1), match.group(2), absolute))
    return list(dict.fromkeys(links))


def _track_matches(venue: str, token: str) -> bool:
    wanted = normalise_venue(venue)
    expected = normalise_venue(VENUE_ALIASES.get(wanted, venue))
    actual = normalise_venue(token.replace("_", " "))
    if wanted == actual or expected == actual:
        return True
    # RQ's file key commonly omits the commercial prefix and sometimes 'Park'.
    compact_wanted = re.sub(r"\b(aquis|park|racecourse|inner|poly)\b", "", expected)
    compact_actual = re.sub(r"\b(aquis|park|racecourse|inner|poly)\b", "", actual)
    compact_wanted = re.sub(r"\s+", " ", compact_wanted).strip()
    compact_actual = re.sub(r"\s+", " ", compact_actual).strip()
    return compact_wanted == compact_actual


def _csv_summary(raw: str) -> dict[str, Any]:
    """Return a schema summary; preserve raw CSV for future feature work."""
    rows = list(csv.reader(io.StringIO(raw)))
    nonempty = [row for row in rows if any(cell.strip() for cell in row)]
    return {
        "line_count": len(rows),
        "nonempty_line_count": len(nonempty),
        "first_rows": nonempty[:3],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Download free official Racing Queensland race sectional CSVs.")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--meeting-dir", type=Path)
    target.add_argument("--archive", action="store_true")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    directories = [args.meeting_dir] if args.meeting_dir else sorted(OUT_DIR.parent.glob("*/"))
    candidates = []
    for directory in directories:
        identity = _meeting_identity(directory)
        if not identity:
            continue
        day, venue = identity
        if normalise_venue(venue) in QLD_VENUES:
            candidates.append((day, venue, directory.name))
    candidates = sorted(set(candidates), reverse=True)
    print(f"QLD meeting candidates: {len(candidates)}")
    if args.dry_run:
        for day, venue, _ in candidates[:args.limit]:
            print(f"{day} {venue} -> Racing Queensland sectional index")
        return 0

    completed = {row.get("record_id") for row in _load_jsonl(MANIFEST_PATH)}
    terminal = {
        row.get("record_id") for row in _load_jsonl(ERRORS_PATH)
        if row.get("error") in TERMINAL_ERRORS
    }
    pending = []
    for day, venue, meeting in candidates:
        record_id = _safe_key(day, venue)
        if record_id not in completed and record_id not in terminal:
            pending.append((day, venue, meeting, record_id))
    pending = pending[:max(0, args.limit)]
    print(f"new QLD race meetings selected: {len(pending)}")
    if not pending:
        return 0

    index = _fetch_text(INDEX_URL)
    links = _sectional_links(index)
    print(f"official index CSV links discovered: {len(links)}")
    records: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for position, (day, venue, meeting, record_id) in enumerate(pending, 1):
        wanted_day = date.fromisoformat(day).strftime("%Y%m%d")
        matches = [link for link in links if link[0] == wanted_day and _track_matches(venue, link[1])]
        if len(matches) != 1:
            errors.append({"record_id": record_id, "meeting": meeting, "date": day, "venue": venue,
                           "error": "sectional_not_listed" if not matches else "ambiguous_sectional_file",
                           "matches": len(matches), "source_url": INDEX_URL})
            print(f"[{position}/{len(pending)}] WARN {day} {venue}: CSV {'not listed' if not matches else 'ambiguous'}")
            continue
        _, token, url = matches[0]
        try:
            raw = _fetch_text(url)
            filename = f"{wanted_day}_{re.sub(r'[^A-Za-z0-9_-]+', '_', token)}_T.csv"
            output = RAW_DIR / filename
            output.write_text(raw, encoding="utf-8")
            records.append({
                "record_id": record_id,
                "record_type": "official_qld_race_sectionals_shadow",
                "authority": "racing_queensland",
                "meeting": meeting,
                "date": day,
                "venue": venue,
                "source_url": url,
                "local_file": str(output.relative_to(OUT_DIR)),
                "csv": _csv_summary(raw),
                "model_rule": "Raw official race sectionals; derive runner-level features only in a leakage-safe, walk-forward research job.",
            })
            print(f"[{position}/{len(pending)}] OK {day} {venue} -> {filename}")
        except Exception as exc:  # retain failure for a resumable, auditable run
            errors.append({"record_id": record_id, "meeting": meeting, "date": day, "venue": venue,
                           "error": f"{type(exc).__name__}: {exc}", "source_url": url})
            print(f"[{position}/{len(pending)}] WARN {day} {venue}: {type(exc).__name__}")
        if position < len(pending):
            time.sleep(max(0.0, args.delay))
    _append_jsonl(MANIFEST_PATH, records)
    _append_jsonl(ERRORS_PATH, errors)
    print(f"written: {len(records)} CSV manifests | {len(errors)} errors | {RAW_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Extract free, official AU trial / jump-out evidence into a shadow dataset.

This deliberately does not use Racenet.  It reads the trial pointers already
present in ``Race_*_Logic.json`` / ``Facts.md`` and verifies them against the
relevant public racing authority result page:

* NSW / ACT: Racing NSW FreeFields results;
* QLD: Racing Queensland is the authority route.  Its trial-result links are
  published through Racing Australia FreeFields, while QLD's richer race-day
  sectional CSVs remain a separate source (see ``source_manifest.json``);
* VIC / SA / WA / TAS: Racing Australia FreeFields official results.

Trial and jump-out values are written as *shadow* records only.  They must pass
walk-forward testing before being used by the production ranker.

Examples
--------
    # Inspect where a meeting will route, without network access.
    python3 au_official_free_data.py --meeting-dir ".../2026-07-08 Sandown Lakeside Race 1-8" --dry-run

    # Collect a polite first archive batch; re-running is idempotent.
    python3 au_official_free_data.py --archive --limit 25 --delay 0.8
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[4]
sys.path.insert(0, str(PROJECT_ROOT))
from wongchoi_paths import AU_RACING  # noqa: E402


OUT_DIR = AU_RACING / "Official_Free_Data"
RECORDS_PATH = OUT_DIR / "official_trial_events.jsonl"
ERRORS_PATH = OUT_DIR / "official_trial_errors.jsonl"
MANIFEST_PATH = OUT_DIR / "source_manifest.json"

# These failures are determined from an authority response (rather than a
# transient network condition).  Do not request them on every resume of a
# historical backfill; the audit log still retains the reason and source URL.
TERMINAL_ERRORS = {"unknown_venue_route", "source_no_longer_available", "heat_not_found"}

USER_AGENT = "Antigravity-WongChoi/1.0 (official-free-data research; contact local operator)"


# Public result keys use the authority's state code, not the state of today's
# meeting.  The trail venue in a horse's prior form decides the route.
NSW_VENUES = {
    "albury", "armidale", "ballina", "bathurst", "beaumont", "beaumont newcastle", "canberra",
    "canberra acton", "canterbury", "canterbury park", "casino", "coffs harbour", "corowa", "cowra",
    "dubbo", "gilgandra", "goulburn", "gosford", "grafton", "gundagai", "gunnedah", "hawkesbury", "kembla grange",
    "kensington", "moruya", "muswellbrook", "newcastle", "nowra",
    "narrandera", "narromine", "orange", "port macquarie", "queanbeyan", "randwick", "royal randwick", "rosehill",
    "rosehill gardens", "sapphire coast", "scone", "tamworth", "taree", "tuncurry", "wagga", "wagga riverside", "warwick farm",
    "wellington", "wyong",
}
QLD_VENUES = {
    "aquis park gold coast", "aquis park gold coast poly", "aquis beaudesert", "beaudesert", "beau desert", "beadesert",
    "bundaberg", "cairns", "dalby", "deagon", "doomben", "eagle farm",
    "gatton", "gold coast", "gold coast poly", "ipswich", "mackay",
    "rockhampton", "sunshine coast", "sunshine coast poly", "sunshine coast inner", "sunshine coast inner track", "townsville",
    "toowoomba", "toowoomba inner track", "warwick",
}
VIC_VENUES = {
    "apiam bendigo", "ararat", "avoca", "ballarat", "ballarat synthetic", "balnarring", "benalla", "bendigo", "bet365 camperdown",
    "burrumbeet", "camperdown", "casterton", "caulfield", "caulfield heath", "colac", "coleraine", "cranbourne", "cranbourne syn", "cranbourne trn", "donald", "echuca", "flemington",
    "geelong", "great western", "hamilton", "horsham", "kerang", "kilmore", "kyneton", "ladbrokes geelong synthetic", "moe", "mornington", "murtoa", "pakenham", "penshurst", "sale", "seymour",
    "sandown hillside", "sandown lakeside", "southside cranbourne",
    "southside pakenham", "southside pakenham synthetic", "sportsbet ballarat",
    "sportsbet pakenham", "sportsbet pakenham synthetic", "sportsbet wangaratta", "st arnaud", "tab park werribee", "wangaratta", "warracknabeal", "swan hill", "terang", "traralgon", "bet365 mortlake",
    "warrnambool", "werribee", "wodonga", "bet365 colac", "bet365 park wodonga", "bet365 seymour", "bet365 stawell", "bet365 swan hill",
}
SA_VENUES = {"balaklava", "gawler", "mount gambier", "murray bdge", "murray bridge", "oakbank", "morphettville", "morphettville parks", "strathalbyn", "thomas farms rc murray bridge"}
WA_VENUES = {"ascot", "belmont", "belmont park", "lark hill", "pinjarra"}
TAS_VENUES = {"devonport", "hobart", "launceston"}

# The name shown in Facts sometimes differs from the authority key.  Keep this
# map intentionally small and auditable; unknown tracks are reported, never
# guessed as another venue.
VENUE_ALIASES = {
    "sportsbet ballarat": "Ballarat",
    "sportsbet ballarat synthetic": "Ballarat Synthetic",
    "sportsbet sandown hillside": "Sandown Hillside",
    "sportsbet wangaratta": "Wangaratta",
    "bet365 camperdown": "bet365 Camperdown",
    "bet365 mortlake": "bet365 Mortlake",
    "bet365 echuca": "Echuca",
    "bet365 hamilton": "Hamilton",
    "bet365 terang": "Terang",
    "bet365 traralgon": "Traralgon",
    "apiam bendigo": "Bendigo",
    "ladbrokes geelong synthetic": "Geelong",
    "tab park werribee": "Werribee",
    "ladbrokes geelong": "Geelong",
    "picklebet park werribee": "Werribee",
    "picklebet park wodonga": "Wodonga",
    "beaumont": "Beaumont Newcastle",
    "murray bdge": "Murray Bridge",
    "thomas farms rc murray bridge": "Murray Bridge",
    "aquis park gold coast": "Aquis Park Gold Coast",
    "gold coast": "Aquis Park Gold Coast",
    "southside cranbourne": "Southside Cranbourne",
    "southside pakenham": "Southside Pakenham",
    "southside pakenham synthetic": "Southside Pakenham",
    "rosehill": "Rosehill Gardens",
    "randwick": "Royal Randwick",
    "canterbury": "Canterbury Park",
}


@dataclass(frozen=True)
class SourceRoute:
    authority: str
    result_host: str
    state: str
    venue_key: str
    supports_trial_l600: bool
    supports_race_sectionals: bool


def normalise_venue(value: str) -> str:
    text = re.sub(r"\*\*\(TRIAL\)\*\*", "", str(value or ""), flags=re.I)
    text = re.sub(r"\s+R\d+\b.*$", "", text, flags=re.I)
    text = text.replace("-", " ").replace("@", " ")
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text


def route_for_venue(venue: str) -> SourceRoute:
    key = normalise_venue(venue)
    venue_key = VENUE_ALIASES.get(key, str(venue).strip())
    # Classify on the reviewed canonical alias, but retain the authority's
    # display key for the public URL.  Commercial track prefixes change often.
    jurisdiction_key = normalise_venue(venue_key)
    if jurisdiction_key in NSW_VENUES:
        return SourceRoute("racing_nsw", "racing_nsw", "NSW", venue_key, True, False)
    if jurisdiction_key in QLD_VENUES:
        # Racing Queensland is the owner route.  Trial-result data is exposed
        # through the Racing Australia public Results page linked by RQ; QLD's
        # own downloadable race sectionals are handled separately below.
        return SourceRoute("racing_queensland", "racing_australia", "QLD", venue_key, True, True)
    if jurisdiction_key in VIC_VENUES:
        return SourceRoute("racing_victoria", "racing_australia", "VIC", venue_key, False, False)
    if jurisdiction_key in SA_VENUES:
        return SourceRoute("racing_sa", "racing_australia", "SA", venue_key, False, False)
    if jurisdiction_key in WA_VENUES:
        return SourceRoute("racing_wa", "racing_australia", "WA", venue_key, False, False)
    if jurisdiction_key in TAS_VENUES:
        return SourceRoute("tasracing", "racing_australia", "TAS", venue_key, False, True)
    # Never guess a state from a similarly named venue.  A record stays in the
    # audit log for a human to add a reviewed alias / route, but no request is
    # made to a potentially wrong authority.
    return SourceRoute("unresolved", "none", "", venue_key, False, False)


def _date_key(day: str) -> str:
    parsed = date.fromisoformat(day)
    return f"{parsed.year}{parsed.strftime('%b')}{parsed.day:02d}"


def public_results_url(day: str, route: SourceRoute) -> str | None:
    if not route.state:
        return None
    # Victorian club sessions recorded as ``試閘`` in legacy Facts are published
    # by Racing Australia under the official ``JumpOut`` meeting type.  NSW and
    # QLD use the literal ``Trial`` type.  A wrong suffix returns a valid-looking
    # empty Results page, so this is part of routing rather than a parser detail.
    event_type = "JumpOut" if route.authority == "racing_victoria" else "Trial"
    key = f"{_date_key(day)},{route.state},{route.venue_key},{event_type}"
    host = "https://mdata.racingnsw.com.au" if route.result_host == "racing_nsw" else "https://www.racingaustralia.horse"
    return f"{host}/FreeFields/Results.aspx?Key={key.replace(' ', '+')}"


def _fetch_text(url: str, timeout: int = 25) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
    with urlopen(request, timeout=timeout) as response:  # nosec B310: fixed public authority URLs
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def _plain_text(page: str) -> str:
    text = re.sub(r"<(?:script|style)[^>]*>.*?</(?:script|style)>", " ", page, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _plain_fragment(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value))).strip()


def _normalise_horse_name(value: str) -> str:
    """Conservative name key for joining one runner to its official heat row."""
    text = re.sub(r"\([^)]*\)", " ", str(value or "").upper())
    return re.sub(r"[^A-Z0-9]+", "", text)


def parse_trial_heat(page: str, heat: int) -> dict[str, Any] | None:
    """Read the heat-level, official timing line from FreeFields HTML.

    A trial's L600 belongs to the heat, not an individual runner.  Storing it
    as an event field prevents the model from falsely treating it as an
    individual sectional.
    """
    text = _plain_text(page)
    if "Results for this meeting are not currently available" in text:
        return {"heat": heat, "availability": "source_no_longer_available"}
    starts = list(re.finditer(r"\bRace\s+(\d+)\s*-", text, flags=re.I))
    for idx, match in enumerate(starts):
        if int(match.group(1)) != heat:
            continue
        block = text[match.start(): starts[idx + 1].start() if idx + 1 < len(starts) else len(text)]
        distance = re.search(r"\((\d{3,4})\s+METRES\)", block, flags=re.I)
        timing = re.search(
            r"Time:\s*([0-9:.]+)(?:\s+Last\s+600m:\s*([0-9:.]+))?\s+Timing\s+Method:\s*([A-Za-z]+)",
            block,
            flags=re.I,
        )
        if not timing:
            return {"heat": heat, "distance_m": int(distance.group(1)) if distance else None,
                    "time": None, "last_600": None, "timing_method": None}
        return {
            "heat": heat,
            "distance_m": int(distance.group(1)) if distance else None,
            "time": timing.group(1),
            "last_600": timing.group(2),
            "timing_method": timing.group(3).title(),
        }
    return None


def parse_trial_runners(page: str, heat: int) -> list[dict[str, str]]:
    """Read runner-level fields (including trial jockey) from a FreeFields heat.

    FreeFields publishes a separate race anchor/table for every trial or
    jump-out heat.  Parsing cells by their CSS class is intentional: the
    generic visual column sequence varies slightly between state authorities.
    """
    anchor = re.compile(
        rf'<a\b[^>]*\bname=["\']Race{heat}["\'][^>]*>.*?(?=<!--\s*start of races\s*-->\s*<a\b[^>]*\bname=["\']Race\d+["\']|<a\b[^>]*\bname=["\']Race{heat + 1}["\']|\Z)',
        flags=re.I | re.S,
    )
    match = anchor.search(page)
    if not match:
        return []
    rows = []
    for row_html in re.findall(r"<tr\b[^>]*>(.*?)</tr>", match.group(0), flags=re.I | re.S):
        cells = [
            {
                "classes": (attrs_match.group(1) if attrs_match else "").lower(),
                "text": _plain_fragment(body),
            }
            for attrs, body in re.findall(r"<td\b([^>]*)>(.*?)</td>", row_html, flags=re.I | re.S)
            for attrs_match in [re.search(r"\bclass=[\"']([^\"']+)[\"']", attrs, flags=re.I)]
        ]
        horse_cell_index = next((idx for idx, cell in enumerate(cells) if "horse" in cell["classes"]), None)
        if horse_cell_index is None:
            continue
        trainer_cell_index = next((idx for idx, cell in enumerate(cells) if "trainer" in cell["classes"]), None)
        jockey_cell_index = next((
            idx for idx, cell in enumerate(cells)
            if "jockey" in cell["classes"].split()
        ), None)
        # Racing NSW leaves the jockey cell unclassed, immediately after the
        # trainer cell; Racing Australia explicitly calls it ``jockey``.
        if jockey_cell_index is None and trainer_cell_index is not None and trainer_cell_index + 1 < len(cells):
            jockey_cell_index = trainer_cell_index + 1
        finish_match = re.search(r"class=[\"'][^\"']*\bFinish\b[^\"']*[\"'][^>]*>(.*?)</", row_html, flags=re.I | re.S)
        saddlecloth = cells[horse_cell_index - 1]["text"] if horse_cell_index > 0 else ""
        rows.append({
            "horse_name": cells[horse_cell_index]["text"],
            "jockey": cells[jockey_cell_index]["text"] if jockey_cell_index is not None else "",
            "trainer": cells[trainer_cell_index]["text"] if trainer_cell_index is not None else "",
            "finish": _plain_fragment(finish_match.group(1)) if finish_match else "",
            "saddlecloth_number": saddlecloth,
        })
    return rows


def match_trial_runner(page: str, heat: int, horse_name: str) -> dict[str, str] | None:
    wanted = _normalise_horse_name(horse_name)
    matches = [row for row in parse_trial_runners(page, heat) if _normalise_horse_name(row["horse_name"]) == wanted]
    return matches[0] if len(matches) == 1 else None


def _parse_trial_rows(facts_section: str, horse_name: str) -> list[dict[str, Any]]:
    records = []
    for raw in str(facts_section or "").splitlines():
        if not raw.lstrip().startswith("|") or "| 試閘 |" not in raw:
            continue
        cols = [part.strip() for part in raw.strip().strip("|").split("|")]
        if len(cols) < 8 or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", cols[2]):
            continue
        match = re.search(r"(.+?)\s+\*\*\(TRIAL\)\*\*\s+R(\d+)", cols[3], flags=re.I)
        if not match:
            continue
        distance_match = re.search(r"(\d{3,4})m", cols[4])
        records.append({
            "horse_name": horse_name,
            "trial_date": cols[2],
            "venue": match.group(1).strip(),
            "heat": int(match.group(2)),
            "distance_m": int(distance_match.group(1)) if distance_match else None,
            "facts_place": cols[7] if len(cols) > 7 else "",
        })
    return records


def _horse_name(horse: dict[str, Any]) -> str:
    data = horse.get("_data") if isinstance(horse.get("_data"), dict) else {}
    facts = str(data.get("facts_section") or "")
    match = re.search(r"^###\s+馬匹\s+#\d+\s+(.+?)\s+\(檔位", facts, flags=re.M)
    return match.group(1).strip() if match else str(horse.get("horse_name") or "").strip()


def _logic_trial_records(logic_path: Path) -> list[dict[str, Any]]:
    logic = json.loads(logic_path.read_text(encoding="utf-8"))
    output = []
    for horse_no, horse in (logic.get("horses") or {}).items():
        if not isinstance(horse, dict):
            continue
        name = _horse_name(horse)
        data = horse.get("_data") if isinstance(horse.get("_data"), dict) else {}
        for item in _parse_trial_rows(str(data.get("facts_section") or ""), name):
            item.update({"meeting": logic_path.parent.name, "race": logic_path.stem, "horse_number": str(horse_no)})
            output.append(item)
    return output


def _load_existing_records(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    records: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if value.get("record_id"):
            records[str(value["record_id"])] = value
    return records


def _load_terminal_error_ids(path: Path) -> set[str]:
    """Return source references that should not be retried automatically."""
    if not path.exists():
        return set()
    ids = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if value.get("record_id") and value.get("error") in TERMINAL_ERRORS:
            ids.add(str(value["record_id"]))
    return ids


def _record_id(item: dict[str, Any]) -> str:
    core = "|".join(str(item.get(key, "")) for key in ("horse_name", "trial_date", "venue", "heat", "meeting", "race"))
    return hashlib.sha1(core.encode("utf-8")).hexdigest()[:20]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _replace_jsonl(path: Path, rows_by_id: dict[str, dict[str, Any]]) -> None:
    """Atomically replace same-id records when a parser schema is upgraded."""
    if not rows_by_id:
        return
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        for record_id in sorted(rows_by_id):
            handle.write(json.dumps(rows_by_id[record_id], ensure_ascii=False, sort_keys=True) + "\n")
    temp_path.replace(path)


def _write_manifest() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 2,
        "purpose": "Shadow-only official free trial/jump-out and sectional evidence for AU model research.",
        "routes": {
            "NSW / ACT": "Racing NSW FreeFields: official trial total time, L600, timing method, result/replay.",
            "QLD": "Racing Queensland authority route; official trial results are published via Racing Australia FreeFields. QLD race sectionals/position maps are downloadable from Racing Queensland.",
            "VIC / SA / WA / TAS": "Racing Australia FreeFields official trial/jump-out results. TAS also publishes post-race 200m sectionals on Tasracing.",
            "Unknown venue": "No request is made.  The reference is recorded as unresolved until a reviewed venue alias and jurisdiction route are added.",
        },
        "model_rule": "Trial/jump-out heat times are readiness evidence only. They must not be treated as individual race sectionals or affect official ranking until walk-forward validation passes.",
        "record_schema": {
            "official": "Heat-level total time, L600 (when published), distance and timing method.",
            "official_runner": "Matched runner's official name, trial jockey, trainer, finish and saddlecloth number when published by the authority.",
            "runner_match_status": "matched or not_found_in_official_heat; never substitute today's jockey for a missing trial jockey.",
        },
    }
    MANIFEST_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract official free AU trial/jump-out evidence to a shadow dataset.")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--meeting-dir", type=Path, help="One meeting directory containing Race_*_Logic.json")
    target.add_argument("--archive", action="store_true", help="Scan all AU archive Logic files")
    parser.add_argument("--limit", type=int, default=25, help="Maximum new trial records to request per run (default: 25)")
    parser.add_argument("--delay", type=float, default=0.8, help="Delay between distinct authority pages in seconds")
    parser.add_argument("--dry-run", action="store_true", help="Discover and route records without network calls or writes")
    args = parser.parse_args()

    logic_files = (
        sorted(args.meeting_dir.glob("Race_*_Logic.json"))
        if args.meeting_dir else
        sorted(AU_RACING.glob("*/Race_*_Logic.json"))
    )
    candidates = [row for path in logic_files for row in _logic_trial_records(path)]
    # Same horse can appear in multiple current archive meetings.  Keep distinct
    # source trials once, then attach all local references when future joins run.
    unique: dict[tuple[str, str, str, int], dict[str, Any]] = {}
    for row in candidates:
        key = (row["horse_name"].lower(), row["trial_date"], normalise_venue(row["venue"]), row["heat"])
        unique.setdefault(key, row)

    routes = Counter(route_for_venue(row["venue"]).authority for row in unique.values())
    print(f"trial pointers: {len(candidates)} | unique horse-trials: {len(unique)}")
    print("route coverage:", ", ".join(f"{key}={value}" for key, value in sorted(routes.items())))
    if args.dry_run:
        for row in list(unique.values())[: min(args.limit, 12)]:
            route = route_for_venue(row["venue"])
            print(f"{row['trial_date']} {row['venue']} R{row['heat']} -> {route.authority} ({route.result_host})")
        return 0

    _write_manifest()
    existing = _load_existing_records(RECORDS_PATH)
    terminal_errors = _load_terminal_error_ids(ERRORS_PATH)
    pending = []
    for row in unique.values():
        row["record_id"] = _record_id(row)
        existing_row = existing.get(row["record_id"])
        # ``official_runner: null`` is a valid completed verification when the
        # authority page has no exact horse-name match.  Retry only legacy
        # schema rows that pre-date the runner-level parser.
        needs_runner_upgrade = bool(existing_row and int(existing_row.get("schema_version") or 1) < 2)
        route = route_for_venue(row["venue"])
        terminal_unresolved = row["record_id"] in terminal_errors and route.authority == "unresolved"
        if (not existing_row or needs_runner_upgrade) and not terminal_unresolved:
            pending.append(row)
    # The public FreeFields archive has a retention window.  Work newest-first
    # so an interrupted historic backfill captures usable evidence before it
    # reaches old sessions whose official results are no longer exposed.
    pending.sort(key=lambda row: (row["trial_date"], row["venue"], row["heat"], row["horse_name"]), reverse=True)
    pending = pending[: max(0, args.limit)]
    print(f"new records selected: {len(pending)}")

    page_cache: dict[str, str] = {}
    records: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for index, item in enumerate(pending, 1):
        route = route_for_venue(item["venue"])
        url = public_results_url(item["trial_date"], route)
        if not url:
            errors.append({**item, "authority": route.authority, "error": "unknown_venue_route"})
            continue
        try:
            if url not in page_cache:
                if page_cache:
                    time.sleep(max(0.0, args.delay))
                page_cache[url] = _fetch_text(url)
            timing = parse_trial_heat(page_cache[url], int(item["heat"]))
            if not timing:
                errors.append({**item, "authority": route.authority, "source_url": url, "error": "heat_not_found"})
                continue
            if timing.get("availability") == "source_no_longer_available":
                errors.append({**item, "authority": route.authority, "source_url": url,
                               "error": "source_no_longer_available"})
                continue
            runner = match_trial_runner(page_cache[url], int(item["heat"]), item["horse_name"])
            records.append({
                **item,
                "authority": route.authority,
                "result_host": route.result_host,
                "source_url": url,
                "official": timing,
                "official_runner": runner,
                "trial_jockey": runner.get("jockey", "") if runner else "",
                "trial_trainer": runner.get("trainer", "") if runner else "",
                "official_finish": runner.get("finish", "") if runner else "",
                "official_saddlecloth_number": runner.get("saddlecloth_number", "") if runner else "",
                "runner_match_status": "matched" if runner else "not_found_in_official_heat",
                "schema_version": 2,
                "record_type": "official_trial_or_jumpout_shadow",
            })
            print(f"[{index}/{len(pending)}] OK {item['trial_date']} {item['venue']} R{item['heat']} {item['horse_name']}")
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            errors.append({**item, "authority": route.authority, "source_url": url, "error": f"{type(exc).__name__}: {exc}"})
            print(f"[{index}/{len(pending)}] WARN {item['venue']} R{item['heat']}: {type(exc).__name__}")

    merged = dict(existing)
    merged.update({row["record_id"]: row for row in records})
    _replace_jsonl(RECORDS_PATH, merged)
    _write_jsonl(ERRORS_PATH, errors)
    print(f"written: {len(records)} records | {len(errors)} errors | {RECORDS_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Read-only, identity-checked supplements for the HKJC PIT result table.

This module never writes historical files and never admits a row past the
caller's as-of filter. Supplementation fixes source coverage, not model weights.
"""
from __future__ import annotations

from collections import Counter
from datetime import date
import hashlib
import json
from pathlib import Path
import re

import pandas as pd


def horse_key(value):
    # Horse names are unique per HKJC meeting; do not join by horse number alone.
    return re.sub(r"\s+|[（(][A-Z]\d{3}[)）]", "", str(value or ""))


def horse_id(value):
    match = re.search(r"[（(]([A-Z]\d{3})[)）]", str(value or ""))
    return match[1] if match else ""


def venue_key(value):
    value = str(value or "")
    if any(s in value for s in ("沙田", "ShaTin", "Sha Tin", "ST")):
        return "沙田"
    if any(s in value for s in ("跑馬地", "HappyValley", "Happy Valley", "HV")):
        return "跑馬地"
    return value


RACECARD_NAME = re.compile(r"Race\s*(\d+)\s*排位表\.md$", re.I)


def racecard_contexts(racecard_paths, read):
    """`(day, race, horse_no, name)` → metadata, from `* Race N 排位表.md`.

    A meeting that was never scored has no `Race_*_Logic.json`, so the Logic
    pass leaves its distance and class empty for every runner. 2026-07-15
    (跑馬地, 107 rows) was exactly that: results present, metadata 100% absent
    — and the results payload itself carries no distance
    (`racedate/race_no/venue/results/sectional_times/...` only). The racecard
    does carry it, is pre-race, and is already on disk.

    Same discipline as the Logic pass: the race number in the filename must
    agree with 場次, the venue must resolve, and nothing is invented — a field
    the racecard does not state stays absent.
    """
    contexts = {}
    for path in sorted(map(Path, racecard_paths)):
        match = RACECARD_NAME.search(path.name)
        if not match:
            continue
        day = path.parent.name[:10]
        date.fromisoformat(day)
        rn = int(match[1])
        text = path.read_bytes()
        read.setdefault(str(path), hashlib.sha256(text).hexdigest())
        body = text.decode("utf-8", errors="replace")

        stated = re.search(r"^場次:\s*第(\d+)場", body, re.M)
        if stated and int(stated[1]) != rn:
            raise ValueError(f"Conflicting racecard race: {path}")
        venue = venue_key((re.search(r"^地點:\s*(.+)$", body, re.M) or [None, ""])[1].strip())
        if venue not in ("沙田", "跑馬地"):
            venue = venue_key(path.parent.name)
        distance_text = re.search(r"^路程:\s*(\d{3,4})\s*米", body, re.M)
        race_class = re.search(r"^班次:\s*(.+)$", body, re.M)
        meta = dict(
            Venue=venue,
            Distance=int(distance_text[1]) if distance_text else None,
            RaceNo=rn,
            RaceClass=race_class[1].strip() if race_class else None,
        )

        # 每匹馬一段，`馬號:` 開頭。
        for block in body.split("馬號: ")[1:]:
            number = re.match(r"(\d+)", block.strip())
            name_text = re.search(r"^馬名:\s*(.+)$", block, re.M)
            if not number or not name_text:
                continue
            key = (day, rn, int(number[1]), horse_key(name_text[1]))
            if key in contexts and contexts[key] != meta:
                raise ValueError(f"Conflicting racecard metadata: {key}")
            contexts[key] = meta
    return contexts


def supplement_rows(base, result_paths, logic_paths, racecard_paths=()):
    """Merge missing results and fill metadata only on verified identities.

    Existing settled outcomes are authoritative; contradictory copies fail
    closed. Logic supplies distance only after date/race/name/number alignment.
    An absent Logic file leaves metadata absent, never fabricates a value —
    unless the meeting's racecard is on disk, which is the same pre-race fact
    from a different file (see `racecard_contexts`). Logic stays authoritative
    where both exist.
    """
    counts = Counter()
    sources = {}
    rows = {}
    def read(path):
        payload = Path(path).read_bytes()
        sources[str(path)] = hashlib.sha256(payload).hexdigest()
        return json.loads(payload)

    for row in base.to_dict("records"):
        day = str(row["Date"])
        date.fromisoformat(day)
        key = (day, horse_key(row["Horse"]))
        if not key[1] or key in rows:
            raise ValueError(f"Empty/duplicate PIT base identity: {key}")
        row["Venue"] = venue_key(row["Venue"])
        rows[key] = row

    contexts = {}
    for path in sorted(map(Path, logic_paths)):
        day = path.parent.name[:10]
        date.fromisoformat(day)
        match = re.fullmatch(r"Race_(\d+)_Logic.json", path.name)
        if not match:
            continue
        rn = int(match[1])
        logic = read(path)
        ctx = logic.get("race_analysis", {})
        if ctx.get("race_date") and ctx["race_date"] != day:
            raise ValueError(f"Conflicting Logic date: {path}")
        if ctx.get("race_number") and int(ctx["race_number"]) != rn:
            raise ValueError(f"Conflicting Logic race: {path}")
        distance = re.fullmatch(r"(\d{3,4})(?:m)?", str(ctx.get("distance", "")).strip())
        venue = venue_key(ctx.get("venue") or path.parent.name)
        if venue not in ("沙田", "跑馬地"):
            venue = venue_key(path.parent.name)
        for hn, horse in logic.get("horses", {}).items():
            name = horse_key(horse.get("horse_name"))
            key = (day, rn, int(hn), name)
            meta = dict(Venue=venue, Distance=int(distance[1]) if distance else None,
                        RaceNo=rn, RaceClass=ctx.get("race_class"))
            if key in contexts and contexts[key] != meta:
                raise ValueError(f"Conflicting Logic metadata: {key}")
            contexts[key] = meta

    for key, meta in racecard_contexts(racecard_paths, sources).items():
        if key not in contexts:
            contexts[key] = meta
            counts["racecard_contexts"] += 1

    for path in sorted(set(map(Path, result_paths))):
        data = read(path)
        for race_key, race in data.items():
            if not str(race_key).isdigit() or not isinstance(race, dict):
                continue
            rn = int(race_key)
            fallback = re.search(r"20\d{2}-\d{2}-\d{2}", str(path))
            day = str(race.get("racedate") or (fallback[0] if fallback else "")).replace("/", "-")
            date.fromisoformat(day)
            if race.get("race_no") and int(race["race_no"]) != rn:
                raise ValueError(f"Conflicting result race: {path} R{rn}")
            if fallback and day != fallback[0]:
                raise ValueError(f"Conflicting result date: {path}")
            for result in race.get("results", []):
                position = re.fullmatch(r"(\d+)(?:\s*\(.*\))?", str(result.get("pos", "")).strip())
                if not position or int(position[1]) < 1:
                    counts["non_finish_rows_excluded"] += 1
                    continue
                rank = int(position[1])
                name = horse_key(result.get("horse_name"))
                if not name:
                    raise ValueError(f"Empty result identity: {path} R{rn}")
                key = (day, name)
                inferred_venue = venue_key(race.get("venue") or path.parent.name)
                if inferred_venue not in ("沙田", "跑馬地"):
                    inferred_venue = ""
                incoming = dict(Date=day, Horse=result["horse_name"], RaceNo=rn,
                    Venue=inferred_venue, Rank=rank, Win=int(rank == 1),
                    Place=int(rank <= 3), Jockey=str(result.get("jockey", "")).strip(),
                    Trainer=str(result.get("trainer", "")).strip(), Distance=None,
                    SeasonTag="24_25" if day < "2025-08-01" else "25_26")
                if key in rows:
                    current = rows[key]
                    old_id, new_id = horse_id(current["Horse"]), horse_id(incoming["Horse"])
                    if old_id and new_id and old_id != new_id:
                        raise ValueError(f"Conflicting horse ID: {key}: {old_id} != {new_id}")
                    for field in ("Rank", "Win", "Place", "Jockey", "Trainer", "Venue"):
                        if field == "Venue" and not incoming[field]:
                            continue
                        if current.get(field) != incoming[field]:
                            raise ValueError(f"Conflicting result {key} {field}: "
                                             f"{current.get(field)} != {incoming[field]}")
                    if pd.notna(current.get("RaceNo")) and int(current["RaceNo"]) != rn:
                        raise ValueError(f"Conflicting result race identity: {key}")
                    current["RaceNo"] = rn
                    counts["duplicate_rows_verified"] += 1
                else:
                    rows[key] = incoming
                    counts["added_rows"] += 1
                current = rows[key]
                hn = str(result.get("horse_no", ""))
                meta = contexts.get((day, rn, int(hn), name)) if hn.isdigit() else None
                if not meta:
                    counts["metadata_unmatched"] += 1
                    continue
                if current["Venue"] and meta["Venue"] != current["Venue"]:
                    raise ValueError(f"Conflicting metadata venue: {key}")
                current["Venue"] = meta["Venue"]
                for field in ("Distance", "RaceClass"):
                    value = meta[field]
                    if value is not None and pd.isna(current.get(field)):
                        current[field] = value
                        counts[f"filled_{field}"] += 1
                    elif field == "Distance" and value and float(current[field]) != value:
                        raise ValueError(f"Conflicting metadata distance: {key}")

    out = pd.DataFrame(rows.values()).sort_values(["Date", "Horse"]).reset_index(drop=True)
    # Keep IDs in Horse for cross-date jockey-change grouping. Different IDs may
    # share a display name; normalizing them would silently join different horses.
    out.attrs["source_audit"] = dict(counts=counts, sources=sources,
        added_dates=sorted(set(out.Date) - set(base.Date)),
        distance_missing=int(out.Distance.isna().sum()))
    return out

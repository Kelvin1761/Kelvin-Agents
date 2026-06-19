#!/usr/bin/env python3
"""Regenerate src/tennis_wc/ingestion/tennisdata_tournament_index.py.

Reads the tennis-data.co.uk ATP/WTA season xlsx in src/data/external and emits a
static (tour, normalised_name) -> (level, surface, normalised_location) index.
Surface is stable year-to-year (reliable); level is best-effort from historical
data, so the curated list takes precedence at lookup time.

Run with a Python that has openpyxl installed (the runtime venv does NOT need it —
the generated module is a plain dict literal with no import-time dependency):

    python3 scripts/build_tennisdata_index.py
"""
from __future__ import annotations

import glob
import os
import re

import openpyxl

LEVEL_MAP = {
    "atp250": "ATP_250",
    "atp500": "ATP_500",
    "masters 1000": "ATP_1000",
    "masters cup": "ATP_FINALS",
    "grand slam": "GRAND_SLAM",
    "wta250": "WTA_250",
    "wta500": "WTA_500",
    "wta1000": "WTA_1000",
}

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXTERNAL = os.path.join(HERE, "src", "data", "external")
OUT = os.path.join(HERE, "src", "tennis_wc", "ingestion", "tennisdata_tournament_index.py")


def _norm(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _year(path: str) -> int:
    match = re.search(r"(20\d\d)", path)
    return int(match.group(1)) if match else 0


def build() -> dict:
    index: dict[tuple[str, str], tuple[str, str, str]] = {}
    for path in sorted(glob.glob(os.path.join(EXTERNAL, "tennisdata_*.xlsx")), key=_year):
        tour = "ATP" if "atp" in os.path.basename(path).lower() else "WTA"
        ws = openpyxl.load_workbook(path, read_only=True).active
        rows = ws.iter_rows(values_only=True)
        header = [str(h) for h in next(rows)]
        col = {h: i for i, h in enumerate(header)}
        level_col = "Series" if "Series" in col else "Tier"
        for row in rows:
            name = row[col["Tournament"]]
            surface = row[col["Surface"]]
            level_raw = row[col[level_col]]
            location = row[col["Location"]]
            level = LEVEL_MAP.get(_norm(level_raw))
            if not name or not surface or not level:
                continue
            # Latest season wins (files iterated oldest -> newest).
            index[(tour, _norm(name))] = (level, str(surface).title(), _norm(location))
    return index


def main() -> None:
    index = build()
    lines = [
        "# AUTO-GENERATED from tennis-data.co.uk ATP/WTA season xlsx. Do not edit by hand.",
        "# Regenerate via: python3 scripts/build_tennisdata_index.py",
        "# Key: (tour, normalised_tournament_name) -> (level, surface, normalised_location).",
        "# Surface is stable year-to-year (reliable); level is best-effort from historical",
        "# data and can lag promotions/demotions, so the curated list takes precedence.",
        "",
        "TENNISDATA_TOURNAMENTS = {",
    ]
    for tour, name in sorted(index):
        level, surface, location = index[(tour, name)]
        lines.append(f"    ({tour!r}, {name!r}): ({level!r}, {surface!r}, {location!r}),")
    lines.append("}")
    with open(OUT, "w") as handle:
        handle.write("\n".join(lines) + "\n")
    print(f"wrote {len(index)} entries to {OUT}")


if __name__ == "__main__":
    main()

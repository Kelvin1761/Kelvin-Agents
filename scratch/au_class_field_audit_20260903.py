#!/usr/bin/env python3
"""Count what the form-score class multiplier actually sees.

`_form_score` computes `entry_tier = _get_class_tier(entry.get("class", ""))`,
but `_record_entries()` never writes a `class` key. If that is true across the
corpus the multiplier is a pure function of today's race class -- identical for
every runner in the race -- and carries no per-horse class evidence at all.
Read-only: parses stored Facts, runs no engine, writes no Logic.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

AUTO = Path("/Users/imac/Antigravity-repo/.agents/skills/au_racing/au_wong_choi_auto/scripts")
sys.path.insert(0, str(AUTO))
sys.path.insert(0, str(Path("/Users/imac/Antigravity-repo/.agents/skills/shared_racing/scripts")))

from au_racing_engine.engine_core import (  # noqa: E402
    METRO_VENUE_TOKENS, RacingEngine, _record_rows, exact_race_class_level)
from au_archive_calibrator import ARCHIVE_ROOT, detect_meeting_date  # noqa: E402
from corpus_paths import meeting_dirs  # noqa: E402

tier = RacingEngine._get_class_tier


def venue_tier(venue: str) -> str:
    text = str(venue or "").strip().lower()
    if not text:
        return "unknown"
    return "metro" if any(tok in text for tok in METRO_VENUE_TOKENS) else "country"


def main() -> int:
    entry_has_class_key = 0
    entry_rows = 0
    src_class_present = 0
    src_class_parses = 0
    today_class_present = 0
    runners = races = 0
    mult_counts: Counter = Counter()
    today_tier_counts: Counter = Counter()
    entry_venue_tier: Counter = Counter()
    per_race_mult_unique: Counter = Counter()
    # level gap: same BM label, metro vs country -- is the label comparable?
    level_by_tier: dict[str, list[float]] = {"metro": [], "country": []}

    for meeting_dir in sorted(meeting_dirs(ARCHIVE_ROOT)):
        date = detect_meeting_date(meeting_dir)
        if not date:
            continue
        for logic_path in sorted(meeting_dir.glob("Race_*_Logic.json")):
            try:
                logic = json.loads(logic_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            ra = logic.get("race_analysis") or {}
            today_class = str(ra.get("race_class") or "")
            if today_class.strip():
                today_class_present += 1
            races += 1
            t_today = tier(None, today_class)
            today_tier_counts[t_today] += 1
            race_mults = set()
            for horse in (logic.get("horses") or {}).values():
                if not isinstance(horse, dict):
                    continue
                facts = (horse.get("_data") or {}).get("facts_section", "")
                if not facts:
                    continue
                runners += 1
                rows = list(_record_rows(facts))
                official = [c for c in rows if "試閘" not in c[1]][:4]
                for cols in official:
                    entry_rows += 1
                    # The engine's own dict never has a "class" key; confirm by
                    # rebuilding the same entry the engine builds.
                    src = cols[19] if len(cols) > 19 and cols[19] != "-" else ""
                    if src:
                        src_class_present += 1
                        lvl = exact_race_class_level(src)
                        if lvl is not None:
                            src_class_parses += 1
                            vt = venue_tier(cols[3])
                            if vt in level_by_tier:
                                level_by_tier[vt].append(lvl)
                    entry_venue_tier[venue_tier(cols[3])] += 1
                    d = t_today - tier(None, "")
                    m = 1.2 if d >= 2 else 1.1 if d == 1 else 1.0 if d == 0 else 0.85 if d == -1 else 0.7
                    mult_counts[m] += 1
                    race_mults.add(m)
            if race_mults:
                per_race_mult_unique[len(race_mults)] += 1

    from statistics import mean
    out = {
        "races": races,
        "runners": runners,
        "entry_rows_scored": entry_rows,
        "entries_with_class_key": entry_has_class_key,
        "today_race_class_present": today_class_present,
        "today_tier_distribution": dict(sorted(today_tier_counts.items())),
        "class_mult_distribution": {str(k): v for k, v in sorted(mult_counts.items())},
        "distinct_class_mults_per_race": dict(sorted(per_race_mult_unique.items())),
        "source_race_class_present": src_class_present,
        "source_race_class_parsed": src_class_parses,
        "entry_venue_tier": dict(entry_venue_tier),
        "mean_exact_level_metro": round(mean(level_by_tier["metro"]), 3) if level_by_tier["metro"] else None,
        "mean_exact_level_country": round(mean(level_by_tier["country"]), 3) if level_by_tier["country"] else None,
        "n_metro_levels": len(level_by_tier["metro"]),
        "n_country_levels": len(level_by_tier["country"]),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Meetings whose *live* prediction record is invalid and must not count.

WHY THIS EXISTS
---------------
2026-10-07 Happy Valley: the host clock (Sydney) rolled past midnight at 21:00
HKT, the engine judged the live card a replay, withheld the J/T priors and
re-scored the whole card on fallback values (fixed in 89afc0c8 / ea5ebb09).
That broken run was the night's last immutable snapshot, so every statistic
built on "our pre-race prediction" — reflection KPIs, miss autopsy, dimension
attribution, shadow / forward-test counts — graded a model that never ran
correctly.  Kelvin decided (2026-11-12) to exclude the meeting rather than
re-grade it from an earlier snapshot after the fact.

This is NOT the same as `au_corpus_exclusions.json`: that list removes
meetings whose *input data* leaks, from replay corpora.  Here the input data
is fine and replays are correct; only the live record is wrong.  So replay /
backtest harnesses must keep the meeting, and only live-record statistics skip
it.

One JSON file in the repo, each entry with a reason, the bad snapshot and the
commit that found it — reviewable, and applied by every consumer through
`is_excluded`.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

EXCLUSIONS_PATH = Path(__file__).resolve().parent / "resources" / "live_record_exclusions.json"
REQUIRED = ("platform", "meeting", "reason", "detected_by", "decided")
PLATFORMS = {"au", "hkjc"}


def _meeting_name(meeting) -> str:
    return Path(str(meeting)).name


@lru_cache(maxsize=None)
def _load(path: str) -> dict[tuple[str, str], dict]:
    source = Path(path)
    if not source.exists():
        return {}
    data = json.loads(source.read_text(encoding="utf-8"))
    out: dict[tuple[str, str], dict] = {}
    for entry in data.get("meetings") or []:
        missing = [k for k in REQUIRED if not entry.get(k)]
        if missing:
            raise ValueError(f"{source}: 排除項欠 {missing}：{entry}")
        if entry["platform"] not in PLATFORMS:
            raise ValueError(f"{source}: 唔識嘅 platform {entry['platform']!r}")
        key = (entry["platform"], entry["meeting"])
        if key in out:
            raise ValueError(f"{source}: 重複排除 {key}")
        out[key] = entry
    return out


def load(platform: str, path: Path | str | None = None) -> dict[str, dict]:
    """Meeting folder name -> exclusion entry for one platform."""
    table = _load(str(path or EXCLUSIONS_PATH))
    return {name: entry for (plat, name), entry in table.items() if plat == platform}


def exclusion(platform: str, meeting, path: Path | str | None = None) -> dict | None:
    """The entry for `meeting` (folder path or name), or None."""
    return load(platform, path).get(_meeting_name(meeting))


def is_excluded(platform: str, meeting, path: Path | str | None = None) -> bool:
    return exclusion(platform, meeting, path) is not None


def keep(platform: str, rows, key: str = "meeting", path: Path | str | None = None) -> list:
    """Drop rows whose `row[key]` names an excluded meeting (ledger readers)."""
    names = load(platform, path)
    return [row for row in rows
            if not (isinstance(row, dict) and _meeting_name(row.get(key) or "") in names)]

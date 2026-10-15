"""Hide retired AU PI evidence in the published projection, preserving scores.

HKJC still uses position PI in its Sha Tin shape component. Source reports and
model artifacts stay untouched; this policy runs after loading a snapshot so
old/cached reports and lazy analysis bundles receive the same display cleanup.
"""
from __future__ import annotations

import re

PI = re.compile(r"(?<![A-Za-z])PI(?![A-Za-z])|位置增益", re.IGNORECASE)
TEXT_FIELDS = (
    "raw_text", "core_analysis", "core_logic", "speed_forensics", "horse_profile",
    "conclusion", "advantage", "risk", "trend_summary", "key_runs",
    "data_readout", "dimension_details", "eem_energy", "forgiveness_file",
    "form_line", "statistics", "engine_distance_summary", "underhorse_reason",
)


def without_pi(text: str) -> str:
    """Remove PI blocks/clauses and table columns, retaining other speed data."""
    output = []
    dropped_columns = None
    skip_indent = None
    skip_heading = None
    for line in text.splitlines():
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        heading = re.match(r"^(#{1,6})\s", stripped)
        if skip_heading is not None:
            if not heading or len(heading[1]) > skip_heading:
                continue
            skip_heading = None
        if skip_indent is not None:
            if stripped and indent > skip_indent:
                continue
            if stripped:
                skip_indent = None
        if stripped.startswith('|'):
            cells = stripped.strip().strip('|').split('|')
            if dropped_columns is None:
                drop = {i for i, cell in enumerate(cells) if PI.search(cell)}
                dropped_columns = drop
            if dropped_columns:
                cells = [cell for i, cell in enumerate(cells) if i not in dropped_columns]
                line = ' ' * indent + '|' + '|'.join(cells) + '|'
            output.append(line)
            continue
        dropped_columns = None
        if not PI.search(line):
            output.append(line)
            continue
        label = re.split(r'[:：]', stripped, maxsplit=1)[0]
        if PI.search(label) and (heading or re.match(r'^[-*]\s', stripped)):
            if heading:
                skip_heading = len(heading[1])
            else:
                skip_indent = indent
            continue
        # Mixed verdicts can contain one PI sentence beside useful L600 facts.
        # Keep the other clauses rather than deleting the whole verdict.
        kept = ''.join(part for part in re.split(r'(?<=[。；;])', line)
                       if not PI.search(part)).strip()
        if kept:
            output.append(' ' * indent + kept)
    return '\n'.join(output).strip()


def _clean(value):
    if isinstance(value, str):
        return without_pi(value)
    if isinstance(value, list):
        result = []
        for item in value:
            if isinstance(item, dict) and PI.search(str(item.get('label') or item.get('name') or '')):
                continue
            cleaned = _clean(item)
            if cleaned not in ('', None):
                result.append(cleaned)
        return result
    if isinstance(value, dict):
        return {key: _clean(item) if isinstance(item, (str, list, dict)) else item
                for key, item in value.items()}
    return value


def apply_au_display_policy(payload: dict) -> dict:
    """Apply only to explicitly AU meetings; all ranking values stay intact."""
    au_keys = {f"{meeting.get('date')}|{meeting.get('venue')}"
               for meeting in payload.get('meetings') or []
               if str(meeting.get('region') or '').lower() == 'au'}
    for key, entry in (payload.get('races') or {}).items():
        region = entry.get('region') or (entry.get('meeting') or {}).get('region')
        if key not in au_keys and str(region or '').lower() != 'au':
            continue
        for races in (entry.get('races_by_analyst') or {}).values():
            for race in races:
                for horse in race.get('horses') or []:
                    for field in TEXT_FIELDS:
                        if horse.get(field) is not None:
                            horse[field] = _clean(horse[field])
    return payload

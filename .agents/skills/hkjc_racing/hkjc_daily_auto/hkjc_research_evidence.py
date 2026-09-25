"""Build deterministic Stage 5 evidence for future HKJC production runs.

This module is deliberately metadata-only.  It reads one completed pre-race
meeting, binds each score feature to the exact immutable input bytes used by
that feature family, and returns a compact projection.  It never edits a
meeting, changes scoring, qualifies a sample, or grants model promotion.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path


SCHEMA = "wong-choi-hkjc-research-feature-provenance/v1"
PROJECTION_NAME = "HKJC_Research_Feature_Provenance.json"
_LOGIC = re.compile(r"Race_(\d+)_Logic\.json")
_FACTS = re.compile(r".+ Race (\d+) Facts\.md")
_RACECARD = re.compile(r".+ Race (\d+) 排位表\.md")
_TRACKWORK = re.compile(r".+ Race (\d+) 晨操\.json")

_FEATURE_SOURCE = {
    "class_score": "Facts",
    "confidence_score": "Facts",
    "consistency_score": "Facts",
    "distance_score": "Facts",
    "draw_score": "Racecard",
    "form_score": "Facts",
    "formline_strength_score": "Facts",
    "jockey_score": "Facts",
    "margin_trend_score": "Facts",
    "race_shape_context_score": "Facts",
    "risk_score": "Facts",
    "same_distance_signal_score": "Facts",
    "speed_score": "Facts",
    "track_going_score": "Facts",
    "trackwork_trend_score": "Trackwork",
    "trainer_score": "Facts",
    "weight_score": "Facts",
}
_INPUTS = {
    "Facts": _FACTS,
    "Racecard": _RACECARD,
    "Trackwork": _TRACKWORK,
}


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _clock(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("captured_at must be timezone-aware")
    return value.astimezone(timezone.utc)


def _event_matches(folder: Path, event_id: str) -> bool:
    parts = event_id.split("|")
    return (
        len(parts) == 2
        and bool(parts[0])
        and bool(parts[1])
        and folder.name.startswith(parts[0])
        and parts[1] in folder.name
    )


def _race_ranges(races: list[int]) -> str:
    groups: list[list[int]] = []
    for race in sorted(set(races)):
        if not groups or race != groups[-1][-1] + 1:
            groups.append([race])
        else:
            groups[-1].append(race)
    return ",".join(
        f"R{group[0]}" if len(group) == 1 else f"R{group[0]}-R{group[-1]}"
        for group in groups
    )


def _inputs(folder: Path) -> dict[int, dict[str, Path]]:
    found: dict[int, dict[str, Path]] = {}
    for path in folder.iterdir():
        if not path.is_file() or path.stat().st_size <= 0:
            continue
        for kind, pattern in _INPUTS.items():
            match = pattern.fullmatch(path.name)
            if match is None:
                continue
            race = int(match.group(1))
            if kind in found.setdefault(race, {}):
                raise ValueError(f"duplicate HKJC {kind} input for Race {race}")
            found[race][kind] = path
    return found


def _source(path: Path, *, cutoff: datetime, race: int, kind: str,
            horse_id: str, feature: str, derivation: str) -> dict:
    return {
        "artifact": path.name,
        "sha256": _sha(path),
        "available_at": cutoff.isoformat(),
        "field": (
            f"race={race};producer_input={kind.lower()};horse={horse_id};"
            f"feature={feature};derivation={derivation}"
        ),
    }


def build_feature_projection(
    folder: Path,
    *,
    event_id: str,
    captured_at: datetime,
) -> bytes:
    """Return immutable-snapshot metadata bytes for one HKJC meeting."""
    folder = Path(folder).resolve()
    if not folder.is_dir() or not _event_matches(folder, event_id):
        raise ValueError("HKJC event/folder mismatch")
    cutoff = _clock(captured_at)
    inputs = _inputs(folder)
    races: set[int] = set()
    logic_files = []
    logic_paths = sorted(
        folder.glob("Race_*_Logic.json"),
        key=lambda path: int(_LOGIC.fullmatch(path.name).group(1))
        if _LOGIC.fullmatch(path.name) else 10**9,
    )
    logic_races = [
        int(match.group(1))
        for path in logic_paths
        if (match := _LOGIC.fullmatch(path.name)) is not None
        and path.is_file() and path.stat().st_size > 0
    ]
    missing_inputs = {
        kind: [race for race in logic_races if kind not in inputs.get(race, {})]
        for kind in _INPUTS
    }
    missing_inputs = {kind: values for kind, values in missing_inputs.items() if values}
    if missing_inputs:
        detail = "; ".join(
            f"{kind} {_race_ranges(values)}"
            for kind, values in missing_inputs.items()
        )
        raise ValueError(f"missing HKJC feature inputs: {detail}")

    for path in logic_paths:
        match = _LOGIC.fullmatch(path.name)
        if match is None or not path.is_file() or path.stat().st_size <= 0:
            continue
        race = int(match.group(1))
        if race in races:
            raise ValueError(f"duplicate HKJC Logic for Race {race}")
        races.add(race)
        try:
            logic = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError) as exc:
            raise ValueError(f"invalid HKJC Logic: {path.name}") from exc
        horses = logic.get("horses") if isinstance(logic, dict) else None
        if not isinstance(horses, dict) or not horses:
            raise ValueError(f"HKJC Logic has no horses: {path.name}")
        race_inputs = inputs.get(race, {})
        projected_horses = {}
        for raw_horse_id, horse in sorted(horses.items(), key=lambda item: str(item[0])):
            horse_id = str(raw_horse_id)
            if not horse_id:
                raise ValueError("invalid HKJC horse identity")
            provenance = ((horse.get("python_auto") or {}).get("score_provenance")
                          if isinstance(horse, dict) else None)
            if not isinstance(provenance, dict) or not provenance:
                raise ValueError(f"HKJC Logic has no feature provenance: {path.name}/{horse_id}")
            projected = {}
            for feature, raw in sorted(provenance.items()):
                kind = _FEATURE_SOURCE.get(feature)
                if kind is None:
                    raise ValueError(f"unknown HKJC feature identity: {feature}")
                source_path = race_inputs.get(kind)
                if source_path is None:
                    raise ValueError(f"missing HKJC {kind} input for Race {race}")
                derivation = raw.get("derivation") if isinstance(raw, dict) else raw
                if not isinstance(derivation, str) or not derivation.strip():
                    raise ValueError(f"invalid HKJC feature derivation: {feature}")
                projected[feature] = {
                    "derivation": derivation,
                    "sources": [_source(
                        source_path,
                        cutoff=cutoff,
                        race=race,
                        kind=kind,
                        horse_id=horse_id,
                        feature=feature,
                        derivation=derivation,
                    )],
                }
            projected_horses[horse_id] = projected
        logic_files.append({
            "name": path.name,
            "sha256": _sha(path),
            "horses": projected_horses,
        })
    if not logic_files:
        raise ValueError("no HKJC Logic files")
    extra_inputs = set(inputs).difference(races)
    if extra_inputs:
        raise ValueError(f"HKJC input set contains unscored races: {sorted(extra_inputs)}")
    payload = {
        "schema_version": SCHEMA,
        "domain": "hkjc",
        "event_id": event_id,
        "captured_at": cutoff.isoformat(),
        "append_only": True,
        "logic_files": logic_files,
        "model_promotion_allowed": False,
    }
    return (json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ) + "\n").encode("utf-8")


def settlement_artifacts(folder: Path, *, event_id: str) -> tuple[Path, Path]:
    """Resolve future HKJC settlement truth and report without writing."""
    folder = Path(folder).resolve()
    if not folder.is_dir() or not _event_matches(folder, event_id):
        raise ValueError("HKJC settlement event/folder mismatch")
    results = sorted(
        path for path in folder.glob("*全日賽果.json")
        if path.is_file() and path.stat().st_size > 0
    )
    if len(results) != 1:
        detail = "missing" if not results else "exactly one required"
        raise ValueError(f"canonical HKJC result artifact {detail}")
    report = folder / "HKJC_Reflection_Report.md"
    if not report.is_file() or report.stat().st_size <= 0:
        raise ValueError("canonical HKJC reflection report missing")
    return results[0], report

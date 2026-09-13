"""Create deterministic, metadata-only Stage 5 evidence for future AU runs.

The producer reads the exact completed pre-race folder and emits bytes that are
admitted directly into the immutable prediction snapshot.  It never rewrites a
meeting input/output, changes a score, qualifies a sample, or grants promotion.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


SCHEMA = "wong-choi-au-research-feature-provenance/v1"
PROJECTION_NAME = "AU_Research_Feature_Provenance.json"
SYDNEY = ZoneInfo("Australia/Sydney")
_LOGIC = re.compile(r"Race_(\d+)_Logic\.json")
_INPUT = re.compile(r".+ Race (\d+) (Racecard|Formguide|Facts)\.md")
_REQUIRED = ("Racecard", "Formguide", "Facts")


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


def _source_map(folder: Path, cutoff: datetime) -> dict[int, list[dict]]:
    found: dict[int, dict[str, Path]] = {}
    for path in folder.iterdir():
        if not path.is_file() or path.stat().st_size <= 0:
            continue
        match = _INPUT.fullmatch(path.name)
        if match:
            race, kind = int(match.group(1)), match.group(2)
            if kind in found.setdefault(race, {}):
                raise ValueError(f"duplicate pre-race input for Race {race}: {kind}")
            found[race][kind] = path
    result = {}
    for race, values in found.items():
        missing = [kind for kind in _REQUIRED if kind not in values]
        if missing:
            raise ValueError(f"missing pre-race input for Race {race}: {missing}")
        result[race] = [
            {
                "artifact": values[kind].name,
                "sha256": _sha(values[kind]),
                "available_at": cutoff.isoformat(),
                "field": f"race={race};producer_input={kind.lower()}",
            }
            for kind in _REQUIRED
        ]
    return result


def _odds_projection(folder: Path, cutoff: datetime, races: set[int]) -> dict:
    path = folder / "odds_history.json"
    if not path.is_file() or path.stat().st_size <= 0:
        return {"status": "missing_history", "artifact": None, "sha256": None,
                "earliest_analysis": {}}
    try:
        history = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError) as exc:
        raise ValueError("invalid odds history") from exc
    if not isinstance(history, dict):
        raise ValueError("invalid odds history")
    earliest = {}
    for race in sorted(races):
        snapshots = history.get(str(race))
        if not isinstance(snapshots, dict):
            continue
        eligible = []
        for key, prices in snapshots.items():
            if not isinstance(key, str) or "|" not in key or not isinstance(prices, dict):
                raise ValueError("invalid odds snapshot")
            raw_at, label = key.rsplit("|", 1)
            if label != "analysis":
                continue
            try:
                observed = datetime.fromisoformat(raw_at)
            except ValueError as exc:
                raise ValueError("invalid odds snapshot timestamp") from exc
            if observed.tzinfo is None:
                observed = observed.replace(tzinfo=SYDNEY)
            observed = observed.astimezone(timezone.utc)
            if observed <= cutoff:
                eligible.append((observed, key, prices))
        if eligible:
            observed, key, prices = min(eligible, key=lambda item: (item[0], item[1]))
            earliest[str(race)] = {
                "snapshot_key": key,
                "captured_at": observed.isoformat(),
                "prices": prices,
            }
    return {
        "status": "complete" if set(map(int, earliest)) == races else "missing_analysis",
        "artifact": path.name,
        "sha256": _sha(path),
        "earliest_analysis": earliest,
    }


def build_feature_projection(folder: Path, *, captured_at: datetime) -> bytes:
    """Return immutable-snapshot bytes for one completed AU meeting."""
    folder = Path(folder).resolve()
    cutoff = _clock(captured_at)
    sources = _source_map(folder, cutoff)
    logic_files = []
    races = set()
    for path in sorted(folder.glob("Race_*_Logic.json")):
        match = _LOGIC.fullmatch(path.name)
        if match is None or not path.is_file() or path.stat().st_size <= 0:
            continue
        race = int(match.group(1))
        races.add(race)
        if race not in sources:
            raise ValueError(f"missing pre-race input for Race {race}")
        try:
            logic = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeError) as exc:
            raise ValueError(f"invalid AU Logic: {path.name}") from exc
        horses = logic.get("horses") if isinstance(logic, dict) else None
        if not isinstance(horses, dict) or not horses:
            raise ValueError(f"AU Logic has no horses: {path.name}")
        projected_horses = {}
        for horse_id, horse in sorted(horses.items(), key=lambda item: str(item[0])):
            provenance = ((horse.get("python_auto") or {}).get("score_provenance")
                          if isinstance(horse, dict) else None)
            if not isinstance(provenance, dict) or not provenance:
                raise ValueError(f"AU Logic has no feature provenance: {path.name}/{horse_id}")
            projected = {}
            for feature, raw in sorted(provenance.items()):
                if not isinstance(feature, str) or not feature.endswith("_score"):
                    raise ValueError("invalid AU feature identity")
                derivation = raw.get("derivation") if isinstance(raw, dict) else raw
                if not isinstance(derivation, str) or not derivation.strip():
                    raise ValueError("invalid AU feature derivation")
                projected[feature] = {
                    "derivation": derivation,
                    "sources": [
                        {**source, "field": (
                            source["field"]
                            + f";horse={horse_id};feature={feature};derivation={derivation}"
                        )}
                        for source in sources[race]
                    ],
                }
            projected_horses[str(horse_id)] = projected
        logic_files.append({
            "name": path.name,
            "sha256": _sha(path),
            "horses": projected_horses,
        })
    if not logic_files:
        raise ValueError("no AU Logic files")
    if set(sources) != races:
        raise ValueError("pre-race input set differs from scored races")
    payload = {
        "schema_version": SCHEMA,
        "domain": "au",
        "event_id": folder.name,
        "captured_at": cutoff.isoformat(),
        "append_only": True,
        "logic_files": logic_files,
        "market": _odds_projection(folder, cutoff, races),
        "model_promotion_allowed": False,
    }
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def settlement_artifacts(folder: Path, *, event_id: str) -> tuple[Path, Path]:
    """Resolve the two exact future-settlement inputs without writing evidence."""
    folder = Path(folder).resolve()
    if folder.name != event_id or not event_id:
        raise ValueError("AU settlement event/folder mismatch")
    result = folder / "Race_Results_Reflector.md"
    report = folder / f"{event_id}_Reflector_Report.md"
    missing = [path.name for path in (result, report) if not path.is_file() or path.stat().st_size <= 0]
    if missing:
        raise ValueError(f"canonical settlement artifact missing: {', '.join(missing)}")
    return result, report

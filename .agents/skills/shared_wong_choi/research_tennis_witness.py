"""Content-verified WARM snapshot witnesses, never model/promotion authority.

Trust boundary: the caller pins a Stage 4 catalog record as the capture-time
authority. This verifies its bytes, artifact identity and exact earlier value;
it is not independent cryptographic attestation of the catalog's wall clock,
historical derivations, market completeness or correctness of player mappings.
Run via research supervision: full hashing and SQLite reads may block on I/O.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from .artifact_archive import artifact_digest
from .research_safety import ResearchSafetyError, _json
from .research_tennis_source import _digest, _name, _numeric, _time


@dataclass(frozen=True)
class SnapshotWitness:
    catalog_record: Path
    catalog_sha256: str
    artifact_id: str
    warm_root: Path
    max_bytes: int = 2_000_000_000

    def validate(self):
        if not re.fullmatch(r"[0-9a-f]{64}", self.catalog_sha256):
            raise ValueError("catalog SHA-256 must be pinned")
        if not re.fullmatch(r"wc-artifact:[0-9a-f]{24}", self.artifact_id):
            raise ValueError("artifact identity must be pinned")
        if type(self.max_bytes) is not int or self.max_bytes <= 0:
            raise ValueError("positive witness byte budget required")
        for path in (self.catalog_record, self.warm_root):
            if not path.is_absolute() or ".." in path.parts:
                raise ValueError("absolute witness paths without traversal required")

    def to_payload(self):
        self.validate()
        return {
            "catalog_record": str(self.catalog_record),
            "catalog_sha256": self.catalog_sha256,
            "artifact_id": self.artifact_id,
            "warm_root": str(self.warm_root),
            "max_bytes": self.max_bytes,
        }

    @classmethod
    def from_payload(cls, payload):
        if set(payload) != {"catalog_record", "catalog_sha256", "artifact_id", "warm_root", "max_bytes"}:
            raise ValueError("invalid witness request schema")
        result = cls(
            Path(payload["catalog_record"]),
            payload["catalog_sha256"],
            payload["artifact_id"],
            Path(payload["warm_root"]),
            payload["max_bytes"],
        )
        result.validate()
        return result


def _regular(path, *, limit):
    if any(part.is_symlink() for part in (path, *path.parents)) or not path.is_file():
        raise ValueError("witness requires existing regular non-symlink files")
    stat = path.stat()
    if stat.st_size <= 0 or stat.st_size > limit:
        raise ValueError("witness exceeds byte budget or is empty")
    return stat


def _stable_signature(path):
    stat = path.stat()
    return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)


def _load_catalog(witness):
    _regular(witness.catalog_record, limit=65536)
    encoded = witness.catalog_record.read_bytes()
    if hashlib.sha256(encoded).hexdigest() != witness.catalog_sha256:
        raise ValueError("catalog content does not match pinned hash")
    try:
        manifest = _json(encoded)
    except ResearchSafetyError as exc:
        raise ValueError("invalid catalog JSON") from exc
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema_version") != "wong-choi-artifact/v1"
        or manifest.get("domain") != "tennis"
        or manifest.get("artifact_class") != "db-snapshot"
        or manifest.get("artifact_id") != witness.artifact_id
    ):
        raise ValueError("catalog identity/domain/class mismatch")
    if (
        witness.catalog_record.parent.name != "records"
        or witness.catalog_record.name != quote(witness.artifact_id, safe="._-") + ".json"
    ):
        raise ValueError("catalog record path does not match artifact identity")
    expected = manifest.get("source_digest")
    if (
        not isinstance(expected, dict)
        or set(expected) != {"sha256", "bytes", "files"}
        or type(expected.get("files")) is not int
        or expected["files"] != 1
        or type(expected.get("bytes")) is not int
        or not 0 < expected["bytes"] <= witness.max_bytes
        or not isinstance(expected.get("sha256"), str)
        or not re.fullmatch(r"[0-9a-f]{64}", expected["sha256"])
        or manifest.get("destination_digest") != expected
    ):
        raise ValueError("catalog digest invariant or byte budget failed")
    source = Path(manifest.get("source", ""))
    destination = Path(manifest.get("destination", ""))
    if not source.is_absolute() or ".." in source.parts or not destination.is_absolute() or ".." in destination.parts:
        raise ValueError("invalid archive paths")
    identity = "|".join(("tennis", "db-snapshot", str(source), expected["sha256"]))
    if "wc-artifact:" + hashlib.sha256(identity.encode()).hexdigest()[:24] != witness.artifact_id:
        raise ValueError("artifact identity digest mismatch")
    if destination != witness.warm_root / "tennis/db-snapshot" / expected["sha256"][:12] / source.name:
        raise ValueError("archive destination is outside pinned WARM layout")
    _time(manifest.get("created_at"))
    _regular(destination, limit=witness.max_bytes)
    if destination.stat().st_size != expected["bytes"]:
        raise ValueError("archive size mismatch")
    for suffix in ("-wal", "-shm", "-journal"):
        sidecar = destination.with_name(destination.name + suffix)
        if sidecar.exists() or sidecar.is_symlink():
            raise ValueError("archive has SQLite sidecars; immutable snapshot required")
    return manifest, destination, expected


def _claims(inventory):
    if (
        not isinstance(inventory, dict)
        or inventory.get("schema_version") != "wong-choi-tennis-source-inventory/v2"
        or inventory.get("proposal_ready") is not False
        or inventory.get("pit_dataset_ready") is not False
        or inventory.get("labels_read") is not False
        or inventory.get("content_hash")
        != _digest({key: value for key, value in inventory.items() if key != "content_hash"})
    ):
        raise ValueError("invalid or mutated source inventory")
    claims, identities = [], set()
    for row in inventory["rows"]:
        if len(row["features"]) != 2 or len(row["quotes"]) != 2:
            raise ValueError("two-player source evidence required")
        decision, event = _time(row["decision_at"]), _time(row["event_at"])
        if decision >= event:
            raise ValueError("witness cannot rescue a post-start decision")
        for player, price in zip(row["features"], row["quotes"]):
            if "overall_elo" not in player["fields"]:
                continue
            value = player["fields"]["overall_elo"]["value"]
            identity = (row["event_id"], player["player_id"])
            if identity in identities or not _numeric(value) or type(player["player_id"]) is not int:
                raise ValueError("duplicate/invalid witness claim")
            identities.add(identity)
            claims.append(
                {
                    "match_id": row["match_id"],
                    "event_id": row["event_id"],
                    "player_id": player["player_id"],
                    "player_name": _name(price["selection_name"]),
                    "snapshot_id": player["snapshot_id"],
                    "field": "overall_elo",
                    "value": value,
                    "decision_at": decision.isoformat(),
                    "stored_match_date": row["stored_match_date"],
                }
            )
    if len(claims) > 1000:
        raise ValueError("too many witness claims")
    return claims


def verify_tennis_snapshot_witness(inventory, witness: SnapshotWitness, *, checkpoint=None):
    """Read only the pinned WARM copy; never restore/fall back to active HOT DB."""
    witness.validate()
    claims = _claims(inventory)
    check = checkpoint or (lambda: None)
    check()
    implementation = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    manifest, snapshot, expected = _load_catalog(witness)
    captured = _time(manifest["created_at"])
    before = _stable_signature(snapshot)
    if artifact_digest(snapshot) != expected:
        raise ValueError("archive full digest mismatch")
    check()
    rows = []
    conn = sqlite3.connect(snapshot.as_uri() + "?mode=ro&immutable=1", uri=True, timeout=0.1)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        conn.execute("PRAGMA trusted_schema=OFF")
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('players','player_elo_history')"
            )
        }
        for claim in claims:
            check()
            item = {
                **claim,
                "catalog_created_at": captured.isoformat(),
                "archived_row": None,
                "derivation_verified": False,
                "status": "archive_schema_missing",
            }
            if captured >= _time(claim["decision_at"]):
                item["status"] = "capture_not_before_decision"
            elif len(tables) == 2:
                player = conn.execute("SELECT name FROM players WHERE id=?", (claim["player_id"],)).fetchall()
                if len(player) != 1 or _name(player[0]["name"]) != claim["player_name"]:
                    item["status"] = "participant_mismatch"
                else:
                    history = conn.execute(
                        "SELECT player_id,as_of_date,surface,rating,matches_played FROM player_elo_history "
                        "WHERE player_id=? AND surface='' AND as_of_date<? ORDER BY as_of_date DESC LIMIT 2",
                        (claim["player_id"], claim["stored_match_date"]),
                    ).fetchall()
                    if not history:
                        item["status"] = "archived_history_missing"
                    elif len(history) == 2 and history[0]["as_of_date"] == history[1]["as_of_date"]:
                        item["status"] = "ambiguous_archived_history"
                    else:
                        item["archived_row"] = dict(history[0])
                        item["status"] = (
                            "catalog_predecision_value_match"
                            if _numeric(history[0]["rating"]) and history[0]["rating"] == claim["value"]
                            else "archived_value_differs"
                        )
            rows.append(item)
    finally:
        conn.close()
    check()
    # Recheck complete bytes and metadata after reads; an immutable URI is not
    # permission to trust a file changed underneath the connection.
    if artifact_digest(snapshot) != expected or _stable_signature(snapshot) != before:
        raise ValueError("archive changed during witness inspection")
    _load_catalog(witness)
    if hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != implementation:
        raise ValueError("witness implementation changed during inspection")
    check()
    payload = {
        "schema_version": "wong-choi-tennis-snapshot-witness/v1",
        "inventory_hash": inventory["content_hash"],
        "catalog_sha256": witness.catalog_sha256,
        "artifact_id": witness.artifact_id,
        "artifact_digest": expected,
        "witness_implementation_sha256": implementation,
        "capture_time_authority": "pinned_stage4_catalog_claim_not_independent_clock_attestation",
        "rows": rows,
        "pit_dataset_ready": False,
        "proposal_ready": False,
        "derivation_verified": False,
    }
    return {**payload, "content_hash": _digest(payload)}

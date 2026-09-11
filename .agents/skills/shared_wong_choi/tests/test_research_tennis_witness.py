from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared_wong_choi.artifact_archive import archive_copy, artifact_digest
from shared_wong_choi.research_tennis_source import inspect_tennis_sources
from shared_wong_choi.research_tennis_witness import SnapshotWitness, verify_tennis_snapshot_witness
from test_research_tennis_source import fixture as source_fixture


def fixture(tmp_path, *, captured_at="2026-08-25T09:00:00Z"):
    db, policy = source_fixture(tmp_path)
    inventory = inspect_tennis_sources(db, policy).to_payload()
    hot = tmp_path / "hot"
    hot.mkdir()
    snapshot = hot / "snapshot.db"
    with sqlite3.connect(snapshot) as conn:
        conn.executescript("""
        CREATE TABLE players(id INTEGER PRIMARY KEY,name TEXT);
        CREATE TABLE player_elo_history(player_id INTEGER,as_of_date TEXT,surface TEXT,rating REAL,matches_played INTEGER,PRIMARY KEY(player_id,as_of_date,surface));
        INSERT INTO players VALUES(11,'Alpha Player'),(12,'Beta Player');
        INSERT INTO player_elo_history VALUES(11,'2026-08-24','',1710,20),(12,'2026-08-24','',1720,30);
        """)
    warm = tmp_path / "warm"
    warm.mkdir()
    result = archive_copy(
        snapshot,
        warm_root=warm,
        catalog_root=tmp_path / "catalog",
        domain="tennis",
        artifact_class="db-snapshot",
        allowed_roots=[hot],
        created_at=captured_at,
    )
    record = Path(result["manifest"])
    witness = SnapshotWitness(record, hashlib.sha256(record.read_bytes()).hexdigest(), result["artifact_id"], warm)
    return inventory, witness, Path(result["destination"])


def test_catalog_verified_earlier_snapshot_witness_is_readonly_not_promotion(tmp_path):
    inventory, witness, snapshot = fixture(tmp_path)
    before = artifact_digest(snapshot)
    report = verify_tennis_snapshot_witness(inventory, witness)
    assert report["artifact_digest"] == before
    assert [item["status"] for item in report["rows"]] == ["catalog_predecision_value_match"] * 2
    assert report["pit_dataset_ready"] is False and report["proposal_ready"] is False
    assert report["derivation_verified"] is False
    assert report == verify_tennis_snapshot_witness(inventory, witness)
    assert artifact_digest(snapshot) == before
    assert not list(snapshot.parent.glob("*-wal"))


def repin(witness, *, change=None):
    payload = json.loads(witness.catalog_record.read_text())
    if change:
        change(payload)
        witness.catalog_record.write_text(json.dumps(payload))
    return replace(witness, catalog_sha256=hashlib.sha256(witness.catalog_record.read_bytes()).hexdigest())


@pytest.mark.parametrize(
    "fault",
    [
        "catalog_hash",
        "snapshot_hash",
        "wrong_id",
        "wrong_domain",
        "path_escape",
        "digest_conflict",
        "symlink",
        "wal",
        "too_large",
    ],
)
def test_missing_or_untrusted_witness_never_silently_falls_back(tmp_path, fault):
    inventory, witness, snapshot = fixture(tmp_path)
    if fault == "catalog_hash":
        witness = replace(witness, catalog_sha256="a" * 64)
    if fault == "snapshot_hash":
        with sqlite3.connect(snapshot) as conn:
            conn.execute("UPDATE player_elo_history SET rating=9")
    if fault == "wrong_id":
        witness = replace(witness, artifact_id="wc-artifact:" + "a" * 24)
    if fault == "wrong_domain":
        witness = repin(witness, change=lambda p: p.update(domain="au"))
    if fault == "path_escape":
        witness = replace(witness, warm_root=tmp_path / "elsewhere")
    if fault == "digest_conflict":
        witness = repin(witness, change=lambda p: p["source_digest"].update(sha256="a" * 64))
    if fault == "symlink":
        original = snapshot.with_suffix(".original")
        snapshot.rename(original)
        snapshot.symlink_to(original)
    if fault == "wal":
        snapshot.with_name(snapshot.name + "-wal").touch()
    if fault == "too_large":
        witness = replace(witness, max_bytes=1)
    with pytest.raises((ValueError, OSError)):
        verify_tennis_snapshot_witness(inventory, witness)


@pytest.mark.parametrize("stamp", ["2026-08-25T10:01:00Z", "2026-08-26T00:00:00Z"])
def test_same_or_later_capture_cannot_witness_prior_value(tmp_path, stamp):
    inventory, witness, _ = fixture(tmp_path, captured_at=stamp)
    report = verify_tennis_snapshot_witness(inventory, witness)
    assert {item["status"] for item in report["rows"]} == {"capture_not_before_decision"}


def test_inventory_mutation_is_rejected(tmp_path):
    inventory, witness, _ = fixture(tmp_path)
    inventory["rows"][0]["features"][0]["fields"]["overall_elo"]["value"] = 1
    with pytest.raises(ValueError):
        verify_tennis_snapshot_witness(inventory, witness)


def test_different_identity_or_value_is_not_repaired(tmp_path):
    inventory, witness, snapshot = fixture(tmp_path)
    # Make a newly cataloged independent snapshot containing different values.
    source = Path(json.loads(witness.catalog_record.read_text())["source"])
    with sqlite3.connect(source) as conn:
        conn.execute("UPDATE players SET name='Different Player' WHERE id=11")
        conn.execute("UPDATE player_elo_history SET rating=100 WHERE player_id=12")
    result = archive_copy(
        source,
        warm_root=witness.warm_root,
        catalog_root=tmp_path / "catalog",
        domain="tennis",
        artifact_class="db-snapshot",
        allowed_roots=[source.parent],
        created_at="2026-08-25T09:00:00Z",
    )
    record = Path(result["manifest"])
    witness = SnapshotWitness(
        record, hashlib.sha256(record.read_bytes()).hexdigest(), result["artifact_id"], witness.warm_root
    )
    report = verify_tennis_snapshot_witness(inventory, witness)
    assert [row["status"] for row in report["rows"]] == ["participant_mismatch", "archived_value_differs"]
    assert inventory["rows"][0]["features"][1]["fields"]["overall_elo"]["value"] == 1720


def test_archive_change_during_read_is_detected(tmp_path):
    inventory, witness, snapshot = fixture(tmp_path)
    calls = 0

    def checkpoint():
        nonlocal calls
        calls += 1
        # After the first full hash and both claim queries, before the rehash.
        if calls != 5:
            return
        with sqlite3.connect(snapshot) as conn:
            conn.execute("UPDATE player_elo_history SET rating=rating+1")

    with pytest.raises(ValueError, match="changed during witness"):
        verify_tennis_snapshot_witness(inventory, witness, checkpoint=checkpoint)
    assert calls == 5

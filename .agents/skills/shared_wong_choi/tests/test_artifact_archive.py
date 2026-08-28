from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT.parent))

from shared_wong_choi.artifact_archive import (  # noqa: E402
    ArtifactArchiveError,
    archive_copy,
    artifact_digest,
    mirror_artifact,
    restore_artifact,
)


def test_archive_copy_is_verified_idempotent_and_keeps_source(tmp_path: Path) -> None:
    hot = tmp_path / "hot"
    source = hot / "meeting"
    source.mkdir(parents=True)
    (source / "result.json").write_text('{"winner": 3}\n', encoding="utf-8")
    (source / "report.md").write_text("Gold\n", encoding="utf-8")
    warm = tmp_path / "warm"
    warm.mkdir()
    catalog = tmp_path / "catalog"

    first = archive_copy(
        source,
        warm_root=warm,
        catalog_root=catalog,
        domain="au",
        artifact_class="settled-meeting",
        allowed_roots=[hot],
        created_at="2026-08-27T00:00:00+00:00",
    )
    second = archive_copy(
        source,
        warm_root=warm,
        catalog_root=catalog,
        domain="au",
        artifact_class="settled-meeting",
        allowed_roots=[hot],
        created_at="2026-08-28T00:00:00+00:00",
    )

    assert first["status"] == "copied_verified"
    assert second["status"] == "duplicate"
    assert source.is_dir()
    assert artifact_digest(Path(first["destination"])) == artifact_digest(source)
    assert len(list((catalog / "records").glob("*.json"))) == 1


def test_archive_rejects_source_outside_allowlist_and_corruption(tmp_path: Path) -> None:
    source = tmp_path / "outside.txt"
    source.write_text("evidence", encoding="utf-8")
    warm = tmp_path / "warm"
    warm.mkdir()
    with pytest.raises(ArtifactArchiveError, match="outside configured"):
        archive_copy(
            source,
            warm_root=warm,
            catalog_root=tmp_path / "catalog",
            domain="tennis",
            artifact_class="db-snapshot",
            allowed_roots=[tmp_path / "hot"],
        )

    hot = tmp_path / "hot"
    hot.mkdir()
    allowed = hot / "snapshot.db"
    allowed.write_bytes(b"sqlite")
    result = archive_copy(
        allowed,
        warm_root=warm,
        catalog_root=tmp_path / "catalog",
        domain="tennis",
        artifact_class="db-snapshot",
        allowed_roots=[hot],
    )
    Path(result["destination"]).write_bytes(b"corrupt")
    with pytest.raises(ArtifactArchiveError, match="conflict"):
        archive_copy(
            allowed,
            warm_root=warm,
            catalog_root=tmp_path / "catalog",
            domain="tennis",
            artifact_class="db-snapshot",
            allowed_roots=[hot],
        )


def test_restore_requires_new_destination_and_matches_manifest(tmp_path: Path) -> None:
    hot = tmp_path / "hot"
    hot.mkdir()
    source = hot / "snapshot.db"
    source.write_bytes(b"sqlite-data")
    warm = tmp_path / "warm"
    warm.mkdir()
    result = archive_copy(
        source,
        warm_root=warm,
        catalog_root=tmp_path / "catalog",
        domain="tennis",
        artifact_class="db-snapshot",
        allowed_roots=[hot],
    )
    manifest = Path(result["manifest"])
    restored = tmp_path / "restore" / "snapshot.db"

    verdict = restore_artifact(
        manifest, restored, restored_at="2026-08-27T01:00:00+00:00"
    )

    assert verdict["status"] == "pass"
    assert restored.read_bytes() == b"sqlite-data"
    assert json.loads(Path(verdict["event"]).read_text(encoding="utf-8"))[
        "artifact_id"
    ] == result["artifact_id"]
    with pytest.raises(ArtifactArchiveError, match="already exists"):
        restore_artifact(manifest, restored)
    assert json.loads(manifest.read_text(encoding="utf-8"))["source_removed"] is False


def test_restore_event_failure_removes_destination_for_safe_retry(
    tmp_path: Path, monkeypatch
) -> None:
    import shared_wong_choi.artifact_archive as module

    hot = tmp_path / "hot"
    hot.mkdir()
    source = hot / "snapshot.db"
    source.write_bytes(b"sqlite-data")
    warm = tmp_path / "warm"
    warm.mkdir()
    result = archive_copy(
        source,
        warm_root=warm,
        catalog_root=tmp_path / "catalog",
        domain="tennis",
        artifact_class="db-snapshot",
        allowed_roots=[hot],
    )
    manifest = Path(result["manifest"])
    restored = tmp_path / "restore" / "snapshot.db"

    def deny_event(_: Path, __: dict) -> None:
        raise PermissionError("catalog is read-only")

    monkeypatch.setattr(module, "_write_exclusive_json", deny_event)
    with pytest.raises(ArtifactArchiveError, match="restore transaction failed"):
        restore_artifact(manifest, restored)

    assert not restored.exists()
    assert source.read_bytes() == b"sqlite-data"


def test_unavailable_warm_root_blocks_without_mutating_source(tmp_path: Path) -> None:
    hot = tmp_path / "hot"
    hot.mkdir()
    source = hot / "snapshot.db"
    source.write_bytes(b"keep-me")

    with pytest.raises(ArtifactArchiveError, match="not mounted"):
        archive_copy(
            source,
            warm_root=tmp_path / "not-mounted",
            catalog_root=tmp_path / "catalog",
            domain="tennis",
            artifact_class="db-snapshot",
            allowed_roots=[hot],
        )

    assert source.read_bytes() == b"keep-me"
    assert not (tmp_path / "catalog").exists()


def test_failed_copy_removes_partial_and_keeps_source(
    tmp_path: Path, monkeypatch
) -> None:
    import shared_wong_choi.artifact_archive as module

    hot = tmp_path / "hot"
    hot.mkdir()
    source = hot / "snapshot.db"
    source.write_bytes(b"keep-me")
    warm = tmp_path / "warm"
    warm.mkdir()

    def corrupt_copy(_: Path, target: Path) -> None:
        target.write_bytes(b"corrupt")

    monkeypatch.setattr(module, "_copy", corrupt_copy)
    with pytest.raises(ArtifactArchiveError, match="hash mismatch"):
        archive_copy(
            source,
            warm_root=warm,
            catalog_root=tmp_path / "catalog",
            domain="tennis",
            artifact_class="db-snapshot",
            allowed_roots=[hot],
        )

    assert source.read_bytes() == b"keep-me"
    assert not list(warm.rglob("*.partial-*"))
    assert not (tmp_path / "catalog").exists()


def test_cold_mirror_is_verified_idempotent_and_append_only(tmp_path: Path) -> None:
    hot = tmp_path / "hot"
    hot.mkdir()
    source = hot / "snapshot.db"
    source.write_bytes(b"sqlite-data")
    warm = tmp_path / "warm"
    warm.mkdir()
    result = archive_copy(
        source,
        warm_root=warm,
        catalog_root=tmp_path / "catalog",
        domain="tennis",
        artifact_class="db-snapshot",
        allowed_roots=[hot],
    )
    cold = tmp_path / "cold"
    cold.mkdir()

    first = mirror_artifact(
        Path(result["manifest"]),
        cold_root=cold,
        mirrored_at="2026-08-27T02:00:00+00:00",
    )
    second = mirror_artifact(
        Path(result["manifest"]),
        cold_root=cold,
        mirrored_at="2026-08-28T02:00:00+00:00",
    )

    assert first["status"] == "copied_verified"
    assert second["status"] == "duplicate"
    assert artifact_digest(Path(first["destination"])) == artifact_digest(source)
    assert source.exists()

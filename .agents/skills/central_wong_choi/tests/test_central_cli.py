from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "central_wong_choi.py"
SPEC = importlib.util.spec_from_file_location("central_wong_choi_cli", SCRIPT)
cli = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(cli)


def test_installation_preview_cannot_approve_or_activate(tmp_path, monkeypatch):
    from shared_wong_choi import installation_reconciliation, release_automation

    captured = {}

    def preview(repo, state_root, **kwargs):
        captured.update(repo=repo, state_root=state_root, **kwargs)
        return {"status": "blocked", "installation_authorized": False}

    def forbidden(*args, **kwargs):
        raise AssertionError("read-only preview entered release mutation path")

    monkeypatch.setattr(installation_reconciliation, "preview_installation_reconciliation", preview)
    monkeypatch.setattr(release_automation, "production_roots", lambda: {"au": tmp_path})
    monkeypatch.setattr(cli, "prepare_release", forbidden)
    monkeypatch.setattr(cli, "approve_release", forbidden)
    monkeypatch.setattr(cli, "activate_release", forbidden)
    assert cli.main([
        "--repo", str(tmp_path), "--state-root", str(tmp_path / "state"),
        "reconcile-installation-preview", "--source-commit", "a" * 40,
        "--target-commit", "b" * 40, "--json",
    ]) == 1
    assert captured == {"repo": tmp_path, "state_root": tmp_path / "state",
                        "source_commit": "a" * 40, "target_commit": "b" * 40,
                        "production_roots": {"au": tmp_path}}


def test_release_does_not_try_to_read_approve_only_arguments(tmp_path, monkeypatch):
    monkeypatch.setattr(
        cli,
        "prepare_release",
        lambda *args, **kwargs: {"status": "pushed", "commit": "a" * 40},
    )
    code = cli.main(
        [
            "--repo", str(tmp_path),
            "--state-root", str(tmp_path / "state"),
            "release", "--path", "docs/test.md", "--message", "docs: test",
            "--no-notify",
        ]
    )
    assert code == 0


def test_approve_activate_merges_then_activates(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        cli,
        "approve_release",
        lambda *args, **kwargs: calls.append("approve") or {"status": "merged"},
    )
    monkeypatch.setattr(
        cli,
        "activate_release",
        lambda *args, **kwargs: calls.append("activate") or {"status": "activated"},
    )
    code = cli.main(
        [
            "--repo", str(tmp_path),
            "--state-root", str(tmp_path / "state"),
            "approve", "--commit", "a" * 12, "--actor", "telegram:test",
            "--activate", "--no-notify",
        ]
    )
    assert code == 0
    assert calls == ["approve", "activate"]


def test_corpus_audit_returns_nonzero_when_catalog_is_incomplete(tmp_path, monkeypatch):
    def blocked(**_kwargs):
        raise cli.CorpusCatalogError("known warm artifact is offline")

    monkeypatch.setattr(cli, "resolve_catalog_artifacts", blocked)
    code = cli.main(
        [
            "--repo", str(tmp_path),
            "--state-root", str(tmp_path / "state"),
            "corpus-audit", "--domain", "tennis", "--json",
        ]
    )
    assert code == 1


def test_tennis_active_sqlite_corpus_audit_uses_live_database(tmp_path, monkeypatch):
    active = tmp_path / "tennis_wc.db"
    active.touch()
    captured = {}

    def audit(database, **kwargs):
        captured["database"] = database
        captured.update(kwargs)
        return {"status": "ok", "runtime_snapshot_substitution_allowed": False}

    monkeypatch.setattr(cli, "audit_active_sqlite_corpus", audit)
    code = cli.main(
        [
            "--repo", str(tmp_path),
            "--state-root", str(tmp_path / "state"),
            "corpus-audit", "--domain", "tennis",
            "--active-sqlite", str(active), "--json",
        ]
    )

    assert code == 0
    assert captured["database"] == active
    assert captured["catalog_root"] == tmp_path / "state" / "storage" / "catalog"


def test_active_sqlite_is_rejected_for_non_tennis_domain(tmp_path):
    code = cli.main(
        [
            "--repo", str(tmp_path),
            "--state-root", str(tmp_path / "state"),
            "corpus-audit", "--domain", "nba",
            "--active-sqlite", str(tmp_path / "nba.db"), "--json",
        ]
    )

    assert code == 1

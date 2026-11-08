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


def test_installation_intent_dispatch_does_not_enter_approval_or_activation(tmp_path, monkeypatch):
    from shared_wong_choi import installation_reconciliation, release_automation

    captured = {}
    def create(repo, state_root, **kwargs):
        captured.update(kwargs)
        return {"status": "pending_fresh_gate", "installation_authorized": False}
    def forbidden(*args, **kwargs):
        raise AssertionError("intent creation entered approval or activation")
    monkeypatch.setattr(installation_reconciliation, "create_installation_intent", create)
    monkeypatch.setattr(release_automation, "production_roots", lambda: {"au": tmp_path})
    monkeypatch.setattr(cli, "approve_release", forbidden)
    monkeypatch.setattr(cli, "activate_release", forbidden)
    assert cli.main([
        "--repo", str(tmp_path), "--state-root", str(tmp_path / "state"),
        "reconcile-installation-intent", "--source-commit", "a" * 40,
        "--target-commit", "b" * 40, "--actor", "fixture", "--json",
    ]) == 0
    assert captured["actor"] == "fixture"
    assert captured["target_commit"] == "b" * 40


def test_installation_gate_dispatch_remains_separate_from_approval(tmp_path, monkeypatch):
    from shared_wong_choi import installation_reconciliation, release_automation

    captured = {}
    def gate(repo, state_root, **kwargs):
        captured.update(kwargs)
        return {"status": "full_gate_observed", "installation_authorized": False}
    def forbidden(*args, **kwargs):
        raise AssertionError("installation gate entered approval or activation")
    monkeypatch.setattr(installation_reconciliation, "gate_installation_intent", gate)
    monkeypatch.setattr(release_automation, "production_roots", lambda: {"au": tmp_path})
    monkeypatch.setattr(cli, "approve_release", forbidden)
    monkeypatch.setattr(cli, "activate_release", forbidden)
    assert cli.main([
        "--repo", str(tmp_path), "--state-root", str(tmp_path / "state"),
        "reconcile-installation-gate", "--intent", "a" * 64, "--json",
    ]) == 0
    assert captured["intent_hash"] == "a" * 64



def test_forward_executor_dispatch_never_calls_historical_approval_or_activation(tmp_path, monkeypatch):
    from shared_wong_choi import installation_reconciliation, release_automation
    calls = []
    monkeypatch.setattr(release_automation, "production_roots", lambda: {"au": tmp_path})
    def disabled(*args, **kwargs):
        calls.append(kwargs)
        raise cli.ReleaseError("native execution disabled")
    monkeypatch.setattr(installation_reconciliation, "execute_installation_intent", disabled)
    def forbidden(*args, **kwargs):
        raise AssertionError("forward executor entered historical release path")
    monkeypatch.setattr(cli, "approve_release", forbidden)
    monkeypatch.setattr(cli, "activate_release", forbidden)
    assert cli.main(["--repo", str(tmp_path), "--state-root", str(tmp_path / "state"),
                     "reconcile-installation-execute", "--intent", "a" * 64,
                     "--actor", "fixture", "--json"]) == 1
    assert calls == [{"intent_hash": "a" * 64, "production_roots": {"au": tmp_path},
                      "actor": "fixture"}]



def test_installation_review_request_dispatch_cannot_approve_or_activate(tmp_path, monkeypatch):
    from shared_wong_choi import installation_reconciliation, release_automation
    calls = []
    monkeypatch.setattr(release_automation, 'production_roots', lambda: {'au': tmp_path})
    monkeypatch.setattr(installation_reconciliation, 'create_installation_review_request',
                        lambda *args, **kwargs: calls.append(kwargs) or {
                            'status': 'pending_independent_review', 'gate_authorized': False,
                            'installation_authorized': False})
    def forbidden(*args, **kwargs):
        raise AssertionError('review request entered approval/activation')
    monkeypatch.setattr(cli, 'approve_release', forbidden)
    monkeypatch.setattr(cli, 'activate_release', forbidden)
    assert cli.main(['--repo', str(tmp_path), '--state-root', str(tmp_path/'state'),
                     'reconcile-installation-review-request', '--source-commit', 'a'*40,
                     '--target-commit', 'b'*40, '--actor', 'fixture', '--json']) == 0
    assert calls[0]['source_commit'] == 'a'*40
    assert calls[0]['target_commit'] == 'b'*40



def test_assessment_intake_and_status_never_call_approval_or_activation(tmp_path, monkeypatch):
    import json
    from shared_wong_choi import installation_reconciliation, release_automation
    value = tmp_path/'claim.json'
    value.write_text(json.dumps({'fixture': True}))
    value.chmod(0o600)
    calls = []
    monkeypatch.setattr(release_automation, 'production_roots', lambda: {'au': tmp_path})
    def intake(*args, **kwargs):
        calls.append(('intake', kwargs))
        return {'status':'unverified_assessment','installation_authorized':False}
    monkeypatch.setattr(installation_reconciliation, 'record_installation_assessment', intake)
    monkeypatch.setattr(installation_reconciliation, 'installation_assessment_status',
                        lambda *args, **kwargs: calls.append(('status',kwargs)) or {'installation_authorized':False})
    def forbidden(*args, **kwargs):
        raise AssertionError('assessment entered approval/activation')
    monkeypatch.setattr(cli, 'approve_release', forbidden)
    monkeypatch.setattr(cli, 'activate_release', forbidden)
    prefix = ['--repo',str(tmp_path),'--state-root',str(tmp_path/'state')]
    assert cli.main(prefix+['reconcile-installation-assessment','--request','a'*64,
                           '--assessment-file',str(value),'--actor','fixture','--json']) == 0
    assert cli.main(prefix+['reconcile-installation-assessment-status','--request','a'*64,'--json']) == 0
    assert calls[0][1]['assessment'] == {'fixture':True}
    assert calls[1][0] == 'status'

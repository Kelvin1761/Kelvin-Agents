"""Read-only eligibility must fail before gates, intents or installation."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared_wong_choi import installation_reconciliation as reconciliation
from shared_wong_choi.release_events import ReleaseEventStore


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True,
                          text=True, check=True).stdout.strip()


@pytest.fixture
def history(tmp_path, monkeypatch, request):
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "--bare", str(remote))
    root = tmp_path / "source"
    git(tmp_path, "clone", str(remote), str(root))
    git(root, "config", "user.name", "Reconciliation Test")
    git(root, "config", "user.email", "test@example.invalid")
    installer = root / reconciliation.INSTALLER
    installer.parent.mkdir(parents=True)
    installer.write_text("#!/bin/zsh\nexit 0\n")
    git(root, "add", ".")
    git(root, "commit", "-m", "installer")
    source = git(root, "rev-parse", "HEAD")
    git(root, "branch", "-M", "main")
    git(root, "branch", "own-source")
    (root / "README.md").write_text("new docs\n")
    for relative, data in getattr(request, 'param', {}).items():
        path = root / relative
        if data is None:
            path.unlink()
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    git(root, "add", ".")
    git(root, "commit", "-m", "target")
    target = git(root, "rev-parse", "HEAD")
    git(root, "branch", "target-release")
    git(root, "push", "origin", "main", "own-source", "target-release")
    production = tmp_path / "production"
    git(tmp_path, "clone", "-b", "main", str(remote), str(production))
    state = tmp_path / "state"
    (state / "releases").mkdir(parents=True)
    events = ReleaseEventStore(state / "release-events")
    for commit, branch, activation in ((source, "own-source", "failed"),
                                       (target, "target-release", "succeeded")):
        manifest = {"commit": commit, "release_id": "release:" + commit,
                    "branch": branch, "status": "pushed", "check_exit_code": 0,
                    "push_exit_code": 0, "policy": {"risk": "code", "check": "full"},
                    "gate": {"commit": commit, "check": "full"},
                    "activation_plan": {"installers": [reconciliation.INSTALLER],
                                        "production_sync_domains": list(reconciliation.DOMAINS)}}
        (state / "releases" / (quote(manifest["release_id"], safe="._-") + ".json")).write_text(json.dumps(manifest))
        approval = events.append(release_id=manifest["release_id"], commit=commit,
                                 event_type="approval_granted", actor="test")
        events.append(release_id=manifest["release_id"], commit=commit,
                      event_type="merged", actor="test",
                      detail={"approval_event": approval["content_hash"]})
        detail = {"verification": [{"domain": domain, "status": "aligned",
                                    "target_commit": commit} for domain in reconciliation.DOMAINS]}
        events.append(release_id=manifest["release_id"], commit=commit,
                      event_type="activation_" + activation, actor="test", detail=detail)
    monkeypatch.setattr(reconciliation, "OWN_FAILED_RELEASES", frozenset({source}))
    return root, production, state, source, target


def preview(history):
    root, production, state, source, target = history
    return reconciliation.preview_installation_reconciliation(
        root, state, source_commit=source, target_commit=target,
        production_roots={domain: production for domain in reconciliation.DOMAINS})


def test_preview_is_repeatable_and_never_writes_state_or_old_manifests(history):
    root, production, state, _, target = history
    before = {p.relative_to(state): p.read_bytes() for p in state.rglob("*") if p.is_file()}
    first = preview(history)
    assert first == preview(history)
    assert first["status"] == "eligible_for_fresh_gate"
    assert first["target_commit"] == target
    assert first["activation"] == "not_started"
    assert {p.relative_to(state): p.read_bytes() for p in state.rglob("*") if p.is_file()} == before
    assert git(root, "status", "--porcelain") == ""
    assert git(production, "rev-parse", "HEAD") == target


def test_installer_change_blocks_before_any_intent(history):
    root, _, _, source, _ = history
    (root / reconciliation.INSTALLER).write_text("#!/bin/zsh\necho changed\n")
    git(root, "add", reconciliation.INSTALLER)
    git(root, "commit", "-m", "changed installer")
    target = git(root, "rev-parse", "HEAD")
    # Byte comparison is independently exposed so unapproved new main cannot
    # hide an installer change behind a different earlier rejection.
    assert reconciliation.changed_installation_dependencies(root, source, target) == [reconciliation.INSTALLER]


@pytest.mark.parametrize("relative", [
    ".agents/skills/nba/nba_daily_auto/new_dependency.py",
    ".agents/skills/central_wong_choi/launchd/new.plist.template",
    ".agents/skills/shared_wong_choi/research_native.py",
    "tennis-wong-choi/scripts/new_installer.sh",
    "tennis-wong-choi/src/tennis_wc/native_dependency.py",
    ".agents/skills/au_racing/au_wong_choi_auto/scripts/au_racing_engine/scoring.py",
    "tennis-wong-choi/launchd/new.plist.template",
    "wongchoi_paths.py",
])
def test_new_dependency_is_not_omitted_from_inventory(history, relative):
    root, _, _, source, _ = history
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("new\n")
    git(root, "add", relative)
    git(root, "commit", "-m", "new dependency")
    assert relative in reconciliation.changed_installation_dependencies(root, source, git(root, "rev-parse", "HEAD"))


@pytest.mark.parametrize("change", ["main", "branch", "production", "dirty", "foreign", "missing-domain"])
def test_moved_or_unowned_state_is_blocked(history, change):
    root, production, state, source, target = history
    roots = {domain: production for domain in reconciliation.DOMAINS}
    if change == "main":
        git(root, "push", "--force", "origin", source + ":main")
    elif change == "branch":
        git(root, "push", "--force", "origin", source + ":target-release")
    elif change == "production":
        git(production, "checkout", "--detach", source)
    elif change == "dirty":
        (production / "unrelated.txt").write_text("concurrent write\n")
    elif change == "foreign":
        source = target
    else:
        roots.pop("nba")
    result = reconciliation.preview_installation_reconciliation(
        root, state, source_commit=source, target_commit=target, production_roots=roots)
    assert result["status"] == "blocked"
    assert result["activation"] == "not_started"


@pytest.mark.parametrize("defect", ["main-membership-only", "bad-link", "no-deployment", "model", "not-full"])
def test_target_requires_real_linked_provenance(history, defect):
    _, _, state, _, target = history
    manifest_path = reconciliation._load_release(state / "releases", target)[0]
    manifest = json.loads(manifest_path.read_text())
    folder = state / "release-events" / ("release%3A" + target)
    if defect == "main-membership-only":
        for p in folder.glob("*.json"):
            p.unlink()
    elif defect == "bad-link":
        events = ReleaseEventStore(state / "release-events")
        events.append(release_id=manifest["release_id"], commit=target,
                      event_type="merged", actor="test", detail={"approval_event": "unlinked"})
    elif defect == "no-deployment":
        events = ReleaseEventStore(state / "release-events")
        events.append(release_id=manifest["release_id"], commit=target,
                      event_type="activation_failed", actor="test")
    elif defect == "model":
        manifest["policy"]["risk"] = "model"
        manifest_path.write_text(json.dumps(manifest))
    else:
        manifest["gate"]["check"] = "quick"
        manifest_path.write_text(json.dumps(manifest))
    assert preview(history)["status"] == "blocked"


def test_preview_cannot_be_misread_as_an_approval_or_gate_receipt(history):
    result = preview(history)
    assert result["fresh_full_gate_required"] is True
    assert result["independent_approval_required"] is True
    assert result["installation_authorized"] is False
    assert "gate_receipt" not in result


def test_failed_production_status_probe_cannot_mean_clean(history, monkeypatch):
    original = reconciliation._run

    def failing_status(root, *args, **kwargs):
        if args[:2] == ("git", "status"):
            return subprocess.CompletedProcess(args, 128, "", "status unavailable")
        return original(root, *args, **kwargs)

    monkeypatch.setattr(reconciliation, "_run", failing_status)
    assert preview(history)["status"] == "blocked"


@pytest.mark.parametrize("defect", ["invalid-json", "bad-hash", "foreign-identity", "wrong-schema"])
def test_corrupt_or_foreign_event_cannot_disappear_from_provenance(history, defect):
    _, _, state, _, target = history
    events = ReleaseEventStore(state / "release-events")
    event = events.append(release_id="release:" + target, commit=target,
                          event_type="approval_rejected", actor="test")
    path = Path(event["path"])
    if defect == "invalid-json":
        path.write_text("broken rejection")
    else:
        value = json.loads(path.read_text())
        if defect == "bad-hash":
            value["content_hash"] = "0" * 64
        else:
            from shared_wong_choi.release_events import _hash
            value.pop("content_hash")
            if defect == "foreign-identity":
                value["release_id"] = "some-other-release"
            else:
                value["schema_version"] = "some-other-schema"
            value["content_hash"] = _hash(value)
        path.write_text(json.dumps(value))
    result = preview(history)
    assert result["status"] == "blocked"
    assert "invalid release event" in result["error"]


def test_renamed_hash_valid_rejection_cannot_reorder_approval(history):
    _, _, state, _, target = history
    event = ReleaseEventStore(state / "release-events").append(
        release_id="release:" + target, commit=target,
        event_type="approval_rejected", actor="test")
    path = Path(event["path"])
    path.rename(path.with_name("0000-" + path.name))
    result = preview(history)
    assert result["status"] == "blocked"
    assert "invalid release event" in result["error"]


def test_intent_binds_target_and_keeps_existing_evidence_immutable(history):
    root, production, state, source, target = history
    before = {p.relative_to(state): p.read_bytes() for p in state.rglob("*") if p.is_file()}
    result = reconciliation.create_installation_intent(
        root, state, source_commit=source, target_commit=target,
        production_roots={domain: production for domain in reconciliation.DOMAINS},
        actor="test")
    assert result["status"] == "pending_fresh_gate"
    assert result["installation_authorized"] is False
    assert result["rollback_commit"] == target
    assert set(result["manifest_hashes"]) == {source, target}
    saved = json.loads(Path(result["path"]).read_text())
    digest = saved.pop("content_hash")
    assert digest == reconciliation._hash(saved)
    assert all((state / path).read_bytes() == data for path, data in before.items())


def test_blocked_intent_leaves_no_intent_directory(history):
    root, production, state, source, _ = history
    with pytest.raises(reconciliation.ReleaseError):
        reconciliation.create_installation_intent(
            root, state, source_commit=source, target_commit="0" * 40,
            production_roots={domain: production for domain in reconciliation.DOMAINS},
            actor="test")
    assert not (state / "installation-intents").exists()


def test_intent_rejects_symlinked_destination(history, tmp_path):
    root, production, state, source, target = history
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (state / "installation-intents").symlink_to(elsewhere)
    with pytest.raises(reconciliation.ReleaseError):
        reconciliation.create_installation_intent(
            root, state, source_commit=source, target_commit=target,
            production_roots={domain: production for domain in reconciliation.DOMAINS},
            actor="test")
    assert list(elsewhere.iterdir()) == []


def intent_arguments(history):
    root, production, state, source, target = history
    roots = {domain: production for domain in reconciliation.DOMAINS}
    intent = reconciliation.create_installation_intent(
        root, state, source_commit=source, target_commit=target,
        production_roots=roots, actor="fixture")
    return root, state, roots, intent


def test_installation_gate_uses_clean_full_gate_and_records_no_authority(history, monkeypatch):
    import time
    from shared_wong_choi import release_approval
    from shared_wong_choi.release_gate import GateReceipt
    root, state, roots, intent = intent_arguments(history)
    calls = []
    def gate(repo, commit, check):
        calls.append((repo, commit, check))
        return GateReceipt(commit, check, "fixture", time.monotonic(), 0.1, "fixture.log")
    monkeypatch.setattr(release_approval, "_run_gate_in_clean_clone", gate)
    result = reconciliation.gate_installation_intent(
        root, state, intent_hash=intent["content_hash"], production_roots=roots)
    assert calls == [(root, intent["target_commit"], "full")]
    assert result["status"] == "full_gate_observed"
    assert result["installation_authorized"] is False
    assert result["independent_approval_required"] is True
    assert Path(result["path"]).is_file()
    assert json.loads(Path(intent["path"]).read_text())["status"] == "pending_fresh_gate"


def test_changed_manifest_bytes_block_before_gate(history, monkeypatch):
    from shared_wong_choi import release_approval
    root, state, roots, intent = intent_arguments(history)
    manifest = reconciliation._load_release(state / "releases", intent["target_commit"])[0]
    manifest.write_bytes(manifest.read_bytes() + b"\n")
    def forbidden(*args):
        pytest.fail("stale intent invoked a gate")
    monkeypatch.setattr(release_approval, "_run_gate_in_clean_clone", forbidden)
    with pytest.raises(reconciliation.ReleaseError):
        reconciliation.gate_installation_intent(
            root, state, intent_hash=intent["content_hash"], production_roots=roots)
    assert not (state / "installation-gates").exists()


def test_serialized_gate_receipt_cannot_satisfy_installation_gate(history, monkeypatch):
    from shared_wong_choi import release_approval
    root, state, roots, intent = intent_arguments(history)
    monkeypatch.setattr(release_approval, "_run_gate_in_clean_clone",
                        lambda *args: {"commit": intent["target_commit"], "check": "full"})
    with pytest.raises(reconciliation.ReleaseError):
        reconciliation.gate_installation_intent(
            root, state, intent_hash=intent["content_hash"], production_roots=roots)
    assert not (state / "installation-gates").exists()


@pytest.mark.parametrize("damage", ["symlink", "extra-field", "duplicate-field", "bad-mode"])
def test_damaged_intent_is_rejected(history, tmp_path, damage):
    root, state, roots, intent = intent_arguments(history)
    path = Path(intent["path"])
    if damage == "symlink":
        other = tmp_path / "foreign"
        other.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(other)
    elif damage == "extra-field":
        value = json.loads(path.read_text())
        value["approved"] = True
        path.write_text(json.dumps(value))
    elif damage == "duplicate-field":
        path.write_text('{"actor":"duplicate",' + path.read_text().lstrip()[1:])
    else:
        path.chmod(0o666)
    with pytest.raises((reconciliation.ReleaseError, OSError)):
        reconciliation.load_installation_intent(
            root, state, intent_hash=intent["content_hash"], production_roots=roots)


@pytest.fixture
def executor(history, monkeypatch):
    import time
    from shared_wong_choi import release_approval, release_activation, deployment_verify
    from shared_wong_choi.release_gate import GateReceipt
    root, state, roots, intent = intent_arguments(history)
    monkeypatch.setenv("WONGCHOI_CONTROL_STATE_ROOT", str(state))
    monkeypatch.setattr(reconciliation, "__file__",
                        str(root / ".agents/skills/shared_wong_choi/installation_reconciliation.py"))
    # Orchestration fixture only: there is no production review authorization.
    monkeypatch.setattr(reconciliation, "_require_installation_review", lambda intent: None)
    monkeypatch.setattr(GateReceipt, "reusable", lambda self, *args: True)
    calls = []
    def gate(repo, commit, check):
        calls.append(check)
        return GateReceipt(commit, check, "fixture", time.monotonic(), 0.1, "fixture.log")
    monkeypatch.setattr(release_approval, "_run_gate_in_clean_clone", gate)
    def native(repo, *args, timeout, lease_fd=None):
        from shared_wong_choi.runtime_cutover_lease import _validate, lease_path, _try_lock
        import fcntl, os
        _validate(lease_fd, lease_path())
        probe = os.open(lease_path(), os.O_RDWR)
        try:
            assert not _try_lock(probe, fcntl.LOCK_SH)
        finally:
            os.close(probe)
        mode = args[2]
        calls.append((mode, timeout))
        if mode == "--snapshot":
            Path(args[3]).mkdir()
            (Path(args[3]) / "evidence").write_text("retain")
        return subprocess.CompletedProcess(args, 0, "isolated native observer", "")
    monkeypatch.setattr(release_activation, "_run_installer", native)
    monkeypatch.setattr(deployment_verify, "verify_deployment", lambda *args: {
        "safe_to_activate": True, "status": "aligned", "target_commit": intent["target_commit"]})
    return root, state, roots, intent, calls, native


def execute(executor):
    root, state, roots, intent, _, _ = executor
    return reconciliation.execute_installation_intent(
        root, state, intent_hash=intent["content_hash"], production_roots=roots, actor="fixture")


def test_executor_holds_kernel_lease_and_uses_same_snapshot_without_git_reset(executor):
    root, state, roots, intent, calls, _ = executor
    manifests = {p: p.read_bytes() for p in (state / "releases").iterdir()}
    result = execute(executor)
    assert result["status"] == "installed_verified"
    assert result["native_acceptance_verified"] is True
    assert calls == ["full", "quick", ("--snapshot", 120),
                     ("--install-from-snapshot", 300), ("--status", 60), ("--acceptance-status", 60)]
    assert git(root, "rev-parse", "HEAD") == intent["target_commit"]
    assert git(next(iter(roots.values())), "rev-parse", "HEAD") == intent["target_commit"]
    assert manifests == {p: p.read_bytes() for p in manifests}
    assert (Path(result["snapshot"]) / "evidence").read_text() == "retain"
    before = list(calls)
    with pytest.raises(reconciliation.ReleaseError, match="already claimed"):
        execute(executor)
    assert calls == before


def test_executor_failed_install_restores_same_snapshot_and_preserves_claim(executor, monkeypatch):
    from shared_wong_choi import release_activation
    root, state, roots, intent, calls, native = executor
    snapshots = []
    def failing(repo, *args, **kwargs):
        mode = args[2]
        if mode in {"--install-from-snapshot", "--restore"}:
            snapshots.append(args[3])
        result = native(repo, *args, **kwargs)
        if mode == "--install-from-snapshot":
            return subprocess.CompletedProcess(args, 124, "owned timeout", "")
        return result
    monkeypatch.setattr(release_activation, "_run_installer", failing)
    with pytest.raises(reconciliation.ReleaseError, match="recovery restored"):
        execute(executor)
    assert len(snapshots) == 2 and snapshots[0] == snapshots[1]
    attempt = state / "installation-attempts" / intent["content_hash"]
    records = [json.loads(p.read_text()) for p in attempt.glob("*.json")]
    assert records[-1] if records else False
    assert any(r["status"] == "failed" and r["recovery"] == "restored" for r in records)
    assert (Path(snapshots[0]) / "evidence").is_file()
    assert ("--restore", 300) in calls


def test_executor_serialized_gate_cannot_reach_native(executor, monkeypatch):
    from shared_wong_choi import release_approval
    monkeypatch.setattr(release_approval, "_run_gate_in_clean_clone", lambda *args: {})
    with pytest.raises(reconciliation.ReleaseError, match="full installation receipt"):
        execute(executor)
    assert executor[4] == []
    assert not (executor[1] / "installation-attempts").exists()


def test_executor_rechecks_evidence_after_independent_approval(executor, monkeypatch):
    from shared_wong_choi import release_approval
    root, state, _, intent, calls, _ = executor
    original = release_approval._run_gate_in_clean_clone
    def changed(*args):
        result = original(*args)
        if args[-1] == "quick":
            path, _ = reconciliation._load_release(state / "releases", intent["target_commit"])
            path.write_bytes(path.read_bytes() + b"\n")
        return result
    monkeypatch.setattr(release_approval, "_run_gate_in_clean_clone", changed)
    with pytest.raises(reconciliation.ReleaseError):
        execute(executor)
    assert calls == ["full", "quick"]
    assert not (state / "installation-attempts").exists()


def test_executor_restore_exception_retains_unresolved_claim(executor, monkeypatch):
    from shared_wong_choi import release_activation
    _, state, _, intent, _, native = executor
    def failing(repo, *args, **kwargs):
        if args[2] == "--restore":
            raise OSError("owned restore spawn failed")
        result = native(repo, *args, **kwargs)
        return subprocess.CompletedProcess(args, 1 if args[2] == "--install-from-snapshot" else 0,
                                           result.stdout, result.stderr)
    monkeypatch.setattr(release_activation, "_run_installer", failing)
    with pytest.raises(reconciliation.ReleaseError, match="recovery blocked"):
        execute(executor)
    attempt = state / "installation-attempts" / intent["content_hash"]
    assert (attempt / "native-snapshot/evidence").is_file()
    assert any(json.loads(p.read_text()).get("recovery_error") == "OSError: owned restore spawn failed"
               for p in attempt.glob("*.json"))


def test_native_runner_preserves_actual_exclusive_descriptor(tmp_path, monkeypatch):
    from shared_wong_choi.release_activation import _run_installer
    from shared_wong_choi.runtime_cutover_lease import cutover_lease
    monkeypatch.setenv("WONGCHOI_CONTROL_STATE_ROOT", str(tmp_path / "control"))
    module_root = Path(reconciliation.__file__).resolve().parents[1]
    program = ("import sys; sys.path.insert(0, sys.argv[1]); "
               "from shared_wong_choi.runtime_cutover_lease import inherited_lease,lease_path; "
               "inherited_lease('exclusive',lease_path()); print('exclusive verified')")
    with cutover_lease("exclusive") as fd:
        result = _run_installer(tmp_path, sys.executable, "-c", program, str(module_root),
                                timeout=10, lease_fd=fd)
    assert result.returncode == 0, result.stderr
    assert "exclusive verified" in result.stdout


def test_live_executor_is_disabled_without_exact_source_review(history, monkeypatch):
    root, state, roots, intent = intent_arguments(history)
    monkeypatch.setenv("WONGCHOI_CONTROL_STATE_ROOT", str(state))
    monkeypatch.setattr(reconciliation, "__file__",
                        str(root / ".agents/skills/shared_wong_choi/installation_reconciliation.py"))
    with pytest.raises(reconciliation.ReleaseError, match="native execution disabled"):
        reconciliation.execute_installation_intent(root, state, intent_hash=intent["content_hash"],
                                                   production_roots=roots, actor="fixture")
    assert not (state / "installation-attempts").exists()


def test_executor_expired_receipt_after_snapshot_blocks_before_install(executor, monkeypatch):
    from shared_wong_choi import release_activation
    from shared_wong_choi.release_gate import GateReceipt
    _, state, _, intent, calls, native = executor
    expired = [False]
    monkeypatch.setattr(GateReceipt, "reusable", lambda *args: not expired[0])
    def snapshot(repo, *args, **kwargs):
        result = native(repo, *args, **kwargs)
        if args[2] == "--snapshot":
            expired[0] = True
        return result
    monkeypatch.setattr(release_activation, "_run_installer", snapshot)
    with pytest.raises(reconciliation.ReleaseError, match="recovery not_needed"):
        execute(executor)
    assert calls == ["full", "quick", ("--snapshot", 120)]
    attempt = state / "installation-attempts" / intent["content_hash"]
    assert (attempt / "native-snapshot/evidence").is_file()


def test_executor_remote_outage_does_not_prevent_owned_native_restore(executor, monkeypatch):
    from shared_wong_choi import release_activation
    _, _, _, _, calls, native = executor
    def failing(repo, *args, **kwargs):
        result = native(repo, *args, **kwargs)
        if args[2] == "--install-from-snapshot":
            def unavailable(*args, **kwargs):
                raise reconciliation.ReleaseError("remote unavailable")
            monkeypatch.setattr(reconciliation, "_remote", unavailable)
            return subprocess.CompletedProcess(args, 124, "owned timeout", "")
        return result
    monkeypatch.setattr(release_activation, "_run_installer", failing)
    with pytest.raises(reconciliation.ReleaseError, match="recovery restored"):
        execute(executor)
    assert calls[-1] == ("--restore", 300)



def test_executor_acceptance_failure_restores_without_claiming_verified(executor, monkeypatch):
    from shared_wong_choi import release_activation
    _, state, _, intent, calls, native = executor
    def rejected(repo, *args, **kwargs):
        result = native(repo, *args, **kwargs)
        return subprocess.CompletedProcess(args, 1 if args[2] == "--acceptance-status" else 0,
                                           result.stdout, "owned missing receipt")
    monkeypatch.setattr(release_activation, "_run_installer", rejected)
    with pytest.raises(reconciliation.ReleaseError, match="recovery restored"):
        execute(executor)
    records = [json.loads(p.read_text()) for p in
               (state / "installation-attempts" / intent["content_hash"]).glob("*.json")]
    assert not any(r["status"] == "installed_verified" for r in records)
    assert calls[-1] == ("--restore", 300)



def review_request(history):
    root, production, state, source, target = history
    return reconciliation.create_installation_review_request(
        root, state, source_commit=source, target_commit=target,
        production_roots={domain: production for domain in reconciliation.DOMAINS}, actor='fixture')


@pytest.mark.parametrize('history', [{
    reconciliation.INSTALLER: b'#!/bin/zsh\nexit 75\n',
    '.agents/skills/shared_wong_choi/file with\nnewline.bin': b'\0\xff\x80native-bytes',
}], indirect=True)
def test_review_request_exposes_changed_bytes_without_gate_or_intent_authority(history, monkeypatch):
    from shared_wong_choi import release_approval, release_activation
    root, _, state, source, target = history
    before = {p: p.read_bytes() for p in state.rglob('*.json')}
    def forbidden(*args, **kwargs):
        pytest.fail('review request entered gate/native path')
    monkeypatch.setattr(release_approval, '_run_gate_in_clean_clone', forbidden)
    monkeypatch.setattr(release_activation, '_run_installer', forbidden)
    result = review_request(history)
    assert result['status'] == 'pending_independent_review'
    assert result['installation_authorized'] is False
    assert result['gate_authorized'] is False
    assert result['execution_intent_created'] is False
    assert result['assessment_authenticated'] is False
    assert result['intent_binding_hash'] == reconciliation._hash(result['intent_binding'])
    entries = {entry['path']: entry for entry in result['material']['dependencies']}
    assert entries[reconciliation.INSTALLER]['change'] == 'M'
    binary = entries['.agents/skills/shared_wong_choi/file with\nnewline.bin']
    assert binary['before'] is None
    assert binary['after']['sha256'] == reconciliation.hashlib.sha256(b'\0\xff\x80native-bytes').hexdigest()
    assert result['material']['patch_bytes'] > 0
    assert {p: p.read_bytes() for p in before} == before
    assert not (state / 'installation-intents').exists()
    assert preview(history)['status'] == 'blocked'
    assert 'independent review required' in preview(history)['error']
    with pytest.raises((reconciliation.ReleaseError, OSError)):
        reconciliation.load_installation_intent(root, state, intent_hash=result['content_hash'],
            production_roots={domain: history[1] for domain in reconciliation.DOMAINS})


@pytest.mark.parametrize('history', [{reconciliation.INSTALLER: b'#!/bin/zsh\nexit 75\n'}], indirect=True)
def test_review_request_cannot_waive_target_deployment_provenance(history):
    root, _, state, _, target = history
    path, manifest = reconciliation._load_release(state / 'releases', target)
    events = ReleaseEventStore(state / 'release-events')
    events.append(release_id=manifest['release_id'], commit=target,
                  event_type='activation_failed', actor='fixture', detail={})
    with pytest.raises(reconciliation.ReleaseError, match='successful deployment provenance'):
        review_request(history)
    assert not (state / 'installation-review-requests').exists()


def test_review_request_rechecks_manifest_bytes_before_publication(history, monkeypatch):
    root, _, state, _, target = history
    original = reconciliation.installation_review_material
    def changed(*args):
        material = original(*args)
        path, _ = reconciliation._load_release(state / 'releases', target)
        path.write_bytes(path.read_bytes() + b'\n')
        return material
    monkeypatch.setattr(reconciliation, 'installation_review_material', changed)
    with pytest.raises(reconciliation.ReleaseError, match='bindings changed'):
        review_request(history)
    assert not (state / 'installation-review-requests').exists()


def test_review_inventory_captures_mode_only_change_and_deletion(history):
    root, _, _, source, target = history
    (root / reconciliation.INSTALLER).chmod(0o755)
    git(root, 'add', reconciliation.INSTALLER)
    git(root, 'commit', '-m', 'fixture executable mode')
    changed = git(root, 'rev-parse', 'HEAD')
    entry = reconciliation.installation_review_material(root, source, changed)['dependencies'][0]
    assert entry['before']['mode'] == '100644'
    assert entry['after']['mode'] == '100755'
    assert entry['before']['sha256'] == entry['after']['sha256']
    (root / reconciliation.INSTALLER).unlink()
    git(root, 'add', reconciliation.INSTALLER)
    git(root, 'commit', '-m', 'fixture delete')
    entry = reconciliation.installation_review_material(root, source, git(root, 'rev-parse', 'HEAD'))['dependencies'][0]
    assert entry['change'] == 'D' and entry['after'] is None


def test_review_request_does_not_claim_authenticated_assessment_or_execution(history):
    result = review_request(history)
    assert result['material']['dependencies'] == []
    assert result['material']['patch_bytes'] == 0
    assert result['material']['source_tree'] != result['material']['target_tree']
    with pytest.raises(reconciliation.ReleaseError, match='native execution disabled'):
        reconciliation._require_installation_review(result)



@pytest.mark.parametrize('history', [{
    '.agents/skills/shared_wong_choi/module[ab].py': b'literal inventoried bytes\n',
    '.agents/skills/shared_wong_choi/modulea.py': b'decoy inventoried bytes\n',
}, {':(exclude)shadow.py': b'literal pathspec magic\n', 'shadow.py': b'decoy\n'}], indirect=True)
def test_review_patch_digest_uses_literal_git_path_identity(history):
    root, _, _, source, target = history
    material = reconciliation.installation_review_material(root, source, target)
    paths = [entry['path'] for entry in material['dependencies']]
    expected = reconciliation._review_git_bytes(root, '--literal-pathspecs', 'diff', '--binary',
        '--full-index', '--no-ext-diff', '--no-textconv', '--no-renames', source, target, '--', *paths)
    assert material['patch_sha256'] == reconciliation.hashlib.sha256(expected).hexdigest()

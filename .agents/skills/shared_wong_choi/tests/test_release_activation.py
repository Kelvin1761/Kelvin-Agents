from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT.parent))

from shared_wong_choi.release_activation import (  # noqa: E402
    _command_failure,
    _rollback_checkout,
    _sync_checkout,
    activate_release,
)
from shared_wong_choi.release_approval import approve_release  # noqa: E402
from shared_wong_choi.release_events import ReleaseEventStore  # noqa: E402
from shared_wong_choi.release_manager import ReleaseError, prepare_release  # noqa: E402


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, text=True, capture_output=True, check=True
    )
    return result.stdout.strip()


@pytest.fixture
def release_setup(tmp_path: Path) -> tuple[Path, Path, Path, dict]:
    remote = tmp_path / "remote.git"
    repo = tmp_path / "repo"
    git(tmp_path, "init", "--bare", str(remote))
    git(tmp_path, "clone", str(remote), str(repo))
    git(repo, "config", "user.name", "Activation Test")
    git(repo, "config", "user.email", "wc@example.test")
    gate = repo / "檢查.sh"
    gate.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    os.chmod(gate, 0o755)
    wrapper = repo / ".agents/skills/nba/nba_daily_auto/run_nba_daily_schedule.sh"
    wrapper.parent.mkdir(parents=True)
    wrapper.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    os.chmod(wrapper, 0o755)
    git(repo, "add", ".")
    git(repo, "commit", "-m", "base")
    git(repo, "branch", "-M", "main")
    git(repo, "push", "-u", "origin", "main")
    production = tmp_path / "production"
    git(tmp_path, "clone", str(remote), str(production))

    wrapper.write_text("#!/bin/sh\necho updated\n", encoding="utf-8")
    state = tmp_path / "state"
    release = prepare_release(
        repo,
        paths=[".agents/skills/nba/nba_daily_auto/run_nba_daily_schedule.sh"],
        message="fix: nba wrapper",
        state_root=state / "releases",
        notify=False,
    )
    approve_release(
        repo,
        state,
        selector=release["commit"][:12],
        actor="telegram:kelvin",
        notify=False,
    )
    return repo, production, state, release


def _verify(_repo: Path, target: Path, domain: str) -> dict:
    return {
        "safe_to_activate": True,
        "status": "aligned",
        "target_commit": git(target, "rev-parse", "HEAD"),
        "domain": domain,
    }


def test_command_failure_preserves_bounded_installer_diagnostics() -> None:
    result = subprocess.CompletedProcess(
        args=["installer"], returncode=7, stdout="partial output\n", stderr="boom\n"
    )
    error = _command_failure("installer failed", result)
    assert str(error) == "installer failed (exit 7); stdout=partial output; stderr=boom"


def test_activation_fast_forwards_and_verifies_production(
    release_setup, monkeypatch
) -> None:
    repo, production, state, release = release_setup
    verifier_sources = []

    def verify(source: Path, target: Path, domain: str) -> dict:
        verifier_sources.append(source)
        assert source != repo
        assert source != target
        assert git(source, "rev-parse", "HEAD") == release["commit"]
        return _verify(source, target, domain)

    monkeypatch.setattr(
        "shared_wong_choi.release_activation.verify_deployment", verify
    )
    result = activate_release(
        repo,
        state,
        selector=release["commit"][:12],
        actor="telegram:kelvin",
        production_roots={"nba": production},
        notify=False,
    )
    assert result["status"] == "activated"
    assert git(production, "rev-parse", "HEAD") == release["commit"]
    assert result["verification"] == [
        {"domain": "nba", "status": "aligned", "target_commit": release["commit"]}
    ]
    assert len(verifier_sources) == 1


def test_activation_is_idempotent(release_setup, monkeypatch) -> None:
    repo, production, state, release = release_setup
    monkeypatch.setattr(
        "shared_wong_choi.release_activation.verify_deployment", _verify
    )
    first = activate_release(
        repo,
        state,
        selector=release["commit"][:12],
        actor="telegram:kelvin",
        production_roots={"nba": production},
        notify=False,
    )
    second = activate_release(
        repo,
        state,
        selector=release["commit"][:12],
        actor="telegram:kelvin",
        production_roots={"nba": production},
        notify=False,
    )
    assert first["status"] == "activated"
    assert second["status"] == "already_active"


def test_unrelated_dirty_production_blocks_activation(release_setup) -> None:
    repo, production, state, release = release_setup
    (production / "README.md").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(ReleaseError, match="unrelated dirty"):
        activate_release(
            repo,
            state,
            selector=release["commit"][:12],
            actor="telegram:kelvin",
            production_roots={"nba": production},
            notify=False,
        )


def test_unrelated_dirty_production_blocks_when_already_on_candidate(
    release_setup, monkeypatch
) -> None:
    repo, production, state, release = release_setup
    monkeypatch.setattr(
        "shared_wong_choi.release_activation.verify_deployment", _verify
    )
    activated = activate_release(
        repo,
        state,
        selector=release["commit"][:12],
        actor="telegram:kelvin",
        production_roots={"nba": production},
        notify=False,
    )
    assert activated["status"] == "activated"

    # Exercise the sync primitive directly because the immutable successful
    # activation event correctly makes activate_release itself idempotent.
    (production / "README.md").write_text("concurrent write\n", encoding="utf-8")
    with pytest.raises(ReleaseError, match="unrelated dirty"):
        _sync_checkout(production, release["commit"])


def test_post_sync_verifier_failure_rolls_back_production(
    release_setup, monkeypatch
) -> None:
    repo, production, state, release = release_setup
    before = git(production, "rev-parse", "HEAD")

    def reject(_source: Path, target: Path, domain: str) -> dict:
        assert git(target, "rev-parse", "HEAD") == release["commit"]
        return {
            "safe_to_activate": False,
            "status": "different",
            "target_commit": release["commit"],
            "domain": domain,
        }

    monkeypatch.setattr(
        "shared_wong_choi.release_activation.verify_deployment", reject
    )
    with pytest.raises(ReleaseError, match="rollback complete"):
        activate_release(
            repo,
            state,
            selector=release["commit"][:12],
            actor="telegram:kelvin",
            production_roots={"nba": production},
            notify=False,
        )

    assert git(production, "rev-parse", "HEAD") == before
    events = ReleaseEventStore(state / "release-events").list(release["release_id"])
    failure = next(item for item in events if item["event_type"] == "activation_failed")
    assert failure["detail"]["rollback_status"] == "succeeded"
    assert failure["detail"]["rollback"][0]["after"] == before


def test_unexpected_verifier_exception_also_rolls_back(
    release_setup, monkeypatch
) -> None:
    repo, production, state, release = release_setup
    before = git(production, "rev-parse", "HEAD")

    def crash(_source: Path, target: Path, _domain: str) -> dict:
        assert git(target, "rev-parse", "HEAD") == release["commit"]
        raise RuntimeError("verifier crashed")

    monkeypatch.setattr(
        "shared_wong_choi.release_activation.verify_deployment", crash
    )
    with pytest.raises(ReleaseError, match="rollback complete"):
        activate_release(
            repo,
            state,
            selector=release["commit"][:12],
            actor="telegram:kelvin",
            production_roots={"nba": production},
            notify=False,
        )

    assert git(production, "rev-parse", "HEAD") == before
    events = ReleaseEventStore(state / "release-events").list(release["release_id"])
    failure = next(item for item in events if item["event_type"] == "activation_failed")
    assert failure["detail"]["error"] == "RuntimeError: verifier crashed"
    assert failure["detail"]["rollback_status"] == "succeeded"


def test_concurrent_unrelated_write_blocks_rollback_without_erasing_it(
    release_setup, monkeypatch
) -> None:
    repo, production, state, release = release_setup

    def dirty_then_reject(_source: Path, target: Path, domain: str) -> dict:
        (target / "README.md").write_text("concurrent operator write\n", encoding="utf-8")
        return {
            "safe_to_activate": False,
            "status": "different",
            "target_commit": release["commit"],
            "domain": domain,
        }

    monkeypatch.setattr(
        "shared_wong_choi.release_activation.verify_deployment", dirty_then_reject
    )
    with pytest.raises(ReleaseError, match="rollback incomplete"):
        activate_release(
            repo,
            state,
            selector=release["commit"][:12],
            actor="telegram:kelvin",
            production_roots={"nba": production},
            notify=False,
        )

    assert git(production, "rev-parse", "HEAD") == release["commit"]
    assert (production / "README.md").read_text(encoding="utf-8") == (
        "concurrent operator write\n"
    )
    events = ReleaseEventStore(state / "release-events").list(release["release_id"])
    failure = next(item for item in events if item["event_type"] == "activation_failed")
    assert failure["detail"]["rollback_status"] == "blocked"
    assert "unrelated production writes" in failure["detail"]["rollback_errors"][0]


def test_concurrent_clean_production_advance_blocks_rollback(release_setup, monkeypatch):
    repo, production, state, release = release_setup
    advanced = []

    def concurrent_commit(_source, target, _domain):
        git(target, "config", "user.name", "Concurrent fixture")
        git(target, "config", "user.email", "fixture@example.invalid")
        (target / "concurrent.py").write_text("new owner work\n")
        git(target, "add", "concurrent.py")
        git(target, "commit", "-m", "concurrent clean advance")
        advanced.append(git(target, "rev-parse", "HEAD"))
        raise ReleaseError("fixture post-sync failure")

    monkeypatch.setattr("shared_wong_choi.release_activation.verify_deployment", concurrent_commit)
    with pytest.raises(ReleaseError, match="rollback incomplete"):
        activate_release(repo, state, selector=release["commit"], actor="fixture",
                         production_roots={"nba": production}, notify=False)
    assert git(production, "rev-parse", "HEAD") == advanced[0]
    assert (production / "concurrent.py").read_text() == "new owner work\n"
    events = ReleaseEventStore(state / "release-events").list(release["release_id"])
    failed = next(event for event in events if event["event_type"] == "activation_failed")
    assert failed["detail"]["rollback_status"] == "blocked"
    assert "production HEAD changed" in failed["detail"]["rollback_errors"][0]


@pytest.mark.parametrize("operation", ["sync", "rollback"])
def test_failed_git_status_cannot_authorize_checkout_mutation(release_setup, monkeypatch, operation):
    from shared_wong_choi import release_activation as activation
    repo, production, state, release = release_setup
    base = git(production, "rev-parse", "HEAD")
    if operation == "rollback":
        _sync_checkout(production, release["commit"])
    before = git(production, "rev-parse", "HEAD")
    original = activation._run

    def status_failure(root, *args, **kwargs):
        if args[:2] == ("git", "status"):
            return subprocess.CompletedProcess(args, 128, "", "fixture status failure")
        return original(root, *args, **kwargs)

    monkeypatch.setattr(activation, "_run", status_failure)
    with pytest.raises(ReleaseError, match="status probe failed"):
        if operation == "sync":
            _sync_checkout(production, release["commit"])
        else:
            _rollback_checkout(production, base, expected_current=release["commit"])
    assert git(production, "rev-parse", "HEAD") == before


def test_whitespace_filename_does_not_become_an_allowed_runtime_path(release_setup):
    repo, production, state, release = release_setup
    relative = " .agents/scripts/hkjc_draw_stats.json "
    tracked = repo / relative
    tracked.parent.mkdir(parents=True)
    tracked.write_bytes(b"tracked baseline\n")
    git(repo, "add", relative)
    git(repo, "commit", "-m", "tracked whitespace fixture")
    git(repo, "push", "origin", "HEAD:main")
    _sync_checkout(production, git(repo, "rev-parse", "HEAD"))
    wrapper = repo / ".agents/skills/nba/nba_daily_auto/run_nba_daily_schedule.sh"
    wrapper.write_text("#!/bin/sh\necho next fixture\n")
    git(repo, "add", str(wrapper.relative_to(repo)))
    git(repo, "commit", "-m", "next fixture")
    git(repo, "push", "origin", "HEAD:main")
    unrelated = production / relative
    unrelated.write_bytes(b"another owner's bytes\n")
    before = git(production, "rev-parse", "HEAD")
    with pytest.raises(ReleaseError, match="unrelated dirty paths"):
        _sync_checkout(production, git(repo, "rev-parse", "HEAD"))
    assert git(production, "rev-parse", "HEAD") == before
    assert unrelated.read_bytes() == b"another owner's bytes\n"


def test_forward_sync_and_rollback_union_runtime_mapping(tmp_path: Path) -> None:
    remote = tmp_path / "remote.git"
    source = tmp_path / "source"
    production = tmp_path / "production"
    git(tmp_path, "init", "--bare", str(remote))
    git(tmp_path, "clone", str(remote), str(source))
    git(source, "config", "user.name", "Mapping Test")
    git(source, "config", "user.email", "wc@example.test")
    mapping = source / ".agents/skills/au_racing/data/sb_archive_meeting_ids.json"
    mapping.parent.mkdir(parents=True)
    mapping.write_text('{"shared": "base", "base_only": 1}\n', encoding="utf-8")
    draw_stats = source / ".agents/scripts/hkjc_draw_stats.json"
    draw_stats.parent.mkdir(parents=True)
    draw_stats.write_text('{"meeting": "base"}\n', encoding="utf-8")
    merger = source / ".agents/skills/au_racing/au_daily_auto/merge_mapping.py"
    merger.parent.mkdir(parents=True)
    merger.write_text(
        "import json,sys\n"
        "from pathlib import Path\n"
        "local,incoming=map(Path,sys.argv[1:3])\n"
        "a=json.loads(local.read_text()); b=json.loads(incoming.read_text())\n"
        "b.update(a)\n"
        "local.write_text(json.dumps(b))\n",
        encoding="utf-8",
    )
    git(source, "add", ".")
    git(source, "commit", "-m", "base mapping")
    git(source, "branch", "-M", "main")
    git(source, "push", "-u", "origin", "main")
    base = git(source, "rev-parse", "HEAD")
    git(tmp_path, "clone", str(remote), str(production))

    mapping.write_text(
        '{"shared": "candidate", "base_only": 1, "candidate_only": 2}\n',
        encoding="utf-8",
    )
    git(source, "add", str(mapping.relative_to(source)))
    git(source, "commit", "-m", "candidate mapping")
    candidate = git(source, "rev-parse", "HEAD")
    git(source, "push", "origin", "HEAD:main")

    runtime_mapping = production / mapping.relative_to(source)
    runtime_mapping.write_text(
        '{"shared": "runtime", "base_only": 1, "runtime_only": 3}\n',
        encoding="utf-8",
    )
    runtime_draw_stats = production / draw_stats.relative_to(source)
    runtime_draw_stats.write_text('{"meeting": "today"}\n', encoding="utf-8")
    synced = _sync_checkout(production, candidate)
    assert synced["status"] == "updated"
    assert json.loads(runtime_mapping.read_text(encoding="utf-8")) == {
        "shared": "runtime",
        "base_only": 1,
        "candidate_only": 2,
        "runtime_only": 3,
    }
    assert runtime_draw_stats.read_text(encoding="utf-8") == '{"meeting": "today"}\n'

    rolled_back = _rollback_checkout(production, base)
    assert rolled_back["status"] == "rolled_back"
    assert git(production, "rev-parse", "HEAD") == base
    assert json.loads(runtime_mapping.read_text(encoding="utf-8")) == {
        "shared": "runtime",
        "base_only": 1,
        "candidate_only": 2,
        "runtime_only": 3,
    }
    assert runtime_draw_stats.read_text(encoding="utf-8") == '{"meeting": "today"}\n'


@pytest.mark.parametrize("restore_mode", ["ok", "exit", "exception", "event-error", "restore-and-event-error", "success-event-error"])
def test_deploy_failure_restores_installer_state_before_git_rollback(
    tmp_path: Path, monkeypatch, restore_mode: str,
) -> None:
    remote = tmp_path / "remote.git"
    repo = tmp_path / "repo"
    production = tmp_path / "production"
    external_state = tmp_path / "installed-runtime.txt"
    state = tmp_path / "state"
    git(tmp_path, "init", "--bare", str(remote))
    git(tmp_path, "clone", str(remote), str(repo))
    git(repo, "config", "user.name", "Installer Rollback Test")
    git(repo, "config", "user.email", "wc@example.test")
    gate = repo / "檢查.sh"
    gate.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    deploy = repo / "deploy.sh"
    deploy.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    os.chmod(gate, 0o755)
    os.chmod(deploy, 0o755)
    git(repo, "add", ".")
    git(repo, "commit", "-m", "base")
    git(repo, "branch", "-M", "main")
    git(repo, "push", "-u", "origin", "main")
    base = git(repo, "rev-parse", "HEAD")
    git(tmp_path, "clone", str(remote), str(production))
    external_state.write_text("old\n", encoding="utf-8")

    installer = (
        repo
        / ".agents/skills/central_wong_choi/install_production_runtime.sh"
    )
    installer.parent.mkdir(parents=True)
    restore_action = ("exit 9" if restore_mode in {"exit", "restore-and-event-error"}
                      else 'cp "$2/state" "$STATE"; exit 0')
    installer.write_text(
        "#!/bin/zsh\n"
        "set -eu\n"
        f"STATE='{external_state}'\n"
        "case \"${1:-}\" in\n"
        "  --snapshot) mkdir -p \"$2\"; cp \"$STATE\" \"$2/state\"; exit 0;;\n"
        f"  --restore) {restore_action};;\n"
        "  --status) exit 0;;\n"
        "esac\n"
        "print -r -- 'candidate' > \"$STATE\"\n",
        encoding="utf-8",
    )
    os.chmod(installer, 0o755)
    deploy.write_text(
        "#!/bin/sh\nexit 0\n" if restore_mode == "success-event-error" else
        "#!/bin/sh\necho 'dashboard too large'\necho 'asset gate' >&2\nexit 9\n",
        encoding="utf-8",
    )
    release = prepare_release(
        repo,
        paths=[
            str(installer.relative_to(repo)),
        ] + ([] if restore_mode == "success-event-error" else ["deploy.sh"]),
        message="feat: transactional runtime installer",
        state_root=state / "releases",
        notify=False,
    )
    approve_release(
        repo,
        state,
        selector=release["commit"][:12],
        actor="telegram:authorised-chat",
        notify=False,
    )
    monkeypatch.setattr(
        "shared_wong_choi.release_activation.verify_deployment", _verify
    )
    if restore_mode == "exception":
        from shared_wong_choi import release_activation as activation
        original_runner = activation._run_installer

        def restore_exec_failure(root, *args, **kwargs):
            if "--restore" in args:
                raise OSError("fixture restore exec failed")
            return original_runner(root, *args, **kwargs)

        monkeypatch.setattr(activation, "_run_installer", restore_exec_failure)
    recovery_roots = []
    event_error = restore_mode in {"event-error", "restore-and-event-error", "success-event-error"}
    if event_error:
        from shared_wong_choi import release_activation as activation
        original_mkdtemp = activation.tempfile.mkdtemp
        original_append = ReleaseEventStore.append

        def record_snapshot_root(*args, **kwargs):
            root = original_mkdtemp(*args, **kwargs)
            if kwargs.get("prefix") == "wc-installer-snapshots-":
                recovery_roots.append(Path(root))
            return root

        def failing_event(store, **kwargs):
            failed_kind = "activation_succeeded" if restore_mode == "success-event-error" else "activation_failed"
            if kwargs["event_type"] == failed_kind:
                raise OSError("fixture event store unavailable")
            return original_append(store, **kwargs)

        monkeypatch.setattr(activation.tempfile, "mkdtemp", record_snapshot_root)
        monkeypatch.setattr(ReleaseEventStore, "append", failing_event)

    expected_error = ("success recording unavailable" if restore_mode == "success-event-error" else
                      "failure event unavailable" if event_error else
                      "rollback complete" if restore_mode == "ok" else "rollback incomplete")
    with pytest.raises(ReleaseError, match=expected_error):
        activate_release(
            repo,
            state,
            selector=release["commit"][:12],
            actor="telegram:authorised-chat",
            production_roots={
                name: production for name in ("au", "hkjc", "nba", "tennis")
            },
            notify=False,
        )

    assert external_state.read_text(encoding="utf-8") == ("old\n" if restore_mode in {"ok", "event-error"} else "candidate\n")
    assert git(production, "rev-parse", "HEAD") == (release["commit"] if restore_mode == "success-event-error" else base)
    if event_error:
        assert len(recovery_roots) == 1
        assert (recovery_roots[0] / "installer-0/state").read_bytes() == b"old\n"
        context = json.loads((recovery_roots[0] / "recovery-context.json").read_text())
        assert context["commit"] == release["commit"]
        if restore_mode == "success-event-error":
            assert context["phase"] == "runtime_actions_completed_unrecorded"
            assert context["success_recorded"] is False
            with pytest.raises(ReleaseError, match="outcome unresolved"):
                activate_release(repo, state, selector=release["commit"], actor="fixture",
                                 production_roots={name: production for name in ("au", "hkjc", "nba", "tennis")},
                                 notify=False)
        else:
            assert context["rollback_status"] == ("blocked" if restore_mode == "restore-and-event-error" else "succeeded")
            assert bool(context["external_rollback_errors"]) == (restore_mode == "restore-and-event-error")
        return
    events = ReleaseEventStore(state / "release-events").list(release["release_id"])
    failure = next(item for item in events if item["event_type"] == "activation_failed")
    assert failure["detail"]["error"] == (
        "ReleaseError: dashboard deployment failed (exit 9); "
        "stdout=dashboard too large; stderr=asset gate"
    )
    if restore_mode != "ok":
        assert failure["detail"]["rollback_status"] == "blocked"
        assert failure["detail"]["external_rollback_errors"]
        recovery = failure["detail"]["recovery_snapshots"]
        assert recovery["retained"] is True
        assert Path(recovery["root"]).parent == state / "activation-recovery"
        assert Path(recovery["root"]).stat().st_mode & 0o777 == 0o700
        assert (Path(recovery["root"]) / "installer-0/state").read_bytes() == b"old\n"
        assert json.loads((Path(recovery["root"]) / "recovery-context.json").read_text())["commit"] == release["commit"]
        return
    assert failure["detail"]["external_rollback"] == [
        {
            "path": ".agents/skills/central_wong_choi/install_production_runtime.sh",
            "status": "restored",
        }
    ]
    assert failure["detail"]["external_rollback_errors"] == []

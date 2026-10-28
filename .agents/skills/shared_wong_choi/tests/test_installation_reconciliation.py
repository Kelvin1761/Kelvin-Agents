"""Read-only eligibility must fail before gates, intents or installation."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared_wong_choi import installation_reconciliation as reconciliation
from shared_wong_choi.release_events import ReleaseEventStore


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True,
                          text=True, check=True).stdout.strip()


@pytest.fixture
def history(tmp_path, monkeypatch):
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
    git(root, "add", "README.md")
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
        (state / "releases" / (commit + ".json")).write_text(json.dumps(manifest))
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
    manifest_path = state / "releases" / (target + ".json")
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

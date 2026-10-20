import hashlib
import json

import pytest

from shared_wong_choi.immutable_settlement_artifacts import capture_settlement_artifacts


EVENT = "2026-10-12 Tamworth Race 1-8"


def inputs(tmp_path):
    meeting = tmp_path / EVENT
    meeting.mkdir()
    result = meeting / "Race_Results_Reflector.md"
    result.write_bytes(b"original result")
    report = meeting / f"{EVENT}_Reflector_Report.md"
    report.write_bytes(b"original report")
    warm = tmp_path / "warm"
    warm.mkdir()
    return result, report, warm


def capture(result, report, warm):
    return capture_settlement_artifacts(
        artifacts=(result, report), event_id=EVENT, root=warm,
    )


def test_rewrite_cannot_change_captured_version_and_retry_is_idempotent(tmp_path):
    result, report, warm = inputs(tmp_path)
    first = capture(result, report, warm)
    assert first == capture(result, report, warm)
    result.write_bytes(b"corrected result")
    report.write_bytes(b"corrected report")
    second = capture(result, report, warm)
    assert second != first
    assert first[0].read_bytes() == b"original result"
    assert first[1].read_bytes() == b"original report"
    assert all(path.parent.name == EVENT for path in (*first, *second))
    manifest = json.loads((first[0].parent.parent / "manifest.json").read_bytes())
    assert manifest["files"][0]["sha256"] in {
        hashlib.sha256(b"original result").hexdigest(),
        hashlib.sha256(b"original report").hexdigest(),
    }


def test_corrupt_existing_capture_is_never_overwritten(tmp_path):
    result, report, warm = inputs(tmp_path)
    captured = capture(result, report, warm)
    captured[0].chmod(0o644)
    captured[0].write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="capture"):
        capture(result, report, warm)
    assert captured[0].read_bytes() == b"corrupt"


@pytest.mark.parametrize("kind", ["file", "parent", "root"])
def test_symlink_refused(tmp_path, kind):
    result, report, warm = inputs(tmp_path)
    link = tmp_path / "link"
    if kind == "file":
        link.symlink_to(result)
        result = link
    elif kind == "parent":
        link.symlink_to(result.parent, target_is_directory=True)
        result, report = link / result.name, link / report.name
    else:
        link.symlink_to(warm, target_is_directory=True)
        warm = link
    with pytest.raises((ValueError, OSError)):
        capture(result, report, warm)


def test_missing_root_is_not_created(tmp_path):
    result, report, warm = inputs(tmp_path)
    missing = warm / "offline"
    with pytest.raises((ValueError, OSError)):
        capture(result, report, missing)
    assert not missing.exists()


def test_source_mutation_during_publication_refuses_capture(tmp_path, monkeypatch):
    import shared_wong_choi.immutable_settlement_artifacts as module

    result, report, warm = inputs(tmp_path)
    original = module._publish

    def mutate(*args, **kwargs):
        report.write_bytes(b"mutated during capture")
        return original(*args, **kwargs)

    monkeypatch.setattr(module, "_publish", mutate)
    with pytest.raises(ValueError, match="source changed"):
        capture(result, report, warm)


def test_file_budget_is_enforced_before_copy(tmp_path, monkeypatch):
    import shared_wong_choi.immutable_settlement_artifacts as module

    result, report, warm = inputs(tmp_path)
    monkeypatch.setattr(module, "MAX_FILE_BYTES", 3)
    with pytest.raises(ValueError, match="bound"):
        capture(result, report, warm)


def test_partial_copy_failure_never_publishes_a_bundle(tmp_path, monkeypatch):
    import shared_wong_choi.immutable_settlement_artifacts as module

    result, report, warm = inputs(tmp_path)
    original = module._write
    calls = 0

    def fail_after_first(path, data):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected copy failure")
        original(path, data)

    monkeypatch.setattr(module, "_write", fail_after_first)
    with pytest.raises(OSError, match="injected"):
        capture(result, report, warm)
    assert list((warm / "settlement-artifacts" / "au").iterdir()) == [
        warm / "settlement-artifacts" / "au" / ".capture.lock",
    ]
    assert result.read_bytes() == b"original result"


def test_total_budget_refuses_without_publication(tmp_path, monkeypatch):
    import shared_wong_choi.immutable_settlement_artifacts as module

    result, report, warm = inputs(tmp_path)
    monkeypatch.setattr(module, "MAX_TOTAL_BYTES", 20)
    with pytest.raises(ValueError, match="bound"):
        capture(result, report, warm)
    assert not (warm / "settlement-artifacts").exists()


def test_storage_guard_failure_before_publish_is_propagated(tmp_path, monkeypatch):
    import shared_wong_choi.immutable_settlement_artifacts as module

    result, report, warm = inputs(tmp_path)
    original = module._publish
    available = True

    def guard():
        if not available:
            raise ValueError("storage unmounted")

    def unmount(*args, **kwargs):
        nonlocal available
        available = False
        return original(*args, **kwargs)

    monkeypatch.setattr(module, "_publish", unmount)
    with pytest.raises(ValueError, match="unmounted"):
        module.capture_settlement_artifacts(
            artifacts=(result, report), event_id=EVENT, root=warm, checkpoint=guard,
        )
    assert not list((warm / "settlement-artifacts" / "au").glob("*/manifest.json"))


def test_new_capture_syncs_parent_directory_entries(tmp_path, monkeypatch):
    import shared_wong_choi.immutable_settlement_artifacts as module

    result, report, warm = inputs(tmp_path)
    synced = []
    identities = []
    original = module._sync

    def record_sync(path):
        synced.append(path)
        info = path.stat()
        identities.append((info.st_dev, info.st_ino))
        original(path)

    monkeypatch.setattr(module, "_sync", record_sync)
    captured = capture(result, report, warm)
    assert warm in synced
    assert warm / "settlement-artifacts" in synced
    for directory in (captured[0].parent, captured[0].parent.parent,
                      captured[0].parent.parent.parent):
        info = directory.stat()
        assert (info.st_dev, info.st_ino) in identities

import importlib.util
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/relocate_reflector_db.py"
spec = importlib.util.spec_from_file_location("nba_db_relocation_test", SCRIPT)
relocation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(relocation)


def fixture(tmp_path):
    source = tmp_path / "code/nba_reflector.db"
    source.parent.mkdir()
    lock = source.parent / ".agents/skills/nba/nba_daily_auto/state/nba_daily_schedule.lock"
    lock.parent.mkdir(parents=True)
    lock.touch()
    with sqlite3.connect(source) as conn:
        conn.execute("CREATE TABLE history (value INTEGER)")
        conn.execute("INSERT INTO history VALUES (42)")
    mount = tmp_path / "external"
    mount.mkdir()
    return dict(source=source, destination=tmp_path / "hot/db.sqlite", warm=mount / "backup/db.sqlite",
                recovery=tmp_path / "recovery/db.sqlite", mount=mount,
                expected_sha256=relocation.inspect_db(source)["sha256"])


def test_relocation_preserves_exact_bytes_and_counts(tmp_path):
    args = fixture(tmp_path)
    original = relocation.inspect_db(args["source"])
    with patch.object(relocation.os.path, "ismount", return_value=True):
        report = relocation.relocate(**args)
    assert report["status"] == "relocated"
    assert not args["source"].exists()
    for key in ("destination", "warm", "recovery"):
        assert relocation.inspect_db(args[key]) == original


@pytest.mark.parametrize("blocker", ["destination", "warm", "recovery", "offline", "hash", "wal", "symlink"])
def test_blockers_never_remove_source(tmp_path, blocker):
    args = fixture(tmp_path)
    raw = args["source"].read_bytes()
    if blocker in ("destination", "warm", "recovery"):
        args[blocker].parent.mkdir(parents=True, exist_ok=True)
        args[blocker].write_bytes(b"do not overwrite")
    elif blocker == "hash":
        args["expected_sha256"] = "0" * 64
    elif blocker == "wal":
        Path(str(args["source"]) + "-wal").touch()
    elif blocker == "symlink":
        args["destination"].parent.mkdir()
        args["destination"].symlink_to(tmp_path / "absent")
    with patch.object(relocation.os.path, "ismount", return_value=blocker != "offline"):
        with pytest.raises((ValueError, FileExistsError)):
            relocation.relocate(**args)
    assert args["source"].read_bytes() == raw


def test_concurrent_writer_blocks_relocation(tmp_path):
    args = fixture(tmp_path)
    with sqlite3.connect(args["source"]) as writer:
        writer.execute("BEGIN IMMEDIATE")
        with patch.object(relocation.os.path, "ismount", return_value=True):
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                relocation.relocate(**args)
    assert args["source"].exists()
    assert not args["destination"].exists()


def test_failed_second_copy_keeps_source(tmp_path):
    args = fixture(tmp_path)
    args["warm"].parent.write_bytes(b"not a directory")
    with patch.object(relocation.os.path, "ismount", return_value=True):
        with pytest.raises(OSError):
            relocation.relocate(**args)
    assert args["source"].exists()
    assert not args["recovery"].exists()


def test_scheduler_lock_blocks_relocation(tmp_path):
    import fcntl
    args = fixture(tmp_path)
    lock = args["source"].parent / ".agents/skills/nba/nba_daily_auto/state/nba_daily_schedule.lock"
    with lock.open("r+") as owner:
        fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            relocation.relocate(**args)
    assert args["source"].exists()
    assert not args["destination"].exists()


def test_direct_producer_blocks_before_copy(tmp_path):
    args = fixture(tmp_path)
    with patch.object(relocation.os.path, "ismount", return_value=True), patch.object(
            relocation, "assert_no_producer", side_effect=RuntimeError("Active NBA")):
        with pytest.raises(RuntimeError, match="Active NBA"):
            relocation.relocate(**args)
    assert args["source"].exists()
    assert not args["destination"].exists()


def test_verified_existing_copies_can_be_reused_without_overwrite(tmp_path):
    args = fixture(tmp_path)
    for key in ("destination", "warm", "recovery"):
        args[key].parent.mkdir(parents=True, exist_ok=True)
        args[key].write_bytes(args["source"].read_bytes())
    identities = {key: args[key].stat().st_ino for key in ("destination", "warm", "recovery")}
    with patch.object(relocation.os.path, "ismount", return_value=True):
        relocation.relocate(**args)
    assert not args["source"].exists()
    assert identities == {key: args[key].stat().st_ino for key in identities}

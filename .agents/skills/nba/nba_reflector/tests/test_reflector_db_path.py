"""Storage isolation only: no scoring, historical outcomes or model training."""
import importlib.util
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "nba_reflector_orchestrator.py"
spec = importlib.util.spec_from_file_location("nba_reflector_db_path_test", SCRIPT)
reflector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reflector)


def test_default_is_hot_not_checkout():
    assert Path(reflector.DB_PATH) == Path.home() / "WongChoiData/NBA/nba_reflector.db"
    assert not Path(reflector.DB_PATH).is_relative_to(Path(reflector.WORKSPACE_ROOT))


def test_new_db_is_created_only_under_data_root(tmp_path):
    checkout = tmp_path / "code"
    checkout.mkdir()
    destination = tmp_path / "data/NBA/nba_reflector.db"
    with patch.object(reflector, "WORKSPACE_ROOT", str(checkout)), patch.object(reflector, "DB_PATH", str(destination)):
        with reflector.open_reflector_db() as conn:
            reflector.ensure_db(conn)
            assert conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    assert destination.is_file()
    assert not (checkout / "nba_reflector.db").exists()


@pytest.mark.parametrize("destination_exists", [False, True])
def test_legacy_db_blocks_silent_split_even_with_destination(tmp_path, destination_exists):
    legacy = tmp_path / "nba_reflector.db"
    legacy.write_bytes(b"preserve legacy bytes")
    destination = tmp_path / "hot/db.sqlite"
    if destination_exists:
        destination.parent.mkdir()
        destination.write_bytes(b"preserve destination bytes")
    with patch.object(reflector, "WORKSPACE_ROOT", str(tmp_path)), patch.object(reflector, "DB_PATH", str(destination)):
        with pytest.raises(RuntimeError, match="controlled relocation"):
            reflector.open_reflector_db()
    assert legacy.read_bytes() == b"preserve legacy bytes"
    assert destination.exists() == destination_exists
    if destination_exists:
        assert destination.read_bytes() == b"preserve destination bytes"


def test_existing_history_is_preserved(tmp_path):
    destination = tmp_path / "hot/db.sqlite"
    destination.parent.mkdir()
    with sqlite3.connect(destination) as conn:
        conn.execute("CREATE TABLE history (value INTEGER)")
        conn.execute("INSERT INTO history VALUES (42)")
    with patch.object(reflector, "WORKSPACE_ROOT", str(tmp_path / "code")), patch.object(reflector, "DB_PATH", str(destination)):
        with reflector.open_reflector_db() as conn:
            assert conn.execute("SELECT value FROM history").fetchall() == [(42,)]


def test_storage_failure_never_falls_back_to_checkout(tmp_path):
    blocked = tmp_path / "blocked"
    blocked.write_bytes(b"not a directory")
    with patch.object(reflector, "WORKSPACE_ROOT", str(tmp_path)), patch.object(reflector, "DB_PATH", str(blocked / "db.sqlite")):
        with pytest.raises(OSError):
            reflector.open_reflector_db()
    assert not (tmp_path / "nba_reflector.db").exists()


def test_symlink_destination_is_rejected(tmp_path):
    destination = tmp_path / "link.sqlite"
    destination.symlink_to(tmp_path / "absent.sqlite")
    with patch.object(reflector, "WORKSPACE_ROOT", str(tmp_path / "code")), patch.object(reflector, "DB_PATH", str(destination)):
        with pytest.raises(RuntimeError, match="symlink"):
            reflector.open_reflector_db()
    assert not (tmp_path / "absent.sqlite").exists()

from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_ROOT))

from wongchoi_paths import is_materialized_file  # noqa: E402


def test_materialized_file_must_be_readable(tmp_path: Path) -> None:
    path = tmp_path / "analysis.md"
    path.write_text("ready", encoding="utf-8")

    assert is_materialized_file(path) is True

    with mock.patch.object(Path, "open", side_effect=PermissionError("TCC blocked")):
        assert is_materialized_file(path) is False


def test_zero_byte_file_is_not_materialized(tmp_path: Path) -> None:
    path = tmp_path / "empty.md"
    path.touch()

    assert is_materialized_file(path) is False

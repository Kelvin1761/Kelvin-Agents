"""External scratch routing must fail closed before starting a child."""
import sys
import hashlib
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import wongchoi_external_run as runner


@pytest.fixture
def mounted(tmp_path, monkeypatch):
    volume = tmp_path / "disk"
    root = volume / "WongChoi-Archive"
    root.mkdir(parents=True)
    monkeypatch.setattr(runner, "_volume_for", lambda path: volume)
    monkeypatch.setattr(Path, "is_mount", lambda path: path == volume)
    monkeypatch.setattr(runner.shutil, "disk_usage", lambda path: SimpleNamespace(free=40 * runner.GIB))
    return root


def test_local_storage_is_not_an_external_volume(tmp_path, monkeypatch):
    # TMPDIR may deliberately put pytest's tmp_path on a mounted external disk.
    # Use a lexical non-/Volumes path; rejection must precede any disk access.
    local = Path(tmp_path.anchor) / "wongchoi-local-storage"
    monkeypatch.setattr(runner.shutil, "disk_usage",
                        lambda path: pytest.fail("local storage reached disk probe"))
    with pytest.raises(ValueError, match="/Volumes"):
        runner.inspect_root(local)


def test_unmounted_disk_does_not_create_scratch(mounted, monkeypatch):
    monkeypatch.setattr(Path, "is_mount", lambda path: False)
    with pytest.raises(ValueError, match="mounted"):
        runner.prepare_environment(mounted, {})
    assert not (mounted / "scratch").exists()


def test_low_capacity_does_not_create_scratch(mounted, monkeypatch):
    monkeypatch.setattr(runner.shutil, "disk_usage", lambda path: SimpleNamespace(free=runner.GIB))
    with pytest.raises(ValueError, match="capacity"):
        runner.prepare_environment(mounted, {})
    assert not (mounted / "scratch").exists()


def test_root_symlink_is_rejected(mounted):
    alias = mounted.parent / "alias"
    alias.symlink_to(mounted, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        runner.prepare_environment(alias, {})


def test_parent_traversal_cannot_route_to_local_disk(mounted):
    local = mounted.parent.parent / "local"
    local.mkdir()
    escaped = mounted.parent / ".." / "local"
    with pytest.raises(ValueError, match="escapes external volume"):
        runner.prepare_environment(escaped, {})
    assert list(local.iterdir()) == []


def test_scratch_symlink_cannot_escape_external_root(mounted, tmp_path):
    (mounted / "scratch").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        runner.prepare_environment(mounted, {})


def test_environment_routes_scratch_and_download_caches(mounted):
    original = {"KEEP_ME": "unchanged", "TMPDIR": "/local", "PIP_CACHE_DIR": "/local-pip"}
    env, scratch = runner.prepare_environment(mounted, original)
    for key in ("TMPDIR", "PIP_CACHE_DIR", "UV_CACHE_DIR", "npm_config_cache"):
        assert Path(env[key]).is_relative_to(mounted)
    assert env["KEEP_ME"] == "unchanged"
    assert original["TMPDIR"] == "/local"
    assert scratch.is_dir()


def test_child_arguments_and_exit_code_are_preserved(mounted, monkeypatch):
    monkeypatch.setenv("WC_WARM_ARCHIVE_ROOT", str(mounted))
    calls = []
    def child(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=23)
    monkeypatch.setattr(runner.subprocess, "run", child)
    assert runner.main(["--", "tool", "a b", "$(not-executed)"]) == 23
    assert calls[0][0] == ["tool", "a b", "$(not-executed)"]
    assert calls[0][1].get("shell", False) is False


def test_check_is_read_only(mounted, monkeypatch):
    monkeypatch.setenv("WC_WARM_ARCHIVE_ROOT", str(mounted))
    monkeypatch.setattr(runner.subprocess, "run", lambda *args, **kwargs: pytest.fail("child started"))
    assert runner.main(["--check"]) == 0
    assert list(mounted.iterdir()) == []


def test_offline_check_never_starts_child(mounted, monkeypatch):
    monkeypatch.setenv("WC_WARM_ARCHIVE_ROOT", str(mounted))
    monkeypatch.setattr(Path, "is_mount", lambda path: False)
    monkeypatch.setattr(runner.subprocess, "run", lambda *args, **kwargs: pytest.fail("child started"))
    assert runner.main(["tool"]) == 75


def test_au_explicit_cache_root_reads_seeded_pages_without_network(tmp_path):
    cache = tmp_path / "seeded-au-html"
    cache.mkdir()
    url = "https://www.sportsbetform.com.au/fixture/race/"
    page = "<html>seeded historical page</html>"
    (cache / (hashlib.sha1(url.encode()).hexdigest() + ".html")).write_text(page)
    au = Path(__file__).resolve().parents[2] / "skills" / "au_racing"
    code = """
import sys, types
from pathlib import Path
from unittest.mock import Mock
network = Mock(side_effect=AssertionError("network request forbidden"))
curl = types.ModuleType("curl_cffi")
curl.requests = types.SimpleNamespace(Session=lambda **kw: types.SimpleNamespace(get=network))
sys.modules["curl_cffi"] = curl
sys.path.insert(0, sys.argv[1])
from claw_sportsbet_form import CACHE_DIR, CACHE_ONLY, SportsbetFormFetcher
assert CACHE_DIR == Path(sys.argv[2]) and CACHE_ONLY
fetcher = SportsbetFormFetcher(verbose=False)
assert fetcher.get_cached(sys.argv[3]) == sys.argv[4]
assert fetcher.get(sys.argv[3]) == sys.argv[4]
assert fetcher.get(sys.argv[3] + "missing") is None
network.assert_not_called()
"""
    env = dict(os.environ, WC_SB_CACHE=str(cache), WC_SB_CACHE_ONLY="1",
               PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run([sys.executable, "-c", code, str(au), str(cache), url, page],
                            env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr

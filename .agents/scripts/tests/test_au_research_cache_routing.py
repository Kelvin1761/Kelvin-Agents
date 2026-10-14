"""Probe native CLI parsing only; never run evaluation or read a dataset."""
import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("script", [
    "au_sportsbet_raw_field_audit.py",
    "au_sportsbet_performance_quality_candidate.py",
])
@pytest.mark.parametrize("mode", ["unset", "empty", "environment", "explicit"])
def test_research_cli_cache_root_precedence(script, mode, tmp_path):
    au = Path(__file__).resolve().parents[2] / "skills" / "au_racing"
    path = au / "au_wong_choi_auto" / "scripts" / script
    alternate = tmp_path / "alternate cache"
    explicit = tmp_path / "explicit cache"
    expected = explicit if mode == "explicit" else alternate if mode == "environment" else au / ".sportsbet_cache"
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", WC_SB_CACHE_ONLY="1")
    env.pop("WC_SB_CACHE", None)
    if mode != "unset":
        env["WC_SB_CACHE"] = "" if mode == "empty" else str(alternate)
    code = """
import argparse, runpy, sys, types
from pathlib import Path
curl = types.ModuleType("curl_cffi")
curl.requests = types.SimpleNamespace(Session=lambda **kw: (_ for _ in ()).throw(AssertionError("HTTP session forbidden")))
sys.modules["curl_cffi"] = curl
namespace = runpy.run_path(sys.argv[1], run_name="cache_path_probe")
original = argparse.ArgumentParser.parse_args
class StopAfterParsing(BaseException):
    pass
def probe(parser, *args, **kwargs):
    options = ["--dataset", "never-open-this-dataset"] if "performance_quality" in sys.argv[1] else []
    if sys.argv[3] == "explicit":
        options += ["--cache-dir", sys.argv[4]]
    parsed = original(parser, options)
    assert parsed.cache_dir == Path(sys.argv[2]), (parsed.cache_dir, sys.argv[2])
    raise StopAfterParsing()
argparse.ArgumentParser.parse_args = probe
try:
    namespace["main"]()
except StopAfterParsing:
    pass
else:
    raise AssertionError("probe did not stop before evaluation")
"""
    result = subprocess.run([sys.executable, "-c", code, str(path), str(expected), mode, str(explicit)],
                            env=env, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert list(tmp_path.iterdir()) == []

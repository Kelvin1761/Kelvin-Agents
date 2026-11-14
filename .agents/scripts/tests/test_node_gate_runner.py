"""Exercise the real shell runner with real Node and isolated Python-suite stubs.

The stubs avoid rerunning domain suites here; these are runner-contract tests,
never evidence that those domain suites passed.
"""
import os
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.parametrize("case", ["pass", "fail", "missing"])
def test_node_suite_gate_uses_exit_status_and_requires_runtime(tmp_path, case):
    node = shutil.which("node")
    assert node is not None, "Node is required for the complete repository gate"
    source = Path(__file__).resolve().parents[3] / "run_tests.sh"
    runner = tmp_path / "run_tests.sh"
    shutil.copyfile(source, runner)
    (tmp_path / "tennis-wong-choi").mkdir()
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    invocations = tmp_path / "python-suite-invocations"
    stub = tmp_path / "python-suite-stub"
    stub.write_text('#!/bin/sh\nprintf "suite\\n" >> "$STUB_INVOCATIONS"\nexit 0\n')
    stub.chmod(0o700)
    tests = tmp_path / "Horse_Racing_Dashboard" / "tests"
    tests.mkdir(parents=True)
    (tests / "test_gate.mjs").write_text(
        "import test from 'node:test';\n"
        "import assert from 'node:assert/strict';\n"
        f"test('runner status contract', () => assert.equal({str(case != 'fail').lower()}, true));\n"
    )
    tools = tmp_path / "tools"
    tools.mkdir()
    for command in ("dirname", "uname", "find", "mktemp", "rm", "grep"):
        executable = shutil.which(command)
        assert executable is not None
        (tools / command).symlink_to(executable)
    runtime_path = str(tools)
    if case != "missing":
        runtime_path = str(Path(node).parent) + ":" + runtime_path
    env = {**os.environ, "PATH": runtime_path, "PYTHON_BIN": str(stub),
           "WC_TEST_TMPDIR": str(scratch), "TMPDIR": str(scratch),
           "STUB_INVOCATIONS": str(invocations)}
    env.pop("NODE_OPTIONS", None)
    result = subprocess.run(["/bin/bash", str(runner)], cwd=tmp_path, env=env,
                            capture_output=True, text=True, timeout=30)
    output = result.stdout + result.stderr
    assert len(invocations.read_text().splitlines()) == 15
    if case == "pass":
        assert result.returncode == 0, output
        assert "PASS  Dashboard (node)" in output
        assert "# pass 1" in output
    else:
        assert result.returncode != 0, output
        assert "FAIL  Dashboard (node)" in output
        if case == "fail":
            assert "ERR_ASSERTION" in output
        else:
            assert "node not found" in output

"""Exercise the real shell driver with cheap stand-in suites."""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize("fail", [False, True])
def test_test_driver_honours_custom_scratch_isolates_suites_and_retains_failures(tmp_path, fail):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "tennis-wong-choi").mkdir()
    source = Path(__file__).resolve().parents[4] / "run_tests.sh"
    shutil.copy2(source, root / "run_tests.sh")
    scratch = tmp_path / "external scratch"
    scratch.mkdir()
    log = tmp_path / "arguments.jsonl"
    interpreter = tmp_path / "python-stub"
    interpreter.write_text(
        '#!/usr/bin/env python3\nimport json,os,sys\n'
        'with open(os.environ["DRIVER_LOG"],"a") as f: f.write(json.dumps(sys.argv[1:])+"\\n")\n'
        'sys.exit(int(os.environ["DRIVER_FAIL"]))\n')
    interpreter.chmod(0o755)
    result = subprocess.run(["bash", "run_tests.sh"], cwd=root, capture_output=True, text=True,
                            env={**os.environ, "PYTHON_BIN": str(interpreter),
                                 "WC_TEST_TMPDIR": str(scratch), "TMPDIR": str(tmp_path / "unused"),
                                 "DRIVER_LOG": str(log), "DRIVER_FAIL": "1" if fail else "0"})
    assert result.returncode == int(fail), result.stdout + result.stderr
    arguments = [json.loads(line) for line in log.read_text().splitlines()]
    bases = [Path(next(a.split("=", 1)[1] for a in row if a.startswith("--basetemp=")))
             for row in arguments]
    assert len(bases) >= 15 and len(set(bases)) == len(bases)
    assert all(path.parent.parent == scratch for path in bases)
    assert len({path.parent for path in bases}) == 1
    assert bases[0].parent.exists() is fail
    assert "retained" in result.stdout if fail else "All suites passed" in result.stdout

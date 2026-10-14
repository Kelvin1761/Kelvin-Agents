from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path


DASHBOARD_ROOT = Path(__file__).resolve().parents[1]
LOCK_RUNNER = DASHBOARD_ROOT / "scripts" / "run_with_file_lock.py"


def test_machine_wide_lock_serialises_the_whole_command(tmp_path: Path):
    lock = tmp_path / "dashboard.lock"
    events = tmp_path / "events.txt"
    worker = tmp_path / "worker.py"
    worker.write_text(
        "import pathlib, sys, time\n"
        "out = pathlib.Path(sys.argv[1])\n"
        "name, delay = sys.argv[2], float(sys.argv[3])\n"
        "with out.open('a') as handle:\n"
        "    handle.write(name + '-start\\n'); handle.flush()\n"
        "time.sleep(delay)\n"
        "with out.open('a') as handle:\n"
        "    handle.write(name + '-end\\n'); handle.flush()\n",
        encoding="utf-8",
    )

    first = subprocess.Popen([
        sys.executable, str(LOCK_RUNNER), "--lock", str(lock), "--",
        sys.executable, str(worker), str(events), "first", "0.25",
    ])
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        if events.exists() and "first-start" in events.read_text(encoding="utf-8"):
            break
        time.sleep(0.01)
    second = subprocess.Popen([
        sys.executable, str(LOCK_RUNNER), "--lock", str(lock), "--",
        sys.executable, str(worker), str(events), "second", "0",
    ])

    assert first.wait(timeout=5) == 0
    assert second.wait(timeout=5) == 0
    assert events.read_text(encoding="utf-8").splitlines() == [
        "first-start", "first-end", "second-start", "second-end",
    ]


def test_deploy_locks_before_touching_shared_dist_and_fails_closed():
    deploy = (DASHBOARD_ROOT / "deploy.sh").read_text(encoding="utf-8")

    assert deploy.index("run_with_file_lock.py") < deploy.index('rm -rf "$DIST_DIR"')
    assert 'grep -q "Deployment complete!"' in deploy
    assert "WRANGLER_RC=${PIPESTATUS[0]}" in deploy


def test_wrangler_completion_requires_both_exit_success_and_signal(tmp_path: Path):
    # Execute the actual upload-and-validation section against a local npx stub.
    # No credentials, build, or remote publication are involved.
    deploy = (DASHBOARD_ROOT / "deploy.sh").read_text(encoding="utf-8")
    upload = deploy[deploy.index('mkdir -p "$DEPLOY_CWD"'):]
    stub = tmp_path / "npx"
    stub.write_text('#!/bin/bash\nprintf "%s\\n" "$FAKE_WRANGLER_OUTPUT"\nexit "$FAKE_WRANGLER_RC"\n')
    stub.chmod(0o755)
    script = tmp_path / "upload.sh"
    script.write_text("#!/bin/bash\nset -euo pipefail\n" + upload)
    environment = dict(os.environ, PATH=str(tmp_path) + os.pathsep + os.environ["PATH"],
        DEPLOY_CWD=str(tmp_path), SCRIPT_DIR=str(tmp_path), WRANGLER_VERSION="test",
        RESOLVED_ACCOUNT_ID="test", DIST_DIR=str(tmp_path / "dist"), PAGES_PROJECT="test",
        COMMIT_HASH="test", COMMIT_MESSAGE="test", COMMIT_DIRTY="true", KEEP_DIST="1")
    for code, output, success in [
        (0, "uploaded assets but upload crashed", False),
        (1, "Deployment complete!", False),
        (0, "Deployment complete!", True),
    ]:
        result = subprocess.run(["/bin/bash", str(script)], env=dict(environment,
            FAKE_WRANGLER_RC=str(code), FAKE_WRANGLER_OUTPUT=output),
            text=True, capture_output=True, check=False)
        assert (result.returncode == 0) is success, result.stdout + result.stderr
        assert ("🎉 發佈完成" in result.stdout) is success
        assert not list(tmp_path.glob("wongchoi-wrangler.*"))

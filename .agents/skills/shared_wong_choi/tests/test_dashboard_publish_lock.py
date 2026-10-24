"""Real processes prove publishers cannot overlap the shared transaction."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared_wong_choi.dashboard_publish_lock import HELD_ENV, publication_lock

HELPER = Path(__file__).resolve().parents[1] / "dashboard_publish_lock.py"


@pytest.fixture
def environment(tmp_path, monkeypatch):
    monkeypatch.setenv("WC_DASHBOARD_PUBLICATION_LOCK_PATH", str(tmp_path / "lock"))
    monkeypatch.delenv(HELD_ENV, raising=False)
    return os.environ.copy()


def test_two_publishers_serialize_whole_transactions(tmp_path, environment):
    events = tmp_path / "events.jsonl"
    child = ("import json,time,sys; from pathlib import Path; "
             "p=Path(sys.argv[1]); name=sys.argv[2]; "
             "f=p.open('a'); f.write(json.dumps([name,'start'])+'\\n'); f.close(); "
             "time.sleep(.15); f=p.open('a'); f.write(json.dumps([name,'end'])+'\\n'); f.close()")
    processes = [subprocess.Popen([sys.executable, str(HELPER), "--", sys.executable,
                                  "-c", child, str(events), name], env=environment)
                 for name in ("AU", "HKJC")]
    try:
        assert all(p.wait(timeout=5) == 0 for p in processes)
    finally:
        for p in processes:
            if p.poll() is None:
                p.kill()
                p.wait()
    rows = [json.loads(line) for line in events.read_text().splitlines()]
    assert [r[1] for r in rows] == ["start", "end", "start", "end"]
    assert rows[0][0] == rows[1][0] != rows[2][0] == rows[3][0]


def test_nested_deploy_inherits_lock_without_deadlocking(environment):
    with publication_lock():
        assert os.environ[HELD_ENV] == "1"
        with publication_lock():
            result = subprocess.run([sys.executable, str(HELPER), "--", sys.executable,
                                     "-c", "import os; assert os.environ['" + HELD_ENV + "']=='1'"],
                                    timeout=5, check=False)
        assert result.returncode == 0
    assert HELD_ENV not in os.environ


def test_lock_timeout_never_runs_competing_publish(tmp_path, environment):
    marker = tmp_path / "unsafe"
    with publication_lock():
        env = dict(environment, WC_DASHBOARD_PUBLICATION_LOCK_TIMEOUT="0.05")
        env.pop(HELD_ENV, None)
        result = subprocess.run([sys.executable, str(HELPER), "--", sys.executable,
                                 "-c", f"from pathlib import Path; Path({str(marker)!r}).touch()"],
                                env=env, capture_output=True, text=True, timeout=5)
    assert result.returncode != 0
    assert "lock busy" in result.stderr
    assert not marker.exists()


def test_exception_releases_lock_and_internal_marker(environment):
    with pytest.raises(RuntimeError), publication_lock():
        raise RuntimeError("build failed")
    assert HELD_ENV not in os.environ
    with publication_lock():
        pass


def test_direct_deploy_enters_same_lock_before_build(environment):
    deploy = HELPER.parents[3] / "Horse_Racing_Dashboard/deploy.sh"
    source = deploy.read_text()
    assert source.index("dashboard_publish_lock.py") < source.index('rm -rf "$DIST_DIR"')
    result = subprocess.run(["/bin/bash", str(deploy), "--unknown-test-flag"],
                            env=environment, capture_output=True, text=True, timeout=5)
    assert result.returncode != 0
    assert "未知參數" in result.stdout

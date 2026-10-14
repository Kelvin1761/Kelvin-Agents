from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared_wong_choi.release_approval import _run_gate_in_clean_clone
from shared_wong_choi.release_manager import ReleaseError
from test_release_manager import git, repo as repo_fixture


@pytest.mark.parametrize("exit_code", [0, 7])
def test_clean_recheck_retains_both_streams_after_clone_cleanup(tmp_path, exit_code):
    repo = repo_fixture.__wrapped__(tmp_path)
    check = repo / "檢查.sh"
    check.write_text(
        "#!/bin/sh\nprintf 'fixture stdout\\n'\n"
        f"printf 'fixture stderr\\n' >&2\nexit {exit_code}\n"
    )
    check.chmod(0o755)
    git(repo, "add", "檢查.sh")
    git(repo, "commit", "-m", "fixture recheck output")
    commit = git(repo, "rev-parse", "HEAD")
    before = git(repo, "status", "--porcelain")

    if exit_code:
        with pytest.raises(ReleaseError, match="recheck gate failed; output retained at") as error:
            _run_gate_in_clean_clone(repo, commit, "full")
    else:
        _run_gate_in_clean_clone(repo, commit, "full")

    logs = list((repo / ".git" / "wongchoi-release-checks" / commit).glob("*.log"))
    assert len(logs) == 1
    contents = logs[0].read_text()
    assert f"commit: {commit}" in contents
    assert f"exit_code: {exit_code}" in contents
    assert "fixture stdout" in contents and "fixture stderr" in contents
    if exit_code:
        assert str(logs[0]) in str(error.value)
    assert git(repo, "status", "--porcelain") == before
    assert git(repo, "rev-parse", "HEAD") == commit
    assert Path(logs[0]).is_file()


def test_initial_gate_failure_retains_output_and_never_stages(tmp_path):
    from shared_wong_choi.release_manager import prepare_release
    repo = repo_fixture.__wrapped__(tmp_path)
    check = repo / "檢查.sh"
    check.write_text("#!/bin/sh\nprintf 'initial stdout\\n'\nprintf 'initial stderr\\n' >&2\nexit 7\n")
    git(repo, "add", "檢查.sh")
    git(repo, "commit", "-m", "failing gate fixture")
    git(repo, "push", "origin", "main")
    head = git(repo, "rev-parse", "HEAD")
    (repo / "candidate.py").write_text("print('candidate')\n")
    with pytest.raises(ReleaseError, match="no files were staged; output retained at") as error:
        prepare_release(repo, paths=["candidate.py"], message="fixture", notify=False)
    logs = list((repo / ".git" / "wongchoi-release-checks" / head).glob("*.log"))
    assert len(logs) == 1 and str(logs[0]) in str(error.value)
    assert "initial stdout" in logs[0].read_text() and "initial stderr" in logs[0].read_text()
    assert git(repo, "diff", "--cached", "--name-only") == ""
    assert git(repo, "rev-parse", "HEAD") == head

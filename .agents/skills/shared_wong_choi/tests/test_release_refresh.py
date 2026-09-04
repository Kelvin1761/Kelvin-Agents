"""過期 release 嘅復原路徑。

`approve_release` 綁死 `origin/main == manifest["rollback_target"]`，所以發佈係
嚴格串行：第一個 merge 之後其餘全部報 `approval expired`。2026-09-04 有五個
pending，approve 咗一個之後其餘四個要逐個由手做（乾淨 worktree → cherry-pick →
重跑 gate → push → approve → 將舊 manifest 記為 superseded）。`refresh_release`
就係將呢個流程收成一個指令。

呢個檔守住嗰四個由手做嗰陣真係踩到嘅陷阱：
  * branch 名唔可以重用（重用 = non-fast-forward push = manifest 有 commit 但
    remote 冇 → approve 之後報 `push_failed`）
  * 未過期嘅唔准 refresh（應該直接 approve）
  * 已經入 main 嘅唔准 refresh（應該 reject 舊 manifest）
  * refresh 完舊 manifest 一定要唔再 pending，唔然 bare `/approve` 永遠拒絕
  * replay 撞 conflict 要乾淨咁失敗，唔可以留低一個爛 index
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT.parent))

from shared_wong_choi.release_approval import (  # noqa: E402
    approve_release,
    pending_releases,
)
from shared_wong_choi.release_manager import ReleaseError, prepare_release  # noqa: E402
from shared_wong_choi.release_refresh import refresh_release  # noqa: E402


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, text=True,
                          capture_output=True, check=True).stdout.strip()


@pytest.fixture
def two_pending(tmp_path: Path):
    """兩個 pending release，兩個都 gate 過同一個 main —— 即係現實情況。"""
    remote = tmp_path / "remote.git"
    repo = tmp_path / "repo"
    git(tmp_path, "init", "--bare", str(remote))
    git(tmp_path, "clone", str(remote), str(repo))
    git(repo, "config", "user.name", "Refresh Test")
    git(repo, "config", "user.email", "wc@example.test")
    gate = repo / "檢查.sh"
    gate.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    os.chmod(gate, 0o755)
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    git(repo, "add", "README.md", "檢查.sh")
    git(repo, "commit", "-m", "base")
    git(repo, "branch", "-M", "main")
    git(repo, "push", "-u", "origin", "main")
    state = tmp_path / "state"

    (repo / "alpha.txt").write_text("alpha\n", encoding="utf-8")
    first = prepare_release(repo, paths=["alpha.txt"], message="feat: alpha",
                            state_root=state / "releases", notify=False)
    git(repo, "checkout", "-q", "-B", "second", "origin/main")
    (repo / "beta.txt").write_text("beta\n", encoding="utf-8")
    second = prepare_release(repo, paths=["beta.txt"], message="feat: beta",
                             state_root=state / "releases", notify=False)
    return repo, state, first, second


def test_the_second_release_really_does_expire(two_pending) -> None:
    """呢個係整個檔存在嘅前提，所以要明文測。"""
    repo, state, first, second = two_pending
    approve_release(repo, state, selector=first["commit"], actor="t", notify=False)
    with pytest.raises(ReleaseError, match="approval expired"):
        approve_release(repo, state, selector=second["commit"], actor="t", notify=False)


def test_refresh_replays_and_the_result_approves(two_pending) -> None:
    repo, state, first, second = two_pending
    approve_release(repo, state, selector=first["commit"], actor="t", notify=False)

    out = refresh_release(repo, state, selector=second["commit"], actor="t", notify=False)
    assert out["status"] == "refreshed"
    assert out["release"]["check_exit_code"] == 0
    new_commit = out["release"]["commit"]
    assert new_commit != second["commit"]

    approved = approve_release(repo, state, selector=new_commit, actor="t", notify=False)
    assert approved["status"] == "merged"
    # 兩個改動都要真係喺 main 上面
    git(repo, "fetch", "origin")
    tree = git(repo, "ls-tree", "--name-only", "origin/main")
    assert "alpha.txt" in tree and "beta.txt" in tree


def test_refresh_keeps_the_message_and_scope(two_pending) -> None:
    repo, state, first, second = two_pending
    approve_release(repo, state, selector=first["commit"], actor="t", notify=False)
    out = refresh_release(repo, state, selector=second["commit"], actor="t", notify=False)
    assert out["release"]["scope"] == second["scope"]
    assert git(repo, "log", "-1", "--pretty=%s", out["release"]["commit"]) == "feat: beta"


def test_the_old_manifest_stops_being_pending(two_pending) -> None:
    """唔清走舊 manifest，bare /approve 會永遠報「N releases are waiting」。"""
    repo, state, first, second = two_pending
    approve_release(repo, state, selector=first["commit"], actor="t", notify=False)
    out = refresh_release(repo, state, selector=second["commit"], actor="t", notify=False)
    commits = {str(item["commit"]) for item in pending_releases(state, repo)}
    assert second["commit"] not in commits
    assert out["release"]["commit"] in commits
    assert len(commits) == 1


def test_branch_names_are_never_reused(two_pending) -> None:
    """重用 branch 名 → 由 main 重開之後 push 係 non-fast-forward → manifest 寫住
    個 commit 但 remote 冇 → approve 報 push_failed。"""
    repo, state, first, second = two_pending
    approve_release(repo, state, selector=first["commit"], actor="t", notify=False)
    out = refresh_release(repo, state, selector=second["commit"], actor="t", notify=False)
    branch = out["branch"]
    # remote 真係有嗰個 commit（即係 push 冇被拒）
    listed = git(repo, "ls-remote", "--heads", "origin", branch)
    assert out["release"]["commit"] in listed
    # 再 refresh 一次同一個舊 commit，一定要換名
    second_out = refresh_release(repo, state, selector=second["commit"], actor="t",
                                 notify=False)
    assert second_out["branch"] != branch


def test_refusing_a_release_that_has_not_expired(two_pending) -> None:
    repo, state, first, _second = two_pending
    with pytest.raises(ReleaseError, match="has not expired"):
        refresh_release(repo, state, selector=first["commit"], actor="t", notify=False)


def test_refusing_a_release_already_in_main(two_pending) -> None:
    """已經入 main 就冇嘢好 refresh —— 呢個訊息比「manifest 寫住 merged」更準，
    因為 out-of-band merge 兩者會唔一致。"""
    repo, state, first, second = two_pending
    approve_release(repo, state, selector=first["commit"], actor="t", notify=False)
    with pytest.raises(ReleaseError, match="already contained in origin/main"):
        refresh_release(repo, state, selector=first["commit"], actor="t", notify=False)

    # refresh 出嚟嘅新 release 一旦 merge，同樣唔准再 refresh
    out = refresh_release(repo, state, selector=second["commit"], actor="t", notify=False)
    approve_release(repo, state, selector=out["release"]["commit"], actor="t", notify=False)
    with pytest.raises(ReleaseError, match="already contained in origin/main"):
        refresh_release(repo, state, selector=out["release"]["commit"], actor="t",
                        notify=False)


def test_refusing_a_dirty_tracked_tree(two_pending) -> None:
    """replay 會改 HEAD 同 index，所以失敗要還原得返 —— 有人改過嘅 tracked 檔
    就還原唔到，唔准開工。"""
    repo, state, first, second = two_pending
    approve_release(repo, state, selector=first["commit"], actor="t", notify=False)
    (repo / "README.md").write_text("touched\n", encoding="utf-8")
    with pytest.raises(ReleaseError, match="clean tracked tree"):
        refresh_release(repo, state, selector=second["commit"], actor="t", notify=False)


def test_a_conflicting_replay_fails_without_leaving_a_broken_index(two_pending) -> None:
    repo, state, first, second = two_pending
    # 令 main 同 second 改同一個檔嘅同一行 → cherry-pick 一定撞
    git(repo, "checkout", "-q", "-B", "clash", "origin/main")
    (repo / "beta.txt").write_text("something else\n", encoding="utf-8")
    clash = prepare_release(repo, paths=["beta.txt"], message="feat: clash",
                            state_root=state / "releases", notify=False)
    approve_release(repo, state, selector=clash["commit"], actor="t", notify=False)

    with pytest.raises(ReleaseError, match="does not replay cleanly"):
        refresh_release(repo, state, selector=second["commit"], actor="t", notify=False)
    # index 要乾淨（冇留低 unmerged path）
    assert git(repo, "diff", "--name-only", "--diff-filter=U") == ""


def test_dry_run_touches_nothing(two_pending) -> None:
    repo, state, first, second = two_pending
    approve_release(repo, state, selector=first["commit"], actor="t", notify=False)
    before = {str(i["commit"]) for i in pending_releases(state, repo)}
    plan = refresh_release(repo, state, selector=second["commit"], actor="t",
                           notify=False, dry_run=True)
    assert plan["status"] == "dry_run"
    assert plan["scope"] == second["scope"]
    assert plan["message"] == "feat: beta"
    assert {str(i["commit"]) for i in pending_releases(state, repo)} == before


def test_there_is_no_refresh_all(two_pending) -> None:
    """明文記住呢個決定：refresh N 個之後仍然要 N 次串行 merge，
    批量準備只會即刻再過期 N-1 個。"""
    import inspect

    import shared_wong_choi.release_refresh as mod

    assert not hasattr(mod, "refresh_all")
    assert "all" not in inspect.signature(refresh_release).parameters

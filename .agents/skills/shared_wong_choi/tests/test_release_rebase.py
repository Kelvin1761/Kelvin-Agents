"""過期 release 幾時可以自動跟住 main 行。

2026-10-21 十個 pending release 全部過期：每個 merge 都令其餘全部失效，而
auto-approve 遇到過期就停，要人手 `refresh`。HKJC 同 NBA 改嘅嘢互不相干，都要
排隊。`release_rebase` 只喺兩邊冇共同檔案、冇共同 production domain、亦冇
掂冇單一歸屬嘅 code 時先自動 replay，而且 replay 出嚟嘅 commit 要喺合併後嘅
tree 再過 gate 先 merge。

呢個檔守住：
  * HKJC 對 NBA：自動 rebase、merge，兩邊都入 main，舊 manifest 唔再 pending
  * 同 domain、共用 package、同一個檔、冇歸屬嘅 code：一律唔自動做
  * replay 唔可以郁到發起嗰個 checkout 嘅 HEAD
  * main 不停郁：最多 MAX_AUTO_REBASES 次就停
  * 唔係過期嘅錯誤（gate 失敗）唔可以觸發 replay
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT.parent))

from test_release_manager import git, repo as repo_fixture  # noqa: E402
from shared_wong_choi import (  # noqa: E402
    release_activation, release_approval, release_automation, release_manager, release_rebase,
)
from shared_wong_choi.release_approval import pending_releases  # noqa: E402
from shared_wong_choi.release_manager import ReleaseError, prepare_release  # noqa: E402
from shared_wong_choi.release_rebase import rebase_blockers  # noqa: E402

HKJC = ".agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts/engine.py"
HKJC_OTHER = ".agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts/renderer.py"
NBA = ".agents/skills/nba/nba_engine.py"
SHARED = ".agents/skills/shared_racing/scripts/field_health.py"
ROOT_SCRIPT = ".agents/scripts/build_comprehensive_stats.py"


# ---------------------------------------------------------------- 判斷規則


def test_disjoint_domains_may_rebase():
    assert rebase_blockers([HKJC], [NBA]) == []


def test_docs_and_tests_do_not_claim_a_domain():
    assert rebase_blockers([HKJC, "docs/experiments/EXP-1.md"],
                           [NBA, ".agents/skills/hkjc_racing/tests/test_x.py"]) == []


def test_same_domain_different_files_is_refused():
    blockers = rebase_blockers([HKJC], [HKJC_OTHER])
    assert any("hkjc" in b for b in blockers)


def test_same_file_is_refused_even_for_docs():
    blockers = rebase_blockers(["docs/experiments/INDEX.md"], ["docs/experiments/INDEX.md"])
    assert any("same files" in b for b in blockers)


@pytest.mark.parametrize("release, main", [([SHARED], [NBA]), ([HKJC], [SHARED])])
def test_shared_package_on_either_side_is_refused(release, main):
    assert rebase_blockers(release, main)


@pytest.mark.parametrize("release, main", [([ROOT_SCRIPT], [NBA]), ([HKJC], ["檢查.sh"])])
def test_code_without_an_owning_domain_is_refused(release, main):
    blockers = rebase_blockers(release, main)
    assert any("no single owning domain" in b for b in blockers)


def test_empty_scope_is_refused():
    assert rebase_blockers([], [NBA]) == ["release recorded no scope"]


# ------------------------------------------------------------ 端對端


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return repo_fixture.__wrapped__(tmp_path)


def _write(repo: Path, path: str) -> None:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(f"# {path}\n", encoding="utf-8")


@pytest.fixture
def two_pending(repo: Path, monkeypatch):
    """兩個喺同一個 main 上 gate 過、仲未批嘅 release：HKJC 同第二個（參數化）。"""
    state = repo.parent / "state"
    monkeypatch.setattr(release_manager, "release_automation_config",
                        lambda _repo: {"enabled": False})
    monkeypatch.setattr(release_automation, "release_automation_config",
                        lambda _repo: {"enabled": True, "authorization": "test"})
    monkeypatch.setattr(release_automation, "production_roots",
                        lambda: {d: repo for d in ("au", "hkjc", "tennis", "nba")})
    monkeypatch.setattr(release_activation, "activate_release",
                        lambda *a, **k: {"status": "activated"})

    def make(second_path: str):
        _write(repo, HKJC)
        first = prepare_release(repo, paths=[HKJC], message="feat: hkjc",
                                state_root=state / "releases", notify=False)
        git(repo, "checkout", "-q", "-B", "second", "origin/main")
        _write(repo, second_path)
        second = prepare_release(repo, paths=[second_path], message="feat: second",
                                 state_root=state / "releases", notify=False)
        return state, first, second

    return make


def _auto(repo: Path, state: Path, commit: str) -> dict:
    return release_automation.auto_approve_release(repo, state, selector=commit, notify=False)


def test_hkjc_and_nba_both_land_without_a_manual_refresh(repo, two_pending):
    state, first, second = two_pending(NBA)
    assert _auto(repo, state, first["commit"])["automation_status"] == "completed"
    head_before = git(repo, "rev-parse", "HEAD")
    branch_before = git(repo, "rev-parse", "--abbrev-ref", "HEAD")

    result = _auto(repo, state, second["commit"])

    assert result["automation_status"] == "completed", result.get("error")
    assert result["rebased_from"] == [second["commit"]]
    assert result["commit"] != second["commit"]
    remote = repo.parent / "remote.git"
    assert git(remote, "rev-parse", "main") == result["commit"]
    files = git(remote, "ls-tree", "-r", "--name-only", "main").splitlines()
    assert HKJC in files and NBA in files
    # 嗰個 replay 喺臨時 worktree 做，發起者個 checkout 原封不動。
    assert git(repo, "rev-parse", "HEAD") == head_before
    assert git(repo, "rev-parse", "--abbrev-ref", "HEAD") == branch_before
    assert pending_releases(state, repo) == []
    assert "wc-release-rebase" not in git(repo, "worktree", "list")


@pytest.mark.parametrize("second_path, reason", [
    (HKJC_OTHER, "same production domains"),
    (SHARED, "same production domains"),
    (ROOT_SCRIPT, "no single owning domain"),
])
def test_interacting_release_still_stops_at_expiry(repo, two_pending, second_path, reason):
    state, first, second = two_pending(second_path)
    _auto(repo, state, first["commit"])
    main_after_first = git(repo.parent / "remote.git", "rev-parse", "main")

    result = _auto(repo, state, second["commit"])

    assert result["automation_status"] == "blocked"
    assert "approval expired" in result["error"]
    assert reason in result["error"]
    assert "rebased_from" not in result
    assert git(repo.parent / "remote.git", "rev-parse", "main") == main_after_first
    assert [p["commit"] for p in pending_releases(state, repo)] == [second["commit"]]


def test_a_failed_gate_never_triggers_a_replay(repo, two_pending, monkeypatch):
    state, first, second = two_pending(NBA)
    calls = []
    monkeypatch.setattr(release_rebase, "refresh_in_isolated_worktree",
                        lambda *a, **k: calls.append(1))

    def failed(*args):
        raise ReleaseError("approval recheck gate failed")
    monkeypatch.setattr(release_approval, "_run_gate_in_clean_clone", failed)

    result = _auto(repo, state, first["commit"])

    assert result["automation_status"] == "blocked"
    assert "recheck gate failed" in result["error"]
    assert calls == []


def test_main_that_keeps_moving_stops_after_the_limit(repo, two_pending, monkeypatch):
    state, first, second = two_pending(NBA)
    _auto(repo, state, first["commit"])
    refreshes = []

    def always_expired(*args, **kwargs):
        raise ReleaseError("origin/main changed after release; approval expired")

    def fake_refresh(repo, state_root, *, selector, actor):
        refreshes.append(selector)
        return {"release": {"commit": selector}}

    monkeypatch.setattr(release_approval, "approve_release", always_expired)
    monkeypatch.setattr(release_rebase, "refresh_in_isolated_worktree", fake_refresh)

    result = _auto(repo, state, second["commit"])

    assert result["automation_status"] == "blocked"
    assert f"after {release_rebase.MAX_AUTO_REBASES} auto-rebases" in result["error"]
    assert len(refreshes) == release_rebase.MAX_AUTO_REBASES

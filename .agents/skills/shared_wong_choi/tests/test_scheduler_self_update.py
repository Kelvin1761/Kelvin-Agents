"""每個排程 wrapper 開工之前都要追上 `origin/main`。

點解要有呢個 test
-----------------
五個排程住喺同一個 worktree，但 2026-09-09 之前**只有 AU 個 wrapper 會 ff**。
實測嗰日：`origin/main` = `e1cbe606`，排程 worktree 仲喺 `396dc522`（落後三個
commit），因為最後一個 AU run 11:49 收咗工。四個修正 merge 咗、Telegram 報咗
上線，但生產跑緊嘅係舊 code。

真正嘅風險唔係「慢咗」：AU 一停（休季、壞咗、被 disable），其餘四個 domain 就會
**無限期跑舊 code 而冇任何嘢會投訴**。所以呢個係一個「全部都要有」嘅不變式，
唔可以靠人記得 —— 加新 wrapper 嗰陣呢個 test 會即刻嗌。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PACKAGE_ROOT.parents[2]
sys.path.insert(0, str(REPO_ROOT / ".agents" / "scripts"))

import wongchoi_self_update as M  # noqa: E402

#: 每一個俾 launchd 直接叫嘅排程入口。
SCHEDULER_WRAPPERS = (
    ".agents/skills/au_racing/au_daily_auto/run_au_daily_schedule.sh",
    ".agents/skills/hkjc_racing/hkjc_daily_auto/run_hkjc_daily_schedule.sh",
    ".agents/skills/nba/nba_daily_auto/run_nba_daily_schedule.sh",
    ".agents/skills/central_wong_choi/scripts/run_central_daily_maintenance.sh",
    "tennis-wong-choi/scripts/run_tennis_daily_schedule.sh",
)


@pytest.mark.parametrize("relative", SCHEDULER_WRAPPERS)
def test_every_scheduler_wrapper_catches_up_with_main(relative: str) -> None:
    path = REPO_ROOT / relative
    assert path.is_file(), f"{relative} 唔見咗 —— 改咗路徑就要同時改呢個 test"
    text = path.read_text(encoding="utf-8")
    # 兩種都收：叫共用 helper，或者自己有 ff 邏輯（AU 因為要保住個 meeting-ID
    # mapping，一直有自己嗰套）。
    assert ("wongchoi_self_update.py" in text) or ("merge --ff-only" in text), (
        f"{relative} 開工之前唔會追 origin/main。五個排程共用一個 worktree，"
        "唔追嘅話 AU 一停就會無限期跑舊 code 而冇任何嘢會投訴。"
    )


def _repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    run = lambda *a: subprocess.run(["git", "-C", str(path), *a], check=True,
                                    capture_output=True)
    run("init", "--quiet", "-b", "main")
    run("config", "user.email", "t@example.com")
    run("config", "user.name", "t")
    (path / "f.txt").write_text("one\n", encoding="utf-8")
    run("add", "f.txt")
    run("commit", "--quiet", "-m", "one")
    return path


def _clone(origin: Path, dest: Path) -> Path:
    subprocess.run(["git", "clone", "--quiet", str(origin), str(dest)],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(dest), "config", "user.email", "t@example.com"],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(dest), "config", "user.name", "t"],
                   check=True, capture_output=True)
    return dest


def _commit(repo: Path, text: str) -> None:
    (repo / "f.txt").write_text(text, encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "commit", "--quiet", "-am", text],
                   check=True, capture_output=True)


def test_behind_main_fast_forwards(tmp_path: Path) -> None:
    origin = _repo(tmp_path / "origin")
    work = _clone(origin, tmp_path / "work")
    _commit(origin, "two\n")

    assert M.self_update(work) == ""
    assert (work / "f.txt").read_text(encoding="utf-8") == "two\n"


def test_a_diverged_branch_is_reported_not_merged(tmp_path: Path) -> None:
    origin = _repo(tmp_path / "origin")
    work = _clone(origin, tmp_path / "work")
    _commit(origin, "upstream\n")
    _commit(work, "local\n")

    warning = M.self_update(work)

    assert "分叉" in warning
    # ⚠️ 最緊要係：一個字都冇改過本機嘅嘢。
    assert (work / "f.txt").read_text(encoding="utf-8") == "local\n"


def test_uncommitted_work_is_never_discarded(tmp_path: Path) -> None:
    origin = _repo(tmp_path / "origin")
    work = _clone(origin, tmp_path / "work")
    _commit(origin, "upstream\n")
    (work / "f.txt").write_text("work in progress\n", encoding="utf-8")

    warning = M.self_update(work)

    assert "fast-forward" in warning
    assert (work / "f.txt").read_text(encoding="utf-8") == "work in progress\n"


def test_a_dead_lock_file_cannot_disable_updates_forever(tmp_path: Path) -> None:
    """鎖要用 flock，唔可以用「個檔存唔存在」。

    process 俾 SIGKILL 殺咗，flock 會由 OS 放返；而「有冇個檔」嗰種鎖會留低一個
    爛鎖，令自動更新**永久靜靜咁停咗** —— 正正就係我哋想避免嗰種失敗形狀。
    """
    origin = _repo(tmp_path / "origin")
    work = _clone(origin, tmp_path / "work")
    _commit(origin, "two\n")
    (work / M.LOCK_NAME).write_text("上一個 process 死咗留低", encoding="utf-8")

    assert M.self_update(work) == ""
    assert (work / "f.txt").read_text(encoding="utf-8") == "two\n"


def test_a_held_lock_skips_instead_of_waiting(tmp_path: Path) -> None:
    import fcntl

    origin = _repo(tmp_path / "origin")
    work = _clone(origin, tmp_path / "work")
    _commit(origin, "two\n")

    holder = (work / M.LOCK_NAME).open("w")
    fcntl.flock(holder, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        assert M.self_update(work) == ""
        # 另一個 wrapper 做緊 —— 我哋唔等、唔更新，亦唔當失敗。
        assert (work / "f.txt").read_text(encoding="utf-8") == "one\n"
    finally:
        fcntl.flock(holder, fcntl.LOCK_UN)
        holder.close()


def test_no_upstream_never_raises_and_never_blocks(tmp_path: Path) -> None:
    """fetch 失敗（冇 origin）唔可以令排程唔開工。"""
    work = _repo(tmp_path / "solo")
    warning = M.self_update(work)
    assert warning  # 有嘢報
    assert M.main([str(work)]) == 0  # 但退出碼一定係 0


def test_a_non_git_directory_is_silently_fine(tmp_path: Path) -> None:
    plain = tmp_path / "tarball"
    plain.mkdir()
    assert M.self_update(plain) == ""
    assert M.main([str(plain)]) == 0


def test_the_kill_switch_is_honoured(tmp_path: Path, monkeypatch) -> None:
    origin = _repo(tmp_path / "origin")
    work = _clone(origin, tmp_path / "work")
    _commit(origin, "two\n")
    monkeypatch.setenv("WC_NO_SELF_UPDATE", "1")

    assert M.self_update(work) == ""
    assert (work / "f.txt").read_text(encoding="utf-8") == "one\n"

"""排程開工之前追上 `origin/main`。**每個 wrapper 都要叫一次。**

點解要有呢個
------------
五個排程全部住喺同一個 worktree（`/Users/imac/wongchoi-scheduler`），但
2026-09-09 之前**只有 AU 個 wrapper 會 fast-forward**。即係 HKJC／Tennis／NBA／
Central 更新 code 全靠「AU 啱啱好有開工」順帶帶挈。

嗰日實測：`origin/main` 已經係 `e1cbe606`，排程 worktree 仲喺 `396dc522`
（落後三個 commit），因為最後一個 AU run 11:49 就收咗工。四個修正 merge 咗、
Telegram 報咗上線，但生產跑緊嘅仍然係舊 code。

真正嘅風險唔係「慢咗」：**AU 一停（休季、壞咗、被 disable），其餘四個 domain
就會無限期跑舊 code，而冇任何嘢會投訴。**

設計取捨（明寫出嚟）
--------------------
* **失敗永遠唔阻開工。** fetch 唔到、ff 唔到、鎖攞唔到 —— 一律 warn 然後用現有
  版本繼續，`main()` 永遠回 0。追唔到新 code 係細事，唔開工係大事。
* **只做 fast-forward。** 分叉（ahead > 0）唔會自動解決，只出警告等人手處理。
* **唔會掉任何未 commit 嘅嘢。** 呢度冇 checkout／reset／stash。`--ff-only`
  撞到會衝突嘅本機改動自己會拒絕，我哋照 warn 就算 —— 拒絕本身就係安全結果。
* **鎖用 `fcntl.flock`，唔用 lock file 存唔存在。** process 俾 SIGKILL 殺咗，
  flock 會由 OS 自動放返；而「有冇個檔」嗰種鎖會留低一個爛鎖，令自動更新**永久
  靜靜咁停咗** —— 就係我哋想避免嗰種失敗形狀。攞唔到鎖 = 另一個 wrapper 做緊
  同一件事，跳過就啱，唔使等。
* ⚠️ **已知殘留風險**：一個 domain 喺另一個 domain **跑到一半**嗰陣 ff，之後
  spawn 出嚟嘅 subprocess 會用新 code。呢個風險 AU 一直都存在（佢個 ff 一樣係
  攞 run lock 之前做），而家由一個更新者變五個，機會率高咗。照做嘅原因係：另一
  個選擇（永遠唔更新）今日已經實測咬過我哋一次。

用法（wrapper 入面，`cd "$REPO_ROOT"` 之後，`exec` 之前）：

    /usr/bin/python3 "$REPO_ROOT/.agents/scripts/wongchoi_self_update.py" || true

`WC_NO_SELF_UPDATE=1` 可以關掉（測試、人手 debug、釘住一個版本跑）。
"""
from __future__ import annotations

import fcntl
import os
import subprocess
import sys
from pathlib import Path

LOCK_NAME = ".wongchoi_code_update.lock"
FETCH_TIMEOUT = 120
MERGE_TIMEOUT = 120


def _git(root: Path, *args: str, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        # ⚠️ 唔可以用 `text=True`：佢係嚴格 UTF-8，而 git 印檔名唔保證合法 UTF-8。
        # 見 `.agents/skills/shared_wong_choi/tests/test_subprocess_output_decoding.py`。
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )


def _warn(message: str) -> str:
    print(f"⚠️ {message}", file=sys.stderr)
    return message


def self_update(root: Path) -> str:
    """追上 origin/main。回一句警告（空字串 = 冇嘢報）。永遠唔會 raise。"""
    if os.environ.get("WC_NO_SELF_UPDATE"):
        return ""
    if _git(root, "rev-parse", "--is-inside-work-tree").returncode != 0:
        # 唔係 git checkout（tarball 部署）—— 冇嘢可以追。
        return ""

    lock_path = root / LOCK_NAME
    try:
        handle = lock_path.open("w")
    except OSError as exc:
        return _warn(f"開唔到更新鎖 {lock_path}：{type(exc).__name__} —— 今次用現有版本")

    with handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            # 另一個 wrapper 做緊同一件事。唔係失敗，唔使等。
            print("ℹ️ 另一個排程正在更新 code，今次跳過", file=sys.stderr)
            return ""
        try:
            return _fast_forward(root)
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _fast_forward(root: Path) -> str:
    try:
        fetched = _git(root, "fetch", "--quiet", "origin", timeout=FETCH_TIMEOUT)
    except subprocess.SubprocessError as exc:
        return _warn(f"git fetch 出事（{type(exc).__name__}）—— 今次用現有版本")
    if fetched.returncode != 0:
        return _warn("git fetch 失敗 —— 未能核實係咪最新，今次用現有版本")

    counts = _git(root, "rev-list", "--left-right", "--count", "HEAD...origin/main")
    parts = (counts.stdout or "").split()
    if counts.returncode != 0 or len(parts) != 2:
        return _warn("比唔到 origin/main —— 今次用現有版本")
    try:
        ahead, behind = int(parts[0]), int(parts[1])
    except ValueError:
        return _warn("讀唔到同 origin/main 嘅差距 —— 今次用現有版本")

    warning = ""
    if behind == 0:
        pass  # 已經包含 origin/main。
    elif ahead > 0:
        warning = _warn(
            f"production branch 已分叉（ahead {ahead} / behind {behind}），"
            "唔會自動 fast-forward；要人手合併 origin/main"
        )
    else:
        try:
            merged = _git(root, "merge", "--ff-only", "--quiet", "origin/main",
                          timeout=MERGE_TIMEOUT)
        except subprocess.SubprocessError as exc:
            return _warn(f"fast-forward 出事（{type(exc).__name__}）—— 今次用現有版本")
        if merged.returncode == 0:
            print(f"▶ 已追上 origin/main（前進 {behind} 個 commit）", file=sys.stderr)
        else:
            # 幾乎一定係本機未 commit 嘅改動同 incoming commit 撞同一個檔。
            # `--ff-only` 拒絕咗 = 冇嘢俾人掉咗。
            warning = _warn(
                f"fast-forward origin/main 失敗（落後 {behind} 個 commit）—— "
                "今次用現有版本，工作區可能有未 commit 改動"
            )

    head = _git(root, "rev-parse", "--short", "HEAD").stdout.strip() or "?"
    branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() or "?"
    print(f"▶ 版本 {head} ({branch})", file=sys.stderr)
    return warning


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    root = Path(args[0]).resolve() if args else Path(__file__).resolve().parents[2]
    try:
        self_update(root)
    except Exception as exc:  # noqa: BLE001
        # ⚠️ 追唔到新 code 永遠唔可以令排程唔開工。
        _warn(f"自動更新出事（{type(exc).__name__}: {exc}）—— 今次用現有版本")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

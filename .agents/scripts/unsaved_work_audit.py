#!/usr/bin/env python3
"""搵出「做咗但未保存」嘅工作 —— 未 commit 改動、commit 咗但未 push。

點解要有：2026-10-14 發現主 checkout 停喺一條 2026-09-05 嘅 release 分支，
落後 origin/main 117 個 commit，入面有 224 個檔嘅工作從來冇 commit。
Claude Code 同 Codex 都會開 worktree，冇人會返轉頭逐個睇。呢個腳本逐個掃。

兩個用法：

  python3 unsaved_work_audit.py            # 掃晒所有 worktree，印 TSV 畀 健康.sh
  python3 unsaved_work_audit.py --hook     # Claude Code Stop hook：stdin 讀 hook JSON

健康.sh 模式輸出（一行一個問題，tab 分隔）：
  BAD   <path>  <detail>     主 checkout 唔喺 main／有未 commit 改動
  WARN  <path>  <detail>     其他 worktree 有超過 --stale-hours 嘅未保存工作
  INFO  <count> <detail>     總結
退出碼：0 = 乾淨，10 = 有 WARN，20 = 有 BAD。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

PRIMARY = Path(os.environ.get("WC_PRIMARY_REPO_ROOT", Path.home() / "Antigravity-repo"))
GIT_TIMEOUT = 20


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, timeout=GIT_TIMEOUT,
    )


@dataclass
class State:
    path: Path
    branch: str = ""
    dirty: list[str] = field(default_factory=list)   # porcelain lines, ignored files excluded
    unpushed: int = 0                                 # commits reachable from HEAD but no remote ref
    behind_main: int = 0
    newest_change: float = 0.0                        # mtime of newest dirty file, or HEAD commit time
    error: str = ""


def inspect(path: Path) -> State:
    st = State(path=path)
    try:
        st.branch = _git(path, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        status = _git(path, "status", "--porcelain=v1", "-z")
        if status.returncode:
            st.error = status.stderr.strip()[:200]
            return st
        entries = [e for e in status.stdout.split("\0") if e]
        # -z rename entries carry the old path as a separate field without a status prefix
        st.dirty = [e for e in entries if len(e) > 3 and e[2] == " "]
        count = _git(path, "rev-list", "--count", "HEAD", "--not", "--remotes")
        st.unpushed = int(count.stdout.strip() or 0) if count.returncode == 0 else 0
        behind = _git(path, "rev-list", "--count", "HEAD..origin/main")
        st.behind_main = int(behind.stdout.strip() or 0) if behind.returncode == 0 else 0
        mtimes = []
        for entry in st.dirty:
            target = path / entry[3:]
            try:
                mtimes.append(target.stat().st_mtime)
            except OSError:
                pass
        if st.unpushed:
            head_time = _git(path, "log", "-1", "--format=%ct").stdout.strip()
            if head_time.isdigit():
                mtimes.append(float(head_time))
        st.newest_change = max(mtimes) if mtimes else 0.0
    except subprocess.TimeoutExpired:
        st.error = "git timed out"
    except OSError as exc:
        st.error = str(exc)[:200]
    return st


def worktrees(primary: Path) -> list[Path]:
    out = _git(primary, "worktree", "list", "--porcelain").stdout
    paths = []
    for block in out.split("\n\n"):
        lines = block.splitlines()
        if not lines or not lines[0].startswith("worktree "):
            continue
        if any(line.startswith("prunable") for line in lines):
            continue
        paths.append(Path(lines[0][len("worktree "):]))
    return paths


def _age_hours(ts: float) -> float:
    return (time.time() - ts) / 3600 if ts else 0.0


def describe(st: State) -> str:
    bits = []
    if st.dirty:
        bits.append(f"{len(st.dirty)} 個檔未 commit")
    if st.unpushed:
        bits.append(f"{st.unpushed} 個 commit 未 push")
    if st.newest_change:
        bits.append(f"最新改動 {_age_hours(st.newest_change):.0f} 個鐘前")
    bits.append(f"分支 {st.branch or '?'}")
    return "，".join(bits)


def run_audit(primary: Path, stale_hours: float) -> int:
    rc = 0
    flagged = 0
    paths = worktrees(primary)
    for path in paths:
        st = inspect(path)
        if st.error:
            print(f"WARN\t{path}\t掃唔到：{st.error}")
            rc = max(rc, 10)
            continue
        if path.resolve() == primary.resolve():
            problems = []
            if st.branch != "main":
                problems.append(f"唔喺 main（喺 {st.branch}）")
            if st.behind_main:
                problems.append(f"落後 origin/main {st.behind_main} 個 commit")
            tracked = [e for e in st.dirty if not e.startswith("??")]
            if tracked:
                problems.append(f"{len(tracked)} 個受 git 管理嘅檔有未 commit 改動")
            untracked = len(st.dirty) - len(tracked)
            if problems:
                print(f"BAD\t{path}\t主 checkout " + "；".join(problems))
                rc, flagged = 20, flagged + 1
            elif untracked:
                print(f"WARN\t{path}\t主 checkout 有 {untracked} 個未追蹤檔（應該喺 worktree 做嘢）")
                rc, flagged = max(rc, 10), flagged + 1
            continue
        if not (st.dirty or st.unpushed):
            continue
        if _age_hours(st.newest_change) < stale_hours:
            continue  # someone is probably still working there
        print(f"WARN\t{path}\t{describe(st)}")
        rc, flagged = max(rc, 10), flagged + 1
    print(f"INFO\t{len(paths)}\t個 worktree 掃完，{flagged} 個有未保存工作")
    return rc


def run_hook() -> int:
    """Claude Code Stop hook: nudge once when this session's worktree holds unsaved work."""
    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError):
        return 0
    if payload.get("stop_hook_active"):
        return 0  # already nudged this stop; never loop
    cwd = Path(payload.get("cwd") or os.getcwd())
    top = _git(cwd, "rev-parse", "--show-toplevel")
    if top.returncode:
        return 0
    st = inspect(Path(top.stdout.strip()))
    if st.error or not (st.dirty or st.unpushed):
        return 0
    is_primary = Path(top.stdout.strip()).resolve() == PRIMARY.resolve()
    where = "主 checkout（唔應該有任何改動）" if is_primary else str(st.path)
    reason = (
        f"[收工檢查] {where} 有未保存工作：{describe(st)}。"
        "停之前揀一樣做（見 AGENTS.md「收工規則」）："
        "(1) 工作完成而用戶要求交付 → `./保存.sh --path <scope> --expected-result ...`；"
        "(2) 未完成／未評估／失敗實驗 → `git add <你自己嘅檔> && git commit` 再 "
        "`git push -u origin HEAD` 推去非 main 分支保存（唔係 release，唔會部署）；"
        "(3) 你只係停低等用戶回覆 → 喺回覆入面講明邊啲檔未保存同點解。"
        "唔好 `git add -A` 掃埋其他 session 嘅改動。"
    )
    print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--hook", action="store_true", help="Claude Code Stop hook mode (reads stdin)")
    ap.add_argument("--repo", type=Path, default=PRIMARY, help="primary checkout (default ~/Antigravity-repo)")
    ap.add_argument("--stale-hours", type=float, default=6.0,
                    help="non-primary worktrees are only flagged after this many idle hours")
    args = ap.parse_args()
    if args.hook:
        return run_hook()
    return run_audit(args.repo, args.stale_hours)


if __name__ == "__main__":
    sys.exit(main())
